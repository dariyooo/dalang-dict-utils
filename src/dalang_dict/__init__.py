"""Fetch sources and build, validate and package DaLang dictionaries (Yomitan format plus DaDb extensions)."""

from dalang_dict.index import build_index
from dalang_dict.package import package_dictionary, write_banks
from dalang_dict.sources import Source, fetch, github_source
from dalang_dict.validate import validate_dictionary_dir

__all__ = [
    "Source",
    "build_index",
    "fetch",
    "github_source",
    "package_dictionary",
    "validate_dictionary_dir",
    "write_banks",
]
