# scrapers/upload_taxonomy_images.py
"""
Upload staged taxonomy images to WordPress and attach them to their terms.

Reads data/image_manifest.json (produced by fetch_taxonomy_images.py). For each
{taxonomy}:{term} entry it:
  1. resolves the term_id on the live site via the REST API (slug, then search),
  2. SKIPS if that term already carries a cbi_hero_image_id (idempotent),
  3. POSTs the optimized .webp to /wp-json/wp/v2/media,
  4. sets alt text + an attribution caption on the new media item,
  5. writes the media id to the term meta cbi_hero_image_id via REST,
  6. records wp_media_id / wp_term_id back into the manifest so re-runs are cheap.

Auth is a WordPress Application Password (Basic auth over HTTPS). Needs, in
/opt/.env (or repo .env):
    WP_API_BASE=https://coffeebeanindex.com
    WP_USERNAME=your-admin-login
    WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx     # Users -> Profile -> Application Passwords

The term-meta write requires cbi_hero_image_id to be registered with
show_in_rest (see functions.php, cbi_register_term_hero_meta) and an editor/
admin account.

Usage:
    python scrapers/upload_taxonomy_images.py --dry-run     # show plan, change nothing
    python scrapers/upload_taxonomy_images.py
    python scrapers/upload_taxonomy_images.py --force        # re-upload even if term has an image

Dependencies: requests.
"""

from __future__ import annotations

import argparse
import logging
import mimetypes
import sys
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

_SCRAPERS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRAPERS_DIR.parent
sys.path.insert(0, str(_REPO_ROOT))

from scrapers.image_utils import attribution_line, load_manifest, save_manifest, slugify  # noqa: E402
from scrapers.resolvers.base import load_env  # noqa: E402

MANIFEST_FILE = _REPO_ROOT / "data" / "image_manifest.json"
TERM_META_KEY = "cbi_hero_image_id"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


class WPClient:
    """Thin REST wrapper around the handful of endpoints we need."""

    def __init__(self, base: str, user: str, app_password: str):
        self.base = base.rstrip("/")
        self.api = f"{self.base}/wp-json/wp/v2"
        self.auth = HTTPBasicAuth(user, app_password)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "coffeebeanindex-uploader/1.0"})

    # -- terms -----------------------------------------------------------
    def find_term(self, taxonomy: str, term: str) -> dict | None:
        """The term object for a name/slug, or None. REST base for these
        taxonomies equals the taxonomy key (no rest_base override)."""
        endpoint = f"{self.api}/{taxonomy}"
        for params in ({"slug": slugify(term)}, {"search": term}):
            try:
                resp = self.session.get(endpoint, params=params, auth=self.auth, timeout=20)
            except requests.RequestException as exc:
                log.warning("Term lookup error (%s): %s", taxonomy, exc)
                return None
            if resp.status_code != 200:
                continue
            results = resp.json()
            if isinstance(results, list) and results:
                # On a name search prefer an exact (case-insensitive) match.
                want = slugify(term)
                for r in results:
                    if slugify(r.get("slug", "")) == want or slugify(r.get("name", "")) == want:
                        return r
                return results[0]
        return None

    def term_hero_id(self, term_obj: dict) -> int:
        meta = term_obj.get("meta") or {}
        try:
            return int(meta.get(TERM_META_KEY) or 0)
        except (TypeError, ValueError):
            return 0

    def set_term_hero(self, taxonomy: str, term_id: int, media_id: int) -> bool:
        endpoint = f"{self.api}/{taxonomy}/{term_id}"
        resp = self.session.post(
            endpoint, json={"meta": {TERM_META_KEY: media_id}}, auth=self.auth, timeout=20
        )
        if resp.status_code in (200, 201):
            confirmed = self.term_hero_id(resp.json())
            if confirmed == media_id:
                return True
            log.error("Term %s/%s meta did not persist (got %r). Is %s registered "
                      "with show_in_rest? See functions.php.", taxonomy, term_id, confirmed, TERM_META_KEY)
            return False
        log.error("Term meta write failed (%s): HTTP %s %s", endpoint, resp.status_code, resp.text[:200])
        return False

    # -- media -----------------------------------------------------------
    def upload_media(self, path: Path, alt_text: str, caption: str, title: str) -> int | None:
        mime = mimetypes.guess_type(path.name)[0] or "image/webp"
        headers = {
            "Content-Disposition": f'attachment; filename="{path.name}"',
            "Content-Type": mime,
        }
        try:
            resp = self.session.post(
                f"{self.api}/media", data=path.read_bytes(), headers=headers, auth=self.auth, timeout=60
            )
        except requests.RequestException as exc:
            log.error("Media upload error (%s): %s", path.name, exc)
            return None
        if resp.status_code not in (200, 201):
            log.error("Media upload failed (%s): HTTP %s %s", path.name, resp.status_code, resp.text[:200])
            return None
        media_id = int(resp.json().get("id"))

        # Second call sets the searchable/displayed metadata on the attachment.
        meta_resp = self.session.post(
            f"{self.api}/media/{media_id}",
            json={"alt_text": alt_text, "caption": caption, "title": title, "description": caption},
            auth=self.auth, timeout=20,
        )
        if meta_resp.status_code not in (200, 201):
            log.warning("Media %s uploaded but alt/caption update returned HTTP %s",
                        media_id, meta_resp.status_code)
        return media_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload staged taxonomy images to WordPress and attach to terms.")
    parser.add_argument("--manifest", default=str(MANIFEST_FILE), help="path to image_manifest.json")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, change nothing on the site")
    parser.add_argument("--force", action="store_true", help="upload even if the term already has a hero image")
    args = parser.parse_args()

    env = load_env()
    base = env.get("WP_API_BASE", "").strip()
    user = env.get("WP_USERNAME", "").strip()
    app_pw = env.get("WP_APP_PASSWORD", "").strip()
    if not args.dry_run and not (base and user and app_pw):
        log.error("Set WP_API_BASE, WP_USERNAME, WP_APP_PASSWORD in /opt/.env (or repo .env).")
        sys.exit(2)

    manifest = load_manifest(args.manifest)
    if not manifest:
        log.error("Empty/missing manifest at %s - run fetch_taxonomy_images.py first.", args.manifest)
        sys.exit(1)

    client = WPClient(base or "https://example.invalid", user, app_pw) if (base and user and app_pw) else None

    uploaded = skipped = failed = 0

    for key, meta in manifest.items():
        taxonomy, _, term = key.partition(":")
        local_path = Path(meta.get("local_path", ""))
        alt_text = meta.get("alt_text", "")
        caption = attribution_line(meta)

        if not local_path.exists():
            log.warning("SKIP  %s - staged file missing: %s", key, local_path)
            skipped += 1
            continue

        if args.dry_run:
            log.info("PLAN  %s -> upload %s | alt=%r | %s", key, local_path.name, alt_text, caption)
            continue

        # Manifest-level idempotency (fast path, no network).
        if meta.get("wp_media_id") and not args.force:
            log.info("SKIP  %s - already uploaded (media #%s)", key, meta["wp_media_id"])
            skipped += 1
            continue

        term_obj = client.find_term(taxonomy, term)
        if not term_obj:
            log.warning("SKIP  %s - no matching term on site (create it first)", key)
            skipped += 1
            continue
        term_id = int(term_obj.get("id"))

        # Site-level idempotency: the term already has a hero image.
        if client.term_hero_id(term_obj) and not args.force:
            log.info("SKIP  %s - term #%s already has hero image #%s",
                     key, term_id, client.term_hero_id(term_obj))
            meta["wp_term_id"] = term_id
            meta["wp_media_id"] = client.term_hero_id(term_obj)
            skipped += 1
            continue

        media_id = client.upload_media(local_path, alt_text, caption, meta.get("title") or term)
        if not media_id:
            failed += 1
            continue

        if client.set_term_hero(taxonomy, term_id, media_id):
            meta["wp_media_id"] = media_id
            meta["wp_term_id"] = term_id
            save_manifest(args.manifest, manifest)  # checkpoint
            log.info("DONE  %s -> media #%s attached to term #%s", key, media_id, term_id)
            uploaded += 1
        else:
            failed += 1

    log.info("=" * 60)
    if args.dry_run:
        log.info("DRY RUN - %d entries would be processed.", len(manifest))
    else:
        log.info("Upload complete - %d uploaded, %d skipped, %d failed.", uploaded, skipped, failed)


if __name__ == "__main__":
    main()
