import streamlit as st

# Title
st.markdown("<h3>Select Prayer Calculation Type</h3>", unsafe_allow_html=True)

# Calculation method dropdown
calculation_methods = [
    "MWL",
    "ISNA",
    "EGYPT",
    "MAKKAH",
    "KARACHI",
    "TEHRAN",
    "JAFARI"
]
selected_method = st.selectbox("Choose a calculation method:", calculation_methods)
st.write(f"Confirmation: **{selected_method}**")

st.write("")

# Year, month, day inputs (each stored as float because that's the value in zain bhai's documentation)
st.markdown("<h4>Enter Date</h4>", unsafe_allow_html=True)
year = float(st.number_input("Enter Year", min_value=1, max_value=2100, value=2025, step=1))
month = float(st.number_input("Enter Month", min_value=1, max_value=12, value=1, step=1))
day = float(st.number_input("Enter Day", min_value=1, max_value=31, value=1, step=1))

st.write("")
st.write("")

# UTC Timezone dropdown (float storage as well)
utc_offsets = list(range(-12, 15))  # UTC -12 to UTC +14
selected_utc = float(st.selectbox(
    "Select UTC Timezone",
    options=utc_offsets,
    format_func=lambda x: f"UTC {x:+d}"
))