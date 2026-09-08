from app.core.logging import get_logger
from app.ws.manager import ws_manager

logger = get_logger(__name__)


async def push_to_app(event_type: str, message: str) -> None:
    await ws_manager.broadcast({"type": event_type, "message": message})
    logger.info("notification sent: %s - %s", event_type, message)
