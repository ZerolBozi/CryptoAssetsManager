FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .

# Install project dependencies
RUN pip install --no-cache-dir -e .

COPY run.py .
COPY app/ ./app/
COPY .env .

RUN mkdir -p /data/db

EXPOSE 5001

CMD ["python", "run.py"]