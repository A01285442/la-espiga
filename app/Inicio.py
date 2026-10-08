"""Punto de entrada: login y menú según el rol."""

import streamlit as st

from lib.auth import NOMBRE_ROL, cerrar_sesion, pantalla_login, usuario_actual

st.set_page_config(page_title="La Espiga Dorada", page_icon="🥐", layout="wide")

usuario = usuario_actual()
if usuario is None:
    pantalla_login()
    st.stop()

# Cada página se define una vez; el menú de cada rol es una lista de ellas.
# Una página que no está en el menú del rol no existe para esa sesión.
# (Además cada página revisa el rol con requerir_rol().)
resumen  = st.Page("paginas/resumen.py",  title="Resumen",          icon="📊", url_path="resumen")
encargos = st.Page("paginas/encargos.py", title="Encargos",         icon="🎂", url_path="encargos")
manana   = st.Page("paginas/manana.py",   title="Mañana sale",      icon="🌙", url_path="manana")
ventas   = st.Page("paginas/ventas.py",   title="Capturar ventas",  icon="🧾", url_path="ventas")
credito  = st.Page("paginas/credito.py",  title="Clientes de crédito", icon="💳", url_path="credito")
compras  = st.Page("paginas/compras.py",  title="Compras e insumos", icon="🛒", url_path="compras")

MENU = {
    "mostrador": [ventas, encargos, manana],
    "duena": [resumen, credito, encargos, manana, ventas, compras],
}

with st.sidebar:
    st.markdown(f"**{usuario['nombre']}**  \n{NOMBRE_ROL[usuario['rol']]}")
    if st.button("Cerrar sesión", use_container_width=True):
        cerrar_sesion()
        st.rerun()

st.navigation(MENU[usuario["rol"]]).run()
