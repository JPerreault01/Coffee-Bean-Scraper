# coffee-bean-profile

WordPress plugin that renders a full flavor profile card for any tracked coffee bean.

## What it renders

- **Radar chart** — 5-axis flavor fingerprint (Acidity, Body, Sweetness, Bitterness, Roast Intensity)
- **Flavor dimension bars** — horizontal bar visualization of each dimension
- **Spec table** — process method, weight, price/oz, best brew methods
- **Flavor note tags** — from products.json
- **Current price** — pulled live from SQLite price_history
- **Affiliate CTA button**
- **Similar beans panel** — 3 nearest neighbors by Euclidean distance across all 5 flavor dimensions, each with a mini radar chart

## Installation

1. Copy the plugin folder to WordPress:
   ```bash
   cp -r wordpress-plugins/coffee-bean-profile/ /var/www/coffeebeans/wp-content/plugins/
   ```

2. Activate in **WordPress Admin → Plugins → Coffee Bean Profile**

3. Sync your products to SQLite (required before any profiles will render):
   ```bash
   /opt/venv/bin/python3 /opt/scrapers/sync_products.py
   ```

4. Verify the database is readable by www-data:
   ```bash
   chown root:coffeebeans /opt/data/prices.db
   chmod 664 /opt/data/prices.db
   ```

## Usage

Add to any post or page:

```
[coffee_bean_profile product_id="lavazza-super-crema"]
```

The `product_id` must match an `id` in `products.json` that has been synced to the database.

## Keeping products in sync

Run `sync_products.py` whenever `products.json` is updated:

```bash
/opt/venv/bin/python3 /opt/scrapers/sync_products.py
```

This is safe to run repeatedly — it upserts, never duplicates.

Optionally add to cron after the scraper to keep product metadata current:

```
30 6 * * * root /opt/venv/bin/python3 /opt/scrapers/sync_products.py >> /opt/data/scraper.log 2>&1
```

## Flavor vector fields (in products.json)

Each product requires these 5 integer fields (1–5 scale):

| Field | What it measures |
|---|---|
| `acidity` | Brightness / tartness |
| `body` | Weight / mouthfeel |
| `sweetness` | Perceived sweetness |
| `bitterness` | Bitterness at standard extraction |
| `roast_intensity` | Roast level expression |

Products without these fields will render but without the radar chart and similar beans panel.

## Similar beans algorithm

Euclidean distance across all 5 flavor dimensions. The 3 beans with the smallest distance to the current product are shown. This scales to any catalog size — 20 products or 2000.

## Dependencies

- Chart.js 4.4.2 (loaded from CDN — shared handle with `coffee-price-chart` plugin if both active)
- PHP PDO SQLite extension (included in PHP 8.2 standard install)
