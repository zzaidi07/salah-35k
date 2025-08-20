from __future__ import annotations
import json
from datetime import datetime, time as dtime, date as ddate
from typing import Any, Dict, Iterable, List, Optional, Tuple
from typing import Union

import pandas as pd
import streamlit as st
from salah_at_35k_calculator import salah_calculator  # external dependency
from FlightDatalogic import get_flight_history  # external dependency

# =======================
# Constants & Config
# =======================
APP_TITLE = "Salah@35k"
APP_SUBTITLE = "Find your flight"

STATE_PAGE = "page"
PAGE_SEARCH = "search"
PAGE_PLAN = "plan"

STATE_ROWS = "rows"
STATE_SELECTED_IDX = "selected_flight_idx"
STATE_SELECTED = "selected_flight"
STATE_SEARCH_CLICKED = "search_clicked"

DATE_FORMATS = ("%Y-%m-%d", "%d-%b-%Y")
TIME_FORMATS = ("%H:%M", "%I:%M %p", "%I:%M%p", "%H%M")
AIRPORTS_CSV = "airports.csv"

STATE_PRAYER_METHOD = "prayer_method"
STATE_SALAH_RESULT = "salah_result"

# =======================
# Parsing & Formatting
# =======================
def parse_date_safe(value: str) -> Optional[ddate]:
    text = (value or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except Exception:
            continue
    return None


def parse_time_safe(value: str) -> Optional[dtime]:
    text = (value or "").strip()
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).time()
        except Exception:
            continue
    return None


def fmt_date_human(value: str) -> str:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%a, %b %d, %Y")
        except Exception:
            continue
    return value or "—"


def ap_label(ap: Any) -> str:
    if isinstance(ap, dict):
        return ap.get("code") or ap.get("name") or "—"
    return str(ap) if ap else "—"


def chip(text: str) -> str:
    # Dark-theme friendly chip
    return (
        "<span style='display:inline-block;padding:2px 8px;border-radius:999px;"
        "border:1px solid rgba(255,255,255,.2);font-size:12px;margin-right:6px;"
        "color:#e5e7eb;background:rgba(255,255,255,.06)'>"
        f"{text}</span>"
    )

# =======================
# Data helpers
# =======================
def sort_flights(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort by (date, departure_time) DESC so the most recent appears first.
    Missing values are pushed using safe defaults.
    """
    def key(r: Dict[str, Any]) -> Tuple[ddate, dtime]:
        d = parse_date_safe(r.get("date", "")) or ddate.min
        t = parse_time_safe(r.get("departure_local", "")) or dtime(0, 0, 0)
        return (d, t)

    return sorted(list(rows), key=key, reverse=True)


@st.cache_data(show_spinner=False)
def load_airports(csv_path: str = AIRPORTS_CSV) -> List[str]:
    """
    Returns 'City, Name, IATA' option strings for selectboxes.
    Cached to avoid re-reading on every rerun.
    """
    try:
        df = pd.read_csv(csv_path, encoding="ISO-8859-1")
        df["airport_options"] = df[df.columns[0]] + ", " + df[df.columns[1]] + ", " + df[df.columns[2]]
        return df["airport_options"].tolist()
    except Exception:
        return []


def strip_tz(clock_text: str) -> str:
    """'08:20AM +03' / '02:50PM EDT' -> '08:20AM' / '02:50PM'."""
    text = (clock_text or "").strip()
    return next((tok for tok in text.split() if any(ch.isdigit() for ch in tok)), text)


def parse_local_clock_safe(value: str) -> Optional[dtime]:
    """Parse '08:20AM +03' or '14:05' into a time object using TIME_FORMATS."""
    return parse_time_safe(strip_tz(value))


def compute_flight_early(record: Dict[str, Any]) -> bool:
    """Best-effort: true if status hints 'Early'; false for 'Scheduled' or unknown."""
    status = (record.get("status") or "").lower()
    if "early" in status:
        return True
    if "scheduled" in status:
        return False
    return False


def fmt_time_ampm(value: Union[str, dtime, None]) -> str:
    """
    Normalize any time-like input (string or dtime) to 'HH:MM:SS AM/PM',
    e.g., '08:10:00 AM'. If parsing fails, returns '—' or the original string.
    """
    if isinstance(value, dtime):
        t = value
    else:
        t = parse_local_clock_safe(value or "")
    return t.strftime("%I:%M:%S %p") if t else ((value or "—") if isinstance(value, str) else "—")

# =======================
# State
# =======================
def init_state() -> None:
    st.session_state.setdefault(STATE_PAGE, PAGE_SEARCH)  
    st.session_state.setdefault(STATE_SEARCH_CLICKED, False)
    st.session_state.setdefault(STATE_SELECTED_IDX, None)
    st.session_state.setdefault(STATE_SELECTED, None)
    st.session_state.setdefault(STATE_ROWS, [])
    st.session_state.setdefault(STATE_PRAYER_METHOD, "MWL")
    st.session_state.setdefault(STATE_SALAH_RESULT, None)


def reset_selection() -> None:
    st.session_state[STATE_SELECTED_IDX] = None
    st.session_state[STATE_SELECTED] = None

# =======================
# UI Sections
# =======================
def render_header() -> None:
    st.title(APP_TITLE)
    st.markdown(f"### {APP_SUBTITLE}")


def render_prayer_method() -> str:
    methods = ["MWL", 'ISNA', 'Egypt', 'Makkah', 'Karachi', 'Tehran', "Jafari"]
    return st.selectbox("Prayer calculation method", methods, index=0, key=STATE_PRAYER_METHOD)


def render_search_controls(airports: List[str]) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """
    Returns (mode, flight_number, departure, arrival)
    Only one of (flight_number) or (departure, arrival) will be set,
    depending on the selected mode.
    """
    search_mode = st.radio(
        "Search by",
        ["Flight Number", "Route (Departure & Arrival)"],
        horizontal=True,
        key="search_mode",
    )

    flight_number: Optional[str] = None
    departure: Optional[str] = None
    arrival: Optional[str] = None

    if search_mode == "Route (Departure & Arrival)":
        col1, col2 = st.columns(2)
        with col1:
            departure = st.selectbox(
                "Departure Location", options=airports, index=None, placeholder="e.g., Dubai", key="departure_sel"
            )
        with col2:
            arrival = st.selectbox(
                "Arrival Location", options=airports, index=None, placeholder="e.g., LAX", key="arrival_sel"
            )
    else:
        flight_number = st.text_input(
            "Flight Number", placeholder="e.g., AA123", key="flight_number_input"
        )

    return search_mode, flight_number, departure, arrival


def handle_search(search_mode: str, flight_number: Optional[str], departure: Optional[str], arrival: Optional[str]) -> None:
    """
    Executes when the user clicks 'Find Matches'.
    Updates session state with results.
    """
    st.session_state[STATE_SEARCH_CLICKED] = True
    reset_selection()

    if search_mode == "Route (Departure & Arrival)":
        load = st.empty()
        load.write(f"Searching flights from **{departure or '—'}** to **{arrival or '—'}**")
        st.info("Route search coming soon. Try Flight Number for now.")
        return

    # Flight Number path
    if not (flight_number or "").strip():
        st.warning("Please enter a flight number (e.g., AA123).")
        st.session_state[STATE_ROWS] = []
        return

    with st.spinner("Fetching latest flight history..."):
        try:
            fn_input = (flight_number or "").strip().upper()
            rows = get_flight_history(fn_input)
        except Exception as e:
            st.error(f"Failed to fetch flight history: {e}")
            st.session_state[STATE_ROWS] = []
            return

        # Normalize expected shapes
        if not rows or (isinstance(rows, dict) and rows.get("error")):
            st.warning("No matching flight found. Check your spelling.")
            st.session_state[STATE_ROWS] = []
            return

        normalized = []
        for r in rows:
            if not r.get("flight_number"):
                r = {**r, "flight_number": fn_input}
            normalized.append(r)

        st.session_state[STATE_ROWS] = sort_flights(normalized)

def set_selected_variables(record: Dict[str, Any]) -> None:
    """
    Derive and stash variables you can use later.
    """
    st.session_state["flight_date"] = record.get("date") or ""
    st.session_state["Departure_time"] = parse_local_clock_safe(record.get("departure_local") or "")
    st.session_state["Flight_early"] = compute_flight_early(record)
    st.session_state["Flight_Number"] = (record.get("flight_number") or "").upper()

def call_salah_for_selected(record: Dict[str, Any], idx: int) -> None:
    # flight number: prefer record, else user's input box
    fnum = (record.get("flight_number") or (st.session_state.get("flight_number_input") or "")).upper()

    # departure_time -> "HH:MM:SS AM/PM" string (safe even if original had TZ text)
    dep_text = record.get("departure_local") or ""
    dep_obj = parse_local_clock_safe(dep_text)
    dep_arg = dep_obj.strftime("%I:%M:%S %p") if dep_obj else fmt_time_ampm(dep_text)

    # date -> (YYYY, M, D) tuple
    d_obj = parse_date_safe(record.get("date") or "")
    date_tuple = (d_obj.year, d_obj.month, d_obj.day) if d_obj else (2025, 8, 1)

    # early flag + method + index
    early = compute_flight_early(record)
    method = st.session_state.get(STATE_PRAYER_METHOD, "MWL")

    try:
        result = salah_calculator(
            flightnumber=fnum,
            departure_time=dep_arg,
            prayer_method=method,
            date=date_tuple,
            flight_early=early,
            debug=False,
            datalog_index=-1,
        )
        st.session_state[STATE_SALAH_RESULT] = result
        st.toast("Salah plan calculated ✅", icon="🕌")
    except Exception as e:
        st.error(f"Salah calculator failed: {e}")

# =======================
# Categorization helpers (with stable, vertical layout)
# =======================
from datetime import datetime as dt

def _combine_local_datetime(record: Dict[str, Any]) -> Optional[datetime]:
    """Best-effort combine record['date'] + record['departure_local'] (no tz)."""
    d = parse_date_safe(record.get("date") or "")
    t = parse_local_clock_safe(record.get("departure_local") or "")
    if not d and not t:
        return None
    d = d or dt.now().date()
    t = t or dtime(0, 0, 0)
    return dt.combine(d, t)

def categorize_flights(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    current: date == today (or now between dep/arr if both exist)
    upcoming: dep in the future
    past: dep in the past
    """
    now = dt.now()
    today = now.date()

    current, future, past = [], [], []
    for r in rows:
        dep_dt = _combine_local_datetime(r)
        if dep_dt is None:
            past.append(r)  # unknown timing -> shove to past
            continue

        arr_t = parse_local_clock_safe(r.get("arrival_local") or "")
        arr_dt = dt.combine(parse_date_safe(r.get("date") or "") or dep_dt.date(), arr_t) if arr_t else None

        if dep_dt.date() == today:
            if arr_dt and dep_dt <= now <= arr_dt:
                current.append(r)
            else:
                current.append(r)  # same-day flights grouped as current
        elif dep_dt > now:
            future.append(r)
        else:
            past.append(r)

    return {
        "current": sort_flights(current),
        "future": sort_flights(future),
        "past": sort_flights(past),
    }

# =======================
# Flight card (dark theme, stable height)
# =======================
def _select_flight(record: Dict[str, Any], idx: int) -> None:
    st.session_state[STATE_SELECTED_IDX] = idx
    st.session_state[STATE_SELECTED] = record

    # Also store the variables you wanted handy
    st.session_state["date"] = record.get("date") or ""
    dep_obj = parse_local_clock_safe(record.get("departure_local") or "")
    st.session_state["departure_time"] = dep_obj
    st.session_state["Flight_early"] = compute_flight_early(record)
    st.session_state["flightnumber"] = (record.get("flight_number") or "").upper()

    # Call calculator
    call_salah_for_selected(record, idx)

    # Flip to details page and rerun
    st.session_state[STATE_PAGE] = PAGE_PLAN      # <-- new
    st.toast("Flight selected", icon="✈️")       

def flight_card(record: Dict[str, Any], idx: int, selected_idx: Optional[int]) -> None:
    fn = (record.get("flight_number") or "").upper()
    org = ap_label(record.get("origin", {}))
    dst = ap_label(record.get("destination", {}))
    date_h = fmt_date_human(record.get("date", ""))
    dep = record.get("departure_local") or "—"
    arr = record.get("arrival_local") or "—"
    stat = record.get("status", "")

    is_selected = (selected_idx == idx)

    # Dark theme colors
    border = "#60a5fa" if is_selected else "rgba(255,255,255,.18)"
    bg = "rgba(37,99,235,0.16)" if is_selected else "#0f172a"   # selected: blue-tinted; base: slate-900
    text_primary = "#f8fafc"   # near-white
    text_muted = "rgba(248,250,252,.75)"  # muted near-white

    badge = "✓ Selected" if is_selected else "Select"

    with st.container():
        st.markdown(
            f"""
            <div style="
                border:1px solid {border};
                background:{bg};
                padding:14px 16px;
                border-radius:12px;
                margin-bottom:10px;
                color:{text_primary};">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="font-size:18px;font-weight:700;line-height:1.2;">
                        {fn} · {org} → {dst}
                    </div>
                    <div style="font-size:13px;color:{text_muted};">{stat or ""}</div>
                </div>
                <div style="font-size:13px;color:{text_muted};margin-top:4px;">📅 {date_h}</div>
                <div style="font-size:15px;margin-top:8px;">🛫 {dep} · {org}
                    &nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp; 🛬 {arr} · {dst}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.button(
            badge,
            key=f"select_{idx}",
            on_click=_select_flight,
            args=(record, idx),
            use_container_width=True,
        )

# =======================
# Results (vertical, 3 sections)
# =======================

def render_plan_page() -> None:
    st.subheader("Salah plan for selected flight")

    result = st.session_state.get(STATE_SALAH_RESULT)
    selected = st.session_state.get(STATE_SELECTED)

    if not selected:
        st.info("No flight selected.")
        if st.button("Back to search"):
            st.session_state[STATE_PAGE] = PAGE_SEARCH
            st.rerun()
        return

    # Header summary
    fn = (selected.get("flight_number") or "").upper()
    org = ap_label(selected.get("origin", {}))
    dst = ap_label(selected.get("destination", {}))
    date_h = fmt_date_human(selected.get("date", ""))
    st.markdown(f"**{fn}** — {org} → {dst} · {date_h}")

    # Render calculator output (expects a dict, see step 2)
    if isinstance(result, dict):
        # Textual schedule (ordered)
        schedule = result.get("schedule", [])
        if schedule:
            st.markdown("### Times (in-flight matches)")
            for item in schedule:
                st.write(f"- **{item['label'].title()}** at {item['time_12h']}")

        # Qiblah figures
        figs = result.get("qibla_figs", [])
        if figs:
            st.markdown("### Qiblah directions")
            for fig in figs:
                st.plotly_chart(fig, use_container_width=True)

        # Debug plots if you choose to return them
        debug_fig = result.get("debug_fig")
        if debug_fig:
            st.markdown("### Debug")
            st.pyplot(debug_fig)
    else:
        # Fallback to whatever the function returned
        st.write(result)

    st.divider()
    if st.button("Back to search"):
        st.session_state[STATE_PAGE] = PAGE_SEARCH
        st.rerun()

def render_results() -> None:
    rows: List[Dict[str, Any]] = st.session_state.get(STATE_ROWS, [])
    if not rows:
        return

    # Freeze indices so keys are stable across categories
    indexed_rows = [{**r, "_idx": i} for i, r in enumerate(rows)]
    cats = categorize_flights(indexed_rows)

    st.caption(f"{len(rows)} flights found. Sorted by most recent departure first.")

    selected_idx = st.session_state.get(STATE_SELECTED_IDX)

    def _section(title: str, items: List[Dict[str, Any]]) -> None:
        if not items:
            return
        st.subheader(title)
        for r in items:
            flight_card(r, r["_idx"], selected_idx)

    _section("Current flights", cats["current"])
    _section("Upcoming flights", cats["future"])
    _section("Past flights", cats["past"])


# =======================
# App Entrypoint
# =======================
def main() -> None:
    init_state()
    render_header()

    if st.session_state[STATE_PAGE] == PAGE_SEARCH:
        render_prayer_method()
        airports = load_airports()
        mode, flight_number, departure, arrival = render_search_controls(airports)

        if st.button("Find Matches", key="search_btn"):
            handle_search(mode, flight_number, departure, arrival)

        render_results()

    elif st.session_state[STATE_PAGE] == PAGE_PLAN:
        render_plan_page()

if __name__ == "__main__":
    main()