# -*- coding: utf-8 -*-
from fastapi import APIRouter, Request, HTTPException
from app.config import config
from app.log.logger import get_logger

router = APIRouter()
logger = get_logger()


@router.post("/select")
async def select_provider(request: Request):
    """选择供应商接口，POST 请求体为供应商索引数字。"""
    IP = getattr(request.state, "ip", "unknown-client")
    trace_id = getattr(request.state, "trace_id", "")
    try:
        logger.info(f"IP:{IP}访问端点 /select", IP=IP, trace_id=trace_id, 信息="访问端点 /select")
        body = await request.body()
        index = int(body.decode().strip())
        if config.set_provider_index(index):
            logger.info(
                f"IP:{IP}访问端点 /select➡️成功，切换到供应商 {index}",
                IP=IP, trace_id=trace_id,
                信息=f"访问端点 /select 成功，切换到供应商 {index}",
            )
            return {
                "状态": "成功",
                "信息": f"已切换到供应商 {index}",
                "供应商信息": config.get_provider_info(index),
                "跟踪ID": trace_id,
            }
        logger.warning(
            f"❌IP:{IP}访问端点 /select➡️失败，索引 {index} 无效",
            IP=IP, trace_id=trace_id,
            信息=f"访问端点 /select 失败，索引 {index} 无效",
        )
        raise HTTPException(status_code=400, detail={"信息": f"无效的供应商索引 {index}", "跟踪ID": trace_id})
    except ValueError:
        logger.error(
            f"IP:{IP}访问端点 /select➡️发生错误: 请求体不是一个数字",
            IP=IP, trace_id=trace_id,
            信息="访问端点 /select 发生错误: 请求体不是一个数字",
        )
        raise HTTPException(status_code=400, detail={"信息": "请求体不是一个数字", "跟踪ID": trace_id})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"IP:{IP}访问端点 /select➡️发生错误: {type(e).__name__}: {e}",
            IP=IP, trace_id=trace_id,
            信息=f"访问端点 /select 发生错误: {type(e).__name__}: {e}",
        )
        raise HTTPException(status_code=500, detail={"信息": f"内部错误: {type(e).__name__}: {e}", "跟踪ID": trace_id})
