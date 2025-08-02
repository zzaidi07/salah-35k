import streamlit as st
import pandas as pd
import json
import time
from datetime import timedelta

# --- Load airport options
df = pd.read_csv("airports.csv", encoding='ISO-8859-1')
df["airport_options"] = df[df.columns[0]] + ", " + df[df.columns[1]] + ", " + df[df.columns[2]]
airports = df["airport_options"].tolist()

# --- Load Flights JSON
with open("FrontendFakeFlights.json", "r") as f:
    flights_data = json.load(f)["flights"]

# --- Logo Map
logo_map = {
    "AA": "https://upload.wikimedia.org/wikipedia/commons/b/b1/Logo_text_American_Airlines_%281967-2013%29.png",
    "BA": "https://upload.wikimedia.org/wikipedia/en/1/15/British_Airways_Logo.svg",
    "DL": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9b/Delta_Air_Lines_Logo.svg/512px-Delta_Air_Lines_Logo.svg.png",
    "AF": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f0/Air_France_Logo.svg/2560px-Air_France_Logo.svg.png",
    "QF": "https://upload.wikimedia.org/wikipedia/en/thumb/4/4e/Qantas_Airways_Logo_2016.svg/512px-Qantas_Airways_Logo_2016.svg.png",
    "LH": "https://upload.wikimedia.org/wikipedia/en/thumb/9/9c/Lufthansa_Logo_2018.svg/512px-Lufthansa_Logo_2018.svg.png",
    "EK": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cd/Emirates_logo.svg/512px-Emirates_logo.svg.png",
    "CX": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2e/Cathay_Pacific_logo_2014.svg/512px-Cathay_Pacific_logo_2014.svg.png",
    "UA": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/66/United_Airlines_Logo.svg/512px-United_Airlines_Logo.svg.png",
    "NH": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/25/All_Nippon_Airways_logo.svg/512px-All_Nippon_Airways_logo.svg.png"
}

# --- Helpers
def format_duration(minutes):
    td = timedelta(minutes=minutes)
    hours, remainder = divmod(td.seconds, 3600)
    minutes = remainder // 60
    return f"{td.days*24 + hours}:{minutes:02d}"

# --- State
if "search_clicked" not in st.session_state:
    st.session_state.search_clicked = False
if "selected_flight" not in st.session_state:
    st.session_state.selected_flight = None

# --- UI
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

# --- Search logic
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
                if f["from_airport"]["iata"].lower() == dep_iata.lower() and
                   f["to_airport"]["iata"].lower() == arr_iata.lower()
            ]

            if not matches:
                st.info("No flights found for the selected route.")
            else:
                Load.write("### Select Your Flight")
                for f in matches:
                    flight_id = f"{f['flight_number']}_{f['from_airport']['iata']}_{f['to_airport']['iata']}"
                    selected = st.session_state.selected_flight == flight_id
                    airline_prefix = f['flight_number'][:2]
                    logo = logo_map.get(airline_prefix, "https://via.placeholder.com/100x50.png?text=Logo")
                    duration = format_duration(f['duration_minutes'])

                    col1, col2 = st.columns([4, 1])
                    with col1:
                        btn_clicked = st.button(
                            f"""
{f['flight_number']} | {f['from_airport']['iata']} ➔ {f['to_airport']['iata']}
Departure: {f['departure_time']}
Arrival: {f['arrival_time']}
Duration: {duration}
""", key=flight_id
                        )
                        if btn_clicked:
                            st.session_state.selected_flight = flight_id

                    with col2:
                        st.image(logo, width=100)

                # --- Show details if selected
                if st.session_state.selected_flight:
                    selected_flight = next(
                        (f for f in matches if f"{f['flight_number']}_{f['from_airport']['iata']}_{f['to_airport']['iata']}" == st.session_state.selected_flight),
                        None
                    )
                    if selected_flight:
                        st.markdown("---")
                        st.subheader(f"Flight {selected_flight['flight_number']} Details")
                        st.markdown(f"""
                        **From:** {selected_flight['from_airport']['name']} ({selected_flight['from_airport']['iata']})  
                        **To:** {selected_flight['to_airport']['name']} ({selected_flight['to_airport']['iata']})  
                        **Departure:** {selected_flight['departure_time']}  
                        **Arrival:** {selected_flight['arrival_time']}  
                        **Duration:** {format_duration(selected_flight['duration_minutes'])}
                        """)
