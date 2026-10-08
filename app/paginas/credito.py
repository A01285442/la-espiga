"""Clientes de crédito: cuánto debe cada uno, qué ya venció y registro de entregas y abonos."""

from urllib.parse import quote

import pandas as pd
import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from lib.auth import requerir_rol
from lib.credito import pendientes_por_antiguedad, proximo_vencimiento, vencido, vencido_desde
from lib.db import leer, mensaje_error, transaccion
from lib.formato import fecha_corta, hoy, md, pesos, telefono

usuario = requerir_rol("duena")

METODOS = {"Efectivo": "efectivo", "Transferencia": "transferencia", "Tarjeta": "tarjeta"}

st.title("💳 Clientes de crédito")

if aviso := st.session_state.pop("cred_aviso", None):
    st.success(md(aviso))


def guardar_y_recargar(aviso: str, sql: str, **params) -> None:
    try:
        with transaccion() as conn:
            conn.execute(text(sql), params)
    except DBAPIError as error:
        st.error(md(mensaje_error(error)))
        return
    st.session_state["cred_aviso"] = aviso
    st.rerun()


# ---------------------------------------------------------------------
# Datos: totales de la vista + antigüedad calculada por cliente
# ---------------------------------------------------------------------
saldos = leer("SELECT * FROM v_saldos_credito ORDER BY nombre")
entregas = leer("""SELECT id, cliente_id, fecha, descripcion, monto, nota_remision
                   FROM entregas_credito ORDER BY fecha, id""")
abonos = leer("SELECT id, cliente_id, fecha, monto, metodo, nota FROM abonos_credito ORDER BY fecha, id")

cuentas = {}
for c in saldos.itertuples():
    suyas = entregas[entregas.cliente_id == c.cliente_id]
    cargos, a_favor = pendientes_por_antiguedad(
        float(c.saldo_inicial),
        [(e.fecha, e.descripcion, float(e.monto)) for e in suyas.itertuples()],
        float(c.abonado), int(c.dias_credito))
    cuentas[c.cliente_id] = dict(cargos=cargos, a_favor=a_favor,
                                 proximo=proximo_vencimiento(cargos, hoy()),
                                 desde=vencido_desde(cargos, hoy()))


def estado(c) -> str:
    if c.saldo_vencido > 0:
        return "🔴 Cobrar ya"
    if c.saldo > 0:
        return f"🟠 Vence {fecha_corta(cuentas[c.cliente_id]['proximo'])}"
    return "🟢 Al corriente"


# ---------------------------------------------------------------------
# Resumen y "toca cobrar"
# ---------------------------------------------------------------------
m1, m2, m3 = st.columns(3)
m1.metric("Te deben en total", pesos(saldos.saldo.clip(lower=0).sum()))
m2.metric("Ya vencido", pesos(saldos.saldo_vencido.sum()))
m3.metric("Clientes por cobrar", int((saldos.saldo_vencido > 0).sum()))

por_cobrar = saldos[saldos.saldo_vencido > 0].sort_values("saldo_vencido", ascending=False)
if not por_cobrar.empty:
    st.subheader("🔔 Toca cobrar")
    for c in por_cobrar.itertuples():
        desde = cuentas[c.cliente_id]["desde"]
        desde_txt = "desde antes de septiembre" if desde is None else f"desde el {fecha_corta(desde)}"
        mensaje = (f"Hola, le saluda Carmen de Panadería La Espiga Dorada. "
                   f"Su saldo pendiente es de {pesos(c.saldo)}. ¡Gracias!")
        col_txt, col_btn = st.columns([4, 1])
        col_txt.markdown(md(f"**{c.nombre}** debe **{pesos(c.saldo_vencido)}** vencido {desde_txt}"
                            + (f" · saldo total {pesos(c.saldo)}" if c.saldo != c.saldo_vencido else "")))
        destino = f"52{c.telefono}" if c.telefono else ""
        col_btn.link_button("📲 Recordar", f"https://wa.me/{destino}?text={quote(mensaje)}",
                            use_container_width=True)

st.subheader("Todos los clientes")
st.dataframe(
    pd.DataFrame({
        "Cliente": saldos.nombre,
        "Estado": [estado(c) for c in saldos.itertuples()],
        "Debe": saldos.saldo.map(pesos),
        "Vencido": saldos.saldo_vencido.map(pesos),
        "Paga a": saldos.dias_credito.map(lambda d: f"{d} días"),
        "Último pago": saldos.ultimo_abono.map(lambda f: fecha_corta(f) if pd.notna(f) else "—"),
    }),
    hide_index=True, use_container_width=True,
)

# ---------------------------------------------------------------------
# Cuenta de un cliente
# ---------------------------------------------------------------------
st.divider()
nombres = dict(zip(saldos.cliente_id, saldos.nombre))
cliente_id = st.selectbox("Ver la cuenta de", list(nombres), format_func=nombres.get, key="cred_cliente",
                          index=list(nombres).index(por_cobrar.cliente_id.iloc[0]) if not por_cobrar.empty else 0)
c = saldos[saldos.cliente_id == cliente_id].iloc[0]
cuenta = cuentas[cliente_id]

d1, d2, d3 = st.columns(3)
d1.metric("Debe", pesos(c.saldo))
d2.metric("Vencido", pesos(c.saldo_vencido))
d3.metric("Paga a", f"{c.dias_credito} días")
if c.saldo_inicial_nota:
    st.warning(md(f"Saldo anterior de {pesos(c.saldo_inicial)}: {c.saldo_inicial_nota}"))
if cuenta["a_favor"] > 0:
    st.info(md(f"Tiene {pesos(cuenta['a_favor'])} a su favor (pagó de más)."))

col_pend, col_mov = st.columns(2)
with col_pend:
    st.markdown("**Lo que debe** (lo más viejo se paga primero)")
    if cuenta["cargos"]:
        st.dataframe(pd.DataFrame({
            "Fecha": [fecha_corta(x.fecha) if x.fecha else "Antes" for x in cuenta["cargos"]],
            "Qué se llevó": [x.descripcion for x in cuenta["cargos"]],
            "Falta": [pesos(x.pendiente) for x in cuenta["cargos"]],
            "Vence": ["Vencido" if x.vence is None or x.vence <= hoy() else fecha_corta(x.vence)
                      for x in cuenta["cargos"]],
        }), hide_index=True, use_container_width=True)
    else:
        st.success("No debe nada.")

with col_mov:
    st.markdown("**Movimientos**")
    movimientos = pd.concat([
        pd.DataFrame([{"Fecha": None, "Concepto": "Saldo anterior", "Cargo": float(c.saldo_inicial), "Abono": 0.0}])
        if c.saldo_inicial > 0 else None,
        pd.DataFrame({"Fecha": e.fecha, "Concepto": e.descripcion, "Cargo": float(e.monto), "Abono": 0.0}
                     for e in entregas[entregas.cliente_id == cliente_id].itertuples()),
        pd.DataFrame({"Fecha": a.fecha, "Concepto": f"Pago ({a.metodo})", "Cargo": 0.0, "Abono": float(a.monto)}
                     for a in abonos[abonos.cliente_id == cliente_id].itertuples()),
    ])
    if not movimientos.empty:
        movimientos = movimientos.assign(orden=movimientos.Fecha.isna().map({True: 0, False: 1}))
        movimientos = movimientos.sort_values(["orden", "Fecha"], kind="stable", na_position="first")
        movimientos["Saldo"] = (movimientos.Cargo - movimientos.Abono).cumsum()
        st.dataframe(pd.DataFrame({
            "Fecha": movimientos.Fecha.map(lambda f: fecha_corta(f) if pd.notna(f) else "Antes"),
            "Concepto": movimientos.Concepto,
            "Cargo": movimientos.Cargo.map(lambda x: pesos(x) if x else ""),
            "Pago": movimientos.Abono.map(lambda x: pesos(x) if x else ""),
            "Saldo": movimientos.Saldo.map(pesos),
        }), hide_index=True, use_container_width=True, height=300)

col_ent, col_abono = st.columns(2)
with col_ent:
    with st.form(f"entrega_{cliente_id}", clear_on_submit=True):
        st.markdown(md(f"**📦 Registrar lo que se llevó {c.nombre}**"))
        fecha_e = st.date_input("Fecha", value=hoy(), max_value=hoy(), format="DD/MM/YYYY")
        desc_e = st.text_input("Qué se llevó", placeholder="Ej. 100 bolillos, 20 teleras")
        monto_e = st.number_input("Monto", min_value=0.0, step=10.0)
        nota_e = st.text_input("Folio de la nota de remisión (opcional)")
        if st.form_submit_button("Guardar entrega", type="primary"):
            if not desc_e.strip() or monto_e <= 0:
                st.error("Escribe qué se llevó y el monto.")
            else:
                guardar_y_recargar(
                    f"Entrega de {pesos(monto_e)} registrada para {c.nombre}.",
                    """INSERT INTO entregas_credito (cliente_id, fecha, descripcion, monto, nota_remision, registrado_por)
                       VALUES (:c, :f, :d, :m, :n, :u)""",
                    c=int(cliente_id), f=fecha_e, d=desc_e.strip(), m=monto_e, n=nota_e.strip() or None,
                    u=usuario["id"])

with col_abono:
    with st.form(f"abono_{cliente_id}", clear_on_submit=True):
        st.markdown(md(f"**💵 Registrar pago de {c.nombre}**"))
        fecha_a = st.date_input("Fecha", value=hoy(), max_value=hoy(), format="DD/MM/YYYY")
        monto_a = st.number_input("Monto", min_value=0.0, step=10.0, value=float(max(c.saldo_vencido, 0)),
                                  key=f"abono_monto_{cliente_id}")
        metodo_a = st.selectbox("Forma de pago", list(METODOS))
        nota_a = st.text_input("Nota (opcional)")
        if st.form_submit_button("Guardar pago", type="primary"):
            if monto_a <= 0:
                st.error("Escribe el monto del pago.")
            else:
                guardar_y_recargar(
                    f"Pago de {pesos(monto_a)} de {c.nombre} registrado. "
                    f"Ahora debe {pesos(float(c.saldo) - monto_a)}.",
                    """INSERT INTO abonos_credito (cliente_id, fecha, monto, metodo, nota, registrado_por)
                       VALUES (:c, :f, :m, :mp, :n, :u)""",
                    c=int(cliente_id), f=fecha_a, m=monto_a, mp=METODOS[metodo_a], n=nota_a.strip() or None,
                    u=usuario["id"])

with st.expander(f"✏️ Datos de {c.nombre}"):
    with st.form(f"datos_{cliente_id}"):
        tel = st.text_input("Teléfono (10 dígitos)", value=c.telefono or "")
        dias = st.number_input("Días de crédito", min_value=0, max_value=60, value=int(c.dias_credito))
        saldo_ini = st.number_input("Saldo anterior a septiembre", min_value=0.0, step=10.0,
                                    value=float(c.saldo_inicial))
        confirmado = st.checkbox("El saldo anterior ya está confirmado con el cliente",
                                 value=not c.saldo_inicial_nota)
        if st.form_submit_button("Guardar datos"):
            if tel and not telefono(tel):
                st.error("El teléfono debe tener 10 dígitos.")
            else:
                guardar_y_recargar(
                    f"Datos de {c.nombre} actualizados.",
                    """UPDATE clientes SET telefono = :t, dias_credito = :d, saldo_inicial = :s,
                              saldo_inicial_nota = CASE WHEN :conf THEN NULL ELSE saldo_inicial_nota END
                       WHERE id = :c""",
                    t=telefono(tel), d=int(dias), s=saldo_ini, conf=confirmado, c=int(cliente_id))

with st.expander("➕ Nuevo cliente de crédito"):
    st.caption("Si ya existe porque encargó pasteles, búscalo aquí y se le activa el crédito.")
    otros = leer("SELECT id, nombre FROM clientes WHERE NOT es_credito ORDER BY nombre")
    with st.form("nuevo_credito", clear_on_submit=True):
        existente = st.selectbox("Cliente que ya existe (opcional)", [None, *otros.id],
                                 format_func=lambda i: "— Es nuevo —" if i is None
                                 else otros.set_index("id").nombre[i])
        nombre_n = st.text_input("Nombre del negocio (si es nuevo)")
        tel_n = st.text_input("Teléfono")
        dias_n = st.number_input("Días de crédito", min_value=0, max_value=60, value=7)
        if st.form_submit_button("Dar de alta"):
            if existente is not None:
                guardar_y_recargar("Crédito activado.",
                                   "UPDATE clientes SET es_credito = true, dias_credito = :d WHERE id = :c",
                                   d=int(dias_n), c=int(existente))
            elif not nombre_n.strip():
                st.error("Escribe el nombre del negocio o elige uno que ya exista.")
            elif tel_n and not telefono(tel_n):
                st.error("El teléfono debe tener 10 dígitos.")
            else:
                guardar_y_recargar(f"{nombre_n.strip()} dado de alta con {dias_n} días de crédito.",
                                   """INSERT INTO clientes (nombre, telefono, es_credito, dias_credito)
                                      VALUES (:n, :t, true, :d)""",
                                   n=nombre_n.strip(), t=telefono(tel_n), d=int(dias_n))
