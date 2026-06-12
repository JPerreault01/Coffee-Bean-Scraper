# scrapers/resolvers/asin.py
"""
ASIN provider chain: [AsinValidator].

The validator VALIDATES existing ASINs. It NEVER fabricates one. Per the
CLAUDE.md content standard ("no fabricated data — if unsure, leave the field
blank rather than guess"), a missing or dead ASIN is reported as a BACKFILL
flag for a human to source, not invented.

Validation tiers:
  * format       — must be 10 chars [A-Z0-9].
  * liveness     — if PAAPI_ENABLED + creds: authoritative GetItems existence
                   check. Otherwise a best-effort Amazon page check that can
                   prove "dead" (404 / not-found page) but treats anti-bot /
                   CAPTCHA as "unverified" rather than falsely flagging dead.

Outcomes (status, error):
  ok          valid + confirmed (or format-valid but unverifiable — not disproven)
  error       present but invalid format or confirmed dead   -> "BACKFILL: ..."
  unavailable no ASIN on the product                          -> "BACKFILL: ..."
"""

from __future__ import annotations

import re

from . import _amazon, _http
from .base import Resolution, env_flag, fetch_with_retry

_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")


class AsinValidator:
    name = "validator"
    field = "asin"

    def enabled(self, ctx: dict) -> bool:
        return True

    def resolve(self, product: dict, ctx: dict) -> Resolution:
        asin = (product.get("amazon_asin") or "").strip()

        if not asin:
            # Missing — flag for human backfill, never invent.
            return Resolution(
                value=None, source=self.name, status="unavailable",
                error="BACKFILL: no ASIN on product",
            )

        if not _ASIN_RE.match(asin):
            return Resolution.failed(self.name, f"BACKFILL: invalid ASIN format '{asin}'")

        if ctx.get("mock"):
            return Resolution.found(asin, "validator:format")

        env = ctx["env"]

        # Tier 1: authoritative PA-API existence check.
        if env_flag(env, "PAAPI_ENABLED") and _amazon.has_credentials(env):
            exists, error = fetch_with_retry(
                lambda: _amazon.item_exists(asin, env),
                label=f"paapi validate {asin}",
            )
            if error:
                return Resolution.failed(self.name, error)
            if exists:
                return Resolution.found(asin, "validator:paapi")
            return Resolution.failed(self.name, f"BACKFILL: ASIN {asin} dead (not in PA-API)")

        # Tier 2: best-effort page check (cannot prove alive under anti-bot).
        status, error = fetch_with_retry(
            lambda: _http.amazon_asin_status(asin),
            label=f"validate {asin}",
        )
        if error:
            return Resolution.failed(self.name, error)
        if status == "dead":
            return Resolution.failed(self.name, f"BACKFILL: ASIN {asin} returns a dead page")
        if status == "alive":
            return Resolution.found(asin, "validator:live")
        # "unknown" — format-valid, liveness unconfirmed. Don't fabricate a failure.
        return Resolution.found(asin, "validator:format-only")


ASIN_CHAIN: list = [AsinValidator()]
