# dalang-dict-utils

Utilities and repo template for building DaLang dictionaries (Yomitan format plus DaDb extensions).

* **[Repo standard](docs/repo-standard.md)**: the rules every dictionary repo follows (naming, layout, tooling, sources, index.json, packaging, CI and releases).
* **Copier template** (`copier.yml`, `template/`): creates new dictionary repos that follow the standard and keeps them in sync with it.
* **Reusable workflows** (`.github/workflows/dict-ci.yml`, `dict-release.yml`, `dict-update.yml`): CI, releases and automatic source updates of the dictionary repos.
* **`dalang_dict` package** (`src/dalang_dict/`): locked source downloads, index.json, banks, validation, packaging and release manifests.
* **Vendored schemas** (`src/dalang_dict/schemas/`): Yomitan's, synced weekly by `.github/workflows/sync-yomitan-schemas.yml`, and DaDb's, copied by hand.

## New dictionary repo

``` bash
uvx copier copy --trust gh:dariyooo/dalang-dict-utils <repo-name>
```

Copier asks for the repo name (`{script}-{content}-{target}`, e.g. `kanji-jlpt-levels-yomitan`), a description and a few defaults.
Afterwards fill in the sources and `build_banks()` in `{module}/build.py`.

## Update an existing repo

``` bash
uvx copier update --trust
```

This applies changes of the template (tooling, workflows, `.gitignore`, ...) and keeps the repo's own code
(`build.py`, `{module}/`, `tests/`, `README.md`), which the template only creates once.

## Sync the Yomitan schemas manually

``` bash
uv run scripts/sync_yomitan_schemas.py
```

## Development

``` bash
uv run ruff check .          # lint
uv run ruff format .         # format
uv run pyright               # type check
uv run pytest                # tests
```

## Release

Bump `version` in `pyproject.toml`, then push a matching tag (`v0.1.0` for version `0.1.0`).
`.github/workflows/release-wheel.yml` runs the checks, builds the wheel and sdist and attaches them to a GitHub release of the tag.
Dictionary repos pin the package and the reusable workflows to that tag.
