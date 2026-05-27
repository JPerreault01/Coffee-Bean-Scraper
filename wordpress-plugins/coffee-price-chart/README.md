# Coffee Price Chart — WordPress Plugin

Displays a Chart.js price history chart and data table for tracked coffee products. Data is read from the SQLite database at `/opt/data/prices.db`.

## Installation

1. Copy this directory to your WordPress plugins folder:

```bash
cp -r wordpress-plugins/coffee-price-chart /var/www/coffeebeans/wp-content/plugins/
```

2. Give the web server read access to the SQLite database:

```bash
chown www-data:www-data /opt/data/prices.db
chmod 644 /opt/data/prices.db
```

3. Activate the plugin in **WP Admin → Plugins → Coffee Price Chart → Activate**.

## Usage

Add the shortcode to any page or post:

```
[coffee_price_chart product_id="lavazza-super-crema"]
```

The `product_id` must match an `id` value in `products.json` and have at least one row in the `price_history` table.

## What it displays

- **Line chart** (Chart.js 4.4.2) with two y-axes:
  - Left axis: daily average price in USD
  - Right axis: daily average price-per-oz in USD (dashed line)
  - Horizontal annotation at current price
- **Price history table** showing date, price, and price/oz for the last 90 days

## Dependencies

All loaded from CDN (no npm required):
- `chart.js@4.4.2`
- `chartjs-plugin-annotation@3.0.1`

Scripts are deferred and only loaded on pages where the shortcode is used.

## PHP requirements

- PHP 8.0+
- `pdo_sqlite` extension enabled (standard on most hosts)

Verify with: `php -m | grep pdo_sqlite`

## Troubleshooting

**Chart shows "No price history available"**
- Run `price_scraper.py` at least once to populate the database
- Check that `product_id` in the shortcode matches exactly the `id` in `products.json`

**Permission denied reading database**
- Run: `chown www-data:www-data /opt/data/prices.db && chmod 644 /opt/data/prices.db`

**PDO SQLite not available**
- Install: `apt install php8.2-sqlite3` then `systemctl restart php8.2-fpm`
