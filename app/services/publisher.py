import json
import os

import pika

from app.schemas import AnalysisResult

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672//")
RESULT_QUEUE = os.getenv("IA_RESULT_QUEUE", "ia.result")


def publish_result(result: AnalysisResult) -> None:
    """Publishes the analysis result to the ia.result queue for scholarship-service."""
    params = pika.URLParameters(RABBITMQ_URL)
    connection = pika.BlockingConnection(params)
    try:
        channel = connection.channel()
        channel.queue_declare(queue=RESULT_QUEUE, durable=True)
        body = result.model_dump_json().encode("utf-8")
        channel.basic_publish(
            exchange="",
            routing_key=RESULT_QUEUE,
            body=body,
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )
    finally:
        connection.close()
