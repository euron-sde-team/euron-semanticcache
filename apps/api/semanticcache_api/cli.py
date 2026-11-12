"""``semanticcache-api`` entry point: serve, or manage API keys."""

from __future__ import annotations

import argparse
import asyncio

import uvicorn
from redis.asyncio import Redis

from .auth import ALL_SCOPES, ApiKeyStore
from .settings import apply_aws_secrets, get_settings


async def _create_key(name: str, scopes: list[str], namespace: str | None) -> None:
    s = apply_aws_secrets(get_settings())
    redis = Redis.from_url(s.redis_url, decode_responses=False)
    try:
        created = await ApiKeyStore(redis, s.prefix, s.api_key_pepper).create(
            name, scopes, namespace=namespace
        )
        print(created.key)
    finally:
        await redis.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="semanticcache-api")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="run the HTTP server (default)")
    k = sub.add_parser("keys:create", help="create an API key and print it once")
    k.add_argument("--name", required=True)
    k.add_argument("--scopes", default="*", help=f"comma-separated: *,{','.join(ALL_SCOPES)}")
    k.add_argument("--namespace", default=None, help="bind the key to one namespace")
    args = parser.parse_args()

    if args.cmd == "keys:create":
        asyncio.run(
            _create_key(args.name, [x.strip() for x in args.scopes.split(",") if x.strip()], args.namespace)
        )
        return
    s = get_settings()
    uvicorn.run(
        "semanticcache_api.main:create_app",
        factory=True,
        host=s.host,
        port=s.port,
        log_config=None,
        proxy_headers=True,
    )


if __name__ == "__main__":
    main()
