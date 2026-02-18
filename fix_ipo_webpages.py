#!/usr/bin/env python3
"""
Check all CSVs for webpage column. If a webpage leads to an IPO/investor relations page,
use AI (ai_openai / OpenAI first, ai_gemini fallback) to find the main company webpage.
Otherwise skip.
"""

import csv
import json
import re
import sys
from pathlib import Path

# Non-company URLs: stock quotes, investor relations, etc. (not main brand website)
NON_BRAND_URL_PATTERNS = [
    r"yahoo\.com",
    r"finance\.yahoo",
    r"/quote/",
    r"\bfinance\.",      # finance.yahoo.com, etc.
    r"\bir\.",           # ir.company.com
    r"\binvestors\.",
    r"\binvestor\.",
    r"sec\.gov",
    r"nasdaq\.com",
    r"bloomberg\.com",
    r"reuters\.com",
    r"edgar",
    r"investorrelations",
    r"/investor[s]?[/\s]",
    r"/ir[/\s]",
    r"/shareholder",
]
NON_BRAND_REGEX = re.compile("|".join(NON_BRAND_URL_PATTERNS), re.I)


def is_non_brand_page(url: str) -> bool:
    """Return True if URL is not the main company site (e.g. Yahoo Finance, investor page)."""
    if not url or not isinstance(url, str):
        return False
    return bool(NON_BRAND_REGEX.search(url))


def _load_openai_key(config_dir: Path) -> str | None:
    p = config_dir / "config_openai.json"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f).get("openai_api_key")


def _load_gemini_key(config_dir: Path) -> str | None:
    p = config_dir / "config_gemini.json"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f).get("ITEM")


def get_ai_keys() -> tuple[str | None, str | None]:
    """Return (openai_key, gemini_key). Tries config dirs, then configix ai_openai/ai_gemini."""
    openai_key = gemini_key = None
    for base in [
        Path(__file__).parent.parent / "config",
        Path("C:/12_CODINGHARD/config"),
        Path(__file__).parent / "config",
    ]:
        if base.exists():
            openai_key = openai_key or _load_openai_key(base)
            gemini_key = gemini_key or _load_gemini_key(base)
    try:
        cfg = __import__("configix").apiManager
        openai_key = openai_key or cfg.get_ai_provider("ai_openai")["api_key"]
        gemini_key = gemini_key or cfg.get_ai_provider("ai_gemini")["api_key"]
    except Exception:
        pass
    return openai_key, gemini_key


def _parse_ai_url(text: str) -> str | None:
    """Extract a valid https URL from AI response."""
    text = (text or "").strip()
    text = re.sub(r"^['\"]|['\"]$", "", text)
    if text.upper() == "NONE" or not text.startswith("http"):
        return None
    return text


def ask_openai_for_webpage(company_name: str, country: str, api_key: str) -> str | None:
    """Use OpenAI (ai_openai) to suggest main company website (not investor page)."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a researcher. Reply with ONLY a single valid URL (https://) of the official MAIN corporate website for the given company—NOT investor relations, NOT SEC filings. If unsure, return best guess. No explanation, no quotes, just the URL. If you cannot find one, reply exactly: NONE",
                },
                {
                    "role": "user",
                    "content": f"Main company website (not investor/IPO page) for: {company_name} (company based in {country}). Construction/real estate/development company.",
                },
            ],
            temperature=0.3,
            max_tokens=256,
        )
        return _parse_ai_url(resp.choices[0].message.content)
    except Exception as e:
        print(f"  OpenAI error: {e}")
        return None


def ask_gemini_for_webpage(company_name: str, country: str, api_key: str) -> str | None:
    """Use Gemini (ai_gemini) to suggest main company website."""
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"Main company website (not investor/IPO page) for: {company_name} (company based in {country}). Construction/real estate/development company. Reply with ONLY a single valid https URL. No explanation. If unknown, reply NONE.",
        )
        text = getattr(resp, "text", None) or (
            resp.candidates[0].content.parts[0].text if resp.candidates and resp.candidates[0].content.parts else ""
        )
        return _parse_ai_url(text)
    except Exception as e:
        print(f"  Gemini error: {e}")
        return None


def ask_ai_for_webpage(company_name: str, country: str, openai_key: str | None, gemini_key: str | None) -> str | None:
    """Try OpenAI (ai_openai) first, then Gemini (ai_gemini) as fallback."""
    if openai_key:
        new_url = ask_openai_for_webpage(company_name, country, openai_key)
        if new_url:
            return new_url
        print("  Trying Gemini fallback...")
    if gemini_key:
        return ask_gemini_for_webpage(company_name, country, gemini_key)
    return None


CSVS = ["CDC_midbln.csv", "CDC_IPO.csv", "CDC_CIS_100mln.csv"]


def main():
    import argparse
    p = argparse.ArgumentParser(description="Replace IPO/non-brand webpages with main company sites via AI")
    p.add_argument("--limit", type=int, default=0, help="Max companies to fix (0=no limit)")
    args = p.parse_args()
    root = Path(__file__).parent
    openai_key, gemini_key = get_ai_keys()

    if not openai_key and not gemini_key:
        print("Error: No AI key found. Set config_openai.json or config_gemini.json (ai_openai / ai_gemini).")
        sys.exit(1)

    try:
        from openai import OpenAI  # noqa: F401
    except ImportError:
        if openai_key:
            print("Error: Install openai: pip install openai")
            sys.exit(1)

    total_fixed = 0
    limit_remaining = args.limit
    for csv_name in CSVS:
        csv_path = root / csv_name
        if not csv_path.exists():
            continue

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = reader.fieldnames

        if "webpage" not in (fieldnames or []):
            print(f"  {csv_name}: no webpage column, skip")
            continue

        fixed = 0
        for row in rows:
            url = (row.get("webpage") or "").strip()
            if not url or not url.startswith("http"):
                continue

            if not is_non_brand_page(url):
                continue

            name = row.get("brand_name", "").strip() or "Unknown"
            country = row.get("country", "").strip() or ""
            print(f"\n[csv={csv_name}] IPO page: {name}")
            print(f"  URL: {url}")
            print("  Asking AI for main company webpage...")
            new_url = ask_ai_for_webpage(name, country, openai_key, gemini_key)
            if new_url:
                print(f"  -> Replaced with: {new_url}")
                row["webpage"] = new_url
                fixed += 1
                total_fixed += 1
                if args.limit and (limit_remaining := limit_remaining - 1) <= 0:
                    break
            else:
                print("  -> No alternative found, keeping original")
        if limit_remaining <= 0 and args.limit:
            break

        if fixed > 0:
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"  Saved {csv_name}: {fixed} updated")

    # Also process companies-by-revenue.json (treemap source)
    # Fix: null webpage (would show Yahoo Finance) or non-brand URLs
    json_path = root / "companies-by-revenue.json"
    if json_path.exists() and not (args.limit and limit_remaining <= 0):
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        companies = data.get("companies", [])
        json_fixed = 0
        for c in companies:
            url = c.get("webpage")
            url_str = (url or "").strip() if isinstance(url, str) else ""
            name = c.get("name", "").strip() or "Unknown"
            country = c.get("country", "").strip() or ""
            # Skip if no ipo (no Yahoo fallback) and we already have a valid main-site URL
            has_ipo = bool(c.get("ipo"))
            needs_fix = (
                (not url_str and has_ipo)  # null webpage -> treemap shows Yahoo Finance
                or (url_str and is_non_brand_page(url_str))
            )
            if not needs_fix:
                continue
            print(f"\n[json] {name}")
            print(f"  Current: {url_str or '(null - treemap shows Yahoo Finance)'}")
            print("  Asking AI for main company webpage...")
            new_url = ask_ai_for_webpage(name, country, openai_key, gemini_key)
            if new_url:
                print(f"  -> Set: {new_url}")
                c["webpage"] = new_url
                json_fixed += 1
                total_fixed += 1
                if args.limit and (limit_remaining := limit_remaining - 1) <= 0:
                    break
            else:
                print("  -> No alternative found")
        if json_fixed > 0:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"  Saved companies-by-revenue.json: {json_fixed} updated")

    print(f"\nDone: {total_fixed} webpage(s) replaced across CSVs + JSON.")


if __name__ == "__main__":
    main()
