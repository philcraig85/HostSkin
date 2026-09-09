#!/usr/bin/env python3
"""Export one Waiting on Rain membrane delivery into HostSkin public state."""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


def report_non_publishable(status):
    print(f"Delivery status {status!r} is non-publishable; output was not changed.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Export a Waiting on Rain delivery into HostSkin public state."
    )
    parser.add_argument("input_json", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()

    try:
        with args.input_json.open("r", encoding="utf-8") as input_file:
            delivery = json.load(input_file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Unable to read delivery: {error}", file=sys.stderr)
        return 1

    if not isinstance(delivery, dict):
        print("Delivery is non-publishable; output was not changed.", file=sys.stderr)
        return 1

    status = delivery.get("status")

    if status == "world_silence":
        print(
            "Genuine world silence was observed but is currently not published "
            "because HostSkin silence behaviour has not yet been decided."
        )
        return 0

    if status != "world_transmission":
        report_non_publishable(status)
        return 0

    committed_at_utc = delivery.get("committed_at_utc")
    text = delivery.get("text")
    if not isinstance(committed_at_utc, str) or not committed_at_utc.strip():
        print(
            "world_transmission requires a non-empty committed_at_utc; "
            "output was not changed.",
            file=sys.stderr,
        )
        return 1
    if not isinstance(text, str) or not text.strip():
        print(
            "world_transmission requires non-empty text; output was not changed.",
            file=sys.stderr,
        )
        return 1

    public_state = {
        "publishedTrace": {
            "timestamp": committed_at_utc,
            "content": text,
        }
    }

    output_directory = args.output_json.parent
    try:
        output_directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_directory,
            prefix=f".{args.output_json.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(public_state, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, args.output_json)
    except OSError as error:
        try:
            temporary_path.unlink()
        except (NameError, OSError):
            pass
        print(f"Unable to write output: {error}", file=sys.stderr)
        return 1

    print(f"Published HostSkin state to {args.output_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
