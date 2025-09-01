import json, re
from pathlib import Path
from FlightDatalogic import find_flights, get_flight_history_json, FetchDate
from salah_at_35k_calculator import salah_calculator
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, Optional, Iterable
import pandas as pd
import streamlit as st
from dateutil import parser as date_parser
import pytz


st.set_page_config(page_title="Flight Finder", page_icon="✈️", layout="wide")

airports_csv = Path("airports.csv")
Airlines_csv = Path("Airlines.csv")
STATE_SELECTED_IDX = "selected_flight_idx"
STATE_SELECTED_FLIGHT = "selected_flight"


@st.cache_data(show_spinner=False)
def load_airports(csv_path: Path) -> pd.DataFrame:
    # Read CSV
    df = pd.read_csv(csv_path)
    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]
    required_cols = {"location", "airport", "icao"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(missing)}")

    # Ensure ICAO is uppercase, remove blanks
    df["icao"] = df["icao"].astype(str).str.strip().str.upper()

    # Build search-friendly label: "Airport Name — Location (ICAO)"
    df["label"] = df.apply(
        lambda r: f"{r['airport']} — {r['location']} ({r['icao']})", axis=1
    )

    # Drop duplicate ICAOs just in case
    df = df.drop_duplicates(subset=["icao"]).sort_values("location", kind="stable")
    return df[["label", "icao", "airport", "location"]]


def IsFlightEarly(status: str) -> bool:
    if status == "Early":
        return True
    else:
        return False


def parse_flight_datetime(time_str: str) -> Optional[str]:
    if not time_str or not isinstance(time_str, str):
        return None

    try:
        # Example: "Sat 09:00PM PDT" -> parse automatically
        dt = date_parser.parse(time_str, fuzzy=True)

        # Ensure it's timezone-aware; if missing, assume UTC
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)

        # Convert to ISO date (YYYY-MM-DD) for consistency
        return dt.strftime("%Y-%m-%d")

    except Exception:
        return None


def _norm(s: str) -> str:
    """Normalize airline names for tolerant comparisons."""
    s = str(s or "").casefold().strip()
    s = re.sub(r'["“”‘’\'.,&/()\-]', " ", s)  # drop punctuation
    s = re.sub(r"\s+", " ", s)  # collapse spaces
    return s


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def parse_time(input_str: str) -> str:
    # Use regex to extract the time (e.g., 08:27AM)
    match = re.search(r"\b\d{1,2}:\d{2}[APMapm]{2}\b", input_str)
    if not match:
        return None  # If no valid time is found

    # Parse the extracted time
    raw_time = match.group()
    parsed_time = datetime.strptime(raw_time.upper(), "%I:%M%p")

    # Convert to desired format hh:mm:ss AM/PM
    return parsed_time.strftime("%I:%M:%S %p")


def _ap_label(ap: Any) -> str:
    """Return a readable airport label from dict or string."""
    if isinstance(ap, dict):
        name = ap.get("name") or ap.get("airport")
        code = ap.get("code") or ap.get("icao") or ap.get("iata")
        if name and code:
            return f"{name} ({code})"
        return name or code or "—"
    return str(ap) if ap else "—"


def filter_by_airline(df: pd.DataFrame, selected_airline: str) -> pd.DataFrame:
    """Filter df (expects a column named 'airline', any case) to the selected airline."""
    if not selected_airline or selected_airline == "All airlines":
        return df

    # locate the column regardless of case
    col_map = {c.lower(): c for c in df.columns}
    if "airline" not in col_map:
        return df  # nothing to filter on

    col = col_map["airline"]
    target = _norm(selected_airline)
    series_norm = df[col].fillna("").map(_norm)

    # exact OR very close (handles tiny punctuation/spacing diffs)
    exact_mask = series_norm == target
    close_mask = series_norm.map(lambda s: _similar(s, target) >= 0.92)

    return df[exact_mask | close_mask]


def menu():
    st.title("✈️ Salah@35k")

    st.session_state["mode"] = st.radio(
        "Search Mode",
        options=["Flight Number", "Destination & Arrival"],
        index=0,
        horizontal=True,
        help="Choose how you want to search for flights.",
    )

    if st.session_state.get("mode") == "Flight Number":
        st.caption("Search for your flight number")

        with st.form("search"):
            Flightnum = st.text_input(
                "Flight Number",
                placeholder="Search Flight Number...",
            )
            submit = st.form_submit_button("Find Flights", use_container_width=True)

        if not submit:
            return

        if not Flightnum:
            st.warning("Please search for a flight number.")
            return

        with st.spinner(f"Searching flights {Flightnum}…"):
            try:
                result = get_flight_history_json(Flightnum)
                status_code = 200
                if isinstance(result, tuple):
                    payload, status_code = result
                else:
                    payload = result

                data = json.loads(payload)
            except Exception as e:
                st.error(f"Error fetching flights: {e}")
                return

        flights = data.get("items", [])
        if not flights:
            st.info("No flights found for this route right now.")
            return

        # Turn results into DataFrame
        try:
            df = pd.DataFrame(flights)
        except Exception:
            df = pd.json_normalize(flights)

        records = (
            df.to_dict("records") if isinstance(df, pd.DataFrame) else (flights or [])
        )

        selected = render_flight_cards(records, section_title="Flights")

        if selected:
            st.success("Selected flight")
            st.json(selected)

    if st.session_state.get("mode") == "Destination & Arrival":
        st.caption("Select departure and arrival airports")

        try:
            airports = load_airports(airports_csv)
        except Exception as e:
            st.error(f"Failed to load airports CSV: {e}")
            st.stop()

        # Build lookup mapping for ICAO codes
        label_to_icao = dict(zip(airports["label"], airports["icao"]))

        # Search inputs
        with st.form("search"):
            col1, col2 = st.columns(2)

            with col1:
                dep_label = st.selectbox(
                    "Departure Airport",
                    options=airports["label"].tolist(),
                    index=None,
                    placeholder="Search departure airport...",
                )

            with col2:
                arr_label = st.selectbox(
                    "Arrival Airport",
                    options=airports["label"].tolist(),
                    index=None,
                    placeholder="Search arrival airport...",
                )
            col3, col4 = st.columns(2)
            with col3:
                options = df = pd.read_csv(Airlines_csv)
                selected_option = st.selectbox(
                    "Select an Airline (Optional)",
                    options,
                    index=None,
                    placeholder="Search airline...",
                )
            with col4:
                selected_date = st.date_input("Select a Date (Optional)", value=None)

            submitted = st.form_submit_button("Find Flights", use_container_width=True)

        if not submitted:
            return

        if not dep_label or not arr_label:
            st.warning("Please select both departure and arrival airports.")
            return

        dep_icao = label_to_icao[dep_label]
        arr_icao = label_to_icao[arr_label]

        if dep_icao == arr_icao:
            st.warning("Departure and arrival airports must be different.")
            return

        # Call scraper
        with st.spinner(f"Searching flights {dep_icao} → {arr_icao}…"):
            try:
                result = find_flights(dep_icao, arr_icao)
                status_code = 200
                if isinstance(result, tuple):
                    payload, status_code = result
                else:
                    payload = result
                data = json.loads(payload)
            except Exception as e:
                st.error(f"Error fetching flights: {e}")
                return

        # Check for API errors
        if status_code != 200 or "items" not in data:
            msg = data.get("message", "No results parsed.")
            st.error(msg)
            if data.get("error"):
                st.caption(f"Error: {data['error']}")
            if data.get("tried_urls"):
                with st.expander("Tried URLs"):
                    for url in data["tried_urls"]:
                        st.code(url)
            return
        # Display results

        flights = data.get("items", [])
        if not flights:
            st.info("No flights found for this route right now.")
            return

        # Turn results into DataFrame
        try:
            df = pd.DataFrame(flights)
            filtered_df = filter_by_airline(df, selected_option)
        except Exception:
            df = pd.json_normalize(flights)

        records = (
            filtered_df.to_dict("records")
            if isinstance(filtered_df, pd.DataFrame)
            else (flights or [])
        )

        for r in records:
            if isinstance(r, dict):
                r["origin"] = dep_icao
                r["destination"] = arr_icao
                r["Dep_date"] = FetchDate(r.get("departure"), r.get("status"))
                r["Arr_date"] = FetchDate(r.get("arrival"), r.get("status"))
        selected = render_flight_cards(records, section_title="Flights")

        if selected:
            salah_calculator(
                flightnumber=selected.get("ident"),
                departure_time=selected.get(parse_time("date"))
                or selected.get("departure"),
                prayer_method="MWL",  # or get this from a selectbox if needed
                date=selected.get("Dep_date") or selected.get("date"),
                flight_early=IsFlightEarly(
                    selected.get("status") or selected.get("flight_status")
                ),
                debug=False,
                datalog_index=0,
            )
        if selected:
            st.success("Selected flight")
            st.json(selected)


def _flight_card(record: Dict[str, Any], idx: int, selected_idx: Optional[int]) -> bool:
    """Render one card; return True if its button was clicked."""
    org = _ap_label(
        record.get("origin")
        or record.get("from")
        or record.get("departure_airport")
        or {}
    )
    dst = _ap_label(
        record.get("destination")
        or record.get("to")
        or record.get("arrival_airport")
        or {}
    )
    # Date & status
    date_h = record.get("Dep_date") or record.get("date")

    dep = (
        record.get("departure_local")
        or record.get("departureLocal")
        or record.get("departure")
        or "—"
    )
    arr = (
        record.get("arrival_local")
        or record.get("arrivalLocal")
        or record.get("arrival")
        or "—"
    )
    stat = (
        record.get("status")
        or record.get("flight_status")
        or record.get("statusText")
        or ""
    )

    fn = record.get("ident", "")
    airline = record.get("airline") or ""

    aircraft = record.get("aircraft") or record.get("aircraftType")
    duration = record.get("duration") or record.get("block_time")

    is_selected = selected_idx == idx
    border = "#60a5fa" if is_selected else "rgba(255,255,255,.18)"
    bg = "rgba(37,99,235,0.16)" if is_selected else "#0f172a"
    text_primary = "#f8fafc"
    text_muted = "rgba(248,250,252,.75)"
    badge = "✓ Selected" if is_selected else "Select"

    extra = " · ".join([p for p in [aircraft, duration] if p])  # e.g. "B77W · 12:41"

    top_line = f"{fn} · " if fn else ""
    if airline:
        top_line += f"{airline} · "
    top_line += f"{org} → {dst}"

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
                <div style="font-size:18px;font-weight:700;">
                    {top_line}
                </div>
                <div style="font-size:13px;color:{text_muted};margin-top:4px;">
                    📅 {date_h} &nbsp;|&nbsp; {stat}{(" &nbsp;|&nbsp; " + extra) if extra else ""}
                </div>
                <div style="font-size:16px;font-weight:600;margin-top:10px;">
                    🛫 Departure: <span style="color:{text_primary};">{dep}</span> from {org}
                </div>
                <div style="font-size:16px;font-weight:600;margin-top:4px;">
                    🛬 Arrival: <span style="color:{text_primary};">{arr}</span> at {dst}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return st.button(badge, key=f"select_{idx}", use_container_width=True)


def render_flight_cards(
    records: Iterable[Dict[str, Any]], section_title: str = "Flights"
) -> Optional[Dict[str, Any]]:
    """
    Render a list of flight cards. Returns the selected record (dict) or None.
    """
    st.session_state.setdefault(STATE_SELECTED_IDX, None)
    st.session_state.setdefault(STATE_SELECTED_FLIGHT, None)
    st.subheader(section_title)

    items = list(records or [])

    selected_idx = st.session_state.get(STATE_SELECTED_IDX)
    clicked_idx: Optional[int] = None

    for i, rec in enumerate(items):
        if isinstance(rec, dict) and _flight_card(rec, i, selected_idx):
            clicked_idx = i

    if clicked_idx is not None:
        st.session_state[STATE_SELECTED_IDX] = clicked_idx
        st.session_state[STATE_SELECTED_FLIGHT] = items[clicked_idx]  # <-- keep dict
        st.toast("Flight selected", icon="✈️")

    return st.session_state.get(STATE_SELECTED_FLIGHT)


if __name__ == "__main__":
    menu()
