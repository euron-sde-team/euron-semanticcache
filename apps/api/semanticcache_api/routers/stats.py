from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ..auth import Principal, require
from ..deps import Cache
from ..schemas import Overview
from ..stats_service import overview as build_overview
from .namespaces import visible

router = APIRouter(prefix="/v1/stats", tags=["stats"])


@router.get("/overview", summary="Savings, hit rate and a per-minute series across your namespaces")
async def overview(
    cache: Cache,
    principal: Annotated[Principal, Depends(require("stats:read"))],
    minutes: Annotated[int, Query(ge=5, le=120)] = 30,
) -> Overview:
    return await build_overview(cache, visible(principal, await cache.store.namespaces()), minutes)
