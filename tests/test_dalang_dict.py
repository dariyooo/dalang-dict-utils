import hashlib
import json
import zipfile

import pytest

from dalang_dict import Source, build_index, fetch, package_dictionary, validate_dictionary_dir, write_banks


def test_build_index_points_to_latest_release():
    index = build_index("Test", "owner/repo", "Test_Dict", revision="2026-10-31", author="me")
    assert index["isUpdatable"] is True
    assert index["indexUrl"] == "https://github.com/owner/repo/releases/latest/download/Test_Dict.index.json"
    assert index["downloadUrl"] == "https://github.com/owner/repo/releases/latest/download/Test_Dict.zip"
    assert index["revision"] == "2026-10-31"
    assert index["author"] == "me"


def test_write_banks_splits_into_chunks(tmp_path):
    paths = write_banks({"kanji_meta_bank": [["一", "freq", i] for i in range(5)]}, tmp_path, chunk_size=2)
    assert [p.name for p in paths] == ["kanji_meta_bank_1.json", "kanji_meta_bank_2.json", "kanji_meta_bank_3.json"]
    assert json.loads(paths[-1].read_text(encoding="utf-8")) == [["一", "freq", 4]]


def test_validate_rejects_invalid_bank(tmp_path):
    (tmp_path / "index.json").write_text(json.dumps(build_index("Test", "owner/repo", "Test_Dict")))
    write_banks({"kanji_meta_bank": [["一", "not-freq", 1]]}, tmp_path)
    with pytest.raises(ValueError, match="kanji_meta_bank_1.json"):
        validate_dictionary_dir(tmp_path)


def test_package_dictionary_writes_zip_and_release_index(tmp_path):
    index = build_index("Test", "owner/repo", "Test_Dict")
    zip_path = package_dictionary(
        "Test_Dict", index, {"kanji_meta_bank": [["一", "freq", 1]]}, tmp_dir=tmp_path / "tmp", out_dir=tmp_path / "out"
    )
    with zipfile.ZipFile(zip_path) as zipf:
        assert sorted(zipf.namelist()) == ["index.json", "kanji_meta_bank_1.json"]
    assert json.loads((tmp_path / "out" / "Test_Dict.index.json").read_text(encoding="utf-8")) == index


def test_fetch_caches_and_verifies_sha256(tmp_path):
    source_file = tmp_path / "source.txt"
    source_file.write_text("data")
    sha256 = hashlib.sha256(b"data").hexdigest()

    path = fetch(Source("source.txt", source_file.as_uri(), sha256), cache_dir=tmp_path / "cache")
    assert path.read_text() == "data"

    source_file.unlink()  # served from the cache from now on
    assert fetch(Source("source.txt", source_file.as_uri()), cache_dir=tmp_path / "cache") == path
    with pytest.raises(ValueError, match="sha256"):
        fetch(Source("source.txt", source_file.as_uri(), "0" * 64), cache_dir=tmp_path / "cache")
