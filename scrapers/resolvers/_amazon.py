# scrapers/resolvers/_amazon.py
"""
Amazon Product Advertising API 5 (PA-API) GetItems — SigV4 signing.

Canonical home for the SigV4 code that previously lived inline in
fetch_bean_images.py. Both the price and image PA-API providers call
get_items() here; the legacy image script imports get_image() so there is a
single signing implementation in the repo.

This module only signs and sends. Gating (PAAPI_ENABLED + creds present) lives
in the providers; callers wrap get_items() in fetch_with_retry so a 429/503 or
network blip is retried and a hard failure never raises out of a resolver.

PA-API requires an APPROVED Associates account with qualifying sales. Until
then PAAPI_ENABLED stays false and none of this code runs.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json

import requests

PAAPI_HOST = "webservices.amazon.com"
PAAPI_REGION = "us-east-1"
PAAPI_SERVICE = "ProductAdvertisingAPI"
PAAPI_PATH = "/paapi5/getitems"
PAAPI_TARGET = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.GetItems"

# Resource sets — request only what each field needs.
PRICE_RESOURCES = [
    "Offers.Listings.Price",
    "Offers.Listings.SavingBasis",
]
IMAGE_RESOURCES = [
    "Images.Primary.Large",
    "Images.Primary.Medium",
]


def has_credentials(env: dict) -> bool:
    return all(env.get(k) for k in ("AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG"))


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signature_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    k = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k = _sign(k, region)
    k = _sign(k, service)
    return _sign(k, "aws4_request")


def get_items(asin: str, resources: list[str], env: dict, *, timeout: int = 15) -> list[dict]:
    """Call PA-API GetItems for a single ASIN.

    Returns the list of item dicts (possibly empty if the ASIN is dead/unknown).
    Raises on a network error or non-200 response so fetch_with_retry can retry;
    an empty list is a clean "fetched fine, nothing there" signal, not an error.
    """
    access_key = env.get("AMAZON_ACCESS_KEY", "")
    secret_key = env.get("AMAZON_SECRET_KEY", "")
    partner_tag = env.get("AMAZON_PARTNER_TAG", "")
    if not (access_key and secret_key and partner_tag and asin):
        raise RuntimeError("PA-API called without credentials or ASIN")

    payload = json.dumps(
        {
            "ItemIds": [asin],
            "Resources": resources,
            "PartnerTag": partner_tag,
            "PartnerType": "Associates",
            "Marketplace": "www.amazon.com",
        },
        separators=(",", ":"),
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    canonical_headers = (
        f"content-encoding:amz-1.0\nhost:{PAAPI_HOST}\n"
        f"x-amz-date:{amz_date}\nx-amz-target:{PAAPI_TARGET}\n"
    )
    signed_headers = "content-encoding;host;x-amz-date;x-amz-target"
    payload_hash = hashlib.sha256(payload.encode()).hexdigest()
    canonical_req = f"POST\n{PAAPI_PATH}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    algorithm = "AWS4-HMAC-SHA256"
    cred_scope = f"{date_stamp}/{PAAPI_REGION}/{PAAPI_SERVICE}/aws4_request"
    string_to_sign = (
        f"{algorithm}\n{amz_date}\n{cred_scope}\n"
        f"{hashlib.sha256(canonical_req.encode()).hexdigest()}"
    )
    sig_key = _signature_key(secret_key, date_stamp, PAAPI_REGION, PAAPI_SERVICE)
    signature = hmac.new(sig_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    auth = (
        f"{algorithm} Credential={access_key}/{cred_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    resp = requests.post(
        f"https://{PAAPI_HOST}{PAAPI_PATH}",
        data=payload,
        timeout=timeout,
        headers={
            "content-encoding": "amz-1.0",
            "content-type": "application/json; charset=utf-8",
            "host": PAAPI_HOST,
            "x-amz-date": amz_date,
            "x-amz-target": PAAPI_TARGET,
            "Authorization": auth,
        },
    )
    if resp.status_code != 200:
        raise RuntimeError(f"PA-API HTTP {resp.status_code} for {asin}: {resp.text[:200]}")
    return resp.json().get("ItemsResult", {}).get("Items", [])


def get_price(asin: str, env: dict, *, timeout: int = 15) -> float | None:
    """Lowest listing price for an ASIN via PA-API, or None if no offer."""
    items = get_items(asin, PRICE_RESOURCES, env, timeout=timeout)
    if not items:
        return None
    listings = items[0].get("Offers", {}).get("Listings", [])
    for listing in listings:
        amount = listing.get("Price", {}).get("Amount")
        if amount:
            return float(amount)
    return None


def get_image(asin: str, env: dict, *, timeout: int = 15) -> str | None:
    """Primary product image URL for an ASIN via PA-API, or None."""
    items = get_items(asin, IMAGE_RESOURCES, env, timeout=timeout)
    if not items:
        return None
    imgs = items[0].get("Images", {}).get("Primary", {})
    for size in ("Large", "Medium"):
        url = imgs.get(size, {}).get("URL")
        if url:
            return url
    return None


def item_exists(asin: str, env: dict, *, timeout: int = 15) -> bool:
    """True if PA-API returns an item for the ASIN (used to validate ASINs)."""
    return bool(get_items(asin, IMAGE_RESOURCES, env, timeout=timeout))
