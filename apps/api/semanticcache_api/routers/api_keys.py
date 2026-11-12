from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth import ALL_SCOPES, ApiKeyCreated, ApiKeyRecord, ApiKeyStore, require
from ..schemas import ActionResult, ApiKeyCreate

router = APIRouter(prefix="/v1/api-keys", tags=["api-keys"], dependencies=[Depends(require("keys:admin"))])


def _store(request: Request) -> ApiKeyStore:
    store: ApiKeyStore = request.app.state.keys
    return store


@router.get("", summary="List API keys (never their secrets)")
async def list_keys(request: Request) -> list[ApiKeyRecord]:
    return await _store(request).list()


@router.get("/scopes", summary="Available scopes")
async def scopes() -> list[str]:
    return ["*", *ALL_SCOPES]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create an API key")
async def create_key(body: ApiKeyCreate, request: Request) -> ApiKeyCreated:
    """The secret is returned once. A key can never hold more than its creator: not scopes it lacks, and a
    namespace-bound creator can only create keys bound to the same namespace."""
    principal = request.state.principal
    if "*" in body.scopes and not principal.can("*"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "cannot grant '*' without holding it")
    for s in body.scopes:
        if s != "*" and not principal.can(s):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"cannot grant scope {s!r} you do not hold")
    if principal.namespace and body.namespace != principal.namespace:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"this key is bound to namespace {principal.namespace!r}; new keys must be too",
        )
    try:
        return await _store(request).create(body.name, body.scopes, namespace=body.namespace)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.delete("/{prefix}", summary="Revoke an API key")
async def revoke(prefix: str, request: Request) -> ActionResult:
    if prefix == request.state.principal.prefix:
        raise HTTPException(status.HTTP_409_CONFLICT, "a key cannot revoke itself")
    if not await _store(request).revoke(prefix):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "key not found")
    return ActionResult()
