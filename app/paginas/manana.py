"""Lo que Toño tiene que hornear: encargos pendientes de un día (mañana por default)."""

from urllib.parse import quote

import streamlit as st

from lib.auth import requerir_rol
from lib.db import leer
from lib.formato import fecha_larga, hoy, manana

requerir_rol("duena", "mostrador")

st.title("🌙 Mañana sale")

dia = st.date_input("Día", value=manana(), format="DD/MM/YYYY")

# Sin montos: a Toño solo le importa qué hornear
encargos = leer("""
    SELECT id, cliente, descripcion, estado, requiere_revision
    FROM v_encargos
    WHERE fecha_entrega = :dia AND estado IN ('pendiente', 'listo')
    ORDER BY id""", dia=dia)

atrasados = leer("""
    SELECT count(*) AS n FROM v_encargos
    WHERE fecha_entrega < :hoy AND estado IN ('pendiente', 'listo')""", hoy=hoy()).n[0]
if atrasados:
    st.warning(f"Además hay {atrasados} encargo(s) atrasados sin entregar. Revísalos en Encargos.")

st.header(f"{fecha_larga(dia).capitalize()}: {len(encargos)} encargo(s)")

if encargos.empty:
    st.success("No hay encargos para ese día.")
else:
    for n, e in enumerate(encargos.itertuples(), start=1):
        listo = " ✅ ya está listo" if e.estado == "listo" else ""
        st.markdown(f"### {n}. {e.descripcion}\nPara **{e.cliente}** · encargo #{e.id}{listo}")

    lista = "\n".join(f"{n}. {e.descripcion} ({e.cliente})" for n, e in enumerate(encargos.itertuples(), 1))
    mensaje = f"Encargos para {fecha_larga(dia)}:\n{lista}"
    st.divider()
    c1, c2 = st.columns(2)
    # wa.me abre WhatsApp con el mensaje escrito; quien lo manda elige a Toño. Sin costo ni API.
    c1.link_button("📲 Mandar lista a Toño por WhatsApp", f"https://wa.me/?text={quote(mensaje)}",
                   use_container_width=True)
    c2.download_button("⬇️ Descargar lista", mensaje, file_name=f"encargos_{dia:%Y-%m-%d}.txt",
                       use_container_width=True)
    st.caption("Para imprimir: Ctrl + P.")
