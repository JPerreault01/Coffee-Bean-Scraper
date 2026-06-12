# scrapers/resolvers/image.py
"""
Image provider chain: [AmazonPaapiImage (disabled), RoasterOgImage].

Same gating story as price.py: PA-API first but skipped until PAAPI_ENABLED +
creds; RoasterOgImage (og:image via requests) handles everything today. The
richer multi-source image tool (fetch_bean_images.py — Amazon page scrape,
waytocoffee, Playwright) still exists for bulk image backfill and now imports
the same helpers; this chain is the lean path refresh_data uses for health.
"""

from __future__ import annotations

from . import _amazon, _http
from .base import Resolution, env_flag, fetch_with_retry


class AmazonPaapiImage:
    name = "amazon_paapi"
    field = "image"

    def enabled(self, ctx: dict) -> bool:
        env = ctx["env"]
        return env_flag(env, "PAAPI_ENABLED") and _amazon.has_credentials(env)

    def resolve(self, product: dict, ctx: dict) -> Resolution:
        asin = (product.get("amazon_asin") or "").strip()
        if not asin:
            return Resolution.missing(self.name, "no ASIN")
        if ctx.get("mock"):
            return Resolution.missing(self.name, "mock: PA-API not exercised")
        value, error = fetch_with_retry(
            lambda: _amazon.get_image(asin, ctx["env"]),
            label=f"paapi image {asin}",
        )
        if error:
            return Resolution.failed(self.name, error)
        if not value:
            return Resolution.missing(self.name, "no image in PA-API response")
        return Resolution.found(value, self.name)


class RoasterOgImage:
    name = "roaster"
    field = "image"

    def enabled(self, ctx: dict) -> bool:
        return True

    def resolve(self, product: dict, ctx: dict) -> Resolution:
        url = (product.get("roaster_url") or "").strip()
        brand = product.get("brand", "")
        if not url:
            return Resolution.missing(self.name, "no roaster URL")
        if _http.is_skippable_url(url):
            return Resolution.missing(self.name, "affiliate/redirect URL — not scrapable")
        if (brand, url) in ctx.get("placeholder_pairs", set()):
            return Resolution.missing(self.name, "shared placeholder URL (3+ products)")

        if ctx.get("mock"):
            return _mock_image(product)

        value, error = fetch_with_retry(
            lambda: _http.get_og_image(url),
            label=f"roaster og:image {url}",
        )
        if error:
            return Resolution.failed(self.name, error)
        if not value:
            return Resolution.missing(self.name, "no og:image on page")
        return Resolution.found(value, self.name)


def _mock_image(product: dict) -> Resolution:
    return Resolution.found(f"https://mock.local/img/{product['id']}.jpg", "roaster")


IMAGE_CHAIN: list = [AmazonPaapiImage(), RoasterOgImage()]
