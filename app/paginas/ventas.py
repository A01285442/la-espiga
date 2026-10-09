"""Caja: se arma el ticket de cada cliente desde el catálogo y se cobra. Cada cobro es una venta.

Mostrador ve el total del ticket que está cobrando, pero no los totales del día:
esos solo los ve la dueña en Resumen.
"""

import pandas as pd
import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from lib.auth import requerir_rol
from lib.db import leer, mensaje_error, transaccion
from lib.formato import ZONA, md, normalizar, pesos
from lib.ui import aviso, encabezado, subpestanas

usuario = requerir_rol("duena", "mostrador")

CATEGORIAS = {"pan_dulce": "Pan dulce", "pan_salado": "Pan salado", "pasteles": "Pasteles", "galletas": "Galletas"}
TODO = "Todo"

encabezado("Caja", "Arma el ticket del cliente y cóbralo. Cada cobro queda como una venta.")
aviso("caja_aviso")

productos = leer("SELECT id, nombre, categoria, unidad, precio FROM productos WHERE activo ORDER BY nombre")
catalogo = {int(p.id): p for p in productos.itertuples()}

# El ticket vive en la sesión: {producto_id: cantidad}
ticket: dict[int, float] = st.session_state.setdefault("caja_ticket", {})


def cantidad_txt(p, cantidad: float) -> str:
    return f"{cantidad:g} kg" if p.unidad == "kg" else f"{cantidad:g}"


def agregar(pid: int, cantidad: float) -> None:
    ticket[pid] = round(ticket.get(pid, 0) + cantidad, 2)
    if ticket[pid] <= 0:
        ticket.pop(pid)


def vaciar() -> None:
    ticket.clear()
    for clave in ("caja_incompleta", "caja_nota"):
        st.session_state.pop(clave, None)


col_catalogo, col_ticket = st.columns([3, 2], gap="large")

# ---------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------
with col_catalogo:
    buscar = st.text_input("Buscar producto", placeholder="Buscar producto…", key="caja_buscar",
                           icon=":material/search:", label_visibility="collapsed")
    seccion = subpestanas([TODO, *CATEGORIAS.values()], key="caja_seccion")

    lista = productos
    if seccion != TODO:
        lista = lista[lista.categoria.map(CATEGORIAS) == seccion]
    if buscar:
        lista = lista[lista.nombre.map(normalizar).str.contains(normalizar(buscar), regex=False)]

    if lista.empty:
        st.caption("No hay productos con ese nombre.")
    for i, p in enumerate(lista.itertuples()):
        # Una fila de 3 columnas por cada 3 productos: en celular se apilan en orden
        if i % 3 == 0:
            columnas = st.columns(3)
        with columnas[i % 3].container(border=True, horizontal=True, vertical_alignment="center", wrap=False,
                                       key=f"tarjeta_{p.id}"):
            st.markdown(md(f"**{p.nombre}**  \n{pesos(p.precio)}{' por kg' if p.unidad == 'kg' else ''}"),
                        width="stretch")
            if p.unidad == "kg":
                with st.popover(":material/scale:", help="Agregar por kilo"):
                    kilos = st.number_input("Kilos", min_value=0.25, step=0.25, value=1.0, key=f"caja_kg_{p.id}")
                    st.button("Agregar al ticket", key=f"caja_add_{p.id}", type="primary", width="stretch",
                              on_click=agregar, args=(int(p.id), kilos))
            else:
                st.button(":material/add:", key=f"caja_add_{p.id}", help="Agregar uno",
                          on_click=agregar, args=(int(p.id), 1))

# ---------------------------------------------------------------------
# Ticket
# ---------------------------------------------------------------------
with col_ticket, st.container(border=True, key="caja_ticket_panel"):
    st.subheader("Ticket")
    total = sum(float(catalogo[pid].precio) * c for pid, c in ticket.items() if pid in catalogo)

    if not ticket:
        st.caption("Agrega productos del catálogo.")
    for pid, cant in list(ticket.items()):
        p = catalogo[pid]
        paso = 0.25 if p.unidad == "kg" else 1
        with st.container(horizontal=True, vertical_alignment="center", key=f"linea_{pid}"):
            st.markdown(md(f"**{p.nombre}**  \n{cantidad_txt(p, cant)} × {pesos(p.precio)}"), width="stretch")
            st.markdown(md(pesos(float(p.precio) * cant)), width="content")
            st.button(":material/remove:", key=f"caja_menos_{pid}", help="Uno menos", type="tertiary",
                      on_click=agregar, args=(pid, -paso))
            st.button(":material/add:", key=f"caja_mas_{pid}", help="Uno más", type="tertiary",
                      on_click=agregar, args=(pid, paso))
            st.button(":material/close:", key=f"caja_quitar_{pid}", help="Quitar", type="tertiary",
                      on_click=agregar, args=(pid, -cant))

    st.divider()
    st.html(f'<div class="total-etiqueta">Total</div><div class="total-ticket">{pesos(total)}</div>')

    with st.popover("Nota o captura incompleta", icon=":material/edit_note:", type="tertiary"):
        incompleta = st.checkbox("Esta captura está incompleta (se fue la luz, no se apuntó todo)",
                                 key="caja_incompleta")
        nota = st.text_input("Nota", key="caja_nota")

    c1, c2 = st.columns([2, 1])
    cobrar = c1.button(f"Cobrar {pesos(total)}", type="primary", icon=":material/payments:",
                       disabled=not ticket, width="stretch", key="caja_cobrar")
    c2.button("Vaciar", disabled=not ticket, width="stretch", on_click=vaciar, key="caja_vaciar")

    if cobrar:
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
                    [{"v": venta_id, "p": pid, "c": float(c)} for pid, c in ticket.items()])
        except DBAPIError as error:
            st.error(md(mensaje_error(error)))
        else:
            st.session_state["caja_aviso"] = f"Ticket #{venta_id} cobrado: {len(ticket)} producto(s), {pesos(total)}."
            vaciar()
            st.rerun()

# ---------------------------------------------------------------------
# Lo que esta persona cobró hoy (sin precios ni totales: vista v_mis_capturas_hoy)
# ---------------------------------------------------------------------
st.subheader("Tus tickets de hoy")
mias = leer("SELECT creado_en, producto, cantidad FROM v_mis_capturas_hoy ORDER BY creado_en DESC, producto")
if mias.empty:
    st.caption("Todavía no has cobrado nada hoy.")
else:
    # Las líneas de una misma venta comparten creado_en (se guardan en la misma transacción)
    tickets = (mias.assign(linea=[f"{c:g} {p}" for p, c in zip(mias.producto, mias.cantidad)])
               .groupby("creado_en", sort=False).linea.agg(", ".join).reset_index())
    st.dataframe(pd.DataFrame({
        "Hora": pd.to_datetime(tickets.creado_en, utc=True).dt.tz_convert(ZONA).dt.strftime("%H:%M"),
        "Productos": tickets.linea,
    }), hide_index=True, width="stretch")
    st.caption("¿Te equivocaste en un ticket? Avísale a Carmen para que lo corrija.")
