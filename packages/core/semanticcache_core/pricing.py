"""Token prices, in USD per 1M tokens. Defaults are approximate list prices; override with SC_PRICING_FILE.

Cost is tracked in integer micro-dollars (1e-6 USD) so that counters in Redis stay exact: with prices expressed per
million tokens, ``tokens * price`` is already a micro-dollar amount.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from .models import Usage

# (input, output) USD per 1M tokens. Longest matching prefix wins.
DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "o3-mini": (1.10, 4.40),
    "claude-haiku": (0.80, 4.00),
    "claude-sonnet": (3.00, 15.00),
    "claude-opus": (15.00, 75.00),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "mock": (1.00, 3.00),
}
FALLBACK = (1.00, 3.00)


def estimate_tokens(text: str) -> int:
    """~4 characters per token. Only used when the upstream did not report usage."""
    return max(1, math.ceil(len(text) / 4))


class Pricing:
    def __init__(self, prices: dict[str, tuple[float, float]] | None = None) -> None:
        self.prices = dict(DEFAULT_PRICES if prices is None else prices)

    @classmethod
    def from_file(cls, path: str | Path) -> Pricing:
        raw = json.loads(Path(path).read_text())
        return cls({**DEFAULT_PRICES, **{k: (float(v[0]), float(v[1])) for k, v in raw.items()}})

    def price_for(self, model: str) -> tuple[float, float]:
        m = model.lower()
        best = max((p for p in self.prices if m.startswith(p)), key=len, default=None)
        return self.prices[best] if best else FALLBACK

    def cost_micro(self, model: str, usage: Usage) -> int:
        pin, pout = self.price_for(model)
        return round(usage.prompt_tokens * pin + usage.completion_tokens * pout)
