# scrapers/resolvers/price.py
"""
Price provider chain, in resolution order (first 'ok' wins):

  1. amazon  (AmazonPaapiPrice)  — PA-API, gated behind PAAPI_ENABLED + creds,
     and skipped entirely when ctx['skip_amazon'] is set. Tried first when a
     product has an ASIN; on failure the chain falls through, the product is
     NOT marked failed yet.
  2. shopify (ShopifyJsonPrice)  — /products/{handle}.js then .json JSON
     endpoints. Variant-aware; price_per_oz from the variant's own weight.
  3. jsonld/meta (JsonLdMetaPrice) — requests + BeautifulSoup: JSON-LD Product
     Offer.price, else og:/product: price meta tags. source is 'jsonld' or 'meta'.
  4. roaster-playwright (RoasterPlaywrightPrice) — headless render, only if a
     chromium binary is installed (ctx['playwright_ok']).

Tiers 2-3 share ctx['http_throttle'] (1.5s gap). Tiers 1 and 4 self-impose the
random 3-8s delay just before the expensive call, so products that get skipped
or resolve early never pay it.

Products whose roaster_url is skippable/placeholder only get the Amazon tier;
tiers 2-4 return 'unavailable' for them so they skip cleanly.
"""

from __future__ import annotations

import random
import time
from urllib.parse import urlparse

from ..url_filters import is_skippable_url
from . import _amazon, _http, _playwright
from .base import Resolution, env_flag, fetch_with_retry

# Random polite delay (seconds) before a Playwright/PA-API call.
PLAYWRIGHT_DELAY = (3.0, 8.0)


def _roaster_url(product: dict) -> str:
    return (product.get("roaster_url") or "").strip()


def _url_blocked(url: str, brand: str, ctx: dict) -> str | None:
    """Reason this roaster URL must not be scraped, or None if it's fine."""
    if not url:
        return "no roaster URL"
    if is_skippable_url(url):
        return "affiliate/redirect URL — not scrapable"
    if (brand, url) in ctx.get("placeholder_pairs", set()):
        return "shared placeholder URL (3+ products)"
    return None


class AmazonPaapiPrice:
    name = "amazon_paapi"  # provider id (refresh_data detects PA-API by this)
    field = "price"
    source = "amazon"      # recorded tier name in price_history.source

    def enabled(self, ctx: dict) -> bool:
        if ctx.get("skip_amazon"):
            return False
        env = ctx["env"]
        return env_flag(env, "PAAPI_ENABLED") and _amazon.has_credentials(env)

    def resolve(self, product: dict, ctx: dict) -> Resolution:
        asin = (product.get("amazon_asin") or "").strip()
        if not asin:
            return Resolution.missing(self.source, "no ASIN")
        if ctx.get("mock"):
            return Resolution.missing(self.source, "mock: PA-API not exercised")
        time.sleep(random.uniform(*PLAYWRIGHT_DELAY))
        value, error = fetch_with_retry(
            lambda: _amazon.get_price(asin, ctx["env"]),
            label=f"paapi price {asin}",
        )
        if error:
            return Resolution.failed(self.source, error)
        if value is None:
            return Resolution.missing(self.source, "no offer in PA-API response")
        return Resolution.found(round(value, 2), self.source)


class ShopifyJsonPrice:
    name = "shopify"
    field = "price"

    def enabled(self, ctx: dict) -> bool:
        return True

    def resolve(self, product: dict, ctx: dict) -> Resolution:
        url = _roaster_url(product)
        blocked = _url_blocked(url, product.get("brand", ""), ctx)
        if blocked:
            return Resolution.missing(self.name, blocked)
        if not _http.shopify_handle(url):
            return Resolution.missing(self.name, "not a /products/{handle} URL")

        host = urlparse(url).netloc
        dead = ctx.setdefault("shopify_dead_hosts", {})
        if dead.get(host, 0) >= 2:
            return Resolution.missing(self.name, f"{host} not a Shopify store (cached)")
        if ctx.get("mock"):
            return Resolution.missing(self.name, "mock: shopify not exercised")

        result, error = fetch_with_retry(
            lambda: _http.get_shopify_price(
                url, product.get("weight_oz"),
                dead_hosts=dead, throttle=ctx.get("http_throttle"),
            ),
            label=f"shopify price {host}",
        )
        if error:
            return Resolution.failed(self.name, error)
        if result is None:
            return Resolution.missing(self.name, "no Shopify JSON endpoint")
        price, price_per_oz, out_of_stock = result
        return Resolution.found(
            round(price, 2), self.name,
            extra={"price_per_oz": price_per_oz, "out_of_stock": out_of_stock},
        )


class JsonLdMetaPrice:
    name = "roaster"  # provider id; the recorded source is 'jsonld' or 'meta'
    field = "price"

    def enabled(self, ctx: dict) -> bool:
        return True

    def resolve(self, product: dict, ctx: dict) -> Resolution:
        url = _roaster_url(product)
        blocked = _url_blocked(url, product.get("brand", ""), ctx)
        if blocked:
            return Resolution.missing(self.name, blocked)
        if ctx.get("mock"):
            return _mock_price(product)

        throttle = ctx.get("http_throttle")
        if throttle:
            throttle()
        result, error = fetch_with_retry(
            lambda: _http.get_roaster_price_tiered(url),
            label=f"roaster price {url}",
        )
        if error:
            return Resolution.failed(self.name, error)
        price, source = result
        if price is None:
            return Resolution.missing(self.name, "no machine-readable price on page")
        return Resolution.found(round(price, 2), source)


class RoasterPlaywrightPrice:
    name = "roaster-playwright"
    field = "price"

    def enabled(self, ctx: dict) -> bool:
        return bool(ctx.get("playwright_ok"))

    def resolve(self, product: dict, ctx: dict) -> Resolution:
        url = _roaster_url(product)
        blocked = _url_blocked(url, product.get("brand", ""), ctx)
        if blocked:
            return Resolution.missing(self.name, blocked)
        if ctx.get("mock"):
            return Resolution.missing(self.name, "mock: playwright not exercised")

        time.sleep(random.uniform(*PLAYWRIGHT_DELAY))
        value, error = fetch_with_retry(
            lambda: _playwright.get_price(url),
            label=f"playwright price {url}",
        )
        if error:
            return Resolution.failed(self.name, error)
        if value is None:
            return Resolution.missing(self.name, "no price rendered on page")
        return Resolution.found(round(value, 2), self.name)


def _mock_price(product: dict) -> Resolution:
    """Deterministic offline price so --mock exercises the full pipeline."""
    weight = product.get("weight_oz") or 12.0
    # ~$1.30/oz, stable per product, rounded to cents.
    price = round(6.0 + weight * 1.3, 2)
    return Resolution.found(price, "roaster")


PRICE_CHAIN: list = [
    AmazonPaapiPrice(),
    ShopifyJsonPrice(),
    JsonLdMetaPrice(),
    RoasterPlaywrightPrice(),
]
