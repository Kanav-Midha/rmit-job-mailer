FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install -e ".[gmail,postgres]"

RUN useradd --create-home --uid 1000 tracker && chown -R tracker:tracker /app
USER tracker

ENTRYPOINT ["python", "-m", "tracker.cli"]
CMD ["run"]
