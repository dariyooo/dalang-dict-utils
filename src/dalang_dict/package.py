"""Writing bank files and packaging them as dictionary zips into out/."""

import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path

from dalang_dict.sources import used_sources
from dalang_dict.validate import (
    BANK_FILE,
    TEXT_BANK_FILE,
    get_format,
    is_audio_file,
    list_files,
    validate_dictionary_dir,
)

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


def count_entries(files: dict[str, Path]) -> dict[str, int]:
    """Entries per bank (summed over its files, a text bank has one per line) and the number of audio files."""
    entries: dict[str, int] = {}
    for arcname, path in files.items():
        if match := BANK_FILE.match(arcname):
            bank, count = match["bank"], len(json.loads(path.read_text(encoding="utf-8")))
        elif TEXT_BANK_FILE.match(arcname):
            bank, count = "example_text_bank", len(path.read_text(encoding="utf-8").splitlines())
        elif is_audio_file(arcname):
            bank, count = "audios", 1
        else:
            continue
        entries[bank] = entries.get(bank, 0) + count
    return dict(sorted(entries.items()))


def build_manifest(index: dict, files: dict[str, Path], sources: dict[str, dict], format: str = "yomitan") -> dict:
    """Format, content hash, entry counts and sources of a dictionary, used to only release changed dictionaries.

    The hash covers every file of the zip besides the index (`files` maps archive names to paths) and the index
    without its revision, so a rebuild of unchanged data has the same hash.
    `sources` (see `used_sources()`) is listed in the release notes.
    """
    digest = hashlib.sha256()
    index_without_revision = {k: v for k, v in index.items() if k != "revision"}
    digest.update(json.dumps(index_without_revision, ensure_ascii=False, sort_keys=True).encode())
    for arcname in sorted(files):
        digest.update(arcname.encode())
        digest.update(files[arcname].read_bytes())
    return {
        "format": format,
        "revision": index["revision"],
        "contentSha256": digest.hexdigest(),
        "entries": count_entries(files),
        "sources": sources,
    }


def _place(source: Path, target: Path) -> None:
    # Hard links keep large files (audio, streamed banks) from being copied, a copy is the fallback across devices
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def package_dictionary(
    package_name: str,
    index: dict,
    banks: dict[str, list],
    extra_files: dict[str, Path] | None = None,
    sources: dict[str, dict] | None = None,
    format: str = "yomitan",
    tmp_dir: Path = DEFAULT_TMP_DIR,
    out_dir: Path = DEFAULT_OUT_DIR,
) -> Path:
    """Writes, validates and zips a dictionary of `format` (see `validate.FORMATS`) to `out/{package_name}.zip`.

    The uncompressed files are kept in `tmp/{package_name}/` for debugging and the index is also written
    to `out/{package_name}.index.json` to be uploaded with the release for the update check.
    `out/{package_name}.manifest.json` holds the content hash, entry counts and sources (see `build_manifest()`).
    `banks` are written as bank files, `extra_files` maps archive names to files that are added as is:
    banks written by the build itself, a manual, audio files (`audios/{name}`).
    `sources` defaults to every source fetched so far, pass a subset if the repo builds several dictionaries.
    Returns the zip path.
    """
    dictionary_format = get_format(format)
    package_dir = tmp_dir / package_name
    shutil.rmtree(package_dir, ignore_errors=True)
    package_dir.mkdir(parents=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    index_json = json.dumps(index, ensure_ascii=False, indent=2)
    index_path = package_dir / dictionary_format.index_file
    index_path.write_text(index_json, encoding="utf-8")
    write_banks(banks, package_dir)
    for arcname, path in (extra_files or {}).items():
        _place(path, package_dir / arcname)
    validate_dictionary_dir(package_dir, format)

    content = {name: package_dir / name for name in list_files(package_dir) if name != dictionary_format.index_file}
    zip_path = out_dir / f"{package_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(index_path, arcname=dictionary_format.index_file)
        for arcname, path in content.items():
            zipf.write(path, arcname=arcname)
    (out_dir / f"{package_name}.index.json").write_text(index_json, encoding="utf-8")
    manifest = build_manifest(index, content, used_sources() if sources is None else sources, format)
    manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    (out_dir / f"{package_name}.manifest.json").write_text(manifest_json, encoding="utf-8")

    print(f"Exported {sum(manifest['entries'].values())} entries to '{zip_path}'.")
    return zip_path
