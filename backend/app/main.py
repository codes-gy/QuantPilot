from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.features.account.router import router as account_router
from app.features.market_data.router import router as market_data_router
from app.features.risk.router import router as risk_router
from app.features.strategy.router import router as strategy_router
from app.features.trading.router import positions_router
from app.features.trading.router import router as trading_router
from app.ws.router import router as ws_router

configure_logging()
settings = get_settings()
settings.assert_safe_to_start()  # live 모드인데 기본 시크릿/빈 자격증명이면 여기서 기동을 거부한다

app = FastAPI(title="QuantPilot API")

# Flutter 웹(PC 브라우저)은 API와 다른 포트에서 뜨므로 CORS 허용이 필요하다.
# 모바일/데스크톱 앱은 브라우저가 아니라 CORS와 무관하다.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(account_router, prefix="/api/v1")
app.include_router(market_data_router, prefix="/api/v1")
app.include_router(strategy_router, prefix="/api/v1")
app.include_router(trading_router, prefix="/api/v1")
app.include_router(positions_router, prefix="/api/v1")
app.include_router(risk_router, prefix="/api/v1")
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "trading_mode": settings.trading_mode.value}
