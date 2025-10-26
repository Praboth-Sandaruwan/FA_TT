# Bootstrap Tooling

This repository contains a minimal Python project skeleton configured with modern developer tooling.

## Getting Started

1. Install [Poetry](https://python-poetry.org/docs/#installation) if it is not already available on your system.
2. Install the project dependencies:

   ```bash
   poetry install
   ```

3. Enable the shared git hooks provided by [pre-commit](https://pre-commit.com/):

   ```bash
   poetry run pre-commit install
   ```

4. Run the test suite:

   ```bash
   poetry run pytest
   ```

## Tooling

- **Formatter**: [Black](https://black.readthedocs.io/en/stable/)
- **Linter**: [Ruff](https://docs.astral.sh/ruff/)
- **Type Checker**: [mypy](https://mypy.readthedocs.io/en/stable/)
- **Test Runner**: [pytest](https://docs.pytest.org/)
- **HTTP Client Library**: [httpx](https://www.python-httpx.org/)
- **Test Coverage**: [coverage.py](https://coverage.readthedocs.io/)

All tooling is configured via the committed configuration files in the project root. The pre-commit hooks ensure that Ruff, Black, and mypy run automatically before each commit.
