#!/usr/bin/env bash
#
# scrapers/create_beans_wpcli.sh
#
# Creates bean CPT posts from products.json via WP-CLI on the VPS.
# Requires: WP-CLI in PATH, Python 3, products.json alongside this script.
#
# Usage (VPS bash):
#   bash /opt/scrapers/create_beans_wpcli.sh [--dry-run] [--wp-path=/path/to/wordpress]
#
# Flags:
#   --dry-run              Print what would be created without writing anything.
#   --wp-path=<path>       WordPress install directory (default: /var/www/coffeebeans).
#
# What this script sets per bean:
#   Post fields  : title, slug, post_status=draft, post_type=bean
#   Taxonomies   : roast-level, origin, process-method, brew-method, roaster, flavor-note
#                  (terms are created if they do not exist)
#   ACF fields   : product_id, weight_oz, amazon_affiliate_url, roaster_url,
#                  acidity, body, sweetness, bitterness, roast_intensity
#
# What this script leaves blank (filled later by scraper + review generator):
#   current_price, price_per_oz, verdict, rating, tasting_notes,
#   whos_for, whos_not_for, price_analysis, last_reviewed
#
# Skips any bean where a post with that slug already exists.

set -euo pipefail

DRY_RUN=false
WP_PATH="/var/www/coffeebeans"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for arg in "$@"; do
    case "$arg" in
        --dry-run)       DRY_RUN=true ;;
        --wp-path=*)     WP_PATH="${arg#*=}" ;;
    esac
done

export DRY_RUN WP_PATH SCRIPT_DIR

python3 - <<'PYEOF'
import json
import os
import re
import subprocess
import sys

dry_run  = os.environ['DRY_RUN'] == 'true'
wp_path  = os.environ['WP_PATH']
script_dir = os.environ['SCRIPT_DIR']

products_file = os.path.join(script_dir, 'products.json')
if not os.path.exists(products_file):
    print(f'ERROR: {products_file} not found', file=sys.stderr)
    sys.exit(1)

with open(products_file) as f:
    products = json.load(f)

# ACF field key map (from group_bean_specs.json) — needed so ACF recognises meta values.
ACF_KEYS = {
    'product_id':            'field_product_id',
    'weight_oz':             'field_weight_oz',
    'amazon_affiliate_url':  'field_amazon_affiliate_url',
    'roaster_url':           'field_roaster_url',
    'acidity':               'field_acidity',
    'body':                  'field_body',
    'sweetness':             'field_sweetness',
    'bitterness':            'field_bitterness',
    'roast_intensity':       'field_roast_intensity',
}


def wp(*args):
    """Run a WP-CLI command. In dry-run mode, print it and return empty string."""
    cmd = ['wp', f'--path={wp_path}'] + [str(a) for a in args]
    if dry_run:
        print(f'  [DRY RUN] {" ".join(cmd)}')
        return ''
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f'  WARN: {result.stderr.strip()}', file=sys.stderr)
    return result.stdout.strip()


def post_exists(slug):
    """Return True if a bean post with this slug already exists."""
    cmd = ['wp', f'--path={wp_path}', 'post', 'list',
           '--post_type=bean', f'--post_name={slug}',
           '--fields=ID', '--format=count']
    result = subprocess.run(cmd, capture_output=True, text=True)
    count = result.stdout.strip()
    return count.isdigit() and int(count) > 0


def set_acf(post_id, field_name, value):
    """Set an ACF field via post meta (value key + ACF _field reference key)."""
    wp('post', 'meta', 'update', post_id, field_name, str(value))
    wp('post', 'meta', 'update', post_id, f'_{field_name}', ACF_KEYS[field_name])


def parse_origins(origin_str):
    """
    Split 'Brazil, Colombia, Indonesia blend' → ['Brazil', 'Colombia', 'Indonesia'].
    Strips trailing ' blend' and '(single origin)'.
    """
    if not origin_str:
        return []
    cleaned = origin_str.strip()
    cleaned = re.sub(r'\s*\(single origin\)', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+blend$', '', cleaned, flags=re.IGNORECASE)
    return [p.strip() for p in cleaned.split(',') if p.strip()]


created = 0
skipped = 0

for product in products:
    pid   = product['id']
    title = product['name']
    slug  = pid  # product IDs are already slug-form

    print(f'\n→ {title}  (slug: {slug})')

    # Skip if a bean with this slug already exists
    if not dry_run and post_exists(slug):
        print(f'  SKIP — post with slug "{slug}" already exists')
        skipped += 1
        continue

    # Create the post
    if dry_run:
        print(f'  [DRY RUN] wp post create --post_type=bean --post_title="{title}" --post_name={slug} --post_status=draft --porcelain')
        post_id = 'DRY_RUN_ID'
    else:
        post_id_raw = wp(
            'post', 'create',
            '--post_type=bean',
            f'--post_title={title}',
            f'--post_name={slug}',
            '--post_status=draft',
            '--porcelain',
        )
        if not post_id_raw.isdigit():
            print(f'  ERROR: wp post create returned unexpected output: {post_id_raw!r}', file=sys.stderr)
            continue
        post_id = int(post_id_raw)
        print(f'  Created post ID: {post_id}')

    # ── Taxonomy terms ──────────────────────────────────────────────────────

    # roast-level
    if product.get('roast_level'):
        wp('post', 'term', 'set', post_id, 'roast-level',
           product['roast_level'], '--by=name', '--create-terms')
        print(f'  roast-level:    {product["roast_level"]}')

    # origin (parsed from origin string — splits multi-origin values)
    origins = parse_origins(product.get('origin', ''))
    if origins:
        wp('post', 'term', 'set', post_id, 'origin', *origins, '--by=name', '--create-terms')
        print(f'  origin:         {", ".join(origins)}')

    # process-method
    if product.get('process_method'):
        wp('post', 'term', 'set', post_id, 'process-method',
           product['process_method'], '--by=name', '--create-terms')
        print(f'  process-method: {product["process_method"]}')

    # brew-method
    if product.get('best_brew_methods'):
        wp('post', 'term', 'set', post_id, 'brew-method',
           *product['best_brew_methods'], '--by=name', '--create-terms')
        print(f'  brew-method:    {", ".join(product["best_brew_methods"])}')

    # roaster (brand field)
    if product.get('brand'):
        wp('post', 'term', 'set', post_id, 'roaster',
           product['brand'], '--by=name', '--create-terms')
        print(f'  roaster:        {product["brand"]}')

    # flavor-note
    if product.get('flavor_notes'):
        wp('post', 'term', 'set', post_id, 'flavor-note',
           *product['flavor_notes'], '--by=name', '--create-terms')
        print(f'  flavor-note:    {", ".join(product["flavor_notes"])}')

    # ── ACF fields (static product data only) ──────────────────────────────

    # product_id (links to prices.db and scraper)
    set_acf(post_id, 'product_id', pid)
    print(f'  ACF product_id:   {pid}')

    # weight_oz
    if product.get('weight_oz') is not None:
        set_acf(post_id, 'weight_oz', product['weight_oz'])
        print(f'  ACF weight_oz:    {product["weight_oz"]}')

    # amazon_affiliate_url — built from ASIN + affiliate_tag
    asin = product.get('amazon_asin')
    tag  = product.get('affiliate_tag')
    if asin and tag:
        affiliate_url = f'https://www.amazon.com/dp/{asin}?tag={tag}'
        set_acf(post_id, 'amazon_affiliate_url', affiliate_url)
        print(f'  ACF amazon_url:   {affiliate_url}')

    # roaster_url (direct-roaster products without an ASIN)
    if product.get('roaster_url'):
        set_acf(post_id, 'roaster_url', product['roaster_url'])
        print(f'  ACF roaster_url:  {product["roaster_url"]}')

    # Sensory scores (static from products.json — radar chart + sensory profile bars)
    for field in ('acidity', 'body', 'sweetness', 'bitterness'):
        if product.get(field) is not None:
            set_acf(post_id, field, product[field])
    if product.get('roast_intensity') is not None:
        set_acf(post_id, 'roast_intensity', product['roast_intensity'])
    print(f'  ACF sensory:      acidity={product.get("acidity")} body={product.get("body")} '
          f'sweetness={product.get("sweetness")} bitterness={product.get("bitterness")} '
          f'roast_intensity={product.get("roast_intensity")}')

    created += 1

# Summary
print(f'\n{"─" * 50}')
if dry_run:
    total = len(products) - skipped
    print(f'DRY RUN complete — would create {total} bean(s), skip {skipped}.')
    print('Re-run without --dry-run to write to WordPress.')
else:
    print(f'Done — created: {created}, skipped (already existed): {skipped}.')

PYEOF
