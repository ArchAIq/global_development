#!/usr/bin/env python3
"""
Check every webpage in companies-by-revenue.json.
If HTTP status is 404 or 423, use AI (ai_openai / OpenAI first, Gemini fallback) to find another relevant official webpage.
"""

import json
import re
import sys
from pathlib import Path

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
    """Return (openai_key, gemini_key). Tries configix ai_openai/ai_gemini, then config dirs."""
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


def check_url(url: str, timeout: int = 10) -> int:
    """Return HTTP status code. Uses HEAD first, falls back to GET."""
    try:
        import urllib.request

        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0 (compatible; WebpageChecker/1.0)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return -1


def _parse_ai_url(text: str) -> str | None:
    """Extract a valid https URL from AI response."""
    text = (text or "").strip()
    text = re.sub(r"^['\"]|['\"]$", "", text)
    if text.upper() == "NONE" or not text.startswith("http"):
        return None
    return text


def ask_openai_for_webpage(company_name: str, country: str, api_key: str) -> str | None:
    """Use OpenAI (ai_openai) to suggest an official company website."""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a researcher. Reply with ONLY a single valid URL (starting with https://) of the official corporate website for the given company. If unsure, return a best guess. No explanation, no quotes, just the URL. If you cannot find a reliable URL, reply with exactly: NONE",
                },
                {
                    "role": "user",
                    "content": f"Official website URL for: {company_name} (company based in {country}). Construction/real estate/development company.",
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
    """Use Gemini (fallback when OpenAI quota exceeded) to suggest an official company website."""
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"Official website URL for: {company_name} (company based in {country}). Construction/real estate/development company. Reply with ONLY a single valid https URL. No explanation. If unknown, reply NONE.",
        )
        text = getattr(resp, "text", None) or (
            resp.candidates[0].content.parts[0].text if resp.candidates and resp.candidates[0].content.parts else ""
        )
        return _parse_ai_url(text)
    except Exception as e:
        print(f"  Gemini error: {e}")
        return None


def ask_ai_for_webpage(company_name: str, country: str, openai_key: str | None, gemini_key: str | None) -> str | None:
    """Try OpenAI (ai_openai) first, then Gemini as fallback."""
    if openai_key:
        new_url = ask_openai_for_webpage(company_name, country, openai_key)
        if new_url:
            return new_url
        print(f"  Trying Gemini fallback...")
    if gemini_key:
        return ask_gemini_for_webpage(company_name, country, gemini_key)
    return None


def main():
    root = Path(__file__).parent
    json_path = root / "companies-by-revenue.json"
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

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    companies = data.get("companies", [])
    BAD_CODES = {404, 423}
    fixed = 0
    failed = []

    for i, c in enumerate(companies):
        url = c.get("webpage") if isinstance(c.get("webpage"), str) else None
        if not url or not url.startswith("http"):
            continue

        name = c.get("name", "Unknown")
        country = c.get("country", "")

        status = check_url(url)
        if status in BAD_CODES:
            print(f"[{status}] {name}: {url}")
            print(f"  Asking AI for alternative...")
            new_url = ask_ai_for_webpage(name, country, openai_key, gemini_key)
            if new_url:
                new_status = check_url(new_url)
                if new_status not in BAD_CODES and new_status >= 200 and new_status < 400:
                    print(f"  -> Replaced with: {new_url} (status {new_status})")
                    c["webpage"] = new_url
                    fixed += 1
                else:
                    print(f"  -> Suggested URL returned {new_status}, kept old")
                    failed.append((name, url, new_url))
            else:
                print(f"  -> No alternative found")
                failed.append((name, url, None))

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"\nDone: {fixed} fixed, {len(failed)} still broken.")


if __name__ == "__main__":
    main()
