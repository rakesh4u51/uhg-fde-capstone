#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
fi

if [ -d .venv ]; then
  . .venv/bin/activate
fi

echo "Starting Mailpit..."
sudo docker compose up -d mailpit

echo "Checking Mailpit..."
sudo docker compose ps mailpit

echo "Checking PostgreSQL..."
pg_isready -h localhost -p 5432

if ss -lnt | grep -q ':8501 '; then
  echo "Port 8501 is already in use by a previous Streamlit session. Cleaning it up..."
  pkill -f "streamlit run app/streamlit_app.py" || true
  pkill -f "uvicorn.*8501" || true
fi

echo "Launching Streamlit demo UI..."
PYTHONPATH=. streamlit run app/streamlit_app.py \
  --server.address=0.0.0.0 \
  --server.port=8501 \
  --server.headless=true
