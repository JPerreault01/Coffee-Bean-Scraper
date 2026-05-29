# Coffee Flavor Explorer — WordPress Plugin

Renders a filterable coffee bean discovery grid and per-product radar chart shortcode. Family filter buttons, note tag sub-filters, sort controls, and mini Chart.js radar charts — no build step required.

---

## Deployment

**1. Copy the plugin folder to the server:**

```bash
cp -r wordpress-plugins/coffee-flavor-explorer/ \
  /var/www/coffeebeans/wp-content/plugins/coffee-flavor-explorer/
```

**2. Generate and upload the flavor data file:**

```bash
# On local machine or VPS:
python scrapers/build_flavors_json.py

# Upload to WordPress uploads directory:
mkdir -p /var/www/coffeebeans/wp-content/uploads/coffee-data/
cp data/flavors.json /var/www/coffeebeans/wp-content/uploads/coffee-data/flavors.json
```

**3. Activate the plugin:**

WP Admin → Plugins → Coffee Flavor Explorer → Activate

**4. Create the explorer page:**

- Title: **Find Your Coffee**
- Slug: `find-your-coffee`
- Body: add the shortcode `[flavor_explorer]`

**5. Add profile charts to review pages:**

Insert `[coffee_profile id="product-id"]` anywhere in review content. Use the product's `id` field from `scrapers/products.json` (e.g. `lavazza-super-crema`).

---

## Updating flavor data

Re-run `python scrapers/build_flavors_json.py` and re-upload `data/flavors.json` to the uploads directory. No plugin changes needed.

```bash
python scrapers/build_flavors_json.py
cp data/flavors.json /var/www/coffeebeans/wp-content/uploads/coffee-data/flavors.json
```

---

## Shortcodes

| Shortcode | Description |
|---|---|
| `[flavor_explorer]` | Full filterable bean grid with family filters, note tags, sort, and mini radar charts |
| `[coffee_profile id="product-id"]` | Standalone 250×250px radar chart with flavor note tags |

---

## File structure

```
wordpress-plugins/coffee-flavor-explorer/
├── coffee-flavor-explorer.php   ← plugin registration, shortcodes
├── flavor-explorer.js           ← all widget logic (vanilla JS, no build step)
├── flavor-explorer.css          ← styles and CSS variables
└── README.md
```

---

## CSS customization

Override the CSS variables in your theme's `style.css` or Additional CSS (WP Admin → Appearance → Customize → Additional CSS):

```css
:root {
    --cfe-radar-fill:       rgba(139, 90, 43, 0.25);
    --cfe-radar-border:     rgba(139, 90, 43, 0.8);
    --cfe-tag-bg:           #f5f0eb;
    --cfe-tag-active-bg:    #8b5a2b;
    --cfe-card-border:      #e0d5c8;
}
```

---

## Requirements

- WordPress 5.0+
- PHP 7.4+ with `pdo_sqlite` (only needed if using the price chart plugin alongside this one)
- Chart.js 4.4.1 is loaded automatically from cdnjs when a shortcode is present — no manual enqueue needed
- No npm, no build step, no node_modules
