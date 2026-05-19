from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


CheckKind = Literal["profile", "criterion"]


class Check(BaseModel):
    """Um item binário do scorecard.

    - `kind="profile"`: derivado da análise estática do perfil (fato).
    - `kind="criterion"`: critério passado pelo usuário, marcado pelo LLM com base no código.
    - `weight`: penalidade subtraída do score se `present == False`.
    """

    id: str
    label: str
    kind: CheckKind
    weight: int = Field(ge=0, le=100)
    present: bool
    evidence: str = ""


class AnalyzePayload(BaseModel):
    user_id: str
    challenge_id: str
    github_repo_url: HttpUrl
    language: str
    criteria: Dict[str, int] = Field(
        default_factory=dict,
        description="Critérios a avaliar, no formato {label: peso}. "
        "Peso é 0-100 (penalidade subtraída quando o critério não é atendido). "
        "Ordem do dicionário é preservada e usada como ordem dos ids (1, 2, 3, ...).",
    )
    challenge_description: Optional[str] = None
    theme: Optional[str] = Field(
        default=None,
        description="Tema/assunto central do desafio (ex.: 'gestão de bolsas'). "
        "Usado como contexto para o LLM marcar os critérios.",
    )

    @field_validator("language")
    @classmethod
    def _strip_and_validate_language(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("language não pode ser vazio")
        # Import local pra evitar ciclo no carregamento do módulo.
        from app.profiles import resolve_profile
        resolve_profile(v)  # raises ValueError com a lista de stacks suportadas
        return v

    @field_validator("criteria")
    @classmethod
    def _clean_criteria(cls, v: Dict[str, int]) -> Dict[str, int]:
        cleaned: Dict[str, int] = {}
        for label, weight in (v or {}).items():
            label = (label or "").strip()
            if not label:
                continue
            try:
                weight_int = int(weight)
            except (TypeError, ValueError):
                raise ValueError(f"peso do critério '{label}' deve ser inteiro, recebido: {weight!r}")
            if not 0 <= weight_int <= 100:
                raise ValueError(f"peso do critério '{label}' fora do intervalo 0-100: {weight_int}")
            cleaned[label] = weight_int
        return cleaned


class AnalysisResult(BaseModel):
    user_id: str
    challenge_id: str
    score: int = Field(ge=0, le=100)
    feedback: str
    checks: List[Check] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    profile: Optional[str] = None


class DetectPayload(BaseModel):
    github_repo_url: HttpUrl


class DetectResult(BaseModel):
    detected_profile: Optional[str]
    detected_canonical_language: Optional[str]
    file_count: int
    sample_paths: List[str] = Field(default_factory=list)


class ProfileInfo(BaseModel):
    name: str
    canonical_language: str
    aliases: List[str]
