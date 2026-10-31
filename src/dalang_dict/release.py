"""Decides whether a rebuild has to be released by comparing its manifests with the previous release."""

import json
from pathlib import Path

DEFAULT_MAX_ENTRY_DROP = 0.05


def manifest_changed(new: dict, old: dict | None, max_entry_drop: float = DEFAULT_MAX_ENTRY_DROP) -> bool:
    """Returns whether `new` differs from the released `old` manifest.

    Raises if a bank lost more than `max_entry_drop` of its entries, which usually means a broken source.
    """
    if old is None:
        return True
    for bank, old_count in old["entries"].items():
        new_count = new["entries"].get(bank, 0)
        if old_count and (old_count - new_count) / old_count > max_entry_drop:
            raise ValueError(f"'{bank}' dropped from {old_count} to {new_count} entries, check the sources")
    return new["contentSha256"] != old["contentSha256"]


def release_changed(out_dir: Path, previous_dir: Path, max_entry_drop: float = DEFAULT_MAX_ENTRY_DROP) -> list[str]:
    """Compares every `out/*.manifest.json` with the same file of the previous release in `previous_dir`.

    Returns the names of the changed dictionaries.
    """
    changed = []
    for path in sorted(out_dir.glob("*.manifest.json")):
        new = json.loads(path.read_text(encoding="utf-8"))
        previous = previous_dir / path.name
        old = json.loads(previous.read_text(encoding="utf-8")) if previous.exists() else None
        if manifest_changed(new, old, max_entry_drop):
            changed.append(path.name.removesuffix(".manifest.json"))
    return changed
