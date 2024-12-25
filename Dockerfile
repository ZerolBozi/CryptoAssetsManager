FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .

RUN pip install --no-cache-dir -e .

COPY run.py .
COPY app/ ./app/
COPY .env .
COPY symbol_exchange_mapping.json .

EXPOSE 5001

CMD ["python", "run.py"]