# Dictionary repo standard

Every repo that builds a dictionary for DaLang follows these rules.
New repos are created from the Copier template in this repo (see [README](../README.md)), which already implements them.

## Naming

* Repos: `{script}-{content}-{target}`, lowercase kebab-case, e.g. `kanji-jlpt-levels-yomitan`, `kanji-visual-similarity-yomitan`.
  * `target` is `yomitan` if the dictionary only uses the Yomitan format (works in Yomitan **and** DaLang),
    `dalang` if it uses DaDb extensions (example and audio dictionaries, works only in DaLang).
  * Name the language if the script does not imply it (`kanji` = Japanese, `hanzi` = Chinese).
* Module: the repo name without target in snake_case, e.g. `kanji_jlpt_levels`.
* Release assets: `{asset}.zip` and its index as `{asset}.index.json`.
  Variants (languages, audio formats) are `{asset}-{variant}.zip`.
  A DaDb only variant with extra files (manual) is `{asset}-dadb.zip`.

## Layout

```text
build.py              entry point, only calls {module}.build.main(); CI always runs `uv run build.py`
{module}/             all conversion code, also when it is a single file
  build.py            main(): fetch sources -> build banks -> package_dictionary()
sources/{name}/       vendored source data, only if it cannot be downloaded; contains a README with origin + license
tests/                pytest tests
tmp/                  git ignored except .gitkeep: tmp/sources/ download cache, tmp/{asset}/ uncompressed dictionary
out/                  git ignored except .gitkeep: release assets only (zips + .index.json)
stats/                optional, committed build statistics
.github/workflows/    ci.yml + release.yml, only call the reusable workflows of dalang-dict-utils
.copier-answers.yml   managed by Copier, do not edit
```

`tmp/` and `out/` always exist so intermediate results can be inspected after every build.

## Tooling

* uv with a committed `uv.lock`, Python version in `.python-version` (3.12). No requirements.txt.
* ruff for linting and formatting (line length 120, rules `E F I UP B`), pyright for type checking.
* pytest for tests. No unittest.
* `dalang-dict-utils` as dependency, pinned to a tag.

## Sources

* Download with `dalang_dict.fetch()`, which caches in `tmp/sources/`.
* Pin every URL to a commit or a dated release. If a URL cannot be pinned, set `sha256`.
* Only vendor data in `sources/{name}/` if it cannot be downloaded.

## index.json

Created with `dalang_dict.build_index()`:

* `format: 3`, `revision` is the build date `YYYY-MM-DD`.
  **Never change the revision format of a released dictionary**: DaLang compares dotted numbers numerically and
  everything else as strings, so a format change breaks update checks.
* `isUpdatable`, `indexUrl` and `downloadUrl` point to `releases/latest/download/` of the repo.
* Required: `title`, `author`, `url`, `description`, `attribution`.
  `sourceLanguage` / `targetLanguage` whenever they apply, DaLang relies on them.
* The title identifies the dictionary in DaLang, do not change it after the first release.
* DaLang extension: `exampleTokenization: "manual"` for example dictionaries whose sentences carry `[[form1||form2]]` markup.

## Packaging

Done by `dalang_dict.package_dictionary()`:

* Bank files only in the zip root, named `{bank}_{n}.json`.
* Output must be deterministic (stable entry order and JSON formatting).
  DaLang reuses unchanged entries on update based on a hash of their bytes.
* Audio dictionaries name their metadata `yomitan_index.json`, `index.json` is the audio mapping there.
* Manuals (`manual.pdf` or `manual.md` + `manual_icon.svg`) go in the zip root and are only read in Yomitan type dictionaries.

DaDb extensions on top of Yomitan, see the DaLang authoring manual for the entry layouts:

| Kind | Files |
|---|---|
| Examples | `example_bank_{n}.json`, `example_text_bank_{n}.txt` + `example_text_meta_bank_{n}.json`, `tag_bank_{n}.json` |
| Audio | `yomitan_index.json`, `index.json` or `entries.json`, audio files (`aac mp3 ogg opus flac wav`, lowercase) |
| Audio sources | `audio_list.json` in a Yomitan dictionary |
| Radicals | radk + krad JSON (jmdict-simplified layout) |
| Stroke order | KanjiVG `.svg` files |

## Validation

Every dictionary is validated before it is zipped:

* Against Yomitan's schemas, vendored in `src/dalang_dict/schemas/yomitan/` and synced weekly by
  `.github/workflows/sync-yomitan-schemas.yml`, which commits upstream changes.
* Against DaDb's schemas for the extensions, vendored by hand in `src/dalang_dict/schemas/dadb/`.

## CI and releases

* `ci.yml` runs on push and pull request: ruff check, ruff format check, pyright, pytest.
* `release.yml` runs manually (plus a cron if the source changes regularly): CI, `uv run build.py`,
  then a GitHub release tagged with the UTC date containing everything in `out/`. A rebuild on the same day replaces it.

## README

Sections in this order: one line summary, Sources (where the data comes from and how it is derived), Installation,
Usage, Development, Release, License.
