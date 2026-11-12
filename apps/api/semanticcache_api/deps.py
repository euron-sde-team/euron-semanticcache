from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from semanticcache_core import SemanticCache

from .settings import ApiSettings
from .upstream import UpstreamClient


def get_cache(request: Request) -> SemanticCache:
    cache: SemanticCache = request.app.state.cache
    return cache


def get_settings_dep(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


def get_upstream(request: Request) -> UpstreamClient:
    up: UpstreamClient = request.app.state.upstream
    return up


Cache = Annotated[SemanticCache, Depends(get_cache)]
Settings = Annotated[ApiSettings, Depends(get_settings_dep)]
Upstream = Annotated[UpstreamClient, Depends(get_upstream)]
