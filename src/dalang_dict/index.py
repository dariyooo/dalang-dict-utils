"""index.json creation, including the URLs Yomitan uses to check for updates."""

import datetime
import os
from typing import Any

# Set by the release workflow to the pushed tag, so the revision always equals the release tag
REVISION_ENV = "DALANG_DICT_REVISION"


def build_index(title: str, github_repo: str, package_name: str, revision: str | None = None, **fields: Any) -> dict:
    """Creates a format 3 index that updates from the latest GitHub release of `github_repo` (`owner/name`).

    The release has to contain `{package_name}.zip` and its index as `{package_name}.index.json`,
    `fields` are added as is (author, url, description, attribution, ...).
    The revision defaults to `$DALANG_DICT_REVISION`, otherwise to today's date.
    """
    release = f"https://github.com/{github_repo}/releases/latest/download"
    return {
        "title": title,
        "format": 3,
        "revision": revision or os.environ.get(REVISION_ENV) or datetime.date.today().isoformat(),
        "sequenced": False,
        "isUpdatable": True,
        "indexUrl": f"{release}/{package_name}.index.json",
        "downloadUrl": f"{release}/{package_name}.zip",
        **fields,
    }
