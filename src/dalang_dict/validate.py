"""Validation of dictionary files against Yomitan's JSON schemas (vendored in schemas/yomitan/)."""

import json
import re
from pathlib import Path

import jsonschema

SCHEMA_DIR = Path(__file__).parent / "schemas" / "yomitan"

# bank file prefix -> schema file
BANK_SCHEMAS = {
    "kanji_bank": "dictionary-kanji-bank-v3-schema.json",
    "kanji_meta_bank": "dictionary-kanji-meta-bank-v3-schema.json",
    "term_bank": "dictionary-term-bank-v3-schema.json",
    "term_meta_bank": "dictionary-term-meta-bank-v3-schema.json",
    "tag_bank": "dictionary-tag-bank-v3-schema.json",
}
BANK_FILE = re.compile(r"^(?P<bank>[a-z_]+)_\d+\.json$")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_dictionary_dir(directory: Path) -> None:
    """Validates index.json and every bank file in `directory`, raises on the first invalid file."""
    jsonschema.validate(_load(directory / "index.json"), _load(SCHEMA_DIR / "dictionary-index-schema.json"))

    for path in sorted(directory.glob("*.json")):
        match = BANK_FILE.match(path.name)
        if path.name == "index.json" or not match:
            continue
        if match["bank"] not in BANK_SCHEMAS:
            raise ValueError(f"Unknown bank file '{path.name}'")
        try:
            jsonschema.validate(_load(path), _load(SCHEMA_DIR / BANK_SCHEMAS[match["bank"]]))
        except jsonschema.ValidationError as e:
            raise ValueError(f"'{path}' is invalid: {e.message} at {list(e.absolute_path)}") from e
