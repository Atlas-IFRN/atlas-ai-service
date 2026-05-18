from __future__ import annotations

import json
import logging
import os
import re
from typing import Dict, List, Optional

import httpx

from app.profiles import ProjectProfile
from app.schemas import AnalysisResult, Check
from app.services.analyzers import build_profile_checks
from app.services.repo import PackedRepository

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "600"))

MAX_CODE_CHARS = int(os.getenv("MAX_CODE_CHARS", "60000"))
MAX_TREE_CHARS = 4000

DEFAULT_CRITERION_WEIGHT = 10
MIN_FINAL_SCORE = 0
MAX_FINAL_SCORE = 100


PROMPT_TEMPLATE = """Você é um avaliador técnico RIGOROSO. Decide, com base em EVIDÊNCIAS no código, se o projeto cumpre o desafio.

============================================================
1. DESAFIO
============================================================
Tema/assunto central: {theme}
Descrição:
{challenge_description}

Stack esperada (perfil "{profile_name}"): {canonical_language}
Tag bruta enviada pelo usuário (apenas rótulo): {declared_language}
Aliases que significam a MESMA stack: {aliases_list}

============================================================
2. ANÁLISE ESTÁTICA  ←  FATOS extraídos pelo parser AST
============================================================
{static_analysis}

============================================================
3. CRITÉRIOS A AVALIAR  ←  use EXATAMENTE estes ids
============================================================
{criteria_list}

Para CADA critério acima, decida:
  • present = true ou false (existe no código sim ou não? sem meio termo)
  • evidence = frase curta citando arquivo/classe/função que prova a decisão
                (se ausente, descreva o que foi procurado e não foi encontrado)

NÃO crie critérios novos. NÃO renomeie. Responda na MESMA ORDEM e com os MESMOS ids.

============================================================
4. CÓDIGO DO REPOSITÓRIO (filtrado pelo perfil "{profile_name}")
============================================================
{code_content}

============================================================
5. SAÍDA — APENAS JSON VÁLIDO, sem markdown, sem comentários
============================================================
Não retorne `score` (o servidor calcula). Apenas:
{{
  "feedback": "<2-3 frases: o que o projeto faz, o que falta, com nomes de arquivos>",
  "criterion_checks": [
    {{"id": "<id exato>", "present": true|false, "evidence": "<arquivo:função ou \\"não encontrei X em Y\\">"}},
    ...
  ],
  "strengths": ["<frase curta citando arquivo/classe real do projeto>", ...],
  "improvements": ["<sugestão acionável aplicada ao projeto>", ...]
}}
"""


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def _format_criteria(criteria: List[str], weights: Optional[Dict[str, int]]) -> str:
    if not criteria:
        return "(sem critérios — avalie apenas os checks do perfil)"
    lines = []
    for c in criteria:
        w = (weights or {}).get(c, DEFAULT_CRITERION_WEIGHT)
        lines.append(f"  - id: {c!r}   peso_se_ausente: {w}")
    return "\n".join(lines)


def _format_aliases(profile: ProjectProfile) -> str:
    return ", ".join(profile.aliases) if profile.aliases else "(nenhum)"


def _truncate(text: str, limit: int, suffix: str) -> str:
    if not text:
        return "(vazio)"
    return text if len(text) <= limit else text[:limit] + suffix


def build_prompt(
    *,
    profile: ProjectProfile,
    theme: Optional[str],
    challenge_description: str,
    declared_language: str,
    criteria: List[str],
    criteria_weights: Optional[Dict[str, int]],
    packed_code: str,
    static_analysis: Optional[str],
) -> str:
    return PROMPT_TEMPLATE.format(
        theme=theme or "(não informado — extraia da descrição)",
        challenge_description=challenge_description or "(sem descrição fornecida)",
        profile_name=profile.name,
        canonical_language=profile.canonical_language,
        declared_language=declared_language or "(não informada)",
        aliases_list=_format_aliases(profile),
        static_analysis=static_analysis or "(perfil sem analisador estático)",
        criteria_list=_format_criteria(criteria, criteria_weights),
        code_content=_truncate(packed_code, MAX_CODE_CHARS, "\n\n(...código truncado...)"),
    )


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
    logger.info("Calling Ollama model=%s ctx=%s prompt_chars=%s", OLLAMA_MODEL, OLLAMA_NUM_CTX, len(prompt))
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
    criteria: List[str],
    weights: Optional[Dict[str, int]],
) -> List[Check]:
    """Builds Checks from the LLM's `criterion_checks` array, locked to the input criteria."""
    by_id: Dict[str, dict] = {}
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, dict) and item.get("id"):
                by_id[str(item["id"]).strip()] = item

    extras = [k for k in by_id.keys() if k not in criteria]
    if extras:
        logger.warning("LLM produziu critérios fora da lista; descartando: %s", extras)

    checks: List[Check] = []
    for c in criteria:
        w = int((weights or {}).get(c, DEFAULT_CRITERION_WEIGHT))
        item = by_id.get(c, {})
        present = bool(item.get("present", False))
        evidence = str(item.get("evidence", "")).strip() or ("encontrado" if present else "não encontrado no código")
        checks.append(Check(id=c, label=c, kind="criterion", weight=w, present=present, evidence=evidence))
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

    prompt = build_prompt(
        profile=packed.profile,
        theme=theme,
        challenge_description=challenge_description,
        declared_language=declared_language,
        criteria=criteria,
        criteria_weights=criteria_weights,
        packed_code=packed.packed_code,
        static_analysis=packed.static_analysis,
    )

    raw = await call_ollama(prompt)
    data = _extract_json(raw)

    criterion_checks = _build_criterion_checks(
        data.get("criterion_checks"),
        criteria=criteria,
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
