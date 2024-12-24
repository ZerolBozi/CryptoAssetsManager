FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY run.py .
COPY app/ ./app/
COPY .env /app/.env

RUN pip install -e .

EXPOSE 5001

CMD ["python", "run.py"]