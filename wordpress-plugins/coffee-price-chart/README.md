# coffee-price-chart

WordPress plugin that renders a Chart.js price history widget for tracked coffee beans.

## Installation

1. Copy the `coffee-price-chart/` folder to `/var/www/coffeebeans/wp-content/plugins/`
2. Activate in **WordPress Admin → Plugins**
3. Ensure `/opt/data/prices.db` exists and is readable by the `www-data` user:
   ```bash
   chown www-data:www-data /opt/data/prices.db
   chmod 640 /opt/data/prices.db
   ```

## Usage

Add the shortcode to any post or page:

```
[coffee_price_chart product_id="lavazza-super-crema"]
```

The `product_id` must match an ID in `products.json` that has price history in the SQLite database.

## What it renders

- **Line chart** with two axes:
  - Price over time (red line, left axis)
  - Price-per-oz over time (blue dashed line, right axis)
  - Horizontal annotation at the current price
- **Price history table** below the chart: date, price, price/oz for the last 90 days
- Mobile responsive (horizontal scroll on small screens)

## Dependencies (loaded from CDN)

- Chart.js 4.4.2
- chartjs-plugin-annotation 3.0.1

No additional WordPress plugin dependencies required.

## SQLite permissions

The web server (`www-data`) needs read access to the SQLite file. The scraper writes to it as `root`. Recommended setup:

```bash
# Create a shared group
groupadd coffeebeans
usermod -aG coffeebeans www-data
usermod -aG coffeebeans root

# Set group ownership
chown root:coffeebeans /opt/data/prices.db
chmod 664 /opt/data/prices.db
chown root:coffeebeans /opt/data/
chmod 775 /opt/data/
```
