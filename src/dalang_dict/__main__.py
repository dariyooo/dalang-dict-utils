"""Command line used by the dictionary workflows.

    uv run python -m dalang_dict update-sources
    uv run python -m dalang_dict release-changed --previous tmp/previous-release

Both print what changed and, when run in GitHub Actions, set the step output `changed` to true or false.
"""

import argparse
import os
from pathlib import Path

from dalang_dict.release import DEFAULT_MAX_ENTRY_DROP, release_changed
from dalang_dict.sources import update_sources


def _set_output(changed: bool) -> None:
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as f:
            f.write(f"changed={str(changed).lower()}\n")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m dalang_dict")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("update-sources", help="update sources.lock.json to the latest version of every source")
    release = commands.add_parser("release-changed", help="compare out/ with the previous release")
    release.add_argument("--previous", type=Path, required=True, help="manifests of the previous release")
    release.add_argument("--out", type=Path, default=Path("out"))
    release.add_argument("--max-entry-drop", type=float, default=DEFAULT_MAX_ENTRY_DROP)
    args = parser.parse_args()

    if args.command == "update-sources":
        changed = update_sources()
        print(f"Updated sources: {', '.join(changed)}" if changed else "All sources are up to date.")
    else:
        changed = release_changed(args.out, args.previous, args.max_entry_drop)
        print(f"Changed dictionaries: {', '.join(changed)}" if changed else "No dictionary changed.")
    _set_output(bool(changed))


if __name__ == "__main__":
    main()
