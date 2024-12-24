FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY run.py .
COPY app/ ./app/

RUN pip install --no-cache-dir uv && \
    uv venv && \
    uv pip install .

EXPOSE 5001

CMD ["python", "run.py"]