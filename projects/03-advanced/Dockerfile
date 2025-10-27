# syntax=docker/dockerfile:1.7
FROM python:3.12-slim as base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_CREATE=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /srv/app

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-interaction --no-ansi --without dev

COPY src ./src
COPY projects/03-advanced ./projects/03-advanced

RUN useradd --create-home --shell /bin/bash app
USER app

ENV PATH="/home/app/.local/bin:${PATH}"

EXPOSE 8004

CMD ["poetry", "run", "advanced-app"]
