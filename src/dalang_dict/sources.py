"""Pinned, cached downloads of the source data a dictionary is built from."""

import hashlib
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CACHE_DIR = Path("tmp/sources")


@dataclass(frozen=True)
class Source:
    """A source file. `url` should be pinned (e.g. to a commit), `sha256` optionally guards against changes."""

    name: str
    url: str
    sha256: str | None = None


def github_source(name: str, repo: str, commit: str, path: str, sha256: str | None = None) -> Source:
    """Source for the file `path` of the GitHub repo `owner/name` at `commit`."""
    return Source(name, f"https://raw.githubusercontent.com/{repo}/{commit}/{path}", sha256)


def fetch(source: Source, cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    """Downloads `source` once into `cache_dir` and returns its path, verifying the sha256 if given."""
    path = cache_dir / source.name
    if not path.exists():
        print(f"Downloading '{source.url}'...")
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(path.name + ".part")
        urllib.request.urlretrieve(source.url, tmp_path)
        tmp_path.replace(path)

    if source.sha256 is not None:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != source.sha256:
            raise ValueError(f"sha256 of '{path}' is {digest}, expected {source.sha256}")

    return path
