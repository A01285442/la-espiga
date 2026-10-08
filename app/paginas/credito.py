import streamlit as st

from lib.auth import requerir_rol

requerir_rol("duena")

st.title("💳 Clientes de crédito")
st.info("En construcción.")
