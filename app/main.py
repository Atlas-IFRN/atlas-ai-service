import logging

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from app.profiles import list_profiles
from app.schemas import (
    AnalysisResult,
    AnalyzePayload,
    DetectPayload,
    DetectResult,
    ProfileInfo,
)
from app.services import llm, repo

app = FastAPI(
    title="Atlas IA Service",
    description="Serviço de IA para análise de repositórios, fornecendo detecção de perfil e avaliação baseada em LLM.",
    version="0.2.0",
    docs_url="/api/ai/docs",
    redoc_url=None,
    openapi_url="/api/ai/schema",
)

# Rotas de negocio sob o namespace do servico (/api/ai/...), roteado pelo gateway.
# O /health fica na raiz por ser probe interno de liveness, fora do prefixo.
router = APIRouter(prefix="/api/ai")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "atlas-ia-service"}


@router.get("/profiles", response_model=list[ProfileInfo])
async def profiles() -> list[ProfileInfo]:
    return [ProfileInfo(**p) for p in list_profiles()]


@router.post("/detect", response_model=DetectResult)
async def detect(payload: DetectPayload) -> DetectResult:
    """Clones the repo and tries to identify the project profile. Diagnostic endpoint."""
    try:
        profile, paths = await repo.detect_repository_profile(str(payload.github_repo_url))
    except ValueError as exc:
        logger.warning("Validação falhou em /detect: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Falha ao clonar/inspecionar repo em /detect")
        raise HTTPException(status_code=502, detail=f"Falha ao clonar/inspecionar repo: {exc}") from exc

    return DetectResult(
        detected_profile=profile.name if profile else None,
        detected_canonical_language=profile.canonical_language if profile else None,
        file_count=len(paths),
        sample_paths=paths[:30],
    )


@router.post("/analyze", response_model=AnalysisResult)
async def analyze(payload: AnalyzePayload) -> AnalysisResult:
    """Runs the full pipeline inline (clone + repomix + LLM)."""
    logger.info(
        "/analyze recebido: user=%s challenge=%s repo=%s language=%s",
        payload.user_id, payload.challenge_id, payload.github_repo_url, payload.language,
    )
    try:
        packed = await repo.pack_repository(str(payload.github_repo_url), declared_language=payload.language)
    except ValueError as exc:
        logger.warning("Validação falhou em /analyze (pack): %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Falha ao coletar repositório em /analyze")
        raise HTTPException(status_code=502, detail=f"Falha ao coletar repositório: {exc}") from exc

    try:
        return await llm.evaluate(
            user_id=payload.user_id,
            challenge_id=payload.challenge_id,
            challenge_description=payload.challenge_description or "",
            theme=payload.theme,
            declared_language=payload.language,
            criteria=payload.criteria,
            packed=packed,
        )
    except Exception as exc:
        logger.exception("Falha na avaliação pelo LLM em /analyze")
        raise HTTPException(status_code=502, detail=f"Falha na avaliação pelo LLM: {exc}") from exc


app.include_router(router)
