# Contributing

Thanks for helping to improve this repository! The guidelines below describe how we collaborate, keep quality high, and ensure consistent documentation across projects.

## Branching strategy

- Develop on short-lived feature branches cut from `main`.
- Use descriptive names that group tickets by area, for example: `docs/add-auth-guide` or `feat/api-rate-limits`.
- Rebase (rather than merge) with `main` before opening a pull request to keep history linear and conflict-free.

## Commit conventions

- Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification: `type(scope): subject`.
- Use the imperative mood for subjects and keep them under 72 characters.
- Group related changes into a single commit; avoid committing generated files or build artefacts.

## Environment management

### Python toolchain

1. Ensure Python 3.12 is available locally.
2. Install dependencies with Poetry:
   ```bash
   poetry install
   ```
3. Use a Poetry shell when running commands interactively:
   ```bash
   poetry shell
   ```
4. Keep virtual environment artefacts out of the repository (Poetry handles this automatically).

### Environment variables

- Copy `.env.example` files to `.env` for the root project or any sub-projects:
  ```bash
  cp .env.example .env
  ```
- Update values as needed for local development. Never commit real secrets.

### Containerised services

- Use Docker Compose to run the full development stack when integration services are required:
  ```bash
  docker compose up -d --build
  docker compose ps
  ```
- Stop services with `docker compose down` (add `-v` to remove volumes when you want a clean slate).

## Quality gates

Run the following commands locally before pushing to ensure CI passes:

```bash
# Format and lint (Black + Ruff)
poetry run ruff check .
poetry run black .

# Static typing
poetry run mypy

# Unit tests
poetry run pytest
```

Pre-commit hooks automate these steps. Enable them once per machine:

```bash
poetry run pre-commit install
```

## Documentation expectations

- Project README files must link to the shared [documentation template](docs/template.md) and follow its structure.
- Store diagrams and other supporting media under [`docs/diagrams`](docs/diagrams/README.md); commit both source and rendered versions.
- Update documentation alongside code changes when behaviour, dependencies, or operations change.

## Pull request workflow

1. Ensure your branch is rebased on `main` and all quality gates pass.
2. Update the changelog or release notes if applicable.
3. Push your branch and open a pull request that clearly explains the change, testing performed, and any follow-up tasks.
4. Request review from the appropriate code owners or subject matter experts.
5. Address feedback with additional commits (squash if necessary) and re-run validations.
6. Once approved, merge via the PR UI; avoid direct pushes to `main`.

By following this process we keep the repository reliable, well-documented, and easy for new contributors to navigate. Thank you for contributing!
