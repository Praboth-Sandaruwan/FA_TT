# syntax=docker/dockerfile:1.7
FROM python:3.12-slim as base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.3

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        gcc \
        libpq-dev \
        git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"
RUN poetry config virtualenvs.create false

WORKDIR /app

# Copy only dependency definitions first for layer caching
COPY apps/app1/pyproject.toml /app/pyproject.toml

RUN poetry install --no-interaction --no-ansi

# Copy the rest of the app source
COPY apps/app1 /app

EXPOSE 8000

CMD ["bash", "-lc", "poetry install --no-interaction --no-ansi && poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
