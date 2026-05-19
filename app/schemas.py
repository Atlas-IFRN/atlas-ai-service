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
    criteria: List[str] = Field(default_factory=list)
    challenge_description: Optional[str] = None
    theme: Optional[str] = Field(
        default=None,
        description="Tema/assunto central do desafio (ex.: 'gestão de bolsas'). "
        "Usado como contexto para o LLM marcar os critérios.",
    )
    criteria_weights: Optional[Dict[str, int]] = Field(
        default=None,
        description="Penalidade (0-100) por critério se ele estiver ausente. "
        "Se omitido, cada critério vale 10 pontos.",
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
    def _clean_criteria(cls, v: List[str]) -> List[str]:
        return [c.strip() for c in (v or []) if c and c.strip()]


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
