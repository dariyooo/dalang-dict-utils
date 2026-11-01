# Dictionary repo standard

Every repo that builds a dictionary for DaLang follows these rules.
New repos are created from the Copier template in this repo (see [README](../README.md)), which already implements them.

## Naming

* Repos: `{script}-{content}-{target}`, lowercase kebab-case, e.g. `kanji-jlpt-levels-yomitan`, `kanji-visual-similarity-yomitan`.
  * `target` is `yomitan` if the dictionary only uses the Yomitan format (works in Yomitan **and** the DaLang apps).
    Dictionaries in a DaKanji format (see [Formats](#formats), they only work in the apps) are named after
    their app: `dakanji` (Japanese), `dahanzi` (Chinese), `dahanja` (Korean),
    or `dalang` if they are useful across languages (e.g. Tatoeba).
  * Name the language if the script does not imply it (`kanji` = Japanese, `hanzi` = Chinese).
* User-facing text (GitHub description, README) names the app, e.g. "for Yomitan and DaKanji" for Japanese dictionaries.
  DaLang is only the name of the shared format and tooling.
* Module: the repo name without target in snake_case, e.g. `kanji_jlpt_levels`.
* Release assets: `{asset}.zip`, its index as `{asset}.index.json` and its manifest (content hash + entry counts)
  as `{asset}.manifest.json`.
  Variants (languages, audio formats) are `{asset}-{variant}.zip`.
  A `dakanji-dictionary` variant of a Yomitan dictionary (e.g. with a manual) is `{asset}-dadb.zip`.

## Layout

```text
build.py              entry point, only calls {module}.build.main(); CI always runs `uv run build.py`
{module}/             all conversion code, also when it is a single file
  build.py            main(): fetch sources -> build banks -> package_dictionary()
sources.lock.json     locked versions of the fetched sources (repos whose sources change)
vendored_sources/     frozen source data, one folder per source with a README (repos whose sources never change)
tests/                pytest tests
tmp/                  git ignored except .gitkeep: tmp/sources/ download cache, tmp/{asset}/ uncompressed dictionary
out/                  git ignored except .gitkeep: release assets only (zips + .index.json + .manifest.json)
stats/                optional, committed build statistics
.github/workflows/    ci.yml + release.yml, only call the reusable workflows of dalang-dict-utils
.copier-answers.yml   managed by Copier, do not edit
```

`tmp/` and `out/` always exist so intermediate results can be inspected after every build.

## Tooling

* uv with a committed `uv.lock`, Python version in `.python-version` (3.12). No requirements.txt.
* ruff for linting and formatting (line length 120, rules `E F I UP B`, `vendored_sources/` excluded), pyright for type checking.
* pytest for tests. No unittest.
* `dalang-dict-utils` as dependency, pinned to a tag.

## Sources

Copier asks whether the sources change (`source_updates`), which decides how sources are handled:

* **Sources change**: declare them in code (`GitHubFile`, `GitHubReleaseAsset`, `Url`) and download them with `dalang_dict.fetch()`,
  which caches in `tmp/sources/` and locks every source to a version + sha256 in the committed `sources.lock.json`.
  A source missing from the lock is locked to its latest version on the next build.
  The *Update* workflow updates the lock weekly (`python -m dalang_dict update-sources`) and releases on changes.
* **Sources never change**: vendor them in `vendored_sources/{name}/` with a README (origin, license, date retrieved),
  regardless of their size, and declare them as `Vendored` with the retrieval date as version.
  Releases are manual only.

Every source has a free text `used_for` (what the dictionary takes from it) and a version:
the commit for `GitHubFile`, the release tag for `GitHubReleaseAsset`, the download date for `Url`, the declared version for `Vendored`.
`fetch()` records both, `package_dictionary()` writes them into the manifest and the release notes list them
together with the changes since the previous release (source versions, entry counts).

## index.json

Created with `dalang_dict.build_index()`:

* `format: 3`, `revision` is the release tag, i.e. the date `YYYY-MM-DD`.
  **Never change the revision format of a released dictionary**: DaLang compares dotted numbers numerically and
  everything else as strings, so a format change breaks update checks.
* `isUpdatable`, `indexUrl` and `downloadUrl` point to `releases/latest/download/` of the repo.
* Required: `title`, `author`, `url`, `description`, `attribution`.
  `sourceLanguage` / `targetLanguage` whenever they apply, DaLang relies on them.
* The title identifies the dictionary in DaLang, do not change it after the first release.
* DaLang extension: `exampleTokenization: "manual"` for example dictionaries whose sentences carry `[[form1||form2]]` markup.

## Formats

Every dictionary declares its format, `package_dictionary(..., format=...)` packages and validates it accordingly
and the manifest records it:

| Format | Works in | Files |
|---|---|---|
| `yomitan` (default) | Yomitan and the apps | `index.json`, Yomitan banks, media |
| `dakanji-dictionary` | the apps | `yomitan` + `audio_list.json` (audio sources), manual (`manual.pdf` or `manual.md` + `manual_icon.svg`) |
| `dakanji-examples` | the apps | `index.json`, `example_bank_{n}.json`, `example_text_bank_{n}.txt` + `example_text_meta_bank_{n}.json`, `tag_bank_{n}.json`, audio files |
| `dakanji-audio` | the apps | `yomitan_index.json`, audio files named `Term [Reading] (Pitch).ext`, or `index.json` / `entries.json` mapping them |

* Audio files (`aac mp3 ogg opus flac wav`, lowercase) are always in `audios/`, everything else in the zip root.
* A manual is only read in a `dakanji-dictionary`.
* See the DaLang authoring manual for the entry layouts.
  Radicals (radk + krad JSON) and stroke order (KanjiVG `.svg`) are imported by DaLang too, they become formats here once
  a repo builds them.

## Packaging

Done by `dalang_dict.package_dictionary()`:

* Bank files only in the zip root, named `{bank}_{n}.json`.
  Banks are passed as lists, or as files in `extra_files` when the build streams them to disk (e.g. Tatoeba).
* Output must be deterministic (stable entry order and JSON formatting).
  DaLang reuses unchanged entries on update based on a hash of their bytes.
* The zip contains exactly the validated files, without a top folder.

## Validation

Every dictionary is validated against the rules of its format before it is zipped:

* The layout: which files the format has and where (the rules of DaLang's importer).
* Yomitan's schemas, for the index of every format and the Yomitan banks.
  They are vendored in `src/dalang_dict/schemas/yomitan/` and synced weekly by
  `.github/workflows/sync-yomitan-schemas.yml`, which commits upstream changes.
* Planned: DaKanji's schemas for the extensions (`audio_list.json`, example banks, audio `index.json` / `entries.json`),
  synced the same way once they are published with the DaLang website.
  Until then only their layout is checked.

## CI and releases

* `ci.yml` runs on push and pull request: ruff check, ruff format check, pyright, pytest.
* `release.yml` runs on a pushed tag `YYYY-MM-DD`: CI, `uv run build.py` with the tag as revision
  (`DALANG_DICT_REVISION`, fails if the build had to change `sources.lock.json`),
  then the GitHub release of the tag containing everything in `out/`, notes from `python -m dalang_dict release-notes`.
  A release of the same tag is replaced, re-release with `git tag -f YYYY-MM-DD && git push -f origin YYYY-MM-DD`.
* `update.yml` (only if the sources change) runs weekly:
  1. updates `sources.lock.json`, stops if no source changed
  2. runs the checks and rebuilds
  3. compares the `{asset}.manifest.json` files with the latest release and fails if a bank lost more than 5% of its entries
  4. commits the lock (`chore: update sources`) and creates a release only if a dictionary changed,
     so users never download an unchanged dictionary with a new revision.
     The release is tagged with the UTC date and replaces a release of the same day,
     its notes compare with the latest release of another day.

## README

Sections in this order: one line summary, Sources (where the data comes from and how it is derived), Installation,
Usage, Development, Release, License.
