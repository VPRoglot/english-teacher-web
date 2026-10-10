set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

# Каждая строка рецепта — отдельная команда: без `&&` (PowerShell 5.1) и без `cd`.

test-backend *args:
    uv --directory backend run pytest {{args}}

lint-backend:
    uv --directory backend run ruff check .
    uv --directory backend run ruff format --check .
    uv --directory backend run mypy

fmt:
    uv --directory backend run ruff check --fix .
    uv --directory backend run ruff format .
