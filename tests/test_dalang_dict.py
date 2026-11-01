import datetime
import hashlib
import json
import zipfile

import pytest

from dalang_dict import (
    GitHubFile,
    Url,
    Vendored,
    build_index,
    fetch,
    manifest_changed,
    package_dictionary,
    release_changed,
    release_notes,
    update_sources,
    used_sources,
    validate_dictionary_dir,
    write_banks,
)
from dalang_dict.sources import load_lock


def test_build_index_points_to_latest_release():
    index = build_index("Test", "owner/repo", "Test_Dict", revision="2026-10-31", author="me")
    assert index["isUpdatable"] is True
    assert index["indexUrl"] == "https://github.com/owner/repo/releases/latest/download/Test_Dict.index.json"
    assert index["downloadUrl"] == "https://github.com/owner/repo/releases/latest/download/Test_Dict.zip"
    assert index["revision"] == "2026-10-31"
    assert index["author"] == "me"


def test_build_index_takes_revision_from_env(monkeypatch):
    monkeypatch.setenv("DALANG_DICT_REVISION", "2026-11-01")
    assert build_index("Test", "owner/repo", "Test_Dict")["revision"] == "2026-11-01"


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
    manifest = json.loads((tmp_path / "out" / "Test_Dict.manifest.json").read_text(encoding="utf-8"))
    assert manifest["entries"] == {"kanji_meta_bank": 1}
    assert manifest["sources"] == used_sources()


def _package(tmp_path, revision, entries):
    index = build_index("Test", "owner/repo", "Test_Dict", revision=revision)
    package_dictionary(
        "Test_Dict", index, {"kanji_meta_bank": entries}, tmp_dir=tmp_path / "tmp", out_dir=tmp_path / "out"
    )
    return json.loads((tmp_path / "out" / "Test_Dict.manifest.json").read_text(encoding="utf-8"))


def test_manifest_hash_ignores_revision_but_not_content(tmp_path):
    first = _package(tmp_path, "2026-10-01", [["一", "freq", 1]])
    assert _package(tmp_path, "2026-10-31", [["一", "freq", 1]])["contentSha256"] == first["contentSha256"]
    assert _package(tmp_path, "2026-10-31", [["一", "freq", 2]])["contentSha256"] != first["contentSha256"]


def _url_source(tmp_path, content):
    source_file = tmp_path / "source.txt"
    source_file.write_text(content)
    return Url("source.txt", source_file.as_uri())


def test_fetch_locks_new_source_and_verifies_it(tmp_path):
    lock_file, cache = tmp_path / "sources.lock.json", tmp_path / "cache"
    source = _url_source(tmp_path, "data")

    path = fetch(source, cache_dir=cache, lock_file=lock_file)
    assert path.read_text() == "data"
    assert load_lock(lock_file)["source.txt"]["sha256"] == hashlib.sha256(b"data").hexdigest()

    _url_source(tmp_path, "changed upstream")
    path.unlink()  # forces a download of the changed source
    with pytest.raises(ValueError, match="update-sources"):
        fetch(source, cache_dir=cache, lock_file=lock_file)


def test_fetch_records_versions_and_use(tmp_path):
    lock_file, cache = tmp_path / "sources.lock.json", tmp_path / "cache"
    source = Url("source.txt", _url_source(tmp_path, "data").address, used_for="everything")
    fetch(source, cache_dir=cache, lock_file=lock_file)
    vendored = Vendored("frozen", str(tmp_path / "frozen.txt"), version="2020-01-01", used_for="old data")
    assert fetch(vendored) == tmp_path / "frozen.txt"

    today = datetime.date.today().isoformat()
    assert used_sources()["source.txt"] == {"version": today, "usedFor": "everything"}
    assert used_sources()["frozen"] == {"version": "2020-01-01", "usedFor": "old data"}
    assert "used_for" not in load_lock(lock_file)["source.txt"]

    # Changing the description does not relock the source
    fetch(Url("source.txt", source.address, used_for="other"), cache_dir=cache, lock_file=lock_file)
    assert load_lock(lock_file)["source.txt"]["version"] == today


def test_update_sources_updates_changed_url_source(tmp_path):
    lock_file, cache = tmp_path / "sources.lock.json", tmp_path / "cache"
    fetch(_url_source(tmp_path, "data"), cache_dir=cache, lock_file=lock_file)

    assert update_sources(cache_dir=cache, lock_file=lock_file) == []
    _url_source(tmp_path, "new data")
    assert update_sources(cache_dir=cache, lock_file=lock_file) == ["source.txt"]
    assert fetch(_url_source(tmp_path, "new data"), cache_dir=cache, lock_file=lock_file).read_text() == "new data"


def test_github_file_is_locked_to_latest_commit(tmp_path, monkeypatch):
    lock_file, cache = tmp_path / "sources.lock.json", tmp_path / "cache"
    for commit in ("c1", "c2"):
        (tmp_path / commit).write_text(f"data {commit}")
    latest = {"commit": "c1"}
    monkeypatch.setattr(GitHubFile, "latest_version", lambda self: latest["commit"])
    monkeypatch.setattr(GitHubFile, "url", lambda self, version: (tmp_path / version).as_uri())
    source = GitHubFile("data.txt", "owner/repo", "data.txt")

    assert fetch(source, cache_dir=cache, lock_file=lock_file).read_text() == "data c1"
    latest["commit"] = "c2"
    assert fetch(source, cache_dir=cache, lock_file=lock_file).read_text() == "data c1"  # stays locked
    assert update_sources(cache_dir=cache, lock_file=lock_file) == ["data.txt"]
    assert load_lock(lock_file)["data.txt"]["version"] == "c2"


def test_manifest_changed():
    old = {"contentSha256": "a", "entries": {"kanji_meta_bank": 100}}
    assert manifest_changed({"contentSha256": "a", "entries": {"kanji_meta_bank": 100}}, old) is False
    assert manifest_changed({"contentSha256": "b", "entries": {"kanji_meta_bank": 98}}, old) is True
    assert manifest_changed({"contentSha256": "b", "entries": {}}, None) is True
    with pytest.raises(ValueError, match="dropped"):
        manifest_changed({"contentSha256": "b", "entries": {"kanji_meta_bank": 90}}, old)


def test_release_changed_compares_with_previous_release(tmp_path):
    out, previous = tmp_path / "out", tmp_path / "previous"
    out.mkdir()
    previous.mkdir()
    manifest = {"contentSha256": "a", "entries": {"kanji_meta_bank": 1}}
    (out / "Test_Dict.manifest.json").write_text(json.dumps(manifest))
    assert release_changed(out, previous) == ["Test_Dict"]  # never released
    (previous / "Test_Dict.manifest.json").write_text(json.dumps(manifest))
    assert release_changed(out, previous) == []


def test_release_notes_list_sources_and_changes(tmp_path):
    out, previous = tmp_path / "out", tmp_path / "previous"
    out.mkdir()
    previous.mkdir()
    commit = "a" * 40
    new = {
        "revision": "2026-11-02",
        "contentSha256": "b",
        "entries": {"kanji_meta_bank": 3},
        "sources": {"data.json": {"version": "b" * 40, "usedFor": "levels"}},
    }
    (out / "Test_Dict.manifest.json").write_text(json.dumps(new))
    assert "First release." in release_notes(out, previous)

    old = {**new, "revision": "2026-11-01", "contentSha256": "a", "entries": {"kanji_meta_bank": 2}}
    old["sources"] = {"data.json": {"version": commit, "usedFor": "levels"}}
    (previous / "Test_Dict.manifest.json").write_text(json.dumps(old))
    notes = release_notes(out, previous)
    assert "- `data.json` @ `bbbbbbb`: levels" in notes
    assert "Changes since 2026-11-01" in notes
    assert "- `data.json`: `aaaaaaa` → `bbbbbbb`" in notes
    assert "- `kanji_meta_bank`: 2 → 3 entries" in notes
