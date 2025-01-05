# Crypto Assets Manager

A FastAPI-based cryptocurrency assets management tool that helps you manage and track your crypto investments across different exchanges

## Requirements

- Python 3.12+
- uv (Python package installer and virtual environment management tool)
- MongoDB

## Installation

1. Clone the repository
```bash
git clone https://github.com/ZerolBozi/CryptoAssetsManager.git
cd CryptoAssetsManager
```

2. Create and activate virtual environment using uv
```bash
uv venv
source .venv/bin/activate  # For Unix/MacOS
# OR
.venv\Scripts\activate     # For Windows
```

3. Install dependencies using the pyproject.toml file:
```bash
uv pip install .
```

## Configuration

1. Copy the example environment file and rename it to `.env`:
```bash
cp .env.example .env
```

2. Open `.env` file and add your exchange API credentials:
```plaintext
# Exchange API Keys
EXCHANGE_API_KEY=your_api_key_here
EXCHANGE_SECRET_KEY=your_secret_key_here
```

To start the service, run:
```bash
python run.py
```
