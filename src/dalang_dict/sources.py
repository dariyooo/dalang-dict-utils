"""Locked, cached downloads of the source data a dictionary is built from.

Sources are declared in code (what to download), `sources.lock.json` pins them (which version):

* `fetch()` downloads the locked version and verifies its sha256. A source missing from the lock
  is resolved to its latest version and added to the lock.
* `update_sources()` checks every locked source for a newer version and updates the lock.

Every fetched source is recorded with its version (`used_sources()`), `package_dictionary()` writes them
into the manifest so each release lists the data it was built from.
"""

import datetime
import hashlib
import http.client
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_CACHE_DIR = Path("tmp/sources")
DEFAULT_LOCK_FILE = Path("sources.lock.json")
# Lock entry keys that pin a version, all other keys are the source's declaration
PIN_KEYS = ("version", "sha256")
# Fields that only describe a source, changing them does not relock it
DESCRIPTION_KEYS = ("used_for",)

DOWNLOAD_RETRIES = 10
DOWNLOAD_TIMEOUT = 20
# Some servers (e.g. Tatoeba's) stall at a few KB/s without closing the connection, which no timeout catches
MIN_DOWNLOAD_SPEED = 50 * 1024
DOWNLOAD_SPEED_WINDOW = 15


@dataclass(frozen=True)
class GitHubFile:
    """The file `path` of the GitHub repo `repo` (`owner/name`), locked to the latest commit on `branch` changing it."""

    name: str
    repo: str
    path: str
    branch: str = "main"
    used_for: str = ""
    kind: str = "github-file"

    def latest_version(self) -> str:
        commits = _github_api(f"repos/{self.repo}/commits?sha={self.branch}&path={self.path}&per_page=1")
        if not commits:
            raise ValueError(f"No commit of '{self.path}' found on {self.repo}@{self.branch}")
        return commits[0]["sha"]

    def url(self, version: str) -> str:
        return f"https://raw.githubusercontent.com/{self.repo}/{version}/{self.path}"


@dataclass(frozen=True)
class GitHubReleaseAsset:
    """The asset `asset` of the GitHub repo `repo` (`owner/name`), locked to the tag of its latest release."""

    name: str
    repo: str
    asset: str
    used_for: str = ""
    kind: str = "github-release-asset"

    def latest_version(self) -> str:
        return _github_api(f"repos/{self.repo}/releases/latest")["tag_name"]

    def url(self, version: str) -> str:
        return f"https://github.com/{self.repo}/releases/download/{version}/{self.asset}"


@dataclass(frozen=True)
class Url:
    """A file at a fixed URL whose content may change, locked to its sha256 (e.g. a daily export).

    Its version is the date its current content was first downloaded.
    """

    name: str
    address: str
    used_for: str = ""
    kind: str = "url"

    def latest_version(self) -> str:
        # Unknown without downloading, only the sha256 of the content tells whether it changed
        return ""

    def url(self, version: str) -> str:
        return self.address


@dataclass(frozen=True)
class Vendored:
    """Frozen data committed in `vendored_sources/`, `version` identifies it (e.g. the date it was retrieved)."""

    name: str
    path: str
    version: str
    used_for: str = ""
    kind: str = "vendored"


# Sources that are downloaded and locked in sources.lock.json
LockedSource = GitHubFile | GitHubReleaseAsset | Url
Source = LockedSource | Vendored
SOURCE_TYPES: dict[str, type[LockedSource]] = {
    "github-file": GitHubFile,
    "github-release-asset": GitHubReleaseAsset,
    "url": Url,
}

_used_sources: dict[str, dict] = {}


def used_sources() -> dict[str, dict]:
    """Version and use of every source fetched so far, by name."""
    return dict(sorted(_used_sources.items()))


def _record_use(source: Source, version: str) -> None:
    _used_sources[source.name] = {"version": version, "usedFor": source.used_for}


def _github_api(path: str) -> Any:
    request = urllib.request.Request(f"https://api.github.com/{path}")
    if token := os.environ.get("GITHUB_TOKEN"):
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _download_part(url: str, part: Path) -> None:
    """Downloads `url` to `part`, continuing a partial download, raises if the download stalls or is cut off."""
    resume_at = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": "Mozilla/5.0"}
    if resume_at:
        headers["Range"] = f"bytes={resume_at}-"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
        resume = resume_at and response.status == 206  # otherwise the server ignored the range
        expected = int(response.headers.get("Content-Length", 0))
        received = 0
        with part.open("ab" if resume else "wb") as f:
            window_start, window_bytes = time.monotonic(), 0
            while chunk := response.read(64 * 1024):
                f.write(chunk)
                received += len(chunk)
                window_bytes += len(chunk)
                elapsed = time.monotonic() - window_start
                if elapsed >= DOWNLOAD_SPEED_WINDOW:
                    if window_bytes / elapsed < MIN_DOWNLOAD_SPEED:
                        raise TimeoutError(f"download stalled at {window_bytes / elapsed / 1024:.1f} KB/s")
                    window_start, window_bytes = time.monotonic(), 0
    # A cut off response just ends, `read()` does not raise
    if received < expected:
        raise http.client.IncompleteRead(b"", expected - received)


def _download(url: str, path: Path) -> None:
    """Downloads `url` to `path`, retrying failed and stalled downloads where they stopped."""
    print(f"Downloading '{url}'...")
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.unlink(missing_ok=True)
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            _download_part(url, part)
            break
        except (OSError, http.client.HTTPException) as e:  # URLError, HTTPError, timeouts, cut off responses
            if isinstance(e, urllib.error.HTTPError) and e.code == 416:
                part.unlink(missing_ok=True)  # the partial download is not a prefix of the file anymore
            if attempt == DOWNLOAD_RETRIES:
                raise
            wait = min(5 * attempt, 30)
            print(f"Attempt {attempt}/{DOWNLOAD_RETRIES} failed ({e}), resuming in {wait}s...")
            time.sleep(wait)
    part.replace(path)


def load_lock(lock_file: Path = DEFAULT_LOCK_FILE) -> dict[str, dict]:
    if not lock_file.exists():
        return {}
    return json.loads(lock_file.read_text(encoding="utf-8"))


def save_lock(lock: dict[str, dict], lock_file: Path = DEFAULT_LOCK_FILE) -> None:
    lock_file.write_text(json.dumps(dict(sorted(lock.items())), indent=2) + "\n", encoding="utf-8")


def _declaration(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if k not in PIN_KEYS}


def _source_declaration(source: LockedSource) -> dict:
    return {k: v for k, v in asdict(source).items() if k not in DESCRIPTION_KEYS}


def _lock_entry(source: LockedSource, version: str, cache_dir: Path) -> dict:
    """Downloads `version` of `source` into the cache and returns its lock entry.

    Sources without a version (`Url`) are versioned by the download date.
    """
    path = cache_dir / source.name
    _download(source.url(version), path)
    version = version or datetime.date.today().isoformat()
    return {**_source_declaration(source), "version": version, "sha256": _sha256(path)}


def fetch(source: Source, cache_dir: Path = DEFAULT_CACHE_DIR, lock_file: Path = DEFAULT_LOCK_FILE) -> Path:
    """Returns the path of the locked version of `source`, downloading it into `cache_dir` if needed.

    A source that is not locked yet (or whose declaration changed) is locked to its latest version,
    `Vendored` sources are returned as is.
    """
    if isinstance(source, Vendored):
        _record_use(source, source.version)
        return Path(source.path)

    lock = load_lock(lock_file)
    entry = lock.get(source.name)
    path = cache_dir / source.name

    if entry is None or _declaration(entry) != _source_declaration(source):
        entry = lock[source.name] = _lock_entry(source, source.latest_version(), cache_dir)
        save_lock(lock, lock_file)
        print(f"Locked '{source.name}' in '{lock_file}'.")
    elif not path.exists() or _sha256(path) != entry["sha256"]:
        _download(source.url(entry["version"]), path)
        digest = _sha256(path)
        if digest != entry["sha256"]:
            raise ValueError(
                f"sha256 of '{path}' is {digest}, '{lock_file}' expects {entry['sha256']}. "
                "The source changed, run `uv run python -m dalang_dict update-sources`."
            )
    _record_use(source, entry["version"])
    return path


def update_sources(cache_dir: Path = DEFAULT_CACHE_DIR, lock_file: Path = DEFAULT_LOCK_FILE) -> list[str]:
    """Updates every locked source to its latest version and returns the names of the changed ones.

    A source only counts as changed if its content changed, a new version with the same content is not locked.
    """
    lock = load_lock(lock_file)
    changed = []
    for name, entry in lock.items():
        source = SOURCE_TYPES[entry["kind"]](**_declaration(entry))
        version = source.latest_version()
        if version and version == entry["version"]:
            continue
        new_entry = _lock_entry(source, version, cache_dir)
        if new_entry["sha256"] != entry["sha256"]:
            lock[name] = new_entry
            changed.append(name)
    save_lock(lock, lock_file)
    return changed
