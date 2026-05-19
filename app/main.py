from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

load_dotenv()

from app.profiles import list_profiles, resolve_profile
from app.schemas import (
    AnalysisResult,
    AnalyzePayload,
    DetectPayload,
    DetectResult,
    ProfileInfo,
)
from app.services import llm, repo
from app.worker import celery_app

app = FastAPI(title="Atlas IA Service", version="0.2.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "atlas-ia-service"}


@app.get("/profiles", response_model=list[ProfileInfo])
async def profiles() -> list[ProfileInfo]:
    return [ProfileInfo(**p) for p in list_profiles()]


@app.post("/detect", response_model=DetectResult)
async def detect(payload: DetectPayload) -> DetectResult:
    """Clones the repo and tries to identify the project profile. Diagnostic endpoint."""
    try:
        profile, paths = await repo.detect_repository_profile(str(payload.github_repo_url))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao clonar/inspecionar repo: {exc}") from exc

    return DetectResult(
        detected_profile=profile.name if profile else None,
        detected_canonical_language=profile.canonical_language if profile else None,
        file_count=len(paths),
        sample_paths=paths[:30],
    )


@app.post("/analyze", status_code=202)
async def analyze(payload: AnalyzePayload) -> dict:
    """Enqueues an analysis task on the ia.analyze queue (production path)."""
    profile = resolve_profile(payload.language)
    task = celery_app.send_task(
        "app.tasks.analyze_repository",
        args=[payload.model_dump(mode="json")],
    )
    return {
        "task_id": task.id,
        "queue": "ia.analyze",
        "status": "queued",
        "resolved_profile": profile.name,
        "canonical_language": profile.canonical_language,
    }


@app.post("/analyze/sync", response_model=AnalysisResult)
async def analyze_sync(payload: AnalyzePayload) -> AnalysisResult:
    """Runs the full pipeline inline (clone + repomix + LLM). Useful for testing."""
    try:
        packed = await repo.pack_repository(str(payload.github_repo_url), declared_language=payload.language)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
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
        raise HTTPException(status_code=502, detail=f"Falha na avaliação pelo LLM: {exc}") from exc
