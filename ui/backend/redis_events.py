"""
Redis pub/sub event publisher for workflow orchestrator.

Publishes step-level events to Redis channels so the FastAPI server
can stream real-time updates to the UI without polling. Falls back
silently when Redis is unavailable.

Uses the shared Redis client from shared_state.py to avoid duplicate
connections.

Channel format: workflow:{execution_id}
"""

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_CHANNEL_PREFIX = "workflow"


def _get_redis():
    try:
        from shared_state import get_redis_client
        return get_redis_client()
    except ImportError:
        return None


def publish_step_event(execution_id: str, event_type: str, data: dict):
    r = _get_redis()
    if not r:
        return

    event = {
        "execution_id": execution_id,
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data,
    }

    try:
        channel = f"{_CHANNEL_PREFIX}:{execution_id}"
        r.publish(channel, json.dumps(event))

        history_key = f"{_CHANNEL_PREFIX}:history:{execution_id}"
        r.rpush(history_key, json.dumps(event))
        r.expire(history_key, 86400)
    except Exception as e:
        logger.debug(f"Failed to publish event: {e}")


def get_event_history(execution_id: str) -> list:
    r = _get_redis()
    if not r:
        return []

    try:
        history_key = f"{_CHANNEL_PREFIX}:history:{execution_id}"
        raw_events = r.lrange(history_key, 0, -1)
        return [json.loads(e) for e in raw_events]
    except Exception:
        return []


def subscribe_execution(execution_id: str, callback: Callable[[dict], None]):
    r = _get_redis()
    if not r:
        return None

    try:
        pubsub = r.pubsub()
        channel = f"{_CHANNEL_PREFIX}:{execution_id}"
        pubsub.subscribe(channel)

        def _listener():
            for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        event = json.loads(message["data"])
                        callback(event)
                    except Exception:
                        pass

        thread = threading.Thread(target=_listener, daemon=True)
        thread.start()
        return pubsub
    except Exception:
        return None


def cache_cluster_status(cluster_name: str, status_data: dict, ttl: int = 60):
    r = _get_redis()
    if not r:
        return

    try:
        key = f"cluster:status:{cluster_name}"
        r.setex(key, ttl, json.dumps(status_data))
    except Exception:
        pass


def get_cached_cluster_status(cluster_name: str) -> Optional[dict]:
    r = _get_redis()
    if not r:
        return None

    try:
        key = f"cluster:status:{cluster_name}"
        data = r.get(key)
        return json.loads(data) if data else None
    except Exception:
        return None
