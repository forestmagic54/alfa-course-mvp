FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir poetry==2.2.1
COPY pyproject.toml poetry.lock README.md alembic.ini ./
COPY src ./src
RUN mkdir -p src/config/demo/files && poetry config virtualenvs.create false && poetry install --only main --no-interaction --no-ansi

EXPOSE 10000
CMD ["uvicorn", "src.__main__:app", "--host", "0.0.0.0", "--port", "10000"]
