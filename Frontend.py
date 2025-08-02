import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import json 

# Scrape airport data
#url = 'https://en.wikipedia.org/wiki/List_of_international_airports_by_country'
#try:
    #page = requests.get(url)
#except Exception as e:
    #print('Error downloading page: ',e)
#soup = BeautifulSoup(page.text, 'html.parser')

#tables = soup.find_all('table', {'class' : "wikitable"})

#dfs = []
#for table in tables:
   # dfs.append(pd.read_html(str(table))[0])

#airports = pd.concat(dfs, ignore_index=True)
#airports.columns = airports.columns.get_level_values(0)
#airports.to_csv('airports.csv', index=False)

df = pd.read_csv("airports.csv", encoding='ISO-8859-1') 
df["airport_options"] = df[df.columns[0]] + ", " + df[df.columns[1]] + ", " + df[df.columns[2]]
airports = df["airport_options"].tolist()
# --- Initialize state
if "search_clicked" not in st.session_state:
    st.session_state.search_clicked = False 

# --- UI Logic
st.title('Salah@35k')
st.markdown("### Find your flight")

search_mode = st.radio("Search by", ["Route (Departure & Arrival)", "Flight Number"], horizontal=True)

if search_mode == "Route (Departure & Arrival)":
    col1, col2 = st.columns(2)
    with col1:
        departure = st.selectbox("Departure Location", options=airports, index=None, placeholder="e.g., Dubai")
    with col2:
        arrival = st.selectbox("Arrival Location", options=airports, index=None, placeholder="e.g., LAX")
else:
    flight_number = st.text_input("Flight Number", placeholder="e.g., AA123")

if st.button("Find Matches"):
    st.session_state.search_clicked = True
    if search_mode == "Route (Departure & Arrival)":
        Load = st.empty()  # Create a placeholder
        Load.write(f"Searching flights from **{departure}** to **{arrival}**")
        time.sleep(2)  # Wait for 2 seconds
        Load.write("Select Your Flight")  # Update the placeholder
        

    elif search_mode == "Flight Number":
        st.write(f"Searching flight with number: **{flight_number}**")
