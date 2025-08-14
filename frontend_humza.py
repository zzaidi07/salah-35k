import streamlit as st
st.markdown("<h3>Select Prayer Calculation Type</h2>", unsafe_allow_html=True)
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
