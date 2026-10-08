"""Resumen para la dueña: cuánto se vendió, qué se vende más, quién debe y qué falta pedir."""

from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy.exc import DBAPIError

from lib.auth import requerir_rol
from lib.db import ejecutar, leer, mensaje_error
from lib.formato import MESES, hoy, md, pesos

requerir_rol("duena")

st.title("📊 Resumen")

if aviso := st.session_state.pop("res_aviso", None):
    st.success(md(aviso))

# ---------------------------------------------------------------------
# Avisos: lo que requiere atención hoy
# ---------------------------------------------------------------------
vencido = leer("SELECT coalesce(sum(saldo_vencido), 0) AS v, count(*) FILTER (WHERE saldo_vencido > 0) AS n "
               "FROM v_saldos_credito").iloc[0]
atrasados = leer("SELECT count(*) AS n FROM v_encargos WHERE fecha_entrega < :h AND estado IN ('pendiente', 'listo')",
                 h=hoy()).n[0]
manana = leer("SELECT count(*) AS n FROM v_encargos WHERE fecha_entrega = :h + 1 AND estado IN ('pendiente', 'listo')",
              h=hoy()).n[0]
por_pedir = leer("SELECT nombre, cantidad, minimo, unidad, proveedor FROM v_insumos_por_pedir ORDER BY nombre")

avisos = st.container()
if vencido.n:
    avisos.error(md(f"💳 **{int(vencido.n)} clientes de crédito** te deben **{pesos(vencido.v)}** ya vencido. "
                    "Ve a *Clientes de crédito* para ver a quién cobrar."))
if atrasados:
    avisos.warning(f"🎂 {atrasados} encargo(s) atrasados sin entregar.")
if manana:
    avisos.info(f"🌙 Mañana salen {manana} encargo(s).")
if not por_pedir.empty:
    avisos.warning("🛒 **Insumos por pedir** (están en el mínimo o abajo):  \n" + "  \n".join(
        f"• {i.nombre}: quedan {i.cantidad:g} {i.unidad} (mínimo {i.minimo:g})"
        + (f" — {i.proveedor}" if i.proveedor else "") for i in por_pedir.itertuples()))

# ---------------------------------------------------------------------
# Ventas del mes
# ---------------------------------------------------------------------
meses = leer("""
    SELECT DISTINCT date_trunc('month', fecha)::date AS mes FROM (
        SELECT fecha FROM ventas
        UNION ALL SELECT fecha_entrega FROM encargos
        UNION ALL SELECT fecha FROM entregas_credito
        UNION ALL SELECT current_date
    ) f ORDER BY mes DESC""").mes.tolist()
# Por default, el mes más reciente que ya tenga ventas
con_ventas = leer("SELECT max(fecha) AS f FROM ventas").f[0]
default = meses.index(date(con_ventas.year, con_ventas.month, 1)) if con_ventas else 0

mes = st.selectbox("Mes", meses, index=default, format_func=lambda m: f"{MESES[m.month - 1].capitalize()} {m.year}")
fin = date(mes.year + mes.month // 12, mes.month % 12 + 1, 1)

cifras = leer("""
    SELECT
      (SELECT coalesce(sum(total), 0) FROM v_ventas_diarias WHERE fecha >= :i AND fecha < :f) AS mostrador,
      (SELECT coalesce(sum(total), 0) FROM encargos
        WHERE fecha_entrega >= :i AND fecha_entrega < :f AND estado <> 'cancelado') AS encargos,
      (SELECT coalesce(sum(monto), 0) FROM entregas_credito WHERE fecha >= :i AND fecha < :f) AS credito,
      (SELECT coalesce(sum(total), 0) FROM compras WHERE fecha >= :i AND fecha < :f) AS compras,
      (SELECT coalesce(sum(total), 0) FROM compras
        WHERE fecha >= :i AND fecha < :f AND posible_duplicado) AS compras_duplicadas,
      (SELECT count(*) FROM v_ventas_diarias
        WHERE fecha >= :i AND fecha < :f AND captura_incompleta) AS dias_incompletos
""", i=mes, f=fin).iloc[0]
vendido = cifras.mostrador + cifras.encargos + cifras.credito

st.subheader(f"Lo que se vendió en {MESES[mes.month - 1]}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total vendido", pesos(vendido))
c2.metric("Mostrador", pesos(cifras.mostrador))
c3.metric("Pasteles por encargo", pesos(cifras.encargos))
c4.metric("Negocios a crédito", pesos(cifras.credito))

c1, c2, c3 = st.columns(3)
c1.metric("Compras", pesos(cifras.compras))
c2.metric("Ventas menos compras", pesos(vendido - cifras.compras),
          help="No es la ganancia: faltan sueldos, renta, luz y lo que quedó en bodega.")
if cifras.compras_duplicadas:
    c3.metric("Compras por revisar", pesos(cifras.compras_duplicadas),
              help="Tickets que parecen repetidos (mismo proveedor, mismo día o el siguiente, monto parecido).")
if cifras.dias_incompletos:
    st.caption(f"⚠️ {int(cifras.dias_incompletos)} día(s) con captura incompleta (se fue la luz): "
               "la venta real de mostrador fue mayor.")

diario = leer("SELECT fecha, total FROM v_ventas_diarias WHERE fecha >= :i AND fecha < :f ORDER BY fecha",
              i=mes, f=fin)
if not diario.empty:
    st.markdown("**Venta de mostrador por día**")
    st.bar_chart(diario.assign(Día=pd.to_datetime(diario.fecha)).set_index("Día").total.rename("Venta"),
                 color="#b5651d", height=260)

# ---------------------------------------------------------------------
# Qué se vende más
# ---------------------------------------------------------------------
productos = leer("""SELECT producto, cantidad, total FROM v_ventas_producto_mes
                    WHERE mes = :m ORDER BY total DESC""", m=mes)
if not productos.empty:
    st.subheader("Qué se vende más en mostrador")
    st.dataframe(pd.DataFrame({
        "Producto": productos.producto,
        "Piezas / kg": productos.cantidad.map(lambda x: f"{x:g}"),
        "Venta": productos.total.map(pesos),
        "% de la venta": (productos.total / productos.total.sum()).map(lambda x: f"{x:.0%}"),
    }), hide_index=True, use_container_width=True)
    st.caption("Para saber cuánto deja cada producto (no solo cuánto se vende) hacen falta las recetas: "
               "es lo siguiente que haríamos con Toño y Memo.")

# ---------------------------------------------------------------------
# Capturas de hoy (la dueña puede corregir; mostrador no puede borrar)
# ---------------------------------------------------------------------
st.divider()
st.subheader("Ventas capturadas hoy")
hoy_ventas = leer("""
    SELECT v.id, to_char(v.creado_en, 'HH24:MI') AS hora, coalesce(u.nombre, 'Excel') AS quien,
           string_agg(vl.cantidad::float || ' ' || p.nombre, ', ' ORDER BY p.nombre) AS que,
           sum(vl.subtotal) AS total, v.captura_incompleta, v.nota
    FROM ventas v
    JOIN venta_lineas vl ON vl.venta_id = v.id
    JOIN productos p ON p.id = vl.producto_id
    LEFT JOIN usuarios u ON u.id = v.capturado_por
    WHERE v.fecha = :h
    GROUP BY v.id, u.nombre
    ORDER BY v.creado_en DESC""", h=hoy())
if hoy_ventas.empty:
    st.caption("Todavía no hay ventas capturadas hoy.")
else:
    st.metric("Vendido hoy en mostrador", pesos(hoy_ventas.total.sum()))
    st.dataframe(pd.DataFrame({
        "#": hoy_ventas.id, "Hora": hoy_ventas.hora, "Capturó": hoy_ventas.quien,
        "Qué": hoy_ventas.que, "Total": hoy_ventas.total.map(pesos),
        "Nota": hoy_ventas.nota.fillna("") + hoy_ventas.captura_incompleta.map({True: " (incompleta)", False: ""}),
    }), hide_index=True, use_container_width=True)
    with st.expander("Borrar una venta capturada por error"):
        venta = st.selectbox("Venta", hoy_ventas.id.tolist(),
                             format_func=lambda i: f"#{i} · " + hoy_ventas.set_index("id").que[i])
        if st.button("Borrar venta"):
            try:
                ejecutar("DELETE FROM ventas WHERE id = :v", v=int(venta))
            except DBAPIError as error:
                st.error(md(mensaje_error(error)))
            else:
                st.session_state["res_aviso"] = f"Venta #{venta} borrada."
                st.rerun()
