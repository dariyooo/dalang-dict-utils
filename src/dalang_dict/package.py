"""Writing bank files and packaging them as dictionary zips into out/."""

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from dalang_dict.sources import used_sources
from dalang_dict.validate import validate_dictionary_dir

DEFAULT_TMP_DIR = Path("tmp")
DEFAULT_OUT_DIR = Path("out")
BANK_CHUNK_SIZE = 10_000


def write_banks(banks: dict[str, list], directory: Path, chunk_size: int = BANK_CHUNK_SIZE) -> list[Path]:
    """Writes each bank (e.g. {"kanji_bank": [...]}) as `{bank}_1.json`, `{bank}_2.json`, ...

    Each file holds at most `chunk_size` entries.
    """
    paths = []
    for bank, entries in banks.items():
        for i, start in enumerate(range(0, len(entries), chunk_size), start=1):
            path = directory / f"{bank}_{i}.json"
            path.write_text(
                json.dumps(entries[start : start + chunk_size], ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            paths.append(path)
    return paths


def build_manifest(index: dict, files: dict[str, Path], banks: dict[str, list], sources: dict[str, dict]) -> dict:
    """Content hash, entry counts and sources of a dictionary, used to only release changed dictionaries.

    The hash covers every file of the zip (`files` maps archive names to paths) but not the index's revision,
    so a rebuild of unchanged data has the same hash. `sources` (see `used_sources()`) is listed in the release notes.
    """
    digest = hashlib.sha256()
    index_without_revision = {k: v for k, v in index.items() if k != "revision"}
    digest.update(json.dumps(index_without_revision, ensure_ascii=False, sort_keys=True).encode())
    for arcname in sorted(files):
        digest.update(arcname.encode())
        digest.update(files[arcname].read_bytes())
    return {
        "revision": index["revision"],
        "contentSha256": digest.hexdigest(),
        "entries": {bank: len(entries) for bank, entries in sorted(banks.items())},
        "sources": sources,
    }


def package_dictionary(
    package_name: str,
    index: dict,
    banks: dict[str, list],
    extra_files: dict[str, Path] | None = None,
    sources: dict[str, dict] | None = None,
    tmp_dir: Path = DEFAULT_TMP_DIR,
    out_dir: Path = DEFAULT_OUT_DIR,
) -> Path:
    """Writes, validates and zips a dictionary to `out/{package_name}.zip` and returns the zip path.

    The uncompressed files are kept in `tmp/{package_name}/` for debugging and the index is also written
    to `out/{package_name}.index.json` to be uploaded with the release for Yomitan's update check.
    `out/{package_name}.manifest.json` holds the content hash, entry counts and sources (see `build_manifest()`).
    `extra_files` maps archive names to files that are added as is (e.g. a manual for DaDb).
    `sources` defaults to every source fetched so far, pass a subset if the repo builds several dictionaries.
    """
    package_dir = tmp_dir / package_name
    shutil.rmtree(package_dir, ignore_errors=True)
    package_dir.mkdir(parents=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    index_json = json.dumps(index, ensure_ascii=False, indent=2)
    (package_dir / "index.json").write_text(index_json, encoding="utf-8")
    bank_files = write_banks(banks, package_dir)
    validate_dictionary_dir(package_dir)

    content = {path.name: path for path in bank_files} | (extra_files or {})
    zip_path = out_dir / f"{package_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(package_dir / "index.json", arcname="index.json")
        for arcname, path in content.items():
            zipf.write(path, arcname=arcname)
    (out_dir / f"{package_name}.index.json").write_text(index_json, encoding="utf-8")
    manifest = build_manifest(index, content, banks, used_sources() if sources is None else sources)
    manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    (out_dir / f"{package_name}.manifest.json").write_text(manifest_json, encoding="utf-8")

    print(f"Exported {sum(map(len, banks.values()))} entries to '{zip_path}'.")
    return zip_path
