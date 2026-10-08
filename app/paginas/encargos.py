import streamlit as st

from lib.auth import requerir_rol

requerir_rol("duena", "mostrador")

st.title("🎂 Encargos")
st.info("En construcción.")
