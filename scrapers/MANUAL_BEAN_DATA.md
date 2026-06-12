# Manual bean data: ASINs + images

When the automated pipeline can't resolve a bean's Amazon ASIN or product image,
pull them by hand and record them with `add_manual_bean_data.py`. The script writes
the ASIN into `products.json` and stages the image in the local image cache. This doc
covers running it and the exact deploy sequence to get the data live on the VPS.

The script never runs git and never touches a bean you didn't name. If `products.json`
can't be parsed, it stops before writing anything.

---

## 1. Run the script (local, Windows)

### Single bean (default)

```powershell
python scrapers/add_manual_bean_data.py
```

It prompts for three things. Leave any optional field blank to skip it:

- **Bean id** — must already exist in `products.json`. If it doesn't, the script prints
  the closest matching ids and exits without changing anything.
- **Amazon ASIN** — optional. Must be exactly 10 alphanumeric characters (e.g.
  `B001HTG4TW`). A bad ASIN is skipped with a reason; the rest still runs.
- **Local image file path** — optional. A `.jpg`/`.png`/`.gif`/`.webp` you saved
  manually. Must be a real image larger than 10 KB.

### Batch (CSV)

```powershell
python scrapers/add_manual_bean_data.py --csv new_asins.csv
```

CSV columns, in order: `id,asin,image_path`. A header row (`id,asin,image_path`) is
optional and auto-skipped. Blank fields per row are skipped, so you can supply just an
ASIN, just an image, or both:

```csv
id,asin,image_path
lavazza-super-crema,B001HTG4TW,C:\Users\Jacks\Pictures\beans\lavazza.jpg
illy-classico-medium,B000YDOIOS,
volcanica-kona-peaberry,,C:\Users\Jacks\Pictures\beans\volcanica-kona.png
```

### Where to put image files

Anywhere on your machine — point the script at the full path. It copies the file into
`scrapers/.image-cache/{id}.jpg` (always saved as `.jpg`; the VPS detects the true
format on import) and records the bean in `scrapers/.image-cache/manifest.json`.

### What it changes

- **ASIN** -> the matching bean object in `scrapers/products.json` (`amazon_asin`).
  Only that one bean's line changes; key order and the rest of the file are preserved.
- **Image** -> copied to `scrapers/.image-cache/{id}.jpg`, and the bean is upserted
  into `scrapers/.image-cache/manifest.json` with the **VPS path** the file will live
  at after you scp it (`/opt/scrapers/scrapers/.image-cache/{id}.jpg`).

At the end it prints counts (ASINs written, images cached, skipped with reasons) and a
literal next-steps block. Those steps are below.

---

## 2. Deploy sequence (do this yourself after running the script)

### Step 1 — Commit and push products.json (ASINs only)

`products.json` is committed; the ASIN change rides to the VPS via git.

```powershell
git add scrapers/products.json
git commit -m "data: add manual Amazon ASINs for unresolved beans"
git push
```

### Step 2 — Pull products.json on the VPS

```bash
ssh cbi-prod
cd /opt/scrapers/scrapers
wget -O products.json \
  https://raw.githubusercontent.com/JPerreault01/Coffee-Bean-Scraper/main/scrapers/products.json
```

### Step 3 — scp the images AND the manifest to the VPS

> **IMPORTANT: images do NOT reach the VPS via git.** `scrapers/.image-cache/` is
> gitignored, so manually-added images live only in your local cache. You must copy
> both the image file(s) and the updated `manifest.json` up by hand, or the featured
> image step on the VPS will skip those beans (the manifest points at files that
> aren't there yet).

Run from the repo root in PowerShell, one bean id per `scp` (replace `<id>`):

```powershell
scp scrapers/.image-cache/manifest.json `
  cbi-prod:/opt/scrapers/scrapers/.image-cache/manifest.json
scp scrapers/.image-cache/<id>.jpg `
  cbi-prod:/opt/scrapers/scrapers/.image-cache/<id>.jpg
```

For several images at once, list them:

```powershell
scp scrapers/.image-cache/manifest.json `
    scrapers/.image-cache/lavazza-super-crema.jpg `
    scrapers/.image-cache/volcanica-kona-peaberry.jpg `
  cbi-prod:/opt/scrapers/scrapers/.image-cache/
```

The manifest values are `/opt/scrapers/scrapers/.image-cache/{id}.jpg`, so the scp
destination above must match exactly or `set_featured_images.php` won't find the files.

### Step 4 — Populate the ACF ASIN + affiliate URL on existing beans

> **`create_beans.php` SKIPS any bean whose slug already exists**, so re-running it does
> NOT update the ASIN on a bean that was already created. Use `update_bean_asins.php`
> instead. It reads `products.json`, finds each bean with an ASIN, and sets both
> `amazon_asin` and `amazon_affiliate_url`
> (`https://www.amazon.com/dp/{ASIN}?tag={affiliate_tag}`). Idempotent and safe to re-run.

```bash
cd /var/www/coffeebeans
wp eval-file /opt/scrapers/scrapers/update_bean_asins.php --allow-root
```

(If you only added images and no ASINs, skip this step.)

### Step 5 — Set featured images from the manifest

```bash
cd /var/www/coffeebeans
wp eval-file /opt/scrapers/scrapers/set_featured_images.php \
  /opt/scrapers/scrapers/.image-cache/manifest.json --allow-root
```

`set_featured_images.php` never overwrites an existing featured image, so it's safe to
re-run. (If you only added ASINs and no images, skip this step.)

### Step 6 — Flush cache and review

```bash
wp cache flush --allow-root
```

Then open the affected draft beans in WP admin and confirm the ASIN, affiliate link, and
featured image look right before you Publish.

---

## CSV column reference

| Column       | Required | Notes                                                        |
|--------------|----------|--------------------------------------------------------------|
| `id`         | yes      | Must exist in `products.json`. Unknown ids are skipped.      |
| `asin`       | no       | 10-char alphanumeric. Blank or invalid is skipped.           |
| `image_path` | no       | Full local path to a real image > 10 KB. Blank is skipped.   |

## Files involved

| File                                   | Role                                               |
|----------------------------------------|----------------------------------------------------|
| `scrapers/add_manual_bean_data.py`     | This tool. Writes ASIN + caches image (local).     |
| `scrapers/products.json`               | Source of truth. Committed. Gets the ASIN.         |
| `scrapers/.image-cache/{id}.jpg`       | Cached image. Gitignored. scp'd to the VPS.        |
| `scrapers/.image-cache/manifest.json`  | id -> VPS image path. Gitignored. scp'd to the VPS.|
| `scrapers/update_bean_asins.php`       | VPS: writes ASIN + affiliate URL ACF on existing beans. |
| `scrapers/set_featured_images.php`     | VPS: sets featured images from the manifest.       |
