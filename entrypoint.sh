#!/bin/bash
set -e

OLLAMA_BASE="${OLLAMA_HOST:-http://ollama:11434}"
MODEL="${OLLAMA_MODEL:-qwen2.5-coder:1.5b}"
MODEL_NAME="${MODEL%%:*}"

echo "==> Aguardando Ollama em ${OLLAMA_BASE}..."
until curl -fsS "${OLLAMA_BASE}/api/tags" >/dev/null 2>&1; do
  sleep 2
done
echo "==> Ollama disponível."

echo "==> Aguardando modelo ${MODEL} ser carregado (pull pode estar em andamento)..."
until curl -fsS "${OLLAMA_BASE}/api/tags" 2>/dev/null | grep -q "${MODEL_NAME}"; do
  sleep 5
done
echo "==> Modelo ${MODEL} disponível."

echo "==> Starting FastAPI server on :8003..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8003
