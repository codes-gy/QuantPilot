import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """구조화 로깅 설정.

    주문 제출/체결/거부, kill-switch 발동, KIS 토큰 갱신 등
    감사 추적이 필요한 이벤트는 각 서비스 레이어에서 logger.info(extra={...}) 형태로 남긴다.
    """
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
