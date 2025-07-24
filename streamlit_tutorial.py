import streamlit as st
import matplotlib.pyplot as plt
import numpy as np
import re
import copy
import csv
import os, fnmatch
import pandas as pd
import time


def main():
    # Intro Messages
    

    st.title("This is a tutorial application")
    
    st.text("Salaamun Alaykum, This is how we can write body-text")
    num1 = np.random.randint(0,20)
    num2 = np.random.randint(0,20)
    st.text(f"What is {num1} + {num2}?")
    
    
    NumSum = st.text_input(f"What is {num1} + {num2}?", value = "0")
    
    if (st.button("Check Answer")):
        try:
            st.text(f"You typed: {NumSum}")
            st.text(f" Answer was {num1 + num2}")
            if (int((NumSum)) == num1 + num2):
                st.success("Correct Answer")
            else:
                st.error("Wrong answer, try again")
        except ValueError:
            st.error("Please enter a valid integer")
    
    
if __name__ == "__main__":
    main()
