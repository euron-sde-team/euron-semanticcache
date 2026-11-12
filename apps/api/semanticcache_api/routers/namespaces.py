from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from semanticcache_core import NamespaceConfig
from semanticcache_core.models import NAMESPACE_PATTERN

from ..auth import Principal, require
from ..deps import Cache
from ..schemas import ActionResult, NamespaceSummary
from ..stats_service import namespace_summary

router = APIRouter(prefix="/v1/namespaces", tags=["namespaces"])
Name = Annotated[str, Path(pattern=NAMESPACE_PATTERN)]


def visible(principal: Principal, names: list[str]) -> list[str]:
    return [n for n in names if principal.namespace in (None, n)]


@router.get("", summary="Namespaces with their settings and savings")
async def list_namespaces(
    cache: Cache, principal: Annotated[Principal, Depends(require("stats:read"))]
) -> list[NamespaceSummary]:
    return [await namespace_summary(cache, n) for n in visible(principal, await cache.store.namespaces())]


@router.put("/{name}", summary="Create a namespace or change its settings")
async def put_namespace(
    name: Name, config: NamespaceConfig, cache: Cache,
    principal: Annotated[Principal, Depends(require("namespaces:write"))],
) -> NamespaceSummary:  # fmt: skip
    if principal.namespace:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "namespace-bound keys cannot change namespace settings"
        )
    await cache.set_config(name, config)
    return await namespace_summary(cache, name)


@router.delete("/{name}", summary="Delete a namespace, its entries and its statistics")
async def delete_namespace(
    name: Name, cache: Cache, principal: Annotated[Principal, Depends(require("namespaces:write"))]
) -> ActionResult:
    if principal.namespace:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "namespace-bound keys cannot delete namespaces")
    if name not in await cache.store.namespaces():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"namespace {name} not found")
    await cache.store.drop_namespace(name)
    cache._cfg.pop(name, None)
    return ActionResult()
