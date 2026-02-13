"""
Find all Construction Development Companies with IPO worldwide.
Uses AI Gemini via configix/apiManager to research and collect data.
Output: CDC_IPO.csv with schema; progress logged as JSONL.
"""

import sys
import json
import csv
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

# Ensure configix is importable
sys.path.insert(0, str(Path(__file__).parent))
from configix.apiManager import ai_gemini

# Try google-genai first (new SDK), fallback to google-generativeai
GEMINI_CLIENT = None
USE_LEGACY = False

try:
    from google import genai
    GEMINI_CLIENT = genai
except ImportError:
    try:
        import google.generativeai as genai
        GEMINI_CLIENT = genai
        USE_LEGACY = True
    except ImportError:
        print("Error: Install Google AI SDK. Run: pip install google-genai")
        print("  Or fallback: pip install google-generativeai")
        sys.exit(1)

# Output paths
OUTPUT_DIR = Path(__file__).parent
CSV_PATH = OUTPUT_DIR / "CDC_IPO.csv"
PROGRESS_PATH = OUTPUT_DIR / "CDC_IPO_progress.jsonl"

# CSV schema
SCHEMA = [
    "brand_id", "brand_name", "hq_office", "hq_address",
    "lat", "lon", "country", "country_code", "founded",
    "last_Y", "last_Ninc", "Y", "IPO", "employees"
]


def log_progress(evt: str, data: Dict[str, Any]) -> None:
    """Append progress event as JSONL; also print."""
    entry = {"evt": evt, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **data}
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(PROGRESS_PATH, "a", encoding="utf-8") as f:
        f.write(line)
    print(json.dumps(entry, ensure_ascii=False))


def _extract_text(response) -> str:
    """Extract text from Gemini API response (supports multiple SDK versions)."""
    if hasattr(response, "text") and response.text:
        return response.text
    if hasattr(response, "candidates") and response.candidates:
        parts = response.candidates[0].content.parts
        if parts:
            return getattr(parts[0], "text", str(parts[0]))
    return str(response)


def call_gemini(prompt: str, model: str = "gemini-2.0-flash") -> str:
    """Call Gemini API via configix apiManager."""
    api_key = ai_gemini.get("api_key")
    if not api_key:
        raise ValueError("Gemini API key not found in config. Check config/config_gemini.json")
    if USE_LEGACY:
        GEMINI_CLIENT.configure(api_key=api_key)
        model_obj = GEMINI_CLIENT.GenerativeModel("gemini-1.5-flash")
        response = model_obj.generate_content(prompt)
        return _extract_text(response)
    else:
        client = GEMINI_CLIENT.Client(api_key=api_key)
        response = client.models.generate_content(model=model, contents=prompt)
        return _extract_text(response)


def extract_json_array(text: str) -> List[Dict]:
    """Extract JSON array from model response."""
    out = []
    # Try markdown code block first
    m = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try raw array
    m = re.search(r"(\[[\s\S]*\])", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "companies" in parsed:
            return parsed["companies"]
    except json.JSONDecodeError:
        pass
    return out


def prompt_companies(region: str) -> str:
    """Build prompt for a region."""
    return f"""List publicly traded (IPO) construction and real estate development companies headquartered in {region}.
Focus on: residential/commercial construction, real estate development, housing developers, infrastructure.
Exclude: purely real estate agencies, REITs (unless also developers), materials-only manufacturers.

For each company return a JSON array with objects having:
- brand_name: protected/trademark brand name
- hq_office: official legal/head office company name
- hq_address: full official address
- lat: latitude (decimal, best estimate)
- lon: longitude (decimal, best estimate)
- country: full country name
- country_code: ISO 3166-1 alpha-2 (e.g. US, DE)
- founded: year established (integer)
- last_Y: last available annual turnover/revenue (number in millions USD)
- last_Ninc: last available net income (number in millions USD)
- Y: year of turnover/income data
- IPO: exchange ticker symbol
- employees: total employees (integer)

Use null for missing data. Be as accurate as possible.

Return ONLY a valid JSON array, no other text."""


def normalize_row(row: Dict, brand_id: int) -> Dict[str, Any]:
    """Map raw API fields to CSV schema."""
    def _n(v):
        if v is None or v == "" or (isinstance(v, str) and v.strip() == ""):
            return ""
        if isinstance(v, (int, float)) and str(v) == "nan":
            return ""
        return v
    return {
        "brand_id": brand_id,
        "brand_name": _n(row.get("brand_name")),
        "hq_office": _n(row.get("hq_office")),
        "hq_address": _n(row.get("hq_address")),
        "lat": _n(row.get("lat")),
        "lon": _n(row.get("lon")),
        "country": _n(row.get("country")),
        "country_code": _n(row.get("country_code")),
        "founded": _n(row.get("founded")),
        "last_Y": _n(row.get("last_Y")),
        "last_Ninc": _n(row.get("last_Ninc")),
        "Y": _n(row.get("Y")),
        "IPO": _n(row.get("IPO")),
        "employees": _n(row.get("employees")),
    }


def main():
    log_progress("start", {"output_csv": str(CSV_PATH), "progress_file": str(PROGRESS_PATH)})
    seen = set()
    rows: List[Dict] = []
    regions = [
        "North America (USA, Canada)",
        "Europe (Western, Central, Eastern)",
        "Asia (China, Japan, India, South Korea, Singapore, etc.)",
        "Latin America and Caribbean",
        "Middle East and Africa",
        "Australia and Oceania",
    ]
    for i, region in enumerate(regions):
        log_progress("region_start", {"region": region, "index": i + 1, "total": len(regions)})
        try:
            prompt = prompt_companies(region)
            resp = call_gemini(prompt)
            log_progress("api_response", {"region": region, "length": len(resp)})
            companies = extract_json_array(resp)
            log_progress("parsed", {"region": region, "count": len(companies)})
            for c in companies:
                if not isinstance(c, dict):
                    continue
                name = (c.get("brand_name") or c.get("hq_office") or "").strip()
                if not name:
                    continue
                key = (name.lower(), c.get("country_code", ""))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(normalize_row(c, len(rows) + 1))
                log_progress("company_added", {"brand_name": name, "brand_id": len(rows)})
        except Exception as e:
            log_progress("error", {"region": region, "message": str(e)})
            continue
        time.sleep(2)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA)
        w.writeheader()
        w.writerows(rows)
    log_progress("done", {"total": len(rows), "csv": str(CSV_PATH)})
    print(f"\nWrote {len(rows)} companies to {CSV_PATH}")


if __name__ == "__main__":
    main()
