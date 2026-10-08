import streamlit as st

from lib.auth import requerir_rol

requerir_rol("duena", "mostrador")

st.title("🧾 Capturar ventas")
st.info("En construcción.")
