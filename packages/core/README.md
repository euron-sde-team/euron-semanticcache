# semanticcache-core

The engine behind Euron SemanticCache: embeddings, scoped vector matching with safety guards, Redis storage,
and cost accounting. See the [architecture docs](../../docs/architecture/LLD.md).

```python
from redis.asyncio import Redis
from semanticcache_core import SemanticCache, ChatRequest, HashingEmbedder

cache = SemanticCache(Redis.from_url("redis://localhost:6379/0", decode_responses=False), HashingEmbedder())
req = ChatRequest(model="gpt-4o-mini", messages=[{"role": "user", "content": "How do I reset my password?"}])
hit = await cache.lookup("default", req)
```
