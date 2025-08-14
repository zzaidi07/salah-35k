import streamlit as st

# App title
st.title("Add 1 to Your Number")

# Step 1: Input from the user (as a string)
number_input = st.text_input("Enter a number", value="0")

# Step 2: When button is clicked
if st.button("Add 1"):
    try:
        # Convert to integer
        num = int(number_input)
        # Add 1 and display
        st.success(f"The result is: {num + 1}")
    except ValueError:
        st.error("Please enter a valid integer.")