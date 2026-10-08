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
- **Logging.** The standard `logging` module, one logger per module. No `print`.
- **Tests.** Plain pytest inside `Test*` classes named after the unit under test, methods named
  `test_<behaviour>_<condition>`. Shared fixtures live in `tests/conftest.py`. The test tree mirrors `src/`. The NiceGUI page wiring in `ui/pages.py` is the main gap: it needs a browser, so it is
  checked by hand and through the pure builders in `ui/components.py`, which are unit-tested.

## Changing the database schema

Append a SQL step to `MIGRATIONS` in `storage/migrations.py` (and its DDL to `storage/models.py`). Opening a `Store`
applies pending steps in order and records the version in `PRAGMA user_version`. Never edit an earlier step: databases
that already ran it will not run it again. Add a test in `tests/unit/storage/test_migrations.py` that starts from the
previous version with a row in it and checks the row survives.

## Adding a subsystem

Create the package with `__init__.py`, `models.py` and `errors.py`, add it to `ALLOWED` in
`tests/unit/test_architecture.py` with the subsystems it may import, and add a page under `docs/reference/`.
The architecture test fails until the three fixed files exist.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org): `feat:`, `fix:`, `refactor:`, `build:`, `docs:`, `test:`,
`style:`, with an optional scope such as `feat(api):`. The body explains why, not what.
