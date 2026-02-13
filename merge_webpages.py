"""Merge webpage URLs from CSVs into companies-by-revenue.json."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent
CSVS = ["CDC_midbln.csv", "CDC_IPO.csv", "CDC_CIS_100mln.csv"]
JSON_PATH = ROOT / "companies-by-revenue.json"


def main():
    webpage_by_name = {}
    for name in CSVS:
        p = ROOT / name
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                brand = row.get("brand_name", "").strip()
                url = row.get("webpage", "").strip()
                if brand and url and url.startswith("http"):
                    webpage_by_name[brand] = url

    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    for c in data["companies"]:
        name = c.get("name", "")
        c["webpage"] = webpage_by_name.get(name) or None

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    merged = sum(1 for c in data["companies"] if c.get("webpage"))
    print(f"Updated {JSON_PATH}: {merged}/{len(data['companies'])} companies have webpage")


if __name__ == "__main__":
    main()
