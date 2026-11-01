"""Compares the manifests of a build with the previous release: whether to release and the release notes."""

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


def _short(version: str) -> str:
    # Commit hashes are shortened like on GitHub
    return version[:7] if len(version) == 40 else version


def _manifest_notes(name: str, new: dict, old: dict | None) -> list[str]:
    lines = [f"## {name}", "", "Sources", ""]
    sources = new.get("sources", {})
    for source, info in sources.items():
        used_for = f": {info['usedFor']}" if info["usedFor"] else ""
        lines.append(f"- `{source}` @ `{_short(info['version'])}`{used_for}")
    if not sources:
        lines.append("- none recorded")

    if old is None:
        lines += ["", "First release."]
        return lines
    changes = []
    # Manifests of releases before source tracking have no sources to compare
    old_sources = old.get("sources", sources)
    for source in sorted(sources.keys() | old_sources.keys()):
        old_version = old_sources.get(source, {}).get("version")
        new_version = sources.get(source, {}).get("version")
        if old_version != new_version:
            old_text = f"`{_short(old_version)}`" if old_version else "new"
            new_text = f"`{_short(new_version)}`" if new_version else "removed"
            changes.append(f"- `{source}`: {old_text} → {new_text}")
    for bank in sorted(new["entries"].keys() | old["entries"].keys()):
        old_count, new_count = old["entries"].get(bank, 0), new["entries"].get(bank, 0)
        if old_count != new_count:
            changes.append(f"- `{bank}`: {old_count} → {new_count} entries")
    if not changes and new["contentSha256"] != old["contentSha256"]:
        changes.append("- content changed, same sources and entry counts")
    lines += ["", f"Changes since {old.get('revision', 'the previous release')}", ""]
    lines += changes or ["- none"]
    return lines


def release_notes(out_dir: Path, previous_dir: Path) -> str:
    """Markdown listing the sources of every dictionary in `out_dir` and what changed since `previous_dir`."""
    sections = []
    for path in sorted(out_dir.glob("*.manifest.json")):
        new = json.loads(path.read_text(encoding="utf-8"))
        previous = previous_dir / path.name
        old = json.loads(previous.read_text(encoding="utf-8")) if previous.exists() else None
        sections.append("\n".join(_manifest_notes(path.name.removesuffix(".manifest.json"), new, old)))
    return "\n\n".join(sections) + "\n"
