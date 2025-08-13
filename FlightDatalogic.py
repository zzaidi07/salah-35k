# flightscraper.py
import json
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

try:
    # Optional, but enables "find the canonical FlightAware ident" via DuckDuckGo
    from ddgs import DDGS
    _DDGS_AVAILABLE = True
except Exception:
    _DDGS_AVAILABLE = False

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

EXPECTED_HEADERS = ["Date", "Aircraft", "Origin", "Destination", "Departure", "Arrival"]

# -------------------------
# Helpers for parsing table
# -------------------------
def parse_airport(cell_text: str):
    m = re.search(r"(.+?)\s*\(([^)]+)\)\s*$", cell_text)
    if m:
        return {"name": m.group(1).strip(), "code": m.group(2).strip()}
    return {"raw": cell_text}

def find_activity_table(soup: BeautifulSoup):
    candidates = []
    for thead in soup.find_all("thead"):
        headers = [th.get_text(strip=True) for th in thead.find_all("th")]
        if not headers:
            continue
        if headers[0].lower().startswith("date") and all(h in " ".join(headers) for h in EXPECTED_HEADERS[1:]):
            tbl = thead.find_parent("table")
            if tbl:
                candidates.append(tbl)
    if not candidates:
        for t in soup.find_all("table"):
            txt = t.get_text(" ", strip=True)
            if all(h in txt for h in EXPECTED_HEADERS):
                candidates.append(t)
    return max(candidates, key=lambda t: len(t.find_all("tr"))) if candidates else None

# ------------------------------------
# Your "resolve the FlightAware ident"
# ------------------------------------
def _digits(s: str) -> str:
    m = re.findall(r"\d+", s)
    return m[0] if m else ""

def _normalize_flight(s: str) -> str:
    # e.g. "AA 123" -> "AA123", "ua-432" -> "UA432"
    return re.sub(r"[^A-Za-z0-9]", "", s).upper()

def _extract_ident_from_url(url: str) -> str | None:
    # Accept URLs like:
    # https://www.flightaware.com/live/flight/UAL123/history
    # https://flightaware.com/live/flight/ACA015
    m = re.search(r"/live/flight/([^/?#]+)/?", url, re.I)
    return m.group(1) if m else None

def _ddg_find_flightaware_ident(user_flight: str) -> str | None:
    """
    Uses DuckDuckGo (ddgs) to find a FlightAware /live/flight/<IDENT> URL that
    contains the same numeric sequence as the user's flight number.
    """
    if not _DDGS_AVAILABLE:
        raise RuntimeError(
            "DuckDuckGo search (ddgs) is not installed. Please `pip install ddgs` "
            "to enable flight ident resolution."
        )

    digits = _digits(user_flight)
    if not digits:
        return None

    queries = [
        # prioritize history pages and live/flight URLs
        f'site:flightaware.com "live/flight" {user_flight}',
        f"site:flightaware.com {user_flight} history",
        f"site:flightaware.com {digits} history",
        f'site:flightaware.com "live/flight" {digits}',
    ]

    with DDGS() as ddgs:
        for q in queries:
            for r in ddgs.text(q, max_results=50):
                href = r.get("href") or ""
                if "flightaware.com" not in href.lower():
                    continue
                if digits and digits not in href:
                    # keep your original logic: numeric part must appear
                    continue
                ident = _extract_ident_from_url(href)
                if ident:
                    return ident
    return None

def resolve_flightaware_ident(user_flight: str, session: requests.Session) -> str | None:
    """
    Try the user input directly. If we can't find the Activity table on that page,
    search FlightAware via DuckDuckGo to discover the ident FlightAware uses.
    Returns the resolved ident or None if not found.
    """
    user_norm = _normalize_flight(user_flight)
    test_url = f"https://www.flightaware.com/live/flight/{user_norm}/history"

    # Try direct
    resp = session.get(test_url, headers=HEADERS, timeout=20)
    if resp.ok:
        soup = BeautifulSoup(resp.text, "lxml")
        if find_activity_table(soup) is not None:
            return user_norm  # valid

    # Try search
    ident = _ddg_find_flightaware_ident(user_norm)
    if ident:
        return ident

    return None  # couldn't find

# -------------------------
# Public scrape functions
# -------------------------
def _scrape_history_page(session: requests.Session, ident: str):
    url = f"https://www.flightaware.com/live/flight/{ident}/history"
    resp = session.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    table = find_activity_table(soup)
    return soup, table

def get_flight_history(flight_number: str):
    """
    Returns a list[dict] of rows.
    If no flight is found, returns {"error": "No flight found"}.
    """
    with requests.Session() as s:
        ident = resolve_flightaware_ident(flight_number, s)
        if ident is None:
            return {"error": "No flight found"}  # <- message returned here

        soup, table = _scrape_history_page(s, ident)

    if table is None:
        return {"error": "No flight found"}  # <- also return message if page has no table

    tbody = table.find("tbody") or table
    rows = []

    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 6:
            continue
        cells = [td.get_text(" ", strip=True) for td in tds[:7]]
        joined = " ".join(cells)
        if re.search(r"ACTIVITY LOG|history search|Buy now", joined, re.I):
            continue
        if cells[0].strip().lower() == "date":
            continue

        date_raw        = cells[0]
        aircraft        = cells[1]
        origin          = parse_airport(cells[2])
        destination     = parse_airport(cells[3])
        departure_local = cells[4]
        arrival_local   = cells[5]
        last_col        = cells[6] if len(cells) > 6 else ""

        try:
            date_iso = datetime.strptime(date_raw, "%d-%b-%Y").date().isoformat()
        except Exception:
            date_iso = date_raw

        if re.search(r"(Scheduled|Cancelled|Diverted|En\s*route|Delayed)", last_col, re.I):
            status, duration = last_col, None
        else:
            status, duration = None, last_col

        rows.append({
            "user_input": flight_number.strip().upper(),
            "resolved_ident": ident.strip().upper(),
            "date": date_iso,
            "aircraft": aircraft,
            "origin": origin,
            "destination": destination,
            "departure_local": departure_local,
            "arrival_local": arrival_local,
            "duration": duration,
            "status": status,
        })

    return rows

def get_flight_history_json(flight_number: str) -> str:
    """Same as above, but returns a JSON string."""
    rows = get_flight_history(flight_number)
    return json.dumps(rows, ensure_ascii=False, indent=2)
