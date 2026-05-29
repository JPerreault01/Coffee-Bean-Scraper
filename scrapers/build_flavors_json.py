import json
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PRODUCTS_FILE = REPO_ROOT / "scrapers" / "products.json"
OUTPUT_FILE = REPO_ROOT / "data" / "flavors.json"

NOTE_FAMILIES = {
    # Chocolate
    "dark chocolate": "Chocolate",
    "milk chocolate": "Chocolate",
    "cocoa": "Chocolate",
    "bittersweet chocolate": "Chocolate",
    "chocolate": "Chocolate",
    # Caramel / Sweet
    "caramel": "Caramel & Sweet",
    "brown sugar": "Caramel & Sweet",
    "honey": "Caramel & Sweet",
    "molasses": "Caramel & Sweet",
    "syrup": "Caramel & Sweet",
    "sweet": "Caramel & Sweet",
    "smooth": "Caramel & Sweet",
    # Fruity
    "blueberry": "Fruity",
    "cherry": "Fruity",
    "citrus": "Fruity",
    "dried fruit": "Fruity",
    "berry": "Fruity",
    "stone fruit": "Fruity",
    "mild citrus": "Fruity",
    "lemon": "Fruity",
    "orange": "Fruity",
    # Nutty
    "hazelnut": "Nutty",
    "almond": "Nutty",
    "walnut": "Nutty",
    "nuts": "Nutty",
    "nutty": "Nutty",
    # Earthy / Savory
    "earthy": "Earthy & Savory",
    "cedar": "Earthy & Savory",
    "tobacco": "Earthy & Savory",
    "leather": "Earthy & Savory",
    "wood": "Earthy & Savory",
    "full body": "Earthy & Savory",
    "herbal": "Earthy & Savory",
    # Floral
    "jasmine": "Floral",
    "rose": "Floral",
    "floral": "Floral",
    "lavender": "Floral",
    # Spice
    "cinnamon": "Spice",
    "clove": "Spice",
    "pepper": "Spice",
    "spice": "Spice",
    # Roast
    "smoky": "Roast",
    "toasty": "Roast",
    "charred": "Roast",
    "ash": "Roast",
    "bold": "Roast",
    "intense": "Roast",
    # Light / Clean
    "light body": "Light & Clean",
    "clean": "Light & Clean",
    "bright": "Light & Clean",
    "low acid": "Light & Clean",
    "mild": "Light & Clean",
    "balanced": "Light & Clean",
    "lingering finish": "Roast",
}

FAMILIES_ORDER = [
    "Chocolate",
    "Caramel & Sweet",
    "Fruity",
    "Nutty",
    "Earthy & Savory",
    "Floral",
    "Spice",
    "Roast",
    "Light & Clean",
]


def build_affiliate_url(product):
    asin = product.get("amazon_asin")
    tag = product.get("affiliate_tag")
    if asin:
        if tag:
            return f"https://www.amazon.com/dp/{asin}?tag={tag}"
        return f"https://www.amazon.com/dp/{asin}"
    roaster_url = product.get("roaster_url")
    if roaster_url:
        return roaster_url
    return None


def main():
    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        products = json.load(f)

    unmapped = []
    output_products = []

    for p in products:
        notes = p.get("flavor_notes", [])
        seen_families = []

        for note in notes:
            family = NOTE_FAMILIES.get(note.lower())
            if family is not None:
                if family not in seen_families:
                    seen_families.append(family)
            else:
                unmapped.append(note)

        if not seen_families:
            seen_families = ["Other"]

        affiliate_url = build_affiliate_url(p)

        entry = {
            "id": p["id"],
            "name": p["name"],
            "brand": p["brand"],
            "roast_level": p["roast_level"],
            "origin": p["origin"],
            "best_brew_methods": p.get("best_brew_methods", []),
            "flavor_notes": notes,
            "note_families": seen_families,
            "scores": {
                "acidity": p["acidity"],
                "body": p["body"],
                "sweetness": p["sweetness"],
                "bitterness": p["bitterness"],
                "roast_intensity": p["roast_intensity"],
            },
            "review_slug": p["id"],
        }
        if affiliate_url is not None:
            entry["affiliate_url"] = affiliate_url

        output_products.append(entry)

    output = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        "families": FAMILIES_ORDER,
        "products": output_products,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"Written {len(output_products)} products to {OUTPUT_FILE}")
    if unmapped:
        unique_unmapped = sorted(set(unmapped))
        print(
            f"{len(unmapped)} unmapped note occurrence(s), "
            f"{len(unique_unmapped)} unique: {unique_unmapped}"
        )
    else:
        print("All notes mapped successfully.")


if __name__ == "__main__":
    main()
