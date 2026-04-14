# -*- coding: utf-8 -*-
from fastapi import APIRouter, Request
from fastapi.responses import Response
from app.config import config
from app.constants import APP_NAME, APP_VERSION
from app.log.logger import get_logger

router = APIRouter()
logger = get_logger()


@router.get("/")
async def root(request: Request):
    """根路径，返回当前状态"""
    IP = getattr(request.state, "ip", "unknown-client")
    trace_id = getattr(request.state, "trace_id", "")
    if IP != "127.0.0.1":
        logger.info(f"IP:{IP}访问端点 /", IP=IP, trace_id=trace_id, 信息="访问端点 /")
    return {
        "应用名称": APP_NAME,
        "当前版本": APP_VERSION,
        "当前供应商": config.get_current_provider_index(),
        "全部供应商信息": config.get_all_providers_info(),
        "跟踪ID": trace_id,
    }


@router.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)
