import streamlit as st
import pandas as pd
import json
import time
from datetime import timedelta, datetime

# ===============================
# Helpers
# ===============================
def format_duration(minutes: int) -> str:
    td = timedelta(minutes=minutes)
    hours, remainder = divmod(td.seconds, 3600)
    mins = remainder // 60
    return f"{td.days*24 + hours}:{mins:02d}"

def format_iso_utc(dt_str: str) -> str:
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    return dt.strftime("%b %d, %Y • %I:%M %p %Z")

# ===============================
# Load data
# ===============================
df = pd.read_csv("airports.csv", encoding='ISO-8859-1')
df["airport_options"] = df[df.columns[0]] + ", " + df[df.columns[1]] + ", " + df[df.columns[2]]
airports = df["airport_options"].tolist()

with open("FrontendFakeFlights.json", "r") as f:
    flights_data = json.load(f)["flights"]

# ===============================
# State
# ===============================
if "search_clicked" not in st.session_state:
    st.session_state.search_clicked = False
if "selected_flight" not in st.session_state:
    st.session_state.selected_flight = None

# ===============================
# UI
# ===============================
st.title('Salah@35k')
st.markdown("### Find your flight")

search_mode = st.radio("Search by", ["Route (Departure & Arrival)", "Flight Number"], horizontal=True)

departure = arrival = flight_number = None

if search_mode == "Route (Departure & Arrival)":
    col1, col2 = st.columns(2)
    with col1:
        departure = st.selectbox("Departure Location", options=airports, index=None, placeholder="e.g., New York")
    with col2:
        arrival = st.selectbox("Arrival Location", options=airports, index=None, placeholder="e.g., Los Angeles")
else:
    flight_number = st.text_input("Flight Number", placeholder="e.g., AA123")

# ===============================
# Search logic
# ===============================
if st.button("Find Matches"):
    st.session_state.search_clicked = True
    st.session_state.selected_flight = None
    Load = st.empty()

    if search_mode == "Route (Departure & Arrival)":
        if not departure or not arrival:
            st.warning("Please select both departure and arrival airports.")
        else:
            Load.write(f"Searching flights from **{departure}** to **{arrival}**...")
            time.sleep(1)

            dep_iata = departure.split(",")[-1].strip()
            arr_iata = arrival.split(",")[-1].strip()

            matches = [
                f for f in flights_data
                if f["from_airport"]["iata"].lower() == dep_iata.lower()
                and f["to_airport"]["iata"].lower() == arr_iata.lower()
            ]

            if not matches:
                st.info("No flights found for the selected route.")
            else:
                Load.write("### Select Your Flight")
                for f in matches:
                    flight_id = f"{f['flight_number']}_{f['from_airport']['iata']}_{f['to_airport']['iata']}"
                    dep_human = format_iso_utc(f['departure_time'])
                    arr_human = format_iso_utc(f['arrival_time'])
                    duration = format_duration(f['duration_minutes'])

                    btn_clicked = st.button(
                        f"""**{f['flight_number']}** · **{f['from_airport']['iata']} ➔ {f['to_airport']['iata']}**  
**🛫 Departure:** {dep_human}  
**🛬 Arrival:** {arr_human}  
**⏱ Duration:** {duration}""",
                        key=flight_id
                    )

                    if btn_clicked:
                        st.session_state.selected_flight = flight_id

    else:  # search_mode == "Flight Number"
        if not flight_number or not flight_number.strip():
            st.warning("Please enter a flight number.")
        else:
            query = flight_number.strip().upper()
            Load.write(f"Searching for flights matching **{query}**...")
            time.sleep(1)

            matches = [f for f in flights_data if f["flight_number"].upper().startswith(query)]

            if not matches:
                st.info("No flights found for that flight number.")
            else:
                Load.write("### Select Your Flight")
                for f in matches:
                    flight_id = f"{f['flight_number']}_{f['from_airport']['iata']}_{f['to_airport']['iata']}"
                    dep_human = format_iso_utc(f['departure_time'])
                    arr_human = format_iso_utc(f['arrival_time'])
                    duration = format_duration(f['duration_minutes'])

                    btn_clicked = st.button(
                        f"""**{f['flight_number']}** · **{f['from_airport']['iata']} ➔ {f['to_airport']['iata']}**  
**🛫 Departure:** {dep_human}  
**🛬 Arrival:** {arr_human}  
**⏱ Duration:** {duration}""",
                        key=flight_id
                    )

                    if btn_clicked:
                        st.session_state.selected_flight = flight_id

# ===============================
# Selected flight details
# ===============================
if st.session_state.search_clicked and st.session_state.selected_flight:
    selected_flight = next(
        (f for f in flights_data if f"{f['flight_number']}_{f['from_airport']['iata']}_{f['to_airport']['iata']}" == st.session_state.selected_flight),
        None
    )

    if selected_flight:
        st.markdown("---")
        st.subheader(f"✈ Flight {selected_flight['flight_number']} Details")
        st.markdown(
            f"""
**From:** {selected_flight['from_airport']['name']} ({selected_flight['from_airport']['iata']})  
**To:** {selected_flight['to_airport']['name']} ({selected_flight['to_airport']['iata']})  

**🛫 Departure:** {format_iso_utc(selected_flight['departure_time'])}  
**🛬 Arrival:** {format_iso_utc(selected_flight['arrival_time'])}  
**⏱ Duration:** {format_duration(selected_flight['duration_minutes'])}
"""
        )
