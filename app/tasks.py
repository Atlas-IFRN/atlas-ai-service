import asyncio
import logging

from app.schemas import AnalysisResult, AnalyzePayload
from app.services import llm, publisher, repo
from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.analyze_repository", bind=True, max_retries=2)
def analyze_repository(self, payload: dict) -> dict:
    """Orchestrates: clone + filter por perfil → evaluate via Ollama → publish result."""
    data = AnalyzePayload(**payload)
    try:
        result = asyncio.run(_run(data))
    except Exception as exc:
        logger.exception(
            "analyze_repository failed for user=%s challenge=%s",
            data.user_id,
            data.challenge_id,
        )
        raise self.retry(exc=exc, countdown=10)

    publisher.publish_result(result)
    return result.model_dump()


async def _run(data: AnalyzePayload) -> AnalysisResult:
    packed = await repo.pack_repository(
        str(data.github_repo_url),
        declared_language=data.language,
    )
    logger.info(
        "Pacote pronto: profile=%s detected=%s files=%s code_chars=%s",
        packed.profile.name,
        packed.detected_profile.name if packed.detected_profile else None,
        packed.file_count,
        len(packed.packed_code),
    )
    return await llm.evaluate(
        user_id=data.user_id,
        challenge_id=data.challenge_id,
        challenge_description=data.challenge_description or "",
        theme=data.theme,
        declared_language=data.language,
        criteria=data.criteria,
        packed=packed,
    )
