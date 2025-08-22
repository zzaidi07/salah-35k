import json, io, re
from pathlib import Path
from FlightDatalogic import find_flights
from FlightDatalogic import get_flight_history_json
from datetime import date
from difflib import SequenceMatcher
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Flight Finder", page_icon="✈️", layout="wide")

airports_csv = Path("airports.csv")
Airlines_csv = Path("Airlines.csv")


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


def _norm(s: str) -> str:
    """Normalize airline names for tolerant comparisons."""
    s = str(s or "").casefold().strip()
    s = re.sub(r'["“”‘’\'.,&/()\-]', " ", s)  # drop punctuation
    s = re.sub(r"\s+", " ", s)  # collapse spaces
    return s


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


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

        count = data.get("count", 0)
        st.metric("Flights Found", count)

        if data.get("source"):
            st.caption(f"Source: {data['source']}")

        flights = data.get("items", [])
        if not flights:
            st.info("No flights found for this route right now.")
            return

        # Turn results into DataFrame
        try:
            df = pd.DataFrame(flights)
        except Exception:
            df = pd.json_normalize(flights)

        st.dataframe(df, use_container_width=True, hide_index=True)

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
        count = data.get("count", 0)
        st.metric("Flights Found", count)

        if data.get("source"):
            st.caption(f"Source: {data['source']}")

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

        st.dataframe(filtered_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    menu()
