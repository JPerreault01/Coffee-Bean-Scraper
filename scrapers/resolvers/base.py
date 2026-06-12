# scrapers/resolvers/base.py
"""
Resolver framework — graceful, chain-based field resolution.

A *field* (price, image, asin) is resolved by walking an ordered list of
*providers*. Each provider returns a Resolution with one of three statuses:

  "ok"          -> a usable value was found. The chain stops here.
  "unavailable" -> this provider does not apply / found nothing. Fall through.
  "error"       -> a fetch failed after retries. Recorded, but still fall
                   through to the next provider.

No fetch failure may ever raise out of a resolver: every network call goes
through fetch_with_retry(), which catches everything and returns an error
string instead of propagating. A single dead source degrades the field to
"stale" in product_data_health; it never crashes the run or blanks a
last-good value.

This module is pure-Python and dependency-free so it stays import-cheap.
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

from ..url_filters import build_placeholder_urls

# ---------------------------------------------------------------------------
# Paths (same /opt-else-repo pattern as scrapers/db.py)
# ---------------------------------------------------------------------------

_SCRAPERS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRAPERS_DIR.parent


def _resolve(opt_path: str, repo_path: Path) -> Path:
    opt = Path(opt_path)
    return opt if opt.exists() else repo_path


ENV_FILE = _resolve("/opt/.env", _REPO_ROOT / ".env")
PRODUCTS_FILE = _resolve("/opt/scrapers/products.json", _SCRAPERS_DIR / "products.json")


def load_env() -> dict:
    """Read /opt/.env (or repo .env) then overlay os.environ.

    Single canonical loader for the whole pipeline — the legacy scripts now
    import this instead of each keeping their own copy.
    """
    env: dict = {}
    if ENV_FILE.exists():
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    env.update(os.environ)
    return env


def env_flag(env: dict, key: str, default: bool = False) -> bool:
    """Interpret an env var as a boolean ('1', 'true', 'yes', 'on')."""
    raw = env.get(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Resolution + Resolver protocol
# ---------------------------------------------------------------------------

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_ERROR = "error"


@dataclass
class Resolution:
    """The outcome of one provider attempting to resolve one field.

    `extra` carries provider-specific metadata that doesn't fit `value` — e.g.
    a Shopify price resolution attaches {"price_per_oz": ..., "out_of_stock": ...}
    computed from the chosen variant's own weight.
    """

    value: Any = None
    source: str = ""
    status: str = STATUS_UNAVAILABLE
    error: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    @classmethod
    def found(cls, value: Any, source: str, extra: dict | None = None) -> "Resolution":
        return cls(value=value, source=source, status=STATUS_OK, extra=extra or {})

    @classmethod
    def missing(cls, source: str, reason: str = "") -> "Resolution":
        return cls(source=source, status=STATUS_UNAVAILABLE, error=reason or None)

    @classmethod
    def failed(cls, source: str, error: str) -> "Resolution":
        return cls(source=source, status=STATUS_ERROR, error=error)


@runtime_checkable
class Resolver(Protocol):
    """A provider for one field. Implementations are plain classes.

    `field` is the field this provider resolves ("price"|"image"|"asin").
    `name`  is the provider id recorded as the resolution source.
    """

    name: str
    field: str

    def enabled(self, ctx: dict) -> bool:
        """Cheap, side-effect-free gate. False -> skipped silently (not an
        error). PA-API providers return False unless PAAPI_ENABLED and creds
        are present.
        """
        ...

    def resolve(self, product: dict, ctx: dict) -> Resolution:
        """Attempt to resolve the field for one product. Must never raise."""
        ...


# ---------------------------------------------------------------------------
# Retry helper — the only place network failures are caught
# ---------------------------------------------------------------------------

# Exponential backoff base delays (seconds) before each retry. Jitter added.
BACKOFF_SECONDS = (2.0, 4.0, 8.0)


def fetch_with_retry(
    fn: Callable[[], Any],
    *,
    attempts: int = 3,
    label: str = "fetch",
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Any, str | None]:
    """Run fn() with up to `attempts` tries and exponential backoff.

    Returns (value, error):
      - On success: (fn_return_value, None). Note fn may legitimately return
        None/"" meaning "fetched fine, nothing there" — that is NOT an error,
        the caller maps it to "unavailable".
      - On failure: (None, "<label>: <last exception>") after all attempts
        raised. Never propagates the exception.

    Backoff before retry N uses BACKOFF_SECONDS[N] + up to 1s of jitter
    (2s/4s/8s + jitter). No sleep after the final attempt.
    """
    last_exc: BaseException | None = None
    for i in range(attempts):
        try:
            return fn(), None
        except Exception as exc:  # noqa: BLE001 — deliberately swallow everything
            last_exc = exc
            if i < attempts - 1:
                base = BACKOFF_SECONDS[i] if i < len(BACKOFF_SECONDS) else BACKOFF_SECONDS[-1]
                sleep(base + random.uniform(0, 1))
    return None, f"{label}: {last_exc}"


# ---------------------------------------------------------------------------
# Chain walker
# ---------------------------------------------------------------------------

def resolve_field(product: dict, providers: list[Resolver], ctx: dict) -> Resolution:
    """Walk providers in order; return the first "ok".

    "unavailable" falls through silently. "error" falls through but is
    remembered so it can be surfaced if nothing later succeeds. If at least one
    provider errored, returns the first error (so health records the real
    failure); otherwise returns the last "unavailable" Resolution so its reason
    (e.g. an ASIN BACKFILL flag) is preserved rather than flattened.
    """
    first_error: Resolution | None = None
    last_unavailable: Resolution | None = None
    for prov in providers:
        try:
            if not prov.enabled(ctx):
                continue
            res = prov.resolve(product, ctx)
        except Exception as exc:  # noqa: BLE001 — a provider must never crash the chain
            res = Resolution.failed(getattr(prov, "name", "unknown"), f"resolver raised: {exc}")
        if res.status == STATUS_OK:
            return res
        if res.status == STATUS_ERROR and first_error is None:
            first_error = res
        elif res.status == STATUS_UNAVAILABLE:
            last_unavailable = res
    if first_error is not None:
        return first_error
    if last_unavailable is not None:
        return last_unavailable
    return Resolution(status=STATUS_UNAVAILABLE, error="no provider returned a value")


# ---------------------------------------------------------------------------
# Rate limiter — enforces a minimum gap between requests-based fetches
# ---------------------------------------------------------------------------

class RateLimiter:
    """Callable that blocks until at least `min_gap` seconds have passed since
    the previous call (the _polite() pattern from fetch_bean_images.py, shared
    across all requests-based resolvers in a run)."""

    def __init__(self, min_gap: float = 1.5, *, sleep: Callable[[float], None] = time.sleep) -> None:
        self.min_gap = min_gap
        self._sleep = sleep
        self._last = 0.0

    def __call__(self) -> None:
        gap = time.time() - self._last
        if gap < self.min_gap:
            self._sleep(self.min_gap - gap)
        self._last = time.time()


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def build_context(products: list[dict], env: dict | None = None, mock: bool = False) -> dict:
    """Assemble the shared ctx passed to every provider.

    placeholder_pairs: (brand, url) pairs reused across 3+ products — these are
    catalog-expansion artifacts (e.g. every Volcanica bean pointing at the same
    sumatra page) and must not be trusted as that product's real source.

    http_throttle: shared 1.5s rate limiter for requests-based tiers.
    shopify_dead_hosts: per-run cache of hosts whose .js endpoint has 404'd, so
    the Shopify tier stops probing a non-Shopify host after two misses.
    """
    env = env if env is not None else load_env()
    return {
        "env": env,
        "mock": mock,
        "placeholder_pairs": build_placeholder_urls(products),
        "http_throttle": RateLimiter(1.5),
        "shopify_dead_hosts": {},
    }
