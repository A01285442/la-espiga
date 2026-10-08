"""Captura de ventas de mostrador: se elige cantidad por producto del catálogo, sin escribir nombres.

Sirve igual para capturar cada venta al momento o el resumen al cierre.
Mostrador ve el total de la venta que está capturando (para cobrar), pero no
los totales del día: esos solo los ve la dueña en Resumen.
"""

import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from lib.auth import requerir_rol
from lib.db import leer, mensaje_error, transaccion
from lib.formato import md, pesos

usuario = requerir_rol("duena", "mostrador")

CATEGORIAS = {"pan_dulce": "🥐 Pan dulce", "pan_salado": "🥖 Pan salado",
              "pasteles": "🍰 Pasteles", "galletas": "🍪 Galletas"}

st.title("🧾 Capturar ventas")

if aviso := st.session_state.pop("ven_aviso", None):
    st.success(md(aviso))

productos = leer("SELECT id, nombre, categoria, unidad, precio FROM productos WHERE activo ORDER BY nombre")
claves = {p.id: f"ven_cant_{p.id}" for p in productos.itertuples()}

# Limpiar cantidades después de guardar (antes de dibujar los campos)
if st.session_state.pop("ven_limpiar", False):
    for clave in [*claves.values(), "ven_incompleta", "ven_nota"]:
        st.session_state.pop(clave, None)

for categoria, titulo in CATEGORIAS.items():
    grupo = productos[productos.categoria == categoria]
    if grupo.empty:
        continue
    st.subheader(titulo)
    for i, p in enumerate(grupo.itertuples()):
        # Una fila de 3 columnas por cada 3 productos: en celular las columnas se apilan
        # y así se conserva el orden alfabético (con 3 columnas fijas saldría salteado).
        if i % 3 == 0:
            columnas = st.columns(3)
        es_kg = p.unidad == "kg"
        columnas[i % 3].number_input(
            f"{p.nombre} · {pesos(p.precio)}{' / kg' if es_kg else ''}",
            min_value=0.0, step=0.25 if es_kg else 1.0, format="%.2f" if es_kg else "%.0f",
            key=claves[p.id])

cantidades = {pid: st.session_state.get(clave, 0) or 0 for pid, clave in claves.items()}
lineas = productos[productos.id.map(cantidades) > 0].assign(cantidad=lambda d: d.id.map(cantidades))
total = float((lineas.cantidad * lineas.precio).sum()) if not lineas.empty else 0.0

st.divider()
with st.expander("¿Pasó algo? (se fue la luz, no se apuntó todo…)"):
    incompleta = st.checkbox("Esta captura está incompleta", key="ven_incompleta")
    nota = st.text_input("Nota", key="ven_nota")

if lineas.empty:
    st.caption("Escribe la cantidad de cada producto vendido.")
else:
    st.markdown(md(f"**Esta venta:** {len(lineas)} producto(s) · **{pesos(total)}**"))

if st.button("Guardar venta", type="primary", disabled=lineas.empty, use_container_width=True):
    try:
        with transaccion() as conn:
            # La fecha la pone la base (hoy) y el precio también (del catálogo):
            # quien captura no puede cambiar ninguno de los dos.
            venta_id = conn.execute(text("""
                INSERT INTO ventas (capturado_por, captura_incompleta, nota)
                VALUES (:u, :inc, :nota) RETURNING id"""),
                {"u": usuario["id"], "inc": incompleta, "nota": nota.strip() or None}).scalar_one()
            conn.execute(text("""
                INSERT INTO venta_lineas (venta_id, producto_id, cantidad)
                VALUES (:v, :p, :c)"""),
                [{"v": venta_id, "p": int(l.id), "c": float(l.cantidad)} for l in lineas.itertuples()])
    except DBAPIError as error:
        st.error(md(mensaje_error(error)))
    else:
        st.session_state["ven_limpiar"] = True
        st.session_state["ven_aviso"] = f"Venta guardada: {len(lineas)} producto(s), {pesos(total)}."
        st.rerun()

# Lo que esta persona capturó hoy (sin precios ni totales: vista v_mis_capturas_hoy)
st.divider()
st.subheader("Lo que capturaste hoy")
mias = leer("SELECT producto, sum(cantidad) AS cantidad FROM v_mis_capturas_hoy GROUP BY producto ORDER BY producto")
if mias.empty:
    st.caption("Todavía no has capturado nada hoy.")
else:
    st.dataframe(mias.rename(columns={"producto": "Producto", "cantidad": "Cantidad"}),
                 hide_index=True, use_container_width=True)
    st.caption("¿Te equivocaste? Avísale a Carmen para que lo corrija.")
