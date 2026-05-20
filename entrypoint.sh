#!/bin/bash
set -e

echo "==> Aguardando Ollama em ${OLLAMA_HOST:-http://ollama:11434}..."
until curl -fsS "${OLLAMA_HOST:-http://ollama:11434}/api/tags" >/dev/null 2>&1; do
  sleep 2
done
echo "==> Ollama disponível."

echo "==> Starting FastAPI server on :8003..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8003
