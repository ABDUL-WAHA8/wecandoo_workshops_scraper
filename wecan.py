

import csv
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd
from tqdm import tqdm

# ── Credentials (confirmed working) ──────────────────────
APP_ID  = "8HA1X9O9Y5"
API_KEY = "57fd369e98cb7055b68d273f418b74e0"
INDEX   = "production_ateliers"
BASE    = "https://wecandoo.fr"

# ── Files ─────────────────────────────────────────────────
OUTPUT_CSV  = "wecandoo_ateliers.csv"
OUTPUT_XLSX = "wecandoo_ateliers.xlsx"
LOG_FILE    = "wecandoo_scraper.log"

CSV_FIELDS = [
    "title", "short_title", "city", "district",
    "street", "house_number", "postcode", "neighbourhood",
    "full_address",
    "lat", "lng",
    "price", "category", "artisan", "duration_min",
    "min_persons", "max_persons", "rating_score",
    "reviews_count", "atelier_id", "lieu_id", "url",
]

ALGOLIA_HEADERS = {
    "Content-Type": "application/json",
    "Referer":      "https://wecandoo.fr/",
    "Origin":       "https://wecandoo.fr",
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
AGENT      = "Algolia%20for%20JavaScript%20(5.38.0)%3B%20Search%20(5.38.0)%3B%20Browser"
SEARCH_URL = (
    f"https://{APP_ID}-dsn.algolia.net/1/indexes/*/queries"
    f"?x-algolia-agent={AGENT}"
    f"&x-algolia-api-key={API_KEY}"
    f"&x-algolia-application-id={APP_ID}"
)


# ── Logging ───────────────────────────────────────────────

def log(msg: str):
    ts   = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    tqdm.write(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── CSV ───────────────────────────────────────────────────

def init_csv():
    if not Path(OUTPUT_CSV).exists():
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()
        log(f"Created {OUTPUT_CSV}")

def append_csv(row: dict):
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore").writerow(row)

def load_saved_ids() -> set:
    if not Path(OUTPUT_CSV).exists():
        return set()
    try:
        df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig", usecols=["atelier_id"])
        return set(df["atelier_id"].dropna().astype(str).tolist())
    except Exception:
        return set()


# ── Strip rank prefix: "1||Paris" → "Paris" ──────────────

def strip_rank(val) -> str:
    s = str(val).strip() if val else ""
    m = re.match(r"^\d+\|\|(.+)$", s)
    return m.group(1).strip() if m else s


# ── Normalize one Algolia hit ─────────────────────────────

def normalize(hit: dict) -> dict:
    city_district = hit.get("city_and_district", "")
    parts         = [p.strip() for p in city_district.split(",")]
    city          = parts[0] if parts else strip_rank(hit.get("ville", ""))
    district      = parts[1] if len(parts) > 1 else ""

    geoloc = hit.get("_geoloc") or {}
    lat    = geoloc.get("lat", "")
    lng    = geoloc.get("lng", "")

    page_url = hit.get("page_url", "")
    url      = BASE + page_url if page_url.startswith("/") else page_url

    return {
        "title":         hit.get("nom", ""),
        "short_title":   hit.get("short_title", ""),
        "city":          city,
        "district":      district,
        "street":        "",          # filled by reverse geocoding
        "house_number":  "",          # filled by reverse geocoding
        "postcode":      "",          # filled by reverse geocoding
        "neighbourhood": "",          # filled by reverse geocoding
        "full_address":  "",          # filled by reverse geocoding
        "lat":           lat,
        "lng":           lng,
        "price":         hit.get("prix", ""),
        "category":      strip_rank(hit.get("craft", "")),
        "artisan":       hit.get("artisan_nom_alternatif") or hit.get("artisan_nom", ""),
        "duration_min":  hit.get("duration", ""),
        "min_persons":   hit.get("nb_pers_min", ""),
        "max_persons":   hit.get("nb_pers_max", ""),
        "rating_score":  hit.get("note", ""),
        "reviews_count": hit.get("artisan_comment_count", ""),
        "atelier_id":    hit.get("atelier_id", ""),
        "lieu_id":       hit.get("lieu_id", ""),
        "url":           url,
    }


# ── STEP 1: Get city list ─────────────────────────────────

def get_cities() -> list[dict]:
    """
    Fetch all cities and their workshop counts from the facets API.
    Returns list of {city, count} sorted by count desc.
    """
    log("Fetching city list from facets API...")
    try:
        r = requests.get(
            f"{BASE}/api/facets/ville?filters=country:%27fr%27",
            headers={"Referer": BASE, "User-Agent": ALGOLIA_HEADERS["User-Agent"]},
            timeout=15,
        )
        if r.status_code == 200:
            data   = r.json()
            # Response is like: {"data": [{"value": "1||Paris", "count": 1200}, ...]}
            # or a flat list, or a dict — handle all shapes
            items  = data if isinstance(data, list) else data.get("data", data.get("facets", []))
            cities = []
            for item in items:
                raw   = item.get("value", item.get("label", item.get("name", "")))
                count = item.get("count", item.get("nb", 1))
                name  = strip_rank(raw)
                if name:
                    cities.append({"city": name, "raw": raw, "count": int(count)})
            cities.sort(key=lambda x: -x["count"])
            log(f"  Found {len(cities)} cities")
            return cities
    except Exception as e:
        log(f"  ⚠ Could not fetch cities: {e}")

    # Fallback: query Algolia for the ville facet
    log("  Falling back to Algolia facet query...")
    r = requests.post(SEARCH_URL, headers=ALGOLIA_HEADERS, json={
        "requests": [{
            "indexName":       INDEX,
            "query":           "",
            "hitsPerPage":     0,
            "facets":          ["ville"],
            "maxValuesPerFacet": 500,
        }]
    }, timeout=15)
    if r.status_code == 200:
        facets = r.json()["results"][0].get("facets", {}).get("ville", {})
        cities = [
            {"city": strip_rank(k), "raw": k, "count": v}
            for k, v in facets.items()
        ]
        cities.sort(key=lambda x: -x["count"])
        log(f"  Found {len(cities)} cities via Algolia facets")
        return cities

    log("  ⚠ Could not get city list. Will try a single global query.")
    return []


# ── STEP 2: Scrape Algolia city by city ──────────────────

def scrape_all_workshops(cities: list[dict], already_saved: set) -> list[dict]:
    """
    Query Algolia for each city. Each city has <1000 workshops so we
    never hit Algolia's result cap. Returns full list of normalized rows.
    """
    all_rows  = []
    seen_ids  = set(already_saved)   # avoid duplicates across cities

    BAR_FMT = (
        "{desc}: [{bar:25}] {percentage:3.0f}%  "
        "{n_fmt}/{total_fmt}  |  {remaining_s:.0f}s left  [{rate_fmt}]"
    )

    log(f"\nScraping Algolia for {len(cities)} cities...")

    with tqdm(total=len(cities), desc="Cities", unit="city",
              bar_format=BAR_FMT, file=sys.stdout,
              dynamic_ncols=True, colour="cyan") as city_bar:

        for c in cities:
            city_name = c["city"]
            raw_ville = c["raw"]

            r = requests.post(SEARCH_URL, headers=ALGOLIA_HEADERS, json={
                "requests": [{
                    "indexName":            INDEX,
                    "query":                "",
                    "hitsPerPage":          1000,
                    "page":                 0,
                    "filters":              f"ville:'{raw_ville}'",
                    "attributesToRetrieve": ["*"],
                }]
            }, timeout=30)

            if r.status_code != 200:
                log(f"  ⚠ {city_name}: Algolia {r.status_code}")
                city_bar.update(1)
                continue

            result = r.json()["results"][0]
            hits   = result.get("hits", [])
            nb     = result.get("nbHits", 0)

            # If city has >1000 hits, paginate
            total_pages = result.get("nbPages", 1)
            if total_pages > 1:
                for p in range(1, total_pages):
                    r2 = requests.post(SEARCH_URL, headers=ALGOLIA_HEADERS, json={
                        "requests": [{
                            "indexName":            INDEX,
                            "query":                "",
                            "hitsPerPage":          1000,
                            "page":                 p,
                            "filters":              f"ville:'{raw_ville}'",
                            "attributesToRetrieve": ["*"],
                        }]
                    }, timeout=30)
                    if r2.status_code == 200:
                        hits += r2.json()["results"][0].get("hits", [])

            new_this_city = 0
            for hit in hits:
                row = normalize(hit)
                aid = str(row["atelier_id"])
                if aid and aid not in seen_ids:
                    seen_ids.add(aid)
                    all_rows.append(row)
                    new_this_city += 1

            city_bar.update(1)
            city_bar.set_postfix(city=city_name[:15], new=new_this_city,
                                 total=len(all_rows), refresh=False)
            time.sleep(0.05)

    log(f"Total unique workshops collected: {len(all_rows):,}")
    return all_rows


# ── STEP 3: Reverse geocode lat/lng → full address ────────

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_HEADERS = {
    "User-Agent": "wecandoo-scraper/1.0 (research project)"  # required by OSM policy
}

def reverse_geocode(lat, lng) -> dict:
    """
    Call OpenStreetMap Nominatim with lat/lng.
    Returns dict with street, house_number, postcode, neighbourhood, full_address.
    Nominatim rate limit: 1 request/second — we respect this.
    """
    if not lat or not lng:
        return {}
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={"lat": lat, "lon": lng, "format": "jsonv2", "addressdetails": 1},
            headers=NOMINATIM_HEADERS,
            timeout=10,
        )
        if r.status_code != 200:
            return {}
        data    = r.json()
        addr    = data.get("address", {})
        street  = addr.get("road") or addr.get("pedestrian") or addr.get("footway") or ""
        house   = addr.get("house_number", "")
        full    = data.get("display_name", "")
        return {
            "street":        f"{house} {street}".strip() if house else street,
            "house_number":  house,
            "postcode":      addr.get("postcode", ""),
            "neighbourhood": addr.get("neighbourhood") or addr.get("suburb") or addr.get("quarter") or "",
            "full_address":  full,
        }
    except Exception:
        return {}


def enrich_with_geocoding(rows: list[dict], already_saved: set) -> list[dict]:
    """
    Reverse geocode every row that has lat/lng.
    Saves each row to CSV immediately after geocoding.
    Respects Nominatim's 1 req/sec rate limit.
    """
    to_enrich = [r for r in rows if str(r["atelier_id"]) not in already_saved]
    total     = len(to_enrich)

    if total == 0:
        log("  Nothing to geocode — all already saved.")
        return rows

    log(f"Reverse geocoding {total:,} workshops via OpenStreetMap Nominatim...")
    log(f"  Rate limit: 1 req/sec → estimated {total//60+1} min")

    BAR_FMT = (
        "Geocoding: [{bar:28}] {percentage:3.0f}%  "
        "{n_fmt}/{total_fmt} done  |  "
        "{remaining_s:.0f}s left  "
        "[{elapsed}<{remaining}, {rate_fmt}]"
    )

    saved_count  = 0
    geo_success  = 0
    geo_fail     = 0

    with tqdm(total=total, desc="Geocoding", unit="rec",
              bar_format=BAR_FMT, file=sys.stdout,
              dynamic_ncols=True, colour="green") as pbar:

        for row in to_enrich:
            geo = reverse_geocode(row.get("lat"), row.get("lng"))

            if geo:
                row.update(geo)
                geo_success += 1
            else:
                geo_fail += 1

            append_csv(row)       # ← written to disk immediately
            saved_count += 1

            pbar.update(1)
            if pbar.n % 50 == 0:
                pbar.set_postfix(
                    saved=saved_count,
                    geo_ok=geo_success,
                    geo_fail=geo_fail,
                    refresh=False,
                )

            time.sleep(1.1)       # Nominatim hard limit: max 1 req/sec

    log(f"  Saved {saved_count:,}  |  Geocoded {geo_success:,}  |  No coords {geo_fail:,}")
    return rows


# ── MAIN ──────────────────────────────────────────────────

def main():
    t0 = time.time()
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"=== Wecandoo Scraper v6  {datetime.now()} ===\n\n")

    init_csv()
    already_saved = load_saved_ids()
    if already_saved:
        log(f"Resume mode: {len(already_saved)} records already saved — will skip them.")

    # ── Step 1: Get cities ─────────────────────────────────
    log("\n=== STEP 1: Fetching city list ===")
    cities = get_cities()
    if not cities:
        log("  No city list — will do single global query (may be capped)")
        cities = [{"city": "all", "raw": "", "count": 9999}]

    # ── Step 2: Collect all workshops from Algolia ─────────
    log("\n=== STEP 2: Collecting workshops from Algolia ===")
    all_rows = scrape_all_workshops(cities, already_saved)

    if not all_rows:
        log("⚠  No workshops collected. Check credentials.")
        return

    # ── Step 3: Reverse geocode ────────────────────────────
    log("\n=== STEP 3: Reverse geocoding addresses ===")
    all_rows = enrich_with_geocoding(all_rows, already_saved)

    # ── Save any rows without lat/lng ──────────────────────
    no_geo = [r for r in all_rows
              if not r.get("lat") and str(r["atelier_id"]) not in already_saved]
    if no_geo:
        log(f"  Saving {len(no_geo)} records without coordinates...")
        for row in no_geo:
            append_csv(row)

    # ── Final summary ──────────────────────────────────────
    elapsed      = time.time() - t0
    total_in_csv = sum(1 for _ in open(OUTPUT_CSV, encoding="utf-8-sig")) - 1

    log("\n" + "=" * 55)
    log(f"✓  Done in {elapsed:.1f}s  ({elapsed/60:.1f} min)")
    log(f"✓  Total records in CSV : {total_in_csv:,}")

    if total_in_csv == 0:
        log("⚠  No data saved.")
        return

    log("Writing XLSX...")
    df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig")
    df.to_excel(OUTPUT_XLSX, index=False, engine="openpyxl")
    log(f"✓  CSV  → {OUTPUT_CSV}")
    log(f"✓  XLSX → {OUTPUT_XLSX}")

    addr_filled = df["street"].notna() & (df["street"] != "")
    log(f"✓  Street fill rate: {addr_filled.sum():,}/{total_in_csv:,} ({addr_filled.mean()*100:.1f}%)")
    log("\n── First 5 rows ──")
    log(df[["title", "city", "street", "house_number", "postcode", "neighbourhood", "price"]].head().to_string())


if __name__ == "__main__":
    main()