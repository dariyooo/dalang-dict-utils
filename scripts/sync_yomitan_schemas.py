# /// script
# requires-python = ">=3.12"
# dependencies = ["jsonschema>=4.23"]
# ///
"""Vendors Yomitan's current dictionary schemas into src/dalang_dict/schemas/yomitan/ and checks them.

Copies every `dictionary-*.json` of yomidevs/yomitan's ext/data/schemas at the latest commit, removes
schemas that no longer exist upstream and records the commit in SOURCE.json. Fails if a schema is not
a valid JSON schema. Set GITHUB_TOKEN to avoid GitHub's API rate limit.

    uv run scripts/sync_yomitan_schemas.py
"""

import json
import os
import urllib.request
from pathlib import Path

from jsonschema.validators import validator_for

REPO = "yomidevs/yomitan"
BRANCH = "master"
SCHEMA_PATH = "ext/data/schemas"
SCHEMA_PREFIX = "dictionary-"
TARGET_DIR = Path(__file__).parent.parent / "src" / "dalang_dict" / "schemas" / "yomitan"


def github_api(path: str):
    request = urllib.request.Request(f"https://api.github.com/repos/{REPO}/{path}")
    if token := os.environ.get("GITHUB_TOKEN"):
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def download(url: str) -> bytes:
    with urllib.request.urlopen(url) as response:
        return response.read()


def main() -> None:
    commit = github_api(f"commits/{BRANCH}")
    sha = commit["sha"]
    listing = github_api(f"contents/{SCHEMA_PATH}?ref={sha}")
    names = sorted(e["name"] for e in listing if e["name"].startswith(SCHEMA_PREFIX) and e["name"].endswith(".json"))
    if not names:
        raise SystemExit(f"No {SCHEMA_PREFIX}*.json schemas found in {REPO}/{SCHEMA_PATH}")

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    for stale in sorted(set(p.name for p in TARGET_DIR.glob(f"{SCHEMA_PREFIX}*.json")) - set(names)):
        print(f"Removed upstream: {stale}")
        (TARGET_DIR / stale).unlink()

    for name in names:
        data = download(f"https://raw.githubusercontent.com/{REPO}/{sha}/{SCHEMA_PATH}/{name}")
        schema = json.loads(data)
        validator_for(schema).check_schema(schema)
        (TARGET_DIR / name).write_bytes(data)

    source = {
        "repo": REPO,
        "path": SCHEMA_PATH,
        "commit": sha,
        "commitDate": commit["commit"]["committer"]["date"],
        "files": names,
    }
    (TARGET_DIR / "SOURCE.json").write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    print(f"Vendored {len(names)} schemas from {REPO}@{sha[:12]}")


if __name__ == "__main__":
    main()
