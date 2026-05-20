# atlas-ia-service

Serviço HTTP que avalia repositórios GitHub contra critérios livres usando um LLM local (Ollama). Recebe um link de repo + uma lista de critérios com pesos, clona, empacota o código relevante por perfil de stack (DRF, React ou React Native), submete a um LLM, e devolve um scorecard `0–100` com evidências citáveis.

## O que faz

Dado um payload assim:

```json
{
  "user_id": "u1",
  "challenge_id": "c1",
  "github_repo_url": "https://github.com/usuario/projeto",
  "language": "django",
  "theme": "gerenciamento financeiro",
  "challenge_description": "Faça um backend para gerenciamento financeiro",
  "criteria": {
    "Deve seguir o tema gerenciamento financeiro": 10,
    "Deve haver uma tabela 'Wallet' no banco": 10,
    "Boas práticas Two Scoops": 10
  }
}
```

O serviço:

1. Clona o repo (`git clone --depth 1`) em uma pasta temporária.
2. Resolve o perfil declarado (`language: "django"` → profile `drf`) e filtra os arquivos relevantes via [repomix](https://github.com/yamadashy/repomix) (ignora `node_modules/`, `__pycache__/`, builds, etc.).
3. Roda um analisador estático específico do perfil (no caso de Django, varre models/serializers/views/urls com AST para gerar checks factuais).
4. Monta um prompt adversarial com regras gerais (R1–R6) + regras específicas do perfil (D1–D4 pra DRF, R1–R8 pra React, RN1–RN10 pra React Native).
5. Chama o Ollama (`/api/generate` com `format: "json"`), valida o JSON, e devolve um `AnalysisResult`.

## Como funciona o score

Saída `0–100` dividida entre duas famílias:

- **Profile checks (20%)** — checks factuais derivados do AST (ex: "tem `manage.py`?", "tem `Serializer`?"). Pesos relativos dentro da família.
- **Critérios do usuário (80%)** — marcados pelo LLM com base no código + regras do prompt. Pesos relativos dentro da família.

Se uma família está vazia, a outra absorve 100%.

## Pré-requisitos

- Python 3.12+
- `git` no PATH (pra clonar)
- [Ollama](https://ollama.com) rodando local com pelo menos um modelo. Default: `qwen2.5-coder:3b`.
  ```bash
  ollama pull qwen2.5-coder:3b
  ```
- `repomix` (package Python usado pra empacotar o código). Se não tiver, instale com `pip install repomix`.

## Setup

```bash
git clone <este-repo>
cd atlas-ai-service

python -m venv venv
source venv/bin/activate    # ou .\venv\Scripts\activate no Windows
pip install -r requirements.txt
```

Crie um `.env` na raiz:

```ini
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:3b
```

Outras vars opcionais (com defaults sensatos em `app/services/llm.py`):

| Var | Default | O que faz |
|---|---|---|
| `OLLAMA_NUM_CTX` | `65536` | Tamanho da janela de contexto (input + output) |
| `OLLAMA_TEMPERATURE` | `0.2` | Mais alto = mais variação |
| `OLLAMA_TIMEOUT` | `600` | Segundos antes de desistir da chamada |
| `MAX_CODE_CHARS` | `200000` | Limite duro de chars de código no prompt |
| `RESPONSE_TOKEN_BUDGET` | `2000` | Tokens reservados pra resposta JSON |

## Rodando

Local:

```bash
uvicorn app.main:app --reload --port 8000
```

Docker:

```bash
docker build -t atlas-ia-service .
docker run --rm -p 8000:8000 --env-file .env atlas-ia-service
```

## Endpoints

### `GET /health`

```json
{ "status": "ok", "service": "atlas-ia-service" }
```

### `GET /profiles`

Lista os perfis suportados.

```json
[
  { "name": "drf", "canonical_language": "Django REST Framework (DRF)", "aliases": ["drf", "django", "..."] },
  { "name": "react-native", "canonical_language": "React Native — TypeScript ou JavaScript (Expo opcional)", "aliases": ["..."] },
  { "name": "react", "canonical_language": "React (web) — TypeScript ou JavaScript", "aliases": ["..."] }
]
```

### `POST /detect`

Clona o repo e tenta identificar o profile sem rodar análise. Útil pra debug.

```json
{ "github_repo_url": "https://github.com/usuario/projeto" }
```

Retorna `detected_profile`, contagem de arquivos e amostra de paths.

### `POST /analyze`

Pipeline completo: clone → empacotamento → análise estática → LLM → scorecard. Resposta inline (não usa fila).

**Request:**

```json
{
  "user_id": "u1",
  "challenge_id": "c1",
  "github_repo_url": "https://github.com/usuario/projeto",
  "language": "django",
  "theme": "gerenciamento financeiro",
  "challenge_description": "faça um backend para gerenciamento financeiro",
  "criteria": {
    "Deve seguir o tema gerenciamento financeiro": 10,
    "Deve haver uma tabela 'Wallet' no banco": 10
  }
}
```

**Response (`AnalysisResult`):**

```json
{
  "user_id": "u1",
  "challenge_id": "c1",
  "score": 47,
  "feedback": "O projeto modela um clube de leitura com Book/Review/Reservation em models.py. Não há entidades do tema financeiro (Transaction, Account, etc.) — o tema não é atendido.",
  "checks": [
    {
      "id": "has_manage_py",
      "label": "Projeto é Django (existe manage.py)",
      "kind": "profile",
      "weight": 15,
      "present": true,
      "evidence": "manage.py encontrado"
    },
    {
      "id": "1",
      "label": "Deve seguir o tema gerenciamento financeiro",
      "kind": "criterion",
      "weight": 10,
      "present": false,
      "evidence": "models.py contém Book/Review/Reservation — nenhuma entidade financeira."
    }
  ],
  "strengths": ["..."],
  "improvements": ["..."],
  "profile": "drf"
}
```

Validações automáticas:
- `language` deve resolver pra um profile suportado (caso contrário 422 com a lista válida).
- `criteria` é `{label: peso}`. Peso é int 0–100. Labels vazios são silenciosamente removidos.
- Ordem do dict é preservada e usada como ordem dos `id`s (`"1"`, `"2"`, `"3"`...).

## Estrutura

```
app/
├── main.py                      # endpoints FastAPI
├── schemas.py                   # AnalyzePayload, AnalysisResult, Check, ...
├── profiles/
│   ├── base.py                  # dataclass ProjectProfile
│   ├── django.py                # DJANGO_PROFILE + evaluation_hints (D1–D4)
│   ├── react.py                 # REACT_PROFILE / REACT_NATIVE_PROFILE
│   └── registry.py              # resolve_profile, detect_profile_from_tree
└── services/
    ├── repo.py                  # clone + repomix + análise estática
    ├── llm.py                   # PROMPT_TEMPLATE, build_prompt, evaluate, compute_score
    └── analyzers/
        ├── django_analyzer.py   # AST de models/serializers/views/urls
        └── checks.py            # converte análise em profile checks
```

## Como o prompt funciona

O `PROMPT_TEMPLATE` em [`app/services/llm.py`](app/services/llm.py) é dividido em:

- **Coringa** (qualquer stack): R1–R6 (tema = seção 1, tabela verdade de `present`, evidência literal, assunto do critério, blacklist de entidades genéricas, critério de tema).
- **Específico do perfil**: bloco renderizado a partir de `ProjectProfile.evaluation_hints`. DRF tem D1–D4, React tem R1–R8, React Native tem RN1–RN10.

O LLM é forçado a preencher uma **ficha de raciocínio** (campos `_assunto`, `_polaridade_criterio`, `_onde_busquei`, `_o_que_achei`, `_polaridade_evidencia`, `_aplicando_R2`, `_se_for_criterio_de_tema`) antes de decidir `present`/`evidence`. O parser do servidor só lê `id`/`present`/`evidence` — os campos `_*` servem só pra forçar o modelo a pensar.

## Adicionando um novo perfil

1. Crie `app/profiles/<stack>.py` com um `ProjectProfile(...)` (siga o padrão de `django.py`).
2. Preencha `evaluation_hints` com as regras específicas da stack.
3. Adicione ao `ALL_PROFILES` em `app/profiles/registry.py`.
4. (Opcional) Crie um analisador estático em `app/services/analyzers/` se for útil.

Nenhuma mudança em `llm.py` é necessária — o bloco do profile é injetado automaticamente no prompt.

## Limitações conhecidas

- `repomix` precisa estar instalado mas não está em `requirements.txt` — adicione lá se for empacotar o serviço pra outra máquina.
- Modelos pequenos (qwen2.5-coder:3b) ocasionalmente alucinam. As regras do prompt mitigam mas não eliminam — para produção, considere um modelo maior (qwen2.5-coder:14b, llama3.1:8b-instruct).
- Não há sistema de fila: requisições longas (repo grande + LLM lento) ficam pendentes na conexão HTTP até completarem.
