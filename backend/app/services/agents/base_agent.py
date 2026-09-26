import asyncio
import json
import logging
import os

from app.services.llm import complete_json, get_client

logger = logging.getLogger(__name__)

RETRY_BASE = 2
RETRY_MAX = 30

SYSTEM_PROMPT = """\
You are FireLink's emergency advisory engine for the 2025 Eaton Fire in Los Angeles.
You will receive a JSON snapshot of the latest fire incidents and weather conditions.

Based on this data, generate a brief, calm, actionable advisory for residents.
Tell them exactly what they should do right now in plain English, and explain
the specific conditions driving that advice.

Respond ONLY with this JSON object (no markdown, no extra text):
{
  "advisory": "<2-3 sentences: what residents should do right now>",
  "reasoning": "<1-2 sentences: why — the specific conditions driving this advisory>",
  "risk_level": "<LOW|MODERATE|HIGH|CRITICAL>",
  "generated_at": "<ISO 8601 timestamp>"
}\
"""


class BaseAgent:
    model = os.getenv("RECOMMENDATION_MODEL") or "gpt-4o-mini"

    def __init__(self):
        # validate provider config early so misconfiguration fails at startup
        get_client()

    async def call_llm(self, context: dict) -> dict:
        return await complete_json(
            model=self.model,
            system=SYSTEM_PROMPT,
            user=json.dumps(context),
        )

    async def _connect_producer(self):
        from aiokafka import AIOKafkaProducer
        from app.core.kafka import KAFKA_BOOTSTRAP

        delay = RETRY_BASE
        attempt = 0
        while True:
            attempt += 1
            producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP)
            try:
                await producer.start()
                logger.info("%s connected to Kafka (attempt %d)", self.__class__.__name__, attempt)
                return producer
            except Exception as e:
                await producer.stop()
                logger.warning(
                    "%s Kafka not ready (attempt %d): %s. Retry in %ds",
                    self.__class__.__name__, attempt, e, delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, RETRY_MAX)
