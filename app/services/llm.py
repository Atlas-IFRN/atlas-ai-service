from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

import httpx

from app.profiles import ProjectProfile
from app.schemas import AnalysisResult, Check
from app.services.analyzers import build_profile_checks
from app.services.repo import PackedRepository

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "65536"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "600"))

MAX_CODE_CHARS = int(os.getenv("MAX_CODE_CHARS", "200000"))
MAX_TREE_CHARS = int(os.getenv("MAX_TREE_CHARS", "12000"))
MAX_STATIC_ANALYSIS_CHARS = int(os.getenv("MAX_STATIC_ANALYSIS_CHARS", "20000"))

# Orçamento de tokens reservado para a resposta JSON (Ollama conta input+output no num_ctx).
RESPONSE_TOKEN_BUDGET = int(os.getenv("RESPONSE_TOKEN_BUDGET", "2000"))
# Conservador de propósito: sub-estima chars/token para SUPER-estimar tokens
# e sub-alocar chars de código, garantindo folga contra truncamento silencioso.
PROMPT_CHARS_PER_TOKEN = float(os.getenv("PROMPT_CHARS_PER_TOKEN", "2.8"))

DEFAULT_CRITERION_WEIGHT = 10
MIN_FINAL_SCORE = 0
MAX_FINAL_SCORE = 100


PROMPT_TEMPLATE = """Você é um avaliador técnico RIGOROSO e SINCERO. Decide, com base em EVIDÊNCIAS CITÁVEIS no código, se o projeto cumpre o desafio e seus critérios. Sua reputação depende de NUNCA inventar evidência — nem para afirmar presença, nem para afirmar ausência.

1. DESAFIO
Tema/assunto central: {theme}
Descrição:
{challenge_description}

Stack esperada (perfil "{profile_name}"): {canonical_language}
Tag bruta enviada pelo usuário (apenas rótulo): {declared_language}
Aliases que significam a MESMA stack: {aliases_list}

2. ANÁLISE ESTÁTICA  ←  FATOS extraídos pelo parser AST
{static_analysis}

3. CRITÉRIOS A AVALIAR  ←  use EXATAMENTE estes ids
{criteria_list}

Para CADA critério acima, decida:
  • present = true ou false (o critério está ATENDIDO no projeto?) - baseie-se apenas em evidências CITÁVEIS no código, NUNCA invente. Se não encontrar evidência clara de presença, assuma ausência (present=false).
  • evidence = frase curta CITANDO arquivo:classe/função/campo/import específico
               que prova a decisão. Nunca uma frase genérica. Seja específico, varra realmente o código para encontrar evidências concretas. Se present=true, a evidence deve ser uma prova concreta de presença. Se present=false, a evidence deve listar o que foi varrido para chegar à conclusão de ausência (ex: "varri X arquivos e não encontrei Y").

REGRAS DE EVIDÊNCIA — leia ANTES de marcar present=true:
  1. LITERAL É LITERAL. Se o critério usa aspas, "exatamente", "com nome", "chamada/o" → procure a STRING idêntica no código. Similaridade NÃO conta.
  2. CASE-SENSITIVE quando o critério especifica um caso. 'Wallet' ≠ 'wallet' ≠ 'WALLET'. Se o caso não bate, present=false.
  3. NOME DE CLASSE/FUNÇÃO/ATRIBUTO ≠ NOME DE TABELA/COLUNA/ENDPOINT/ARQUIVO. Não infira um do outro.
     - Tabela do banco: só conta se vier de `class Meta: db_table = "X"`, de uma migration (`CREATE TABLE X`, `RenameModel`, `db_table=`), ou de SQL/DDL explícito. Em Django, `class Wallet(models.Model)` no app `book` cria a tabela `book_wallet` (minúsculo, com prefixo) — NÃO 'Wallet'.
     - Coluna do banco: só conta se vier de `db_column="X"` ou da migration. Nome do atributo Python é pista, não prova.
     - Rota/endpoint: só conta se aparecer literal no urls.py / decorator / router.
     - Nome de arquivo: só conta se o arquivo existir com aquele nome exato.
  4. INFERÊNCIA POR SINÔNIMO É PROIBIDA. "Tem classe Carteira → atende critério de Wallet" = ERRADO. present=false.
  5. NA DÚVIDA → present=false. É melhor errar para o lado da ausência do que inventar uma presença.
  6. A evidence DEVE conter a string literal que você encontrou. Se você não consegue citar a string exata no código, present=false.

NÃO crie critérios novos. NÃO renomeie. Responda na MESMA ORDEM e com os MESMOS ids
(o id é o slug; o label é só descritivo).

4. FORMATO DE SAÍDA — APENAS JSON VÁLIDO, sem markdown, sem comentários
Não retorne `score` (o servidor calcula). Apenas:
{{
  "feedback": "<2-3 frases: o que o projeto faz, o que falta, com nomes de arquivos>",
  "criterion_checks": [
    {{
      "id": "<id exato listado em 3>",
      "present": true|false,
      "evidence": "<para presença: cite arquivo:linha + a STRING LITERAL encontrada no código (ex: \"book/migrations/0001_initial.py: db_table='Wallet'\"). Se o critério pede um nome literal e você só viu nome de classe/atributo Python (não db_table/migration/DDL), NÃO marque presente. Para ausência: liste o que foi VARRIDO e o resultado (ex: \"varri models.py e migrations/*.py, nenhum db_table='Wallet' encontrado\"). Se não foi varrido nada, não invente.>"
    }},
    ...
  ],
  "strengths": ["<frase curta citando arquivo/classe real do projeto>", ...],
  "improvements": ["<sugestão acionável aplicada ao projeto real>", ...]
}}

5. CÓDIGO DO REPOSITÓRIO (filtrado pelo perfil "{profile_name}")
{code_content}
"""


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """'Tem que guardar dinheiro do usuário!' → 'tem-que-guardar-dinheiro-do-usuario'."""
    normalized = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug or "criterion"


def build_criterion_map(criteria: List[str]) -> List[Tuple[str, str]]:
    """Returns [(slug, original_label), ...] with unique slugs (suffix on collision)."""
    used: set[str] = set()
    out: List[Tuple[str, str]] = []
    for label in criteria:
        base = _slugify(label)
        slug = base
        i = 2
        while slug in used:
            slug = f"{base}-{i}"
            i += 1
        used.add(slug)
        out.append((slug, label))
    return out


def _format_criteria(criteria_map: List[Tuple[str, str]], weights: Optional[Dict[str, int]]) -> str:
    if not criteria_map:
        return "(sem critérios — avalie apenas os checks do perfil)"
    lines = []
    for slug, label in criteria_map:
        w = (weights or {}).get(label, DEFAULT_CRITERION_WEIGHT)
        lines.append(f"  - id: {slug!r}\n    label: {label!r}\n    peso_se_ausente: {w}")
    return "\n".join(lines)


def _format_aliases(profile: ProjectProfile) -> str:
    return ", ".join(profile.aliases) if profile.aliases else "(nenhum)"


def _truncate(text: str, limit: int, suffix: str) -> str:
    if not text:
        return "(vazio)"
    if limit <= 0:
        return suffix.lstrip()
    return text if len(text) <= limit else text[:limit] + suffix


def _estimate_tokens(text: str) -> int:
    """Conservative token estimate (over-estimates tokens to avoid overflow)."""
    if not text:
        return 0
    return int(len(text) / PROMPT_CHARS_PER_TOKEN) + 1


def build_prompt(
    *,
    profile: ProjectProfile,
    theme: Optional[str],
    challenge_description: str,
    declared_language: str,
    criteria_map: List[Tuple[str, str]],
    criteria_weights: Optional[Dict[str, int]],
    packed_code: str,
    static_analysis: Optional[str],
) -> str:
    static_text = static_analysis or "(perfil sem analisador estático)"
    static_text = _truncate(static_text, MAX_STATIC_ANALYSIS_CHARS,
                            "\n(...análise estática truncada...)")

    template_kwargs = dict(
        theme=theme or "(não informado — extraia da descrição)",
        challenge_description=challenge_description or "(sem descrição fornecida)",
        profile_name=profile.name,
        canonical_language=profile.canonical_language,
        declared_language=declared_language or "(não informada)",
        aliases_list=_format_aliases(profile),
        static_analysis=static_text,
        criteria_list=_format_criteria(criteria_map, criteria_weights),
    )

    # Mede o "esqueleto" do prompt (tudo, menos o código) para descobrir
    # quantos chars de código cabem no OLLAMA_NUM_CTX sem truncar nada.
    skeleton = PROMPT_TEMPLATE.format(code_content="", **template_kwargs)
    skeleton_tokens = _estimate_tokens(skeleton)

    available_tokens = OLLAMA_NUM_CTX - skeleton_tokens - RESPONSE_TOKEN_BUDGET
    if available_tokens <= 0:
        logger.error(
            "Esqueleto do prompt (~%s tokens) + reserva de resposta (%s tokens) "
            "já excede OLLAMA_NUM_CTX=%s. Reduza CRITÉRIOS/ANÁLISE ESTÁTICA "
            "ou aumente OLLAMA_NUM_CTX. Código será omitido para não estourar.",
            skeleton_tokens, RESPONSE_TOKEN_BUDGET, OLLAMA_NUM_CTX,
        )
        dynamic_code_chars = 0
    else:
        dynamic_code_chars = int(available_tokens * PROMPT_CHARS_PER_TOKEN)

    effective_code_limit = min(MAX_CODE_CHARS, dynamic_code_chars)
    code_text = _truncate(
        packed_code, effective_code_limit,
        "\n\n(...código truncado para caber no contexto...)",
    )

    code_truncated = len(packed_code) > effective_code_limit
    static_truncated = bool(static_analysis) and len(static_analysis) > MAX_STATIC_ANALYSIS_CHARS
    sent_code_chars = min(len(packed_code), effective_code_limit)
    sent_static_chars = min(len(static_analysis or ""), MAX_STATIC_ANALYSIS_CHARS)

    if code_truncated:
        lost = len(packed_code) - effective_code_limit
        pct = (effective_code_limit / len(packed_code) * 100) if packed_code else 100
        logger.warning(
            "[PROMPT CORTADO] código: %s/%s chars enviados (%.1f%%) — perda de %s chars. "
            "Limite efetivo = min(MAX_CODE_CHARS=%s, budget_ctx=%s chars ≈ %s tokens). "
            "Aumente OLLAMA_NUM_CTX para enviar mais contexto sem cortar.",
            effective_code_limit, len(packed_code), pct, lost,
            MAX_CODE_CHARS, dynamic_code_chars, available_tokens,
        )
    else:
        logger.info(
            "[PROMPT INTEIRO] código: %s/%s chars enviados (100%%) — nada foi cortado.",
            len(packed_code), len(packed_code),
        )

    if static_truncated:
        logger.warning(
            "[PROMPT CORTADO] análise estática: %s/%s chars enviados — perda de %s chars.",
            MAX_STATIC_ANALYSIS_CHARS, len(static_analysis),
            len(static_analysis) - MAX_STATIC_ANALYSIS_CHARS,
        )

    final_prompt = PROMPT_TEMPLATE.format(code_content=code_text, **template_kwargs)

    # Resumo final em UMA linha — fácil de grepar: "[PROMPT INTEIRO]" ou "[PROMPT CORTADO]".
    status = "CORTADO" if (code_truncated or static_truncated) else "INTEIRO"
    logger.info(
        "[PROMPT %s] total=%s chars (~%s tokens) | esqueleto=%s tokens | "
        "código=%s/%s chars | análise=%s/%s chars | ctx=%s | reserva_resposta=%s",
        status, len(final_prompt), _estimate_tokens(final_prompt), skeleton_tokens,
        sent_code_chars, len(packed_code),
        sent_static_chars, len(static_analysis or ""),
        OLLAMA_NUM_CTX, RESPONSE_TOKEN_BUDGET,
    )

    return final_prompt


# ---------------------------------------------------------------------------
# Ollama call + JSON parsing
# ---------------------------------------------------------------------------

async def call_ollama(prompt: str) -> str:
    url = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": OLLAMA_TEMPERATURE, "num_ctx": OLLAMA_NUM_CTX},
    }
    estimated_tokens = _estimate_tokens(prompt)
    logger.info(
        "Calling Ollama model=%s ctx=%s prompt_chars=%s prompt_tokens~%s response_reserve=%s",
        OLLAMA_MODEL, OLLAMA_NUM_CTX, len(prompt), estimated_tokens, RESPONSE_TOKEN_BUDGET,
    )
    # Sentinela: build_prompt já dimensionou o código para caber. Se ainda assim
    # exceder, é bug no estimador ou esqueleto cresceu — alerta para investigar.
    if estimated_tokens > OLLAMA_NUM_CTX - RESPONSE_TOKEN_BUDGET:
        logger.error(
            "INVARIANTE QUEBRADO: prompt (~%s tokens) excede OLLAMA_NUM_CTX=%s - reserva=%s "
            "mesmo após dimensionamento dinâmico. Ollama pode truncar o FIM silenciosamente. "
            "Ajuste PROMPT_CHARS_PER_TOKEN para um valor menor (mais conservador).",
            estimated_tokens, OLLAMA_NUM_CTX, RESPONSE_TOKEN_BUDGET,
        )
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"Ollama {resp.status_code} at {url}: {resp.text}")
        return resp.json().get("response", "")


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("Resposta do LLM vazia.")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError(f"Resposta do LLM não contém JSON. Bruto: {text!r}")
        candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido ({exc.msg} char {exc.pos}). Bruto: {candidate!r}") from exc


# ---------------------------------------------------------------------------
# Score calculation
# ---------------------------------------------------------------------------

def compute_score(checks: List[Check]) -> int:
    """Score = max(0, 100 − Σ weight of every check whose `present` is False)."""
    penalty = sum(c.weight for c in checks if not c.present)
    return max(MIN_FINAL_SCORE, min(MAX_FINAL_SCORE, MAX_FINAL_SCORE - penalty))


def _build_criterion_checks(
    raw_list: list,
    criteria_map: List[Tuple[str, str]],
    weights: Optional[Dict[str, int]],
) -> List[Check]:
    """Builds Checks from the LLM `criterion_checks` array.

    Looks the LLM item up by either the slug (preferred) or the original label
    (fallback, in case the model echoes the label). Anything else is dropped.
    """
    by_key: Dict[str, dict] = {}
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, dict) and item.get("id"):
                by_key[str(item["id"]).strip()] = item

    valid_keys = {slug for slug, _ in criteria_map} | {label for _, label in criteria_map}
    extras = [k for k in by_key.keys() if k not in valid_keys]
    if extras:
        logger.warning("LLM produziu critérios fora da lista; descartando: %s", extras)

    checks: List[Check] = []
    for slug, label in criteria_map:
        w = int((weights or {}).get(label, DEFAULT_CRITERION_WEIGHT))
        item = by_key.get(slug) or by_key.get(label) or {}
        present = bool(item.get("present", False))
        evidence = str(item.get("evidence", "")).strip() or ("encontrado" if present else "não encontrado no código")
        checks.append(Check(id=slug, label=label, kind="criterion", weight=w, present=present, evidence=evidence))
    return checks


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------

async def evaluate(
    *,
    user_id: str,
    challenge_id: str,
    challenge_description: str,
    theme: Optional[str],
    declared_language: str,
    criteria: List[str],
    criteria_weights: Optional[Dict[str, int]],
    packed: PackedRepository,
) -> AnalysisResult:
    profile_checks = build_profile_checks(packed.profile.name, packed.django_analysis)
    criteria_map = build_criterion_map(criteria)

    prompt = build_prompt(
        profile=packed.profile,
        theme=theme,
        challenge_description=challenge_description,
        declared_language=declared_language,
        criteria_map=criteria_map,
        criteria_weights=criteria_weights,
        packed_code=packed.packed_code,
        static_analysis=packed.static_analysis,
    )
    
    print(len(prompt))

    raw = await call_ollama(prompt)
    data = _extract_json(raw)

    criterion_checks = _build_criterion_checks(
        data.get("criterion_checks"),
        criteria_map=criteria_map,
        weights=criteria_weights,
    )
    all_checks = profile_checks + criterion_checks
    score = compute_score(all_checks)

    return AnalysisResult(
        user_id=user_id,
        challenge_id=challenge_id,
        score=score,
        feedback=str(data.get("feedback", "")).strip(),
        checks=all_checks,
        strengths=[str(s).strip() for s in (data.get("strengths") or []) if str(s).strip()],
        improvements=[str(s).strip() for s in (data.get("improvements") or []) if str(s).strip()],
        profile=packed.profile.name,
    )
