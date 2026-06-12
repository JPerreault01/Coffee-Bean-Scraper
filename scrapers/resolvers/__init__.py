# scrapers/resolvers/__init__.py
"""
Bean data resolvers — graceful, chain-based field resolution.

Each field walks an ordered provider chain (see base.resolve_field). PA-API
providers lead every chain but stay disabled behind PAAPI_ENABLED + creds, so
roaster-only resolution works today and Amazon activates with a single .env
change once the Associates account is approved.

Public surface:
    resolve_field, build_context, Resolution, load_env
    CHAINS["price" | "image" | "asin"]
"""

from .asin import ASIN_CHAIN
from .base import Resolution, build_context, load_env, resolve_field
from .image import IMAGE_CHAIN
from .price import PRICE_CHAIN

CHAINS: dict[str, list] = {
    "price": PRICE_CHAIN,
    "image": IMAGE_CHAIN,
    "asin": ASIN_CHAIN,
}

FIELDS = tuple(CHAINS.keys())

__all__ = [
    "Resolution",
    "build_context",
    "load_env",
    "resolve_field",
    "CHAINS",
    "FIELDS",
]
