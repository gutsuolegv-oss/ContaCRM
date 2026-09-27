FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# INSTALL_DEV=true instalează și dependențele de test (pytest, ruff, mypy)
ARG INSTALL_DEV=false

RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN if [ "$INSTALL_DEV" = "true" ]; then pip install ".[dev]"; else pip install .; fi

COPY . .
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
