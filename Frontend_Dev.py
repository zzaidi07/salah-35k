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
STATE_CURRENT_VIEW = "current_view"  # "search" or "results"


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
    if (
        not selected_airline
        or selected_airline == "All airlines"
        or selected_airline == "Select an Airline"
    ):
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


def filter_by_date(records: list, selected_date):
    """Return only flights whose Dep_date == YYYY-MM-DD of selected_date."""
    if not selected_date:
        return records
    want = selected_date.strftime("%Y-%m-%d")
    return [r for r in records if r.get("Dep_date") == want]


def search_view():
    """Display the flight search interface"""
    st.title("✈️ Salah@35k")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.session_state["mode"] = st.radio(
            "Search Mode",
            options=["Flight Number", "Destination & Arrival"],
            index=0,
            horizontal=True,
            help="Choose how you want to search for flights.",
        )
    with col2:
        prayer_method = st.selectbox(
            "Prayer Method",
            options=["Jafari", "Tehran", "MWL", "ISNA", "Egypt", "Makkah", "Karachi"],
            index=0,
            help="Choose how you want your prayer method calculated",
        )

    if st.session_state.get("mode") == "Flight Number":
        st.caption("Search for your flight number")

        with st.form("search"):
            Flightnum = st.text_input(
                "Flight Number",
                placeholder="Search Flight Number...",
            )
            submit = st.form_submit_button("Find Flights", use_container_width=True)

        if submit:
            if not Flightnum:
                st.warning("Please search for a flight number.")
            else:
                with st.spinner(f"Searching flights {Flightnum}…"):
                    try:
                        result = get_flight_history_json(Flightnum)
                        payload = result[0] if isinstance(result, tuple) else result
                        data = json.loads(payload)
                        flights = data.get("items", [])
                        for r in flights:
                            if isinstance(r, dict):
                                r["ident"] = Flightnum
                        st.session_state["records_by_flightnum"] = flights  # <-- store
                    except Exception as e:
                        st.error(f"Error fetching flights: {e}")
                        st.session_state.pop("records_by_flightnum", None)

        # Render results if we have them (even when submit=False on reruns)
        records = st.session_state.get("records_by_flightnum")
        if records:
            try:
                df = pd.DataFrame(records)
                items = df.to_dict("records")
            except Exception:
                items = records or []

            selected = render_flight_cards(items, section_title="Flights")
            if selected:
                # Store prayer method and selected flight, then switch to results view
                st.session_state["selected_prayer_method"] = prayer_method
                st.session_state["selected_flight_data"] = selected
                st.session_state[STATE_CURRENT_VIEW] = "results"
                st.rerun()

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
        # ---- inside "Destination & Arrival" mode ----
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
                airlines_df = pd.read_csv(Airlines_csv)
                # Make options a list of strings, not a DataFrame
                airline_options = ["Select an Airline"] + sorted(
                    {str(a) for a in airlines_df.iloc[:, 0].dropna().tolist()}
                )
                selected_option = st.selectbox(
                    "Select an Airline (Optional)", airline_options, index=0
                )
            with col4:
                selected_date = st.date_input("Select a Date (Optional)", value=None)

            submitted = st.form_submit_button("Find Flights", use_container_width=True)

        if submitted:
            if not dep_label or not arr_label:
                st.warning("Please select both departure and arrival airports.")
            else:
                dep_icao = label_to_icao[dep_label]
                arr_icao = label_to_icao[arr_label]
                if dep_icao == arr_icao:
                    st.warning("Departure and arrival airports must be different.")
                else:
                    with st.spinner(f"Searching flights {dep_icao} → {arr_icao}…"):
                        try:
                            result = find_flights(dep_icao, arr_icao)
                            payload = result[0] if isinstance(result, tuple) else result
                            data = json.loads(payload)
                            flights = data.get("items", [])
                            # Enrich records now; store in state
                            for r in flights:
                                if isinstance(r, dict):
                                    r["origin"] = dep_icao
                                    r["destination"] = arr_icao
                                    r["Dep_date"] = FetchDate(
                                        r.get("departure"), r.get("status")
                                    )
                                    r["Arr_date"] = FetchDate(
                                        r.get("arrival"), r.get("status")
                                    )

                            # Optional airline filter
                            try:
                                df = pd.DataFrame(flights)
                                df = filter_by_airline(df, selected_option)
                                flights = df.to_dict("records")
                                flights = filter_by_date(flights, selected_date)
                            except Exception:
                                pass

                            st.session_state["records_by_route"] = flights  # <-- store
                        except Exception as e:
                            st.error(f"Error fetching flights: {e}")
                            st.session_state.pop("records_by_route", None)

        # Render results if we have them (even when submitted=False on reruns)
        records = st.session_state.get("records_by_route")
        if records:
            selected = render_flight_cards(records, section_title="Flights")
            if selected:
                # Store prayer method and selected flight, then switch to results view
                st.session_state["selected_prayer_method"] = prayer_method
                st.session_state["selected_flight_data"] = selected
                st.session_state[STATE_CURRENT_VIEW] = "results"
                st.rerun()


def results_view():
    """Display the results page with flight info, salah times, and qiblah directions"""
    selected = st.session_state.get("selected_flight_data")
    prayer_method = st.session_state.get("selected_prayer_method", "ISNA")

    if not selected:
        st.error("No flight data found. Please return to search.")
        if st.button("Return to Search"):
            st.session_state[STATE_CURRENT_VIEW] = "search"
            st.rerun()
        return

    # Add return to search button at the top
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🔙 Return to Search", use_container_width=True):
            # Clear all search results and selections when returning to search
            st.session_state.pop("records_by_flightnum", None)
            st.session_state.pop("records_by_route", None)
            st.session_state.pop(STATE_SELECTED_FLIGHT, None)
            st.session_state.pop(STATE_SELECTED_IDX, None)
            st.session_state.pop("selected_flight_data", None)
            st.session_state.pop("selected_prayer_method", None)
            st.session_state[STATE_CURRENT_VIEW] = "search"
            st.rerun()

    st.title("🕌 Salah Times and Qiblah Directions")

    # Extract flight information from selected flight
    flight_number = selected.get("ident", "")
    departure_time_str = selected.get("departure", "")
    dep_date_str = selected.get("Dep_date") or selected.get("date", "")

    # Parse departure time
    departure_time = parse_time(departure_time_str) if departure_time_str else None

    # Parse date
    if dep_date_str:
        try:
            dep_date = datetime.strptime(dep_date_str, "%Y-%m-%d").date()
            date_tuple = (dep_date.year, dep_date.month, dep_date.day)
        except:
            # Fallback to today's date if parsing fails
            today = datetime.now().date()
            date_tuple = (today.year, today.month, today.day)
    else:
        today = datetime.now().date()
        date_tuple = (today.year, today.month, today.day)

    # Check if flight is early
    status = (selected.get("status") or "").lower()
    flight_early = IsFlightEarly(status)

    # Display flight information
    st.subheader("✈️ Flight Information")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Flight Number", flight_number or "N/A")
    with col2:
        st.metric("Departure Time", departure_time or "N/A")
    with col3:
        st.metric("Date", f"{date_tuple[1]}/{date_tuple[2]}/{date_tuple[0]}")

    if not flight_number:
        st.error("Flight number not found in selected flight data.")
        return

    if not departure_time:
        st.error("Departure time not found in selected flight data.")
        return

    # Calculate salah times and qiblah directions
    with st.spinner("Calculating salah times and qiblah directions..."):
        try:
            result = salah_calculator(
                flightnumber=flight_number,
                departure_time=departure_time,
                prayer_method=prayer_method,
                date=date_tuple,
                flight_early=flight_early,
                debug=False,  # Set to False for production
                datalog_index=0,  # Use first datalog by default
            )

            # Display prayer schedule with improved styling
            st.subheader("📅 Prayer Schedule")
            if result.get("schedule"):
                schedule_df = pd.DataFrame(result["schedule"])
                # Filter to only show label and time_12h columns
                display_df = schedule_df[["label", "time_12h"]].copy()
                display_df.columns = ["Prayer", "Time"]

                # Style the table
                st.markdown(
                    """
                <style>
                .prayer-table {
                    font-size: 16px;
                    border-collapse: collapse;
                    width: 100%;
                }
                .prayer-table th {
                    background-color: #262730;
                    color: #262730;
                    font-weight: bold;
                    padding: 12px;
                    text-align: left;
                    border-bottom: 2px solid #000000;
                }
                .prayer-table td {
                    padding: 12px;
                    border-bottom: 1px solid #000000;
                }
                .prayer-table tr:nth-child(even) {
                    background-color: #262730;
                }
                .prayer-table tr:hover {
                    background-color: #4a4b52;
                }
                </style>
                """,
                    unsafe_allow_html=True,
                )

                # Convert to HTML table for better styling
                html_table = display_df.to_html(
                    classes="prayer-table", index=False, escape=False
                )
                st.markdown(html_table, unsafe_allow_html=True)
            else:
                st.warning("No prayer schedule available.")

            # Display qiblah directions
            st.subheader("🧭 Qiblah Directions")
            if result.get("qibla_figs"):
                for i, fig in enumerate(result["qibla_figs"]):
                    st.plotly_chart(fig, use_container_width=True)
                    if i < len(result["qibla_figs"]) - 1:
                        st.divider()
            else:
                st.warning("No qiblah direction data available.")

        except Exception as e:
            st.error(f"Error calculating salah times: {str(e)}")
            st.info(
                "This might be due to network issues or missing flight data. Please try again later."
            )


def menu():
    """Main function that handles view switching"""
    # Initialize view state if not set
    if STATE_CURRENT_VIEW not in st.session_state:
        st.session_state[STATE_CURRENT_VIEW] = "search"

    current_view = st.session_state[STATE_CURRENT_VIEW]

    if current_view == "search":
        search_view()
    elif current_view == "results":
        results_view()
    else:
        # Fallback to search view
        st.session_state[STATE_CURRENT_VIEW] = "search"
        search_view()


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
