import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672//")

celery_app = Celery(
    "atlas_ia",
    broker=RABBITMQ_URL,
    backend=None,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_default_queue="ia.analyze",
    task_routes={"app.tasks.analyze_repository": {"queue": "ia.analyze"}},
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
)
