#!/usr/bin/env python3
"""Observe one Waiting on Rain delivery and publish genuinely new transmissions."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def read_json(path):
    with path.open("r", encoding="utf-8") as input_file:
        return json.load(input_file)


def atomic_write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(value, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, path)
    except OSError:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass
        raise


def load_observer_state(path):
    if not path.exists():
        return None

    state = read_json(path)
    if not isinstance(state, dict):
        raise ValueError("observer state must be a JSON object")

    event_id = state.get("last_published_event_id")
    revision = state.get("last_published_revision")
    if (
        not isinstance(event_id, str)
        or not event_id.strip()
        or isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision <= 0
    ):
        raise ValueError("observer state has an invalid publication record")

    return state


def main():
    parser = argparse.ArgumentParser(
        description="Observe a Waiting on Rain delivery for new transmissions."
    )
    parser.add_argument("--disabled", action="store_true")
    parser.add_argument("delivery_json", type=Path)
    parser.add_argument("observer_state_json", type=Path)
    parser.add_argument("output_public_state_json", type=Path)
    args = parser.parse_args()

    if args.disabled:
        print("observer disabled")
        return 0

    try:
        delivery = read_json(args.delivery_json)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Unable to read delivery: {error}", file=sys.stderr)
        return 1

    if not isinstance(delivery, dict):
        print("Delivery is non-publishable; no state was changed.", file=sys.stderr)
        return 0

    status = delivery.get("status")
    if status != "world_transmission":
        print(
            f"Delivery status {status!r} is non-publishable; "
            "observer state and output were not changed."
        )
        return 0

    event_id = delivery.get("event_id")
    revision = delivery.get("revision")
    committed_at_utc = delivery.get("committed_at_utc")
    text = delivery.get("text")

    if (
        not isinstance(event_id, str)
        or not event_id.strip()
        or isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision <= 0
        or not isinstance(committed_at_utc, str)
        or not committed_at_utc.strip()
        or not isinstance(text, str)
        or not text.strip()
    ):
        print(
            "Invalid world_transmission; observer state and output were not changed.",
            file=sys.stderr,
        )
        return 1

    try:
        observer_state = load_observer_state(args.observer_state_json)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Unable to read observer state: {error}", file=sys.stderr)
        return 1

    if observer_state is not None:
        last_event_id = observer_state["last_published_event_id"]
        last_revision = observer_state["last_published_revision"]

        if event_id == last_event_id:
            print(f"Duplicate delivery {event_id!r}; nothing changed.")
            return 0

        if revision <= last_revision:
            print(
                f"Delivery revision {revision} is stale or out of order; "
                "nothing changed."
            )
            return 0

    exporter = Path(__file__).with_name("export_waiting_on_rain_delivery.py")
    completed = subprocess.run(
        [sys.executable, str(exporter), str(args.delivery_json), str(args.output_public_state_json)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        print("Export failed; observer state was not advanced.", file=sys.stderr)
        return completed.returncode

    try:
        atomic_write_json(
            args.observer_state_json,
            {
                "last_published_event_id": event_id,
                "last_published_revision": revision,
            },
        )
    except OSError as error:
        print(
            f"Export succeeded but observer state could not be updated: {error}",
            file=sys.stderr,
        )
        return 1

    print(f"Published new delivery {event_id!r} at revision {revision}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
