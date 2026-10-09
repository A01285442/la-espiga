"""Compras (tickets) e inventario de insumos con mínimos. Solo dueña."""

from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from lib.auth import requerir_rol
from lib.db import leer, mensaje_error, transaccion
from lib.formato import MESES, fecha_corta, hoy, md, pesos
from lib.ui import aviso, encabezado, encabezado_tabla, fila, subpestanas

usuario = requerir_rol("duena")

FACTURA = {"facturada": "Facturada", "por_pedir": "Pedir factura",
           "sin_factura": "Sin factura", "sin_dato": "Sin dato"}

encabezado("Compras", "Tickets de compra, facturas pendientes e insumos en bodega.")
aviso("com_aviso")


def guardar_y_recargar(aviso: str, sentencias: list[tuple[str, dict]]) -> None:
    try:
        with transaccion() as conn:
            for sql, params in sentencias:
                conn.execute(text(sql), params)
    except DBAPIError as error:
        st.error(md(mensaje_error(error)))
        return
    st.session_state["com_aviso"] = aviso
    st.rerun()


GASTO, REVISAR, REGISTRAR, BODEGA = "Gasto del mes", "Por revisar", "Registrar ticket", "Bodega"
vista = subpestanas([GASTO, REVISAR, REGISTRAR, BODEGA], key="com_vista")

# ---------------------------------------------------------------------
# Gasto del mes
# ---------------------------------------------------------------------
if vista == GASTO:
    meses = leer("""SELECT DISTINCT date_trunc('month', f)::date AS mes
                    FROM (SELECT fecha AS f FROM compras UNION ALL SELECT current_date) x
                    ORDER BY mes DESC""").mes.tolist()
    ultima = leer("SELECT max(fecha) AS f FROM compras").f[0]
    default = meses.index(date(ultima.year, ultima.month, 1)) if ultima else 0
    mes = st.selectbox("Mes", meses, index=default, width=240,
                       format_func=lambda m: f"{MESES[m.month - 1].capitalize()} {m.year}")
    fin = date(mes.year + mes.month // 12, mes.month % 12 + 1, 1)

    compras = leer("""
        SELECT c.id, c.fecha, p.nombre AS proveedor, c.total, c.descripcion, c.estado_factura,
               c.incluye_gastos_personales, c.posible_duplicado
        FROM compras c JOIN proveedores p ON p.id = c.proveedor_id
        WHERE c.fecha >= :i AND c.fecha < :f
        ORDER BY c.fecha, c.id""", i=mes, f=fin)
    # Un mes sin compras llega con columnas sin tipo: fijarlo para que los filtros funcionen
    compras = compras.astype({"total": float, "incluye_gastos_personales": bool, "posible_duplicado": bool})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Gastado en el mes", pesos(compras.total.sum()), border=True)
    c2.metric("Facturas por pedir", int((compras.estado_factura == "por_pedir").sum()), border=True)
    c3.metric("Con cosas de la casa", int(compras.incluye_gastos_personales.sum()), border=True,
              help="El contador advirtió que esos tickets no deberían facturarse completos a la panadería.")
    c4.metric("Posibles duplicados", int(compras.posible_duplicado.sum()), border=True)

    if compras.empty:
        st.caption("No hay compras registradas en este mes.")
    else:
        col_prov, col_tickets = st.columns([2, 3], gap="large")
        with col_prov:
            st.subheader("En qué se fue el dinero")
            por_proveedor = (compras.groupby("proveedor").total.agg(["sum", "count"])
                             .sort_values("sum", ascending=False).reset_index())
            st.dataframe(pd.DataFrame({
                "Proveedor": por_proveedor.proveedor,
                "Tickets": por_proveedor["count"],
                "Total": por_proveedor["sum"].map(pesos),
                "% del gasto": (por_proveedor["sum"] / por_proveedor["sum"].sum()).map(lambda x: f"{x:.0%}"),
            }), hide_index=True, width="stretch")
            st.caption("Los tickets no dicen cuánto fue de harina, huevo o mantequilla: para el costo por "
                       "producto habría que capturar el detalle de cada ticket (segunda etapa).")
        with col_tickets:
            st.subheader(f"Tickets del mes ({len(compras)})")
            st.dataframe(pd.DataFrame({
                "Fecha": compras.fecha.map(fecha_corta), "Proveedor": compras.proveedor,
                "Total": compras.total.map(pesos), "Qué se compró": compras.descripcion,
                "Factura": compras.estado_factura.map(FACTURA),
                "Casa": compras.incluye_gastos_personales.map({True: "Sí", False: ""}),
                "Revisar": compras.posible_duplicado.map({True: "Posible duplicado", False: ""}),
            }), hide_index=True, width="stretch", height=420)

# ---------------------------------------------------------------------
# Por revisar: posibles duplicados y facturas por pedir (de todos los meses)
# ---------------------------------------------------------------------
if vista == REVISAR:
    pendientes = leer("""
        SELECT c.id, c.fecha, p.nombre AS proveedor, c.total, c.descripcion, c.estado_factura,
               c.posible_duplicado
        FROM compras c JOIN proveedores p ON p.id = c.proveedor_id
        WHERE c.posible_duplicado OR c.estado_factura = 'por_pedir'
        ORDER BY c.fecha, c.id""")
    duplicados = pendientes[pendientes.posible_duplicado.astype(bool)]
    por_pedir = pendientes[pendientes.estado_factura == "por_pedir"]

    c1, c2 = st.columns(2)
    c1.metric("Posibles duplicados", len(duplicados), border=True)
    c2.metric("Facturas por pedir", len(por_pedir), border=True)

    ANCHOS = [1, 2, 1, 3.2, 1.1, 1.1]
    st.subheader("¿Se apuntaron dos veces?")
    st.caption("Mismo proveedor, mismo día o el siguiente y monto parecido. Revisa el ticket y decide.")
    if duplicados.empty:
        st.caption("Nada por revisar.")
    else:
        encabezado_tabla("duplicados", ["Fecha", "Proveedor", "Total", "Qué se compró", "", ""], ANCHOS)
    for d in duplicados.itertuples():
        col = fila(f"dup_{d.id}", ANCHOS)
        col[0].markdown(fecha_corta(d.fecha))
        col[1].markdown(md(f"**{d.proveedor}**"))
        col[2].markdown(md(pesos(d.total)))
        col[3].markdown(md(d.descripcion or "—"))
        if col[4].button("Es correcto", key=f"dup_ok_{d.id}", width="stretch"):
            guardar_y_recargar(f"Ticket de {d.proveedor} por {pesos(d.total)} confirmado.", [
                ("UPDATE compras SET posible_duplicado = false WHERE id = :c", {"c": int(d.id)})])
        if col[5].button("Borrar", key=f"dup_borrar_{d.id}", icon=":material/delete:", width="stretch"):
            guardar_y_recargar(f"Ticket repetido de {d.proveedor} por {pesos(d.total)} borrado.", [
                ("DELETE FROM compras WHERE id = :c", {"c": int(d.id)})])

    st.subheader("Facturas por pedir")
    if por_pedir.empty:
        st.caption("No hay facturas pendientes.")
    else:
        encabezado_tabla("facturas", ["Fecha", "Proveedor", "Total", "Qué se compró", "", ""], ANCHOS)
    for f in por_pedir.itertuples():
        col = fila(f"fact_{f.id}", ANCHOS)
        col[0].markdown(fecha_corta(f.fecha))
        col[1].markdown(md(f"**{f.proveedor}**"))
        col[2].markdown(md(pesos(f.total)))
        col[3].markdown(md(f.descripcion or "—"))
        if col[4].button("Ya la tengo", key=f"fact_{f.id}", icon=":material/check:", width="stretch"):
            guardar_y_recargar(f"Factura de {f.proveedor} marcada como recibida.", [
                ("UPDATE compras SET estado_factura = 'facturada' WHERE id = :c", {"c": int(f.id)})])

# ---------------------------------------------------------------------
# Registrar ticket
# ---------------------------------------------------------------------
if vista == REGISTRAR:
    proveedores = leer("SELECT id, nombre FROM proveedores ORDER BY nombre")
    with st.form("nueva_compra", clear_on_submit=True, width=720):
        st.subheader("Nuevo ticket de compra")
        c1, c2, c3 = st.columns(3)
        fecha = c1.date_input("Fecha", value=hoy(), max_value=hoy(), format="DD/MM/YYYY")
        proveedor = c2.selectbox("Dónde", proveedores.id.tolist(),
                                 format_func=dict(zip(proveedores.id, proveedores.nombre)).get)
        total = c3.number_input("Total del ticket", min_value=0.0, step=10.0)
        descripcion = st.text_input("Qué se compró", placeholder="Ej. 20 bultos harina")
        c1, c2 = st.columns(2)
        factura = c1.selectbox("Factura", ["facturada", "por_pedir", "sin_factura"], format_func=FACTURA.get)
        personal = c2.checkbox("El ticket trae cosas de la casa")
        if st.form_submit_button("Guardar ticket", type="primary"):
            if total <= 0:
                st.error("Escribe el total del ticket.")
            else:
                guardar_y_recargar(f"Ticket por {pesos(total)} guardado.", [(
                    """INSERT INTO compras (fecha, proveedor_id, total, descripcion, estado_factura,
                                            incluye_gastos_personales, registrado_por)
                       VALUES (:f, :p, :t, :d, :e, :casa, :u)""",
                    {"f": fecha, "p": int(proveedor), "t": total, "d": descripcion.strip() or None,
                     "e": factura, "casa": personal, "u": usuario["id"]})])

# ---------------------------------------------------------------------
# Insumos
# ---------------------------------------------------------------------
if vista == BODEGA:
    insumos = leer("""
        SELECT i.id, i.nombre, i.unidad, i.cantidad, i.minimo, pr.nombre AS proveedor, i.nota, i.actualizado_en
        FROM insumos i LEFT JOIN proveedores pr ON pr.id = i.proveedor_id
        ORDER BY i.nombre""")

    def estado(i) -> str:
        if pd.isna(i.minimo):
            return "Falta definir mínimo"
        if pd.isna(i.cantidad):
            return "No se cuenta"
        return "Pedir" if i.cantidad <= i.minimo else "Hay"

    insumos["estado"] = [estado(i) for i in insumos.itertuples()]
    pedir = insumos[insumos.estado == "Pedir"]
    sin_minimo = insumos[insumos.estado == "Falta definir mínimo"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Por pedir", len(pedir), border=True)
    c2.metric("Sin mínimo definido", len(sin_minimo), border=True)
    ultimo = insumos.actualizado_en.max()
    c3.metric("Última actualización", fecha_corta(ultimo.date()) if pd.notna(ultimo) else "—", border=True)

    if not pedir.empty:
        st.error(md("**Hay que pedir:**  \n" + "  \n".join(
            f"- {p.nombre}: quedan {p.cantidad:g} {p.unidad} (mínimo {p.minimo:g})"
            + (f" — {p.proveedor}" if p.proveedor else "") for p in pedir.itertuples())))
    if not sin_minimo.empty:
        st.caption("Sin mínimo no se puede avisar a tiempo: "
                   + ", ".join(sin_minimo.nombre) + ". Escríbelo en la tabla.")

    st.subheader("Conteo de bodega")
    st.caption("Escribe lo que contó Toño y, si hace falta, ajusta el mínimo. Luego **Guardar conteo**. "
               "Tip: la manteca se acabó dos veces en septiembre; quizá su mínimo debe ser mayor.")
    editado = st.data_editor(
        insumos[["id", "nombre", "unidad", "cantidad", "minimo", "proveedor", "estado"]],
        column_config={
            "id": None,
            "nombre": st.column_config.TextColumn("Insumo", disabled=True),
            "unidad": st.column_config.TextColumn("Unidad", disabled=True),
            "cantidad": st.column_config.NumberColumn("Hay", min_value=0, step=0.5),
            "minimo": st.column_config.NumberColumn("Mínimo para pedir", min_value=0, step=0.5),
            "proveedor": st.column_config.TextColumn("Proveedor", disabled=True),
            "estado": st.column_config.TextColumn("Estado", disabled=True),
        },
        hide_index=True, width="stretch", num_rows="fixed", key="com_conteo",
    )

    cambios = editado[(editado.cantidad.fillna(-1) != insumos.cantidad.fillna(-1))
                      | (editado.minimo.fillna(-1) != insumos.minimo.fillna(-1))]
    if st.button(f"Guardar conteo ({len(cambios)} cambio(s))", type="primary", disabled=cambios.empty):
        guardar_y_recargar(f"Conteo guardado: {len(cambios)} insumo(s) actualizados.", [
            ("""UPDATE insumos SET cantidad = :c, minimo = :m, actualizado_en = now() WHERE id = :i""",
             {"c": None if pd.isna(r.cantidad) else float(r.cantidad),
              "m": None if pd.isna(r.minimo) else float(r.minimo), "i": int(r.id)})
            for r in cambios.itertuples()])
