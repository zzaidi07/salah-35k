# flightscraper.py
from pathlib import Path
import requests, re, json, html
from typing import Dict, Any, Tuple, List
import datetime as dt
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from salah_at_35k_calculator import salah_calculator

_TZ_ABBREV_OFFSETS = {
    # UTC-ish
    "UTC": (0, 0),
    "GMT": (0, 0),
    "Z": (0, 0),
    # North America
    "EDT": (-4, 0),
    "EST": (-5, 0),
    "CDT": (-5, 0),
    "CST": (-6, 0),
    "MDT": (-6, 0),
    "MST": (-7, 0),
    "PDT": (-7, 0),
    "PST": (-8, 0),
    # Europe
    "BST": (+1, 0),  # UK summer
    "IST": (
        +5,
        30,
    ),  # India (note: ambiguous with Ireland/Israel, but India is most common)
    "WET": (0, 0),
    "WEST": (+1, 0),
    "CET": (+1, 0),
    "CEST": (+2, 0),
    "EET": (+2, 0),
    "EEST": (+3, 0),
    # Asia-Pacific
    "JST": (+9, 0),
    "KST": (+9, 0),
    "AEST": (+10, 0),
    "AEDT": (+11, 0),
    "ACST": (+9, 30),
    "ACDT": (+10, 30),
    "NZST": (+12, 0),
    "NZDT": (+13, 0),
}


headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
    "Connection": "close",
}

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
        if headers[0].lower().startswith("date") and all(
            h in " ".join(headers) for h in EXPECTED_HEADERS[1:]
        ):
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


def resolve_flightaware_ident(
    user_flight: str, session: requests.Session
) -> str | None:
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


def get_flight_history(flight_number: str) -> Dict[str, Any]:
    """
    Returns a normalized envelope dict, never a bare list:
    {
        "count": int,
        "source": "FlightAware",
        "resolved_ident": str | None,
        "items": list[dict],
        "error": str | None
    }
    """
    envelope: Dict[str, Any] = {
        "count": 0,
        "source": "FlightAware",
        "resolved_ident": None,
        "items": [],
        "error": None,
    }

    try:
        with requests.Session() as s:
            ident = resolve_flightaware_ident(flight_number, s)
            if ident is None:
                envelope["error"] = "No flight found"
                return envelope

            envelope["resolved_ident"] = ident
            soup, table = _scrape_history_page(s, ident)
    except Exception as e:
        envelope["error"] = f"Fetch error: {e}"
        return envelope

    if table is None:
        envelope["error"] = "No flight found"
        return envelope

    tbody = table.find("tbody") or table
    rows: List[Dict[str, Any]] = []

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

        date_raw = cells[0]
        aircraft = cells[1]
        origin = parse_airport(cells[2])
        destination = parse_airport(cells[3])
        departure = cells[4]
        arrival = cells[5]
        last_col = cells[6] if len(cells) > 6 else ""

        try:
            date_iso = dt.datetime.strptime(date_raw, "%d-%b-%Y").date().isoformat()
        except Exception:
            date_iso = date_raw

        if re.search(
            r"(Scheduled|Cancelled|Diverted|En\s*route|Delayed)", last_col, re.I
        ):
            status, duration = last_col, None
        else:
            status, duration = None, last_col

        rows.append(
            {
                "date": date_iso,
                "aircraft": aircraft,
                "origin": origin,
                "destination": destination,
                "departure": departure,
                "arrival": arrival,
                "duration": duration,
                "status": status,
            }
        )

    envelope["items"] = rows
    envelope["count"] = len(rows)
    return envelope


def get_flight_history_json(flight_number: str) -> Tuple[str, int]:
    """
    Returns (json_string, status_code).
    200 if we found at least one row, 404 if none, 500 if an unexpected error occurred.
    """
    try:
        data = get_flight_history(flight_number)
        status = 200 if data.get("count", 0) > 0 else 404
        return json.dumps(data, ensure_ascii=False, indent=2), status
    except Exception as e:
        err = {
            "count": 0,
            "source": "FlightAware",
            "resolved_ident": None,
            "items": [],
            "error": f"Unexpected error: {e}",
        }
        return json.dumps(err, ensure_ascii=False, indent=2), 500


# -------- Route search ----------------


def strip_tags(s: str) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = re.sub(r"<[^>]*>", "", s)
    s = s.replace("\xa0", " ")
    return " ".join(s.split()).strip()


def parse_results_content(html_text: str):
    """
    Extract and parse: FA.findflight.resultsContent = [ ... ];
    Return list of dicts with ident, airline, departure, arrival, status.
    """
    m = re.search(r"FA\.findflight\.resultsContent\s*=\s*(\[[\s\S]*?\]);", html_text)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []

    flights = []
    for it in data:
        ident = strip_tags(it.get("flightIdent", ""))
        airline = strip_tags(it.get("airlineName", ""))  # <— NEW
        dep = f"{strip_tags(it.get('flightDepartureDay', ''))} {strip_tags(it.get('flightDepartureTime', ''))}".strip()
        arr = f"{strip_tags(it.get('flightArrivalDay', ''))} {strip_tags(it.get('flightArrivalTime', ''))}".strip()
        status = strip_tags(it.get("flightStatus", ""))
        if ident:
            flights.append(
                {
                    "ident": ident,
                    "airline": airline,
                    "departure": dep,
                    "arrival": arr,
                    "status": status,
                }
            )
    return flights


def fetch_flightaware_page(origin_icao: str, dest_icao: str, timeout=15):
    url = f"https://www.flightaware.com/live/findflight?origin={origin_icao}&destination={dest_icao}"
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return url, resp.text


# ------------- endpoint -------------


def find_flights(departure: str, arrival: str):
    """
    GET /flights?departure=CYYZ&arrival=KLAX
    Scrapes FlightAware's page and returns flight JSON.
    """
    tried = []
    last_error = None
    try:
        url, html_text = fetch_flightaware_page(departure, arrival)
        tried.append(url)
        items = parse_results_content(html_text)
        if items:
            return json.dumps({"count": len(items), "items": items, "source": url})
        last_error = "Parsed 0 items from resultsContent."
    except requests.HTTPError as e:
        last_error = f"HTTP {e.response.status_code}"
    except requests.RequestException as e:
        last_error = str(e)
    except Exception as e:
        last_error = f"Parse error: {e}"

    return json.dumps(
        {
            "message": "No results parsed from FlightAware.",
            "tried_urls": tried,
            "error": last_error,
        }
    ), 502


# ------------- Date_finder -------------


def FetchDate(input_str: str, status: str | None = None) -> dt.date:
    """
    Given a string like 'Sun 9:00 PM UTC' or 'Mon 07:00 +03', return the DATE (datetime.date)
    for THIS CONTEXT'S WEEK in the specified timezone.

    Status-driven week selection:
      - Past-ish (Arrived, Gate Arrival, En Route, On Time): most recent weekday (<= today)
      - Future-ish (Scheduled, Delayed): next weekday (>= today)
      - Unknown/missing: defaults to most recent (<= today)

    Supported tz forms:
      - IANA: 'America/Toronto', 'Europe/Paris'
      - Abbrevs: 'EDT', 'PST', 'CET', ...
      - UTC/GMT: 'UTC', 'GMT'
      - Offsets: '+03', '-05', '+0330', '-0530', '+03:00', 'UTC+3', 'GMT +03:00'
    """
    s = input_str.strip()

    # Day, time, optional AM/PM, then the rest as tz (time is ignored for return, but still parsed)
    m = re.match(r"^\s*([A-Za-z]{3})\s+(\d{1,2}:\d{2})(?:\s*([AaPp][Mm]))?\s*(.*)$", s)
    if not m:
        raise ValueError(
            "Invalid format. Example: 'Mon 7:00 AM +03' or 'Sun 21:00 UTC'"
        )
    day_str, time_str, ampm, tz_str = m.groups()

    # Normalize day -> index (Mon=0 ... Sun=6)
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    try:
        day_index = days.index(day_str.lower())
    except ValueError:
        raise ValueError(f"Invalid day: {day_str}")

    # Parse time (even though we return only date) to validate input and keep behavior consistent
    if ampm:
        _ = dt.datetime.strptime(f"{time_str} {ampm.upper()}", "%I:%M %p")
    else:
        _ = dt.datetime.strptime(time_str, "%H:%M")

    # ---- Timezone parsing ----
    tz_raw = (tz_str or "").strip()
    if not tz_raw:
        tz = timezone.utc
    else:
        upper = tz_raw.upper()

        if upper in _TZ_ABBREV_OFFSETS:
            hh, mm = _TZ_ABBREV_OFFSETS[upper]
            delta = timedelta(hours=abs(hh), minutes=abs(mm))
            if hh < 0:  # negative offset
                delta = -delta
            tz = timezone(delta)
        elif upper in {"UTC", "GMT"}:
            tz = timezone.utc
        else:
            cleaned = re.sub(r"^(?i:UTC|GMT)\s*", "", tz_raw)
            m_off = re.match(r"^([+-])\s*(\d{1,2})(?::?(\d{2}))?\s*$", cleaned)
            if m_off:
                sign, hh, mm = m_off.groups()
                hours = int(hh)
                minutes = int(mm) if mm else 0
                if hours > 14 or minutes > 59:
                    raise ValueError(f"Invalid numeric offset: {tz_raw}")
                delta = timedelta(hours=hours, minutes=minutes)
                if sign == "-":
                    delta = -delta
                tz = timezone(delta)
            else:
                try:
                    tz = ZoneInfo(tz_raw)
                except Exception:
                    raise ValueError(f"Invalid timezone: {tz_raw}")

    # ---- Decide week direction from status ----
    status_norm = (status or "").strip().lower()
    is_future = any(k in status_norm for k in ["scheduled", "delay"])  # delayed/delay
    is_pastish = any(
        k in status_norm
        for k in [
            "arrived",
            "gate arrival",
            "gate-arrival",
            "en route",
            "enroute",
            "on time",
            "ontime",
        ]
    )

    # Default: treat as past-ish if unknown
    mode = "future" if (is_future and not is_pastish) else "past"

    # Compute date based on mode
    today = dt.datetime.now(tz).date()
    today_idx = today.weekday()  # Mon=0..Sun=6
    diff = day_index - today_idx

    if mode == "future":
        # next occurrence (>= today)
        if diff < 0:
            diff += 7
        target_date = today + timedelta(days=diff)
    else:
        # most recent occurrence (<= today)
        if diff > 0:
            diff -= 7
        target_date = today + timedelta(days=diff)

    return target_date
