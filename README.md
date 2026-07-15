# Atlas · AI Service 🤖

> Parte do **Projeto Atlas** — plataforma acadêmica desenvolvida para o **IFRN Campus Pau dos Ferros** como Projeto Integrador de Sistemas Distribuídos. O Atlas conecta alunos a trilhas de conhecimento e bolsas, com avaliação automática de código por IA.

Serviço HTTP que **avalia repositórios GitHub** contra critérios definidos, usando um **LLM local (Ollama)**. Recebe o link de um repositório e uma lista de critérios com pesos, clona o código, empacota-o por perfil de stack, submete ao LLM e devolve um *scorecard* `0–100` com evidências.

## O que este serviço faz

1. **Clona** o repositório (`git clone --depth 1`) em pasta temporária.
2. **Detecta o perfil** da stack (ex.: Django/DRF, React).
3. **Empacota** os arquivos relevantes com **repomix** (ignora `node_modules/`, `__pycache__/`, builds).
4. **Analisa estaticamente** por perfil (ex.: AST para Django) gerando *checks* factuais.
5. **Monta o prompt** com regras gerais + regras específicas do perfil e chama o **Ollama** (`format: json`).
6. **Retorna** `score`, `feedback`, `checks`, `strengths` e `improvements`.

### Composição do score
- **Checks de perfil (20%)** — verificações factuais derivadas da análise estática.
- **Critérios do usuário (80%)** — avaliados pelo LLM com base no código.

## Stack

- Python 3.12 · **FastAPI** · Uvicorn · Pydantic
- **Ollama** (LLM local, ex.: `qwen2.5-coder`) · **repomix** · httpx
- Docker · prometheus-fastapi-instrumentator

> Diferente dos demais serviços do Atlas (Django), este serviço é um app **FastAPI** enxuto, focado em processamento.

## Como se encaixa no Atlas

| Repositório | Responsabilidade |
|---|---|
| atlas-auth-service | Identidade: SUAP OAuth2, JWT, perfis de usuário |
| atlas-track-service | Trilhas, módulos, conteúdos, progresso e submissão de desafios |
| atlas-scholarship-service | Bolsas, candidaturas, banco de talentos e notas |
| atlas-feed-service | Feed institucional: posts, comentários, curtidas e banners |
| atlas-notification-service | Notificações (consumidor central via RabbitMQ) |
| **atlas-ai-service** | **Avaliação de repositórios GitHub por LLM local (Ollama)** |
| atlas-frontend | SPA React + TypeScript (aluno e professor) |
| atlas-infra | Docker Compose, Nginx (gateway), Postgres/Redis/RabbitMQ, deploy e backup |
| atlas-observability | Prometheus + Grafana (métricas dos serviços) |

**Quem chama:** o **tracks-service** aciona este serviço quando um aluno submete um desafio. A chamada é feita de forma **assíncrona** por um worker Celery (`POST /analyze`), mantendo a experiência do aluno responsiva enquanto a análise por IA roda em segundo plano. O container `ollama` roda junto na stack do [atlas-infra](https://github.com/Atlas-IFRN/atlas-infra).

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/ai/profiles` | Perfis de stack suportados |
| POST | `/api/ai/detect` | Detecta o perfil de um repositório |
| POST | `/api/ai/analyze` | Avalia o repositório e retorna o scorecard |

## Estrutura

```
app/main.py              FastAPI + rotas
app/schemas.py           modelos Pydantic (payloads e resultados)
app/profiles/            perfis de stack (base, django, react, registry)
app/services/repo.py     clone + empacotamento (repomix)
app/services/llm.py      integração com o Ollama
app/services/analyzers/  análise estática (django_analyzer, checks)
```

## Executando localmente

> Orquestrado pelo repositório central: **[Atlas-IFRN/atlas-infra](https://github.com/Atlas-IFRN/atlas-infra)** (que já sobe o Ollama).

Para rodar isolado (requer Ollama local):

```bash
# Pré-requisito: Ollama com o modelo baixado
ollama pull qwen2.5-coder:1.5b

cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```

## Variáveis de ambiente

Baseie seu `.env` no `.env.example`. Principais: `OLLAMA_HOST`, `OLLAMA_MODEL`, `OLLAMA_NUM_CTX`, `OLLAMA_TEMPERATURE`, `OLLAMA_TIMEOUT` e o orçamento de prompt (`MAX_CODE_CHARS`, `MAX_TREE_CHARS`, `RESPONSE_TOKEN_BUDGET`, ...).

## Observabilidade

Métricas expostas via `prometheus-fastapi-instrumentator`, coletadas pelo [atlas-observability](https://github.com/Atlas-IFRN/atlas-observability) (job `ai`, porta `8003`).

## CI/CD

Workflows de GitHub Actions em `.github/workflows/`.
