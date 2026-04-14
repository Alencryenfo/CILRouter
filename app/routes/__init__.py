# -*- coding: utf-8 -*-
from fastapi import APIRouter
from .health import router as health_router
from .admin import router as admin_router
from .proxy import router as proxy_router

router = APIRouter()
router.include_router(health_router)
router.include_router(admin_router)
router.include_router(proxy_router)
