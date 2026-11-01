"""Validation of dictionary directories, one set of rules per format (see `FORMATS`).

Every format checks the layout DaLang's importer expects (which files, where) and validates the files it has a
schema for: Yomitan's schemas are vendored in schemas/yomitan/, DaKanji's are planned (see schemas/dadb/README.md).
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import jsonschema

SCHEMA_DIR = Path(__file__).parent / "schemas" / "yomitan"
INDEX_SCHEMA = "dictionary-index-schema.json"

# bank file prefix -> schema file, None until DaKanji's schemas are published
YOMITAN_BANKS: dict[str, str | None] = {
    "kanji_bank": "dictionary-kanji-bank-v3-schema.json",
    "kanji_meta_bank": "dictionary-kanji-meta-bank-v3-schema.json",
    "term_bank": "dictionary-term-bank-v3-schema.json",
    "term_meta_bank": "dictionary-term-meta-bank-v3-schema.json",
    "tag_bank": "dictionary-tag-bank-v3-schema.json",
}
EXAMPLE_BANKS: dict[str, str | None] = {
    "example_bank": None,
    "example_text_meta_bank": None,
    "tag_bank": "dictionary-tag-bank-v3-schema.json",
}
BANK_FILE = re.compile(r"^(?P<bank>[a-z_]+)_\d+\.json$")
TEXT_BANK_FILE = re.compile(r"^example_text_bank_\d+\.txt$")

AUDIO_DIR = "audios"
AUDIO_EXTENSIONS = {".aac", ".mp3", ".ogg", ".opus", ".flac", ".wav"}
AUDIO_METADATA_FILES = {"index.json", "entries.json"}
AUDIO_LIST_FILE = "audio_list.json"
MANUAL_FILES = {"manual.pdf", "manual.md", "manual_icon.svg"}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_json(path: Path, schema: str) -> None:
    try:
        jsonschema.validate(_load(path), _load(SCHEMA_DIR / schema))
    except jsonschema.ValidationError as e:
        raise ValueError(f"'{path}' is invalid: {e.message} at {list(e.absolute_path)}") from e


def list_files(directory: Path) -> list[str]:
    """All files below `directory` as sorted archive names, e.g. `audios/a.mp3`."""
    return sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file())


def is_audio_file(name: str) -> bool:
    """Whether `name` is an audio file in `audios/`, where the audio files of every format belong."""
    path = PurePosixPath(name)
    return str(path.parent) == AUDIO_DIR and path.suffix in AUDIO_EXTENSIONS


def _check_banks(directory: Path, files: list[str], banks: dict[str, str | None]) -> set[str]:
    """Validates the bank files in the root (`{bank}_{n}.json`), raises on unknown banks and returns the bank files."""
    found = set()
    for name in files:
        match = BANK_FILE.match(name)
        if not match:
            continue
        if match["bank"] not in banks:
            raise ValueError(f"Unknown bank file '{name}'")
        schema = banks[match["bank"]]
        if schema:
            _validate_json(directory / name, schema)
        found.add(name)
    return found


def _reject_unexpected(files: set[str]) -> None:
    if files:
        raise ValueError(f"Unexpected files {sorted(files)[:5]}, audio files belong in '{AUDIO_DIR}/'")


def _check_yomitan(directory: Path, files: list[str]) -> None:
    # Every file besides the banks is media, e.g. the images of structured content
    _check_banks(directory, files, YOMITAN_BANKS)
    extensions = sorted(set(files) & (MANUAL_FILES | {AUDIO_LIST_FILE}))
    if extensions:
        raise ValueError(f"{extensions} are DaKanji extensions, use the dakanji-dictionary format")


def _check_dakanji_dictionary(directory: Path, files: list[str]) -> None:
    # Yomitan plus an audio source list (schema planned) and a manual, which DaLang only reads in this format
    _check_banks(directory, files, YOMITAN_BANKS)


def _check_dakanji_examples(directory: Path, files: list[str]) -> None:
    banks = _check_banks(directory, files, EXAMPLE_BANKS)
    text_banks = {name for name in files if TEXT_BANK_FILE.match(name)}
    for name in banks:
        if name.startswith("example_text_meta_bank_"):
            text_bank = name.replace("example_text_meta_bank_", "example_text_bank_").replace(".json", ".txt")
            if text_bank not in text_banks:
                raise ValueError(f"'{name}' has no text bank '{text_bank}'")
    if not text_banks and not any(name.startswith("example_bank_") for name in banks):
        raise ValueError("No example banks")
    # DaLang ignores everything besides banks and audio files
    _reject_unexpected(set(files) - banks - text_banks - {"index.json"} - set(filter(is_audio_file, files)))


def _check_dakanji_audio(directory: Path, files: list[str]) -> None:
    # Without index.json / entries.json (schemas planned) the audio files are named `Term [Reading] (Pitch).ext`,
    # which DaLang reads from any name, so there is nothing to check about the names.
    audio_files = set(filter(is_audio_file, files))
    if not audio_files:
        raise ValueError(f"No audio files in '{AUDIO_DIR}/'")
    _reject_unexpected(set(files) - audio_files - AUDIO_METADATA_FILES - {"yomitan_index.json"})


@dataclass(frozen=True)
class Format:
    index_file: str
    check: Callable[[Path, list[str]], None]


# The formats DaLang imports, a dictionary declares its format when it is packaged
FORMATS = {
    "yomitan": Format("index.json", _check_yomitan),
    "dakanji-dictionary": Format("index.json", _check_dakanji_dictionary),
    "dakanji-examples": Format("index.json", _check_dakanji_examples),
    "dakanji-audio": Format("yomitan_index.json", _check_dakanji_audio),
}


def get_format(name: str) -> Format:
    if name not in FORMATS:
        raise ValueError(f"Unknown format '{name}', use one of {list(FORMATS)}")
    return FORMATS[name]


def validate_dictionary_dir(directory: Path, format: str = "yomitan") -> None:
    """Validates the dictionary in `directory` against the rules of `format`, raises on the first problem."""
    dictionary_format = get_format(format)
    _validate_json(directory / dictionary_format.index_file, INDEX_SCHEMA)
    dictionary_format.check(directory, list_files(directory))
