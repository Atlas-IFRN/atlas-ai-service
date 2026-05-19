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

# Distribuição final do score entre as duas famílias de checks.
# Profile checks (análise estática do perfil) valem 20 pontos no máximo;
# critérios passados pelo usuário valem 80. Se uma das famílias estiver vazia,
# a outra absorve 100% — ver compute_score().
PROFILE_SHARE = 20
CRITERIA_SHARE = 80


PROMPT_TEMPLATE = """Você é AVALIADOR TÉCNICO. Para cada critério da seção 3, você vai PREENCHER UMA FICHA DE RACIOCÍNIO antes de decidir present. A ficha é obrigatória e seus campos `_*` são lidos. Em dúvida, present=false. NUNCA invente arquivo, classe ou linha que não apareça no código abaixo.

# 1. DESAFIO
Tema: "{theme}"
Descrição: {challenge_description}
Stack: {canonical_language} (perfil "{profile_name}", aliases: {aliases_list})

# 2. ANÁLISE ESTÁTICA (fatos AST — confiáveis)
{static_analysis}

# 3. CRITÉRIOS — id é token opaco, copie literal
{criteria_list}

# 4. REGRAS DE DECISÃO (curtas, MECÂNICAS)

R1. "tema" / "domínio" / "desafio" em QUALQUER critério SEMPRE = "{theme}" da seção 1. Nunca o tema que o código tem.

R2. TABELA VERDADE de `present` (apply via ficha, nunca pule):
       critério "deve ter X"      + X achado no código      → present=true
       critério "deve ter X"      + X ausente               → present=false
       critério "NÃO deve ter X"  + X achado no código      → present=false
       critério "NÃO deve ter X"  + X ausente               → present=true

R3. "X achado" exige UM identificador literal real do código (classe, função, campo, rota, db_table, decorador), num arquivo do bloco 6 ou da seção 2. README, nome de pasta, nome de repo NÃO contam.

R4. "X" do critério é o ASSUNTO específico que ele cita (Wallet → procure Wallet; entidades do tema → procure entidades do `{theme}`). Nunca procure outra coisa.

R5. Entidades universais (User, Auth, Session, Profile, Permission, Role, Token, Log, Notification, Tag, Comment) NÃO provam aderência ao tema — todo sistema tem.

R6. CRITÉRIO DE TEMA (gatilho: label contém "tema", "domínio", "consistente com o desafio", "seguir o desafio/tema"):
    (a) Extraia a palavra-chave do `{theme}` (ex: "financeiro", "saúde", "logística", "educação").
    (b) Extraia a palavra-chave do DOMÍNIO REAL do projeto a partir de NOMES de apps/pastas/models/rotas (ex: `apps/scholarship/` → "scholarship/bolsas"; `models/Book` → "livros"; `wallet_service/` → "financeiro").
    (c) Compare (a) vs (b). Se NÃO casam semanticamente → present=false, SEM EXCEÇÃO. Apontar arquivos como `apps/scholarship/...` num tema "financeiro" é PROVA DE MISMATCH, não prova de aderência — a própria palavra "scholarship" no path mostra que o projeto é de bolsas, não financeiro.
    (d) Se casam (a == b semanticamente), aplique R2 normalmente (verifique se há entidades do tema no código).
    (e) Atenção: existir bolsas/scholarships não conta como "financeiro" porque envolve dinheiro. Domínio é o NEGÓCIO modelado (gestão de bolsas é educacional/concessão, não financeiro de transações).

# 5. SAÍDA — APENAS JSON, sem markdown nem texto fora

`criterion_checks` precisa ter EXATAMENTE um item por id da seção 3, na mesma ordem. Cada item preenche TODOS os campos `_*` (ficha de raciocínio — força você a pensar) E os 3 campos consumidos pelo servidor (`id`, `present`, `evidence`). Sem campos vazios.

{{
  "feedback": "2-3 frases sobre o conteúdo do projeto: qual domínio o código de fato implementa (cite models/rotas reais), e o quanto isso bate ou não com \"{theme}\". Fale do projeto, NÃO do processo de avaliação (proibido: 'present', 'critério', 'evidence', 'JSON').",
  "criterion_checks": [
    {{
      "id": "<copie literal da LISTA DE IDS PERMITIDOS da seção 3>",
      "_assunto": "<o que o critério está pedindo, em 2-5 palavras (ex: 'tabela Wallet ligada a User', 'aderência ao tema X')>",
      "_polaridade_criterio": "positivo|negativo",
      "_onde_busquei": "<arquivos e seções que você varreu de fato, separados por vírgula>",
      "_o_que_achei": "<identificadores literais que respondem ao _assunto, OU descreva o que ESTÁ nos arquivos varridos sem o assunto (ex: 'apenas Book/Review/Reservation, nenhum Wallet'). NUNCA escreva só 'nenhum' — você precisa nomear o que está lá>",
      "_polaridade_evidencia": "afirmativa|negativa",
      "_aplicando_R2": "<diga em uma frase qual linha da R2 você está aplicando e qual o resultado>",
      "_se_for_criterio_de_tema": "<APENAS se R6 dispara: 'tema_pedido=<palavra-chave de {theme}> vs dominio_real=<palavra-chave extraída de nomes do código>; casam=sim|nao'. Se não for critério de tema, escreva 'n/a'>",
      "present": true,
      "evidence": "<frase única, ver REGRAS DE EVIDENCE abaixo>"
    }}
  ],
  "strengths": ["<observação de alto nível sobre o projeto — emita 2 a 4 strings concretas, NUNCA o texto literal '...'>"],
  "improvements": ["<sugestão acionável — emita 2 a 4 strings concretas, NUNCA o texto literal '...'>"]
}}

REGRAS DE evidence:
  • FRASE COMPLETA: 6-18 palavras, sujeito + verbo, termina em ponto. PROIBIDO emitir uma palavra só ("nenhum", "sim", "não", "presente") — isso é fragmento, não evidência.
  • DEVE conter (a) arquivo (`X.py` ou `X.py:linha`) E (b) identificador literal do código que responde ao `_assunto`.
  • DEVE falar do `_assunto`. Se o critério é sobre Wallet, evidence menciona Wallet (achado ou não, e o que tem no lugar). Se é sobre tema, lista models/entidades do domínio `{theme}` (achados ou não).
  • UNICIDADE: cada critério faz a SUA própria busca. PROIBIDO usar a MESMA evidence (mesmo texto, mesma linha do código) em 2+ critérios. Se acontecer, está errado — re-leia cada critério e busque algo específico dele.
  • Coerente com `_aplicando_R2`: false → "<arquivo> contém <Y, Z>; <X> não encontrado." | true → "<arquivo>:<linha> define <X literal>."
  • Proibido também: prosa sem âncora ("O projeto implementa Y."); "encontrado" / "não encontrado"; copiar texto do prompt; citar tema/entidade ALHEIO ao desafio.

REGRAS DE strengths / improvements (diferente de evidence — NÃO use o mesmo estilo):
  • Emita entre 2 e 4 strings concretas em cada array. NUNCA inclua o literal "..." nem qualquer reticência como item — isso aparece no schema apenas como notação, é PROIBIDO na saída.
  • Nível arquitetural / qualitativo (padrões, organização, cobertura, separação de responsabilidades).
  • Sem `arquivo:linha`, sem placeholders, sem `<...>`, sem nomes inventados.
  • strengths: o que um tech lead destacaria em code review.
  • improvements: sugestão acionável + onde aplicar (ex: "Registrar ViewSets via DefaultRouter em urls.py" — área + ação).
  • Proibido: repetir feedback ou evidence; "está bem feito"; placeholders; temas alheios; o literal "...".

# 6. CÓDIGO ({profile_name})
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
    for i, (slug, label) in enumerate(criteria_map, start=1):
        w = (weights or {}).get(label, DEFAULT_CRITERION_WEIGHT)
        # Formato em "campo: valor" sem aspas em volta do slug — aspas viram
        # convite ao LLM para editar o texto. Slug deve parecer um token fixo.
        lines.append(
            f"[{i}] id    = {slug}\n"
            f"    label = {label}\n"
            f"    peso  = {w}"
        )
    lines.append("")
    lines.append("LISTA DE IDS PERMITIDOS (COPIE LITERALMENTE — qualquer outro id será descartado):")
    for slug, _ in criteria_map:
        lines.append(f"  - {slug}")
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
    """Score 0–100 dividido entre profile (20%) e criteria (80%).

    Dentro de cada família, o `weight` de cada check é relativo: a contribuição
    da família vem de (Σ weight dos checks presentes) / (Σ weight total da família)
    multiplicado pela fatia (20 ou 80).

    Se uma família não tem checks, a outra absorve 100% — assim um payload sem
    critérios não zera o score, e um perfil sem checks estáticos também não.
    """
    profile_checks = [c for c in checks if c.kind == "profile"]
    criterion_checks = [c for c in checks if c.kind == "criterion"]

    profile_total = sum(c.weight for c in profile_checks)
    criteria_total = sum(c.weight for c in criterion_checks)
    profile_got = sum(c.weight for c in profile_checks if c.present)
    criteria_got = sum(c.weight for c in criterion_checks if c.present)

    if profile_total == 0 and criteria_total == 0:
        return MAX_FINAL_SCORE
    if profile_total == 0:
        score = (criteria_got / criteria_total) * MAX_FINAL_SCORE
    elif criteria_total == 0:
        score = (profile_got / profile_total) * MAX_FINAL_SCORE
    else:
        score = (
            (profile_got / profile_total) * PROFILE_SHARE
            + (criteria_got / criteria_total) * CRITERIA_SHARE
        )

    return max(MIN_FINAL_SCORE, min(MAX_FINAL_SCORE, round(score)))


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
