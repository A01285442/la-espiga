"""Punto de entrada: login y menú según el rol."""

import streamlit as st

from lib.auth import NOMBRE_ROL, cerrar_sesion, pantalla_login, usuario_actual
from lib.ui import estilo

st.set_page_config(page_title="La Espiga Dorada", page_icon=":material/bakery_dining:", layout="wide")
estilo()

usuario = usuario_actual()
if usuario is None:
    pantalla_login()
    st.stop()

# Cada página se define una vez; el menú de cada rol es una lista de ellas.
# Una página que no está en el menú del rol no existe para esa sesión.
# (Además cada página revisa el rol con requerir_rol().)
resumen  = st.Page("paginas/resumen.py",  title="Resumen",  icon=":material/monitoring:", url_path="resumen")
credito  = st.Page("paginas/credito.py",  title="Crédito",  icon=":material/account_balance_wallet:",
                   url_path="credito")
encargos = st.Page("paginas/encargos.py", title="Encargos", icon=":material/cake:", url_path="encargos")
ventas   = st.Page("paginas/ventas.py",   title="Caja",     icon=":material/point_of_sale:", url_path="caja")
compras  = st.Page("paginas/compras.py",  title="Compras",  icon=":material/inventory_2:", url_path="compras")

MENU = {
    "mostrador": [ventas, encargos],
    "duena": [resumen, credito, encargos, ventas, compras],
}

# El menú lo dibujamos nosotros (barra de arriba); el de Streamlit queda oculto
pagina = st.navigation(MENU[usuario["rol"]], position="hidden")

with st.container(horizontal=True, vertical_alignment="center", key="barra_menu"):
    st.markdown("**La Espiga Dorada**", width="content")
    for p in MENU[usuario["rol"]]:
        actual = p.url_path == pagina.url_path
        if st.button(p.title, icon=p.icon, key=f"menu_{p.url_path}", type="primary" if actual else "tertiary"):
            st.switch_page(p)
    st.space("stretch")
    st.caption(f"{usuario['nombre']} · {NOMBRE_ROL[usuario['rol']]}", width="content")
    if st.button("Cerrar sesión", icon=":material/logout:", type="tertiary", key="menu_salir"):
        cerrar_sesion()
        st.rerun()

pagina.run()
