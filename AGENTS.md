# Agent guide

## Verification before delivery

Before committing, pushing, or opening/updating a pull request, run the same
checks as CI from the repository root:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run alembic upgrade head
uv run alembic check
git diff --check
```

Do not describe work as ready when any required check has not run or has
failed. Report the commands run and their outcomes in the handoff or pull
request description.

## Staging and secrets

Before a commit or push, inspect `git status --short` and the staged diff.
Stage only files required for the requested change. Never stage `.env`, private
keys, API tokens, connection strings, or ignored local wrappers such as
`scripts/*.local.sh`.

Use redacted values in issue, chat, and pull-request descriptions. Keep
production secrets in Railway variables, not repository files.

## Pull requests

Use a focused commit and pull request title. Include a short summary of
behavioral changes and the verification results. Do not create, update, or
merge a pull request unless the user has asked for it.
