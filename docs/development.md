# Development

## Setup

```bash
uv sync                      # runtime and dev dependencies
uv sync --group docs         # also the documentation tools
uv run pre-commit install    # run the checks on every commit
```

## Everyday commands

| Command | What it does |
|---|---|
| `uv run pytest` | Run the tests. `--cov=livestocks` adds coverage and fails below 70%. |
| `uv run ruff check .` | Lint. `--fix` applies the safe fixes. |
| `uv run ruff format .` | Format. |
| `uv run pyright` | Type-check `src/`. |
| `uv run python scripts/check_docstrings.py` | Check the docstring format. |
| `uv run pre-commit run --all-files` | Everything above, as the commit hook runs it. |
| `uv run mkdocs serve` | Preview this documentation. `mkdocs build --strict` fails on any warning. |

## Code style

- **Formatting.** `ruff format`, 100 columns, double quotes.
- **Imports.** Absolute only: `from livestocks.domain import Forecast`. Relative imports are rejected by Ruff.
  Imports across subsystems go through the package root, see [Architecture](architecture.md).
- **Docstrings.** Every public module, class, function and method in `src/` has a docstring of exactly three lines of
  prose, with no `Args:`, `Returns:` or `Raises:` sections. The text starts right after the opening quotes and the
  closing quotes sit on their own line:

    ```python
    def fetch_forecast(client, exchange, symbol):
        """Fetch the forecast page and parse it, retrying transient upstream failures.
        A 404 raises NotFoundError at once; other errors are retried with backoff
        up to `retries` extra times before UpstreamError is raised.
        """
    ```

  Ruff checks that docstrings exist and `scripts/check_docstrings.py` checks their shape. Comments explain *why*, not
  *what*.
- **Types.** Full annotations in `src/` with modern syntax (`X | None`, `list[str]`). `domain`, `crawler`, `storage`,
  `services` and `api` pass pyright's strict mode; `ui` is checked in standard mode.
- **Data classes.** Domain objects are `@dataclass(frozen=True, slots=True)`. Pydantic is used only at the edges (API
  models, `Settings`). Fixed value sets are `StrEnum`s.
- **Errors.** Each subsystem raises its own exceptions from its `errors.py`. A bare `except` is never used;
  `except Exception` is allowed only in background tasks and best-effort extras, must log, and carries a
  `# noqa: BLE001` with the reason.
- **Logging.** loguru's `logger`, with context bound as fields (`logger.bind(ticker=key)`). No `print`, no direct use of the
  standard `logging` module except in `logging_config.py`.
- **Tests.** Plain pytest inside `Test*` classes named after the unit under test, methods named
  `test_<behaviour>_<condition>`. Shared fixtures live in `tests/conftest.py`. The test tree mirrors `src/`. The NiceGUI page wiring in `ui/pages/` is the main gap: it needs a browser, so it is
  checked by hand and through the pure builders in `ui/components.py`, which are unit-tested.

## Changing the database schema

The schema lives in the SQLModel classes in `storage/models.py` and is versioned with Alembic. `alembic.ini` at the
repository root points the command line at the migrations and the development database. After editing a model:

```bash
uv run alembic revision --autogenerate -m "describe the change"   # writes storage/migrations/versions/NNNN_*.py
uv run alembic upgrade head                                        # applies it to data/livestocks.db
uv run alembic check                                               # fails if models and migrations disagree
```

Review the generated revision and fix it by hand where needed; SQLite cannot alter some things in place, so batch mode
is on. The app upgrades its database to the latest revision on start-up. Never edit a revision that has shipped; add a
new one. Add a test in `tests/unit/storage/test_migrations.py` that starts from the previous schema with a row in it and
checks the row survives. A test also runs `alembic check`, so a model change without a revision fails the suite.

Tests build their schema straight from the models (`Store(path, migrate=False)`) for speed and run the real migrations
only in `test_migrations.py`.

## Adding a subsystem

Create the package with `__init__.py`, `models.py` and `errors.py`, add it to `ALLOWED` in
`tests/unit/test_architecture.py` with the subsystems it may import, and add a page under `docs/reference/`.
The architecture test fails until the three fixed files exist.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org): `feat:`, `fix:`, `refactor:`, `build:`, `docs:`, `test:`,
`style:`, with an optional scope such as `feat(api):`. The body explains why, not what.

## Web UI structure

The pages live in `ui/pages/`: one module per page (`dashboard`, `detail`, `suggestions_page`, `calendar_page`), shared pieces in `common`, and `register()` in `__init__` wiring them to one `Deps` bundle. Shared HTML lives in pure builder modules: `components`
(dashboard pieces, the sortable forecast table), `dividends` (dividend card and calendar), `suggestions`, `chart`,
`financials`, `seasonals`, `primitives` (cards, crumbs, empty states, table headers) and `live` (guards for timers and
first renders). `hunter` builds the dividend-hunting page (controls, ranked table with timelines, detail panel and the
how-to guide), and `domain/hunt.py` holds the score and checklist as pure functions. Each builder escapes its text and
is unit-tested without NiceGUI.

The pages themselves are rendered in tests with NiceGUI's simulated user on fake services
(`tests/unit/ui/app/`, `tests/unit/ui/test_pages_calendar.py`). The `simulate()` helper restores the `livestocks`
modules that the simulation removes from `sys.modules`, so later tests can still patch them by name.

Styles live in `ui/static/app.css`, served from `/static/app.css`. Colour tokens are defined on `:root` and
`body.body--light`. `tests/unit/ui/test_theme.py` checks text contrast in both themes and that every class the builders
use is styled. `tests/unit/ui/test_chart.py` checks that the chart palette matches the stylesheet.

Fonts are IBM Plex, self-hosted in `ui/static/fonts/` under the SIL Open Font License (`OFL.txt` alongside).
