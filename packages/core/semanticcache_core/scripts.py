"""Lua scripts: each cache mutation is one atomic step, and bumps the namespace version so that every
replica can sync its in-memory vector index from a change log.

Key layout under ``{prefix}:{ns}``:
  :e:{id}   hash   json, vec (float32 bytes), scope, pn (normalised prompt), xk (exact key), hits, last_hit
  :ids      zset   id -> last access (ms); the LRU order used for eviction
  :x:{h}    string exact-match key -> id (same TTL as the entry)
  :ver      string monotonically increasing version
  :log      zset   version -> "a:{id}" | "d:{id}" | "f" (flush); capped to the last 1000 changes
"""

from __future__ import annotations

from redis.asyncio import Redis
from redis.commands.core import AsyncScript

_LIB = """
local function bump(P, op)
  local ver = redis.call('INCR', P .. ':ver')
  redis.call('ZADD', P .. ':log', ver, op)
  redis.call('ZREMRANGEBYRANK', P .. ':log', 0, -1001)
  return ver
end
local function drop(P, id)
  local ek = P .. ':e:' .. id
  local xk = redis.call('HGET', ek, 'xk')
  if xk and redis.call('GET', xk) == id then redis.call('DEL', xk) end
  redis.call('DEL', ek)
  redis.call('ZREM', P .. ':ids', id)
end
"""

PUT = (
    _LIB
    + """
-- ARGV: prefix ns id json vec scope pn ttl_s now_ms exact_hash max_entries
local P = ARGV[1] .. ':' .. ARGV[2]
local id, ek, xk = ARGV[3], P .. ':e:' .. ARGV[3], P .. ':x:' .. ARGV[10]
local old = redis.call('GET', xk)
if old and old ~= id then drop(P, old); bump(P, 'd:' .. old) end
redis.call('HSET', ek, 'json', ARGV[4], 'vec', ARGV[5], 'scope', ARGV[6], 'pn', ARGV[7], 'xk', xk, 'hits', 0)
redis.call('EXPIRE', ek, ARGV[8])
redis.call('SET', xk, id, 'EX', ARGV[8])
redis.call('ZADD', P .. ':ids', ARGV[9], id)
bump(P, 'a:' .. id)
local evicted = 0
local max = tonumber(ARGV[11])
while redis.call('ZCARD', P .. ':ids') > max do
  local victim = redis.call('ZPOPMIN', P .. ':ids')[1]
  local ek2 = P .. ':e:' .. victim
  local xk2 = redis.call('HGET', ek2, 'xk')
  if xk2 and redis.call('GET', xk2) == victim then redis.call('DEL', xk2) end
  redis.call('DEL', ek2)
  bump(P, 'd:' .. victim)
  evicted = evicted + 1
end
return evicted
"""
)

DELETE = (
    _LIB
    + """
-- ARGV: prefix ns id
local P = ARGV[1] .. ':' .. ARGV[2]
if redis.call('EXISTS', P .. ':e:' .. ARGV[3]) == 0 then
  redis.call('ZREM', P .. ':ids', ARGV[3])
  return 0
end
drop(P, ARGV[3])
bump(P, 'd:' .. ARGV[3])
return 1
"""
)

FLUSH = (
    _LIB
    + """
-- ARGV: prefix ns
local P = ARGV[1] .. ':' .. ARGV[2]
local ids = redis.call('ZRANGE', P .. ':ids', 0, -1)
for _, id in ipairs(ids) do drop(P, id) end
redis.call('DEL', P .. ':ids')
redis.call('DEL', P .. ':log')
local ver = redis.call('INCR', P .. ':ver')
redis.call('ZADD', P .. ':log', ver, 'f')
return #ids
"""
)

TOUCH = """
-- ARGV: prefix ns id now_ms
local P = ARGV[1] .. ':' .. ARGV[2]
local ek = P .. ':e:' .. ARGV[3]
if redis.call('EXISTS', ek) == 0 then return 0 end
redis.call('HINCRBY', ek, 'hits', 1)
redis.call('HSET', ek, 'last_hit', ARGV[4])
redis.call('ZADD', P .. ':ids', 'XX', ARGV[4], ARGV[3])
return 1
"""


class Scripts:
    put: AsyncScript
    delete: AsyncScript
    flush: AsyncScript
    touch: AsyncScript

    def __init__(self, redis: Redis) -> None:
        self.put = redis.register_script(PUT)
        self.delete = redis.register_script(DELETE)
        self.flush = redis.register_script(FLUSH)
        self.touch = redis.register_script(TOUCH)
