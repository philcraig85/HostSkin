#!/usr/bin/env python3
"""Publish a HostSkin public state into a separate Git checkout."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


TARGET_NAME = "waiting-on-rain-state.json"
COMMIT_MESSAGE = "Receive Waiting on Rain transmission"


def run_git(repository, *arguments):
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def configured_upstream(repository):
    result = run_git(
        repository,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{u}",
    )
    if result.returncode != 0:
        return None
    upstream = result.stdout.strip()
    return upstream or None


def safe_ahead_commits(repository):
    upstream = configured_upstream(repository)
    if upstream is None:
        return None, []

    commits_result = run_git(repository, "rev-list", "--reverse", f"{upstream}..HEAD")
    if commits_result.returncode != 0:
        raise RuntimeError(
            f"unable to inspect commits ahead of {upstream}: "
            f"{commits_result.stderr.strip()}"
        )

    commits = [line for line in commits_result.stdout.splitlines() if line]
    for commit in commits:
        subject_result = run_git(repository, "show", "-s", "--format=%s", commit)
        if subject_result.returncode != 0:
            raise RuntimeError(
                f"unable to inspect commit {commit}: "
                f"{subject_result.stderr.strip()}"
            )
        subject = subject_result.stdout[:-1] if subject_result.stdout.endswith("\n") else subject_result.stdout
        if subject != COMMIT_MESSAGE:
            raise ValueError(
                f"commit {commit} has an unsafe subject; refusing to push"
            )

        parents_result = run_git(repository, "rev-list", "--parents", "-n", "1", commit)
        if parents_result.returncode != 0:
            raise RuntimeError(
                f"unable to inspect parents of commit {commit}: "
                f"{parents_result.stderr.strip()}"
            )
        if len(parents_result.stdout.split()) > 2:
            raise ValueError(f"commit {commit} is a merge; refusing to push")

        paths_result = run_git(
            repository,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            commit,
        )
        if paths_result.returncode != 0:
            raise RuntimeError(
                f"unable to inspect paths in commit {commit}: "
                f"{paths_result.stderr.strip()}"
            )
        paths = [line for line in paths_result.stdout.splitlines() if line]
        if set(paths) != {TARGET_NAME}:
            raise ValueError(
                f"commit {commit} changes paths outside {TARGET_NAME}; refusing to push"
            )

    return upstream, commits


def validate_source(path):
    source_bytes = path.read_bytes()
    source_text = source_bytes.decode("utf-8")
    state = json.loads(source_text)

    if not isinstance(state, dict) or set(state) != {"publishedTrace"}:
        raise ValueError("source must contain only a publishedTrace object")

    trace = state["publishedTrace"]
    if not isinstance(trace, dict) or set(trace) != {"timestamp", "content"}:
        raise ValueError("publishedTrace must contain only timestamp and content")

    if (
        not isinstance(trace["timestamp"], str)
        or not trace["timestamp"].strip()
        or not isinstance(trace["content"], str)
        or not trace["content"].strip()
    ):
        raise ValueError("timestamp and content must be non-empty strings")

    return source_bytes


def require_clean_repository(repository, target):
    if not repository.exists() or not repository.is_dir():
        raise ValueError("HostSkin repository does not exist")

    worktree = run_git(repository, "rev-parse", "--is-inside-work-tree")
    if worktree.returncode != 0 or worktree.stdout.strip() != "true":
        raise ValueError("HostSkin repository is not a Git working tree")

    if not target.exists() or not target.is_file() or target.is_symlink():
        raise ValueError(f"{TARGET_NAME} is missing from the repository")

    status = run_git(repository, "status", "--porcelain=v1")
    if status.returncode != 0:
        raise RuntimeError(f"unable to inspect repository status: {status.stderr.strip()}")
    if status.stdout:
        raise ValueError(
            "repository has existing uncommitted changes; refusing to publish"
        )


def atomic_copy(source_bytes, target):
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(source_bytes)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, target)
    except OSError:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Publish HostSkin public state into a separate Git checkout."
    )
    parser.add_argument("--disabled", action="store_true")
    parser.add_argument("source_state_json", type=Path)
    parser.add_argument("hostskin_repository", type=Path)
    args = parser.parse_args()

    if args.disabled:
        print("publisher disabled")
        return 0

    try:
        source_bytes = validate_source(args.source_state_json)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        print(f"Invalid source public state: {error}", file=sys.stderr)
        return 1

    repository = args.hostskin_repository
    target = repository / TARGET_NAME
    try:
        require_clean_repository(repository, target)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Refusing to publish: {error}", file=sys.stderr)
        return 1

    try:
        upstream, ahead_commits = safe_ahead_commits(repository)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Refusing to publish: {error}", file=sys.stderr)
        return 1

    if source_bytes == target.read_bytes():
        if not ahead_commits:
            print("public state already current")
            return 0
        if upstream is None:
            print(
                "Refusing to push pending commits: current branch has no configured upstream",
                file=sys.stderr,
            )
            return 1

        pushed = run_git(repository, "push")
        if pushed.returncode != 0:
            print(
                "Push failed; pending HostSkin transmission commit(s) remain intact: "
                f"{pushed.stderr.strip()}",
                file=sys.stderr,
            )
            return 1
        print("pending HostSkin transmission commit(s) were pushed")
        return 0

    if upstream is None:
        print(
            "Refusing to publish: current branch has no configured upstream",
            file=sys.stderr,
        )
        return 1

    try:
        atomic_copy(source_bytes, target)
    except OSError as error:
        print(f"Unable to write public state: {error}", file=sys.stderr)
        return 1

    diff = run_git(repository, "diff", "--quiet", "--", TARGET_NAME)
    if diff.returncode == 0:
        print("public state already current")
        return 0
    if diff.returncode != 1:
        print(f"Unable to inspect public state diff: {diff.stderr.strip()}", file=sys.stderr)
        return 1

    staged = run_git(repository, "add", "--", TARGET_NAME)
    if staged.returncode != 0:
        print(f"Unable to stage public state: {staged.stderr.strip()}", file=sys.stderr)
        return 1

    committed = run_git(repository, "commit", "-m", COMMIT_MESSAGE)
    if committed.returncode != 0:
        print(f"Commit failed: {committed.stderr.strip()}", file=sys.stderr)
        return 1

    try:
        safe_ahead_commits(repository)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Refusing to push: {error}", file=sys.stderr)
        return 1

    pushed = run_git(repository, "push")
    if pushed.returncode != 0:
        print(
            "Push failed; the local commit remains intact for later retry: "
            f"{pushed.stderr.strip()}",
            file=sys.stderr,
        )
        return 1

    print("Published public state and pushed commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
