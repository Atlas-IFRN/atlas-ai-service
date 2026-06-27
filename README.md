# Atlas AI Service 🤖

Serviço HTTP que avalia repositórios GitHub contra critérios livres usando um **LLM local (Ollama)**. Recebe um link de repositório + lista de critérios com pesos, clona, empacota o código por perfil de stack (DRF, React, React Native), submete ao LLM e devolve um scorecard `0–100` com evidências citáveis.

## Stack

- Python 3.12 · FastAPI · Uvicorn
- Ollama (LLM local) · repomix
- Docker

## Como funciona

1. Clona o repo (`git clone --depth 1`) em pasta temporária
2. Detecta o perfil da stack (`django` → `drf`, `react`, `react-native`)
3. Filtra arquivos relevantes via **repomix** (ignora `node_modules/`, `__pycache__/`, builds)
4. Roda analisador estático por perfil (AST para Django, estrutura de componentes para React)
5. Monta prompt adversarial com regras gerais (R1–R6) + regras específicas do perfil
6. Chama Ollama (`/api/generate` com `format: "json"`) e valida resposta
7. Retorna `AnalysisResult` com `score`, `feedback`, `checks`, `strengths`, `improvements`

## Score

- **Profile checks (20%)** — checks factuais derivados do AST
- **Critérios do usuário (80%)** — avaliados pelo LLM com base no código

## Executando localmente

Este serviço é orquestrado junto com todos os outros pelo repositório central de infraestrutura:

> **[Atlas-IFRN/atlas-infra](https://github.com/Atlas-IFRN/atlas-infra)** — Docker Compose canônico, Nginx, scripts de deploy e backup.

Para rodar isolado em modo dev (requer Ollama rodando localmente):

```bash
# Pré-requisito: Ollama com modelo baixado
ollama pull qwen2.5-coder:3b

# Setup
cp .env.example .env
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Rodar
uvicorn app.main:app --reload --port 8003
```

`.env` mínimo:
```ini
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:3b
```

## Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET`  | `/health` | Health check |
| `GET`  | `/profiles` | Lista perfis de stack suportados |
| `POST` | `/detect` | Clona e detecta o perfil sem rodar análise |
| `POST` | `/analyze` | Pipeline completo → scorecard |

**Exemplo de request para `/analyze`:**
```json
{
  "user_id": "u1",
  "challenge_id": "c1",
  "github_repo_url": "https://github.com/usuario/projeto",
  "language": "django",
  "theme": "gerenciamento financeiro",
  "challenge_description": "Backend para gerenciamento financeiro",
  "criteria": {
    "Deve seguir o tema gerenciamento financeiro": 10,
    "Deve haver uma tabela Wallet no banco": 10,
    "Boas práticas Two Scoops": 10
  }
}
```

## Estrutura

```
app/
├── main.py             # endpoints FastAPI
├── schemas.py          # AnalyzePayload, AnalysisResult, Check
├── profiles/           # base.py, django.py, react.py, registry.py
└── services/
    ├── repo.py         # clone + repomix + análise estática
    ├── llm.py          # PROMPT_TEMPLATE, build_prompt, evaluate, compute_score
    └── analyzers/      # django_analyzer.py, checks.py
```

## Adicionando novo perfil de stack

1. Crie `app/profiles/<stack>.py` seguindo o padrão de `django.py`
2. Preencha `evaluation_hints` com as regras específicas
3. Adicione ao `ALL_PROFILES` em `app/profiles/registry.py`

## Variáveis opcionais

| Variável | Default | Descrição |
|----------|---------|-----------|
| `OLLAMA_NUM_CTX` | `65536` | Tamanho da janela de contexto |
| `OLLAMA_TEMPERATURE` | `0.2` | Criatividade do modelo |
| `OLLAMA_TIMEOUT` | `600` | Timeout em segundos |
| `MAX_CODE_CHARS` | `200000` | Limite de chars de código no prompt |

## Limitações conhecidas

- Modelos pequenos (3b) podem alucinar — para produção recomenda-se `qwen2.5-coder:14b` ou superior
- Não há fila: requisições longas ficam pendentes na conexão HTTP até completar
- `repomix` deve estar no `requirements.txt` se for empacotar para outra máquina

