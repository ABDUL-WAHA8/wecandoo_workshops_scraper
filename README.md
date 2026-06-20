# Wecandoo Workshops & Locations Scraper

A robust Python scraper that collects workshop data from Wecandoo (via Algolia), enriches records with reverse geocoded addresses (OpenStreetMap Nominatim), and exports clean datasets to **CSV** and **XLSX**.

---

## Features

- Fetches workshop records from Algolia index (`production_ateliers`)
- Automatically retrieves all cities from facets API
- Scrapes city-by-city to avoid result caps
- Deduplicates records by `atelier_id`
- Resume mode: skips already saved records from existing CSV
- Reverse geocodes coordinates to full address fields
- Writes incrementally to CSV for crash-safe progress
- Exports final dataset to Excel (`.xlsx`)
- Progress bars + log file for transparent runs

---

## Output Files

- `wecandoo_ateliers.csv` → main dataset (incrementally written)
- `wecandoo_ateliers.xlsx` → Excel export of final CSV
- `wecandoo_scraper.log` → run logs and summary

---

## Data Fields

The scraper outputs the following columns:

- `title`, `short_title`
- `city`, `district`
- `street`, `house_number`, `postcode`, `neighbourhood`, `full_address`
- `lat`, `lng`
- `price`, `category`, `artisan`, `duration_min`
- `min_persons`, `max_persons`
- `rating_score`, `reviews_count`
- `atelier_id`, `lieu_id`, `url`

---

## Requirements

- Python 3.10+
- pip packages:
  - `requests`
  - `pandas`
  - `tqdm`
  - `openpyxl`

Install dependencies:

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install requests pandas tqdm openpyxl
```

---

## Usage

1. Place the script in your project (recommended name: `wecandoo_workshops_scraper.py`)
2. Run:

```bash
python wecandoo_workshops_scraper.py
```

3. Wait for:
   - city discovery
   - Algolia collection
   - reverse geocoding
   - CSV/XLSX export

---

## How it Works

### Step 1 — Fetch city list
The scraper first queries Wecandoo facets API (`/api/facets/ville`) to collect city values and counts.  
If this fails, it falls back to Algolia facet retrieval.

### Step 2 — Collect workshops
For each city, it queries Algolia and retrieves all workshop hits (`hitsPerPage=1000`, paginated if needed), then normalizes records into a consistent schema.

### Step 3 — Reverse geocode
Each workshop with coordinates is reverse geocoded using OpenStreetMap Nominatim to enrich:
- street
- house number
- postcode
- neighbourhood
- full address

Rows are saved immediately after each geocoding call.

---

## Resume / Incremental Behavior

If `wecandoo_ateliers.csv` already exists:
- existing `atelier_id`s are loaded
- duplicates are skipped
- only new records are fetched/enriched/saved

This allows safe restart after interruption.

---

## Rate Limit & Performance Notes

- Nominatim reverse geocoding is rate-limited to approximately **1 request/second**
- Geocoding phase can take significant time for large datasets
- Progress bars display ETA and live throughput

---

## Configuration

Main constants in script:

- `APP_ID`
- `API_KEY`
- `INDEX`
- `BASE`
- output file names (`OUTPUT_CSV`, `OUTPUT_XLSX`, `LOG_FILE`)

You can adapt these to other indexes or environments.

---

## Ethical / Legal Note

Use this scraper responsibly and ensure your usage complies with:
- target website Terms of Service
- API provider policies (Algolia/Nominatim)
- local laws and data usage regulations

For Nominatim specifically, keep respectful request rates and proper User-Agent identification.

---

## Suggested Repository Structure

```text
.
├── wecandoo_workshops_scraper.py
├── requirements.txt
├── README.md
├── .gitignore
└── output/
    ├── wecandoo_ateliers.csv
    ├── wecandoo_ateliers.xlsx
    └── wecandoo_scraper.log
```

---

## Example `.gitignore`

```gitignore
__pycache__/
*.pyc
.venv/
venv/

# scraper outputs
wecandoo_ateliers.csv
wecandoo_ateliers.xlsx
wecandoo_scraper.log
output/
```

---

## Disclaimer

This project is for educational/research and data engineering workflow purposes.
