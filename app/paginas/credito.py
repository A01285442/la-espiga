"""Clientes de crédito: cuánto debe cada uno, qué ya venció y registro de entregas y abonos."""

from urllib.parse import quote

import pandas as pd
import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from lib.auth import requerir_rol
from lib.credito import pendientes_por_antiguedad, proximo_vencimiento, vencido_desde
from lib.db import leer, mensaje_error, transaccion
from lib.formato import fecha_corta, hoy, md, pesos, telefono
from lib.ui import aviso, encabezado, encabezado_tabla, fila

usuario = requerir_rol("duena")

METODOS = {"Efectivo": "efectivo", "Transferencia": "transferencia", "Tarjeta": "tarjeta"}

encabezado("Clientes de crédito", "Negocios a los que se les surte a crédito: saldos, vencidos y cobranza.")
aviso("cred_aviso")


def guardar_y_recargar(aviso: str, sql: str, **params) -> None:
    try:
        with transaccion() as conn:
            conn.execute(text(sql), params)
    except DBAPIError as error:
        st.error(md(mensaje_error(error)))
        return
    st.session_state["cred_aviso"] = aviso
    cerrar_ventana()
    st.rerun()


# La ventana abierta se guarda en la sesión (tipo, cliente) y se vuelve a dibujar en cada recarga
# hasta que se guarda o se cierra con la X. Así no se pierde si algo recarga la página.
def abrir_ventana(tipo: str, cliente_id: int | None = None) -> None:
    st.session_state["cred_ventana"] = (tipo, cliente_id)


def cerrar_ventana() -> None:
    st.session_state.pop("cred_ventana", None)


# ---------------------------------------------------------------------
# Datos: totales de la vista + antigüedad calculada por cliente
# ---------------------------------------------------------------------
saldos = leer("SELECT * FROM v_saldos_credito ORDER BY saldo_vencido DESC, saldo DESC, nombre")
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


def desde_txt(cliente_id) -> str:
    desde = cuentas[cliente_id]["desde"]
    return "desde antes de septiembre" if desde is None else f"desde el {fecha_corta(desde)}"


def etiqueta_estado(c) -> None:
    if c.saldo_vencido > 0:
        st.badge("Vencido", color="red")
    elif c.saldo > 0:
        st.badge(f"Vence {fecha_corta(cuentas[c.cliente_id]['proximo'])}", color="orange")
    else:
        st.badge("Al corriente", color="gray")


# ---------------------------------------------------------------------
# Ventanas: recordar, nuevo cliente, editar cliente, entrega y pago
# ---------------------------------------------------------------------
@st.dialog("Recordar pago", width="medium", on_dismiss=cerrar_ventana)
def recordar(c) -> None:
    st.markdown(md(f"**{c.nombre}** · Tel. {c.telefono or 'sin teléfono'}"))
    m1, m2 = st.columns(2)
    m1.metric("Debe según el sistema", pesos(c.saldo), border=True)
    m2.metric("Vencido", pesos(c.saldo_vencido), border=True)
    if c.saldo_vencido > 0:
        st.caption(f"Vencido {desde_txt(c.cliente_id)}.")

    sugerido = float(c.saldo_vencido if c.saldo_vencido > 0 else max(c.saldo, 0))
    monto = st.number_input("Monto a recordar", min_value=0.0, step=10.0, value=sugerido,
                            key=f"rec_monto_{c.cliente_id}")
    if monto != sugerido:
        st.caption("El ajuste solo cambia el mensaje: el saldo del cliente no se modifica.")
    # Sin key: si cambia el monto, el mensaje se vuelve a escribir con el nuevo monto
    mensaje = st.text_area("Mensaje", height=110, value=(
        f"Hola, le saluda Carmen de Panadería La Espiga Dorada. Le recordamos su saldo pendiente "
        f"de {pesos(monto)}. ¡Gracias!"))
    if not c.telefono:
        st.warning("Este cliente no tiene teléfono: WhatsApp te pedirá elegir el contacto.")
    destino = f"52{c.telefono}" if c.telefono else ""
    st.link_button("Abrir WhatsApp", f"https://wa.me/{destino}?text={quote(mensaje)}", type="primary",
                   icon=":material/send:", width="stretch", disabled=monto <= 0)


@st.dialog("Nuevo cliente de crédito", width="medium", on_dismiss=cerrar_ventana)
def nuevo_cliente() -> None:
    st.caption("Si ya existe porque encargó pasteles, elígelo y se le activa el crédito.")
    otros = leer("SELECT id, nombre FROM clientes WHERE NOT es_credito ORDER BY nombre")
    with st.form("nuevo_credito", border=False):
        existente = st.selectbox("Cliente que ya existe (opcional)", [None, *otros.id],
                                 format_func=lambda i: "Es nuevo" if i is None
                                 else otros.set_index("id").nombre[i])
        nombre_n = st.text_input("Nombre del negocio (si es nuevo)")
        tel_n = st.text_input("Teléfono (10 dígitos)")
        dias_n = st.number_input("Días de crédito", min_value=0, max_value=60, value=7)
        if st.form_submit_button("Dar de alta", type="primary", width="stretch"):
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


@st.dialog("Editar cliente", width="medium", on_dismiss=cerrar_ventana)
def editar_cliente(c) -> None:
    with st.form(f"datos_{c.cliente_id}", border=False):
        nombre = st.text_input("Nombre", value=c.nombre)
        tel = st.text_input("Teléfono (10 dígitos)", value=c.telefono or "")
        dias = st.number_input("Días de crédito", min_value=0, max_value=60, value=int(c.dias_credito))
        saldo_ini = st.number_input("Saldo anterior a septiembre", min_value=0.0, step=10.0,
                                    value=float(c.saldo_inicial))
        confirmado = st.checkbox("El saldo anterior ya está confirmado con el cliente",
                                 value=not c.saldo_inicial_nota)
        if st.form_submit_button("Guardar cambios", type="primary", width="stretch"):
            if not nombre.strip():
                st.error("El nombre no puede quedar vacío.")
            elif tel and not telefono(tel):
                st.error("El teléfono debe tener 10 dígitos.")
            else:
                guardar_y_recargar(
                    f"Datos de {nombre.strip()} actualizados.",
                    """UPDATE clientes SET nombre = :n, telefono = :t, dias_credito = :d, saldo_inicial = :s,
                              saldo_inicial_nota = CASE WHEN :conf THEN NULL ELSE saldo_inicial_nota END
                       WHERE id = :c""",
                    n=nombre.strip(), t=telefono(tel), d=int(dias), s=saldo_ini, conf=confirmado,
                    c=int(c.cliente_id))


@st.dialog("Registrar entrega a crédito", width="medium", on_dismiss=cerrar_ventana)
def registrar_entrega(c) -> None:
    with st.form(f"entrega_{c.cliente_id}", border=False):
        st.markdown(md(f"Lo que se llevó **{c.nombre}**"))
        fecha_e = st.date_input("Fecha", value=hoy(), max_value=hoy(), format="DD/MM/YYYY")
        desc_e = st.text_input("Qué se llevó", placeholder="Ej. 100 bolillos, 20 teleras")
        monto_e = st.number_input("Monto", min_value=0.0, step=10.0)
        nota_e = st.text_input("Folio de la nota de remisión (opcional)")
        if st.form_submit_button("Guardar entrega", type="primary", width="stretch"):
            if not desc_e.strip() or monto_e <= 0:
                st.error("Escribe qué se llevó y el monto.")
            else:
                guardar_y_recargar(
                    f"Entrega de {pesos(monto_e)} registrada para {c.nombre}.",
                    """INSERT INTO entregas_credito (cliente_id, fecha, descripcion, monto, nota_remision, registrado_por)
                       VALUES (:c, :f, :d, :m, :n, :u)""",
                    c=int(c.cliente_id), f=fecha_e, d=desc_e.strip(), m=monto_e, n=nota_e.strip() or None,
                    u=usuario["id"])


@st.dialog("Registrar pago", width="medium", on_dismiss=cerrar_ventana)
def registrar_pago(c) -> None:
    with st.form(f"abono_{c.cliente_id}", border=False):
        st.markdown(md(f"Pago de **{c.nombre}** · debe {pesos(c.saldo)}"))
        fecha_a = st.date_input("Fecha", value=hoy(), max_value=hoy(), format="DD/MM/YYYY")
        monto_a = st.number_input("Monto", min_value=0.0, step=10.0, value=float(max(c.saldo_vencido, 0)),
                                  key=f"abono_monto_{c.cliente_id}")
        metodo_a = st.selectbox("Forma de pago", list(METODOS))
        nota_a = st.text_input("Nota (opcional)")
        if st.form_submit_button("Guardar pago", type="primary", width="stretch"):
            if monto_a <= 0:
                st.error("Escribe el monto del pago.")
            else:
                guardar_y_recargar(
                    f"Pago de {pesos(monto_a)} de {c.nombre} registrado. "
                    f"Ahora debe {pesos(float(c.saldo) - monto_a)}.",
                    """INSERT INTO abonos_credito (cliente_id, fecha, monto, metodo, nota, registrado_por)
                       VALUES (:c, :f, :m, :mp, :n, :u)""",
                    c=int(c.cliente_id), f=fecha_a, m=monto_a, mp=METODOS[metodo_a], n=nota_a.strip() or None,
                    u=usuario["id"])


# ---------------------------------------------------------------------
# Indicadores, barra de acciones y tabla de clientes
# ---------------------------------------------------------------------
m1, m2, m3 = st.columns(3)
m1.metric("Te deben en total", pesos(saldos.saldo.clip(lower=0).sum()), border=True)
m2.metric("Ya vencido", pesos(saldos.saldo_vencido.sum()), border=True)
m3.metric("Clientes por cobrar", int((saldos.saldo_vencido > 0).sum()), border=True)

nombres = dict(zip(saldos.cliente_id, saldos.nombre))
with st.container(horizontal=True, vertical_alignment="bottom"):
    cliente_id = st.selectbox("Ver cuenta de", list(nombres), format_func=nombres.get, key="cred_cliente",
                              width=320)
    c = saldos[saldos.cliente_id == cliente_id].iloc[0]
    st.button("Editar cliente", icon=":material/edit:", key="cred_editar",
              on_click=abrir_ventana, args=("editar", int(cliente_id)))
    st.button("Nuevo cliente", icon=":material/person_add:", key="cred_nuevo",
              on_click=abrir_ventana, args=("nuevo",))

ANCHOS = [2.6, 1.5, 1.1, 1.1, 0.9, 1.1, 1.2]
encabezado_tabla("clientes", ["Cliente", "Estado", "Debe", "Vencido", "Paga a", "Último pago", ""], ANCHOS)
for cli in saldos.itertuples():
    col = fila(f"cliente_{cli.cliente_id}", ANCHOS)
    col[0].markdown(md(f"**{cli.nombre}**"))
    with col[1]:
        etiqueta_estado(cli)
    col[2].markdown(md(pesos(cli.saldo)))
    col[3].markdown(md(pesos(cli.saldo_vencido)) if cli.saldo_vencido > 0 else "—")
    col[4].markdown(f"{cli.dias_credito} días")
    col[5].markdown(fecha_corta(cli.ultimo_abono) if pd.notna(cli.ultimo_abono) else "—")
    col[6].button("Recordar", key=f"recordar_{cli.cliente_id}", icon=":material/chat:", width="stretch",
                  disabled=cli.saldo <= 0, on_click=abrir_ventana, args=("recordar", int(cli.cliente_id)))

# ---------------------------------------------------------------------
# Cuenta del cliente elegido
# ---------------------------------------------------------------------
cuenta = cuentas[cliente_id]
st.space("medium")
with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader(f"Cuenta de {c.nombre}", width="stretch")
    st.button("Registrar entrega", icon=":material/local_shipping:", key="cred_entrega",
              on_click=abrir_ventana, args=("entrega", int(cliente_id)))
    st.button("Registrar pago", icon=":material/payments:", type="primary", key="cred_pago",
              on_click=abrir_ventana, args=("pago", int(cliente_id)))

d1, d2, d3 = st.columns(3)
d1.metric("Debe", pesos(c.saldo), border=True)
d2.metric("Vencido", pesos(c.saldo_vencido), border=True)
d3.metric("Paga a", f"{c.dias_credito} días", border=True)
if c.saldo_inicial_nota:
    st.warning(md(f"Saldo anterior de {pesos(c.saldo_inicial)}: {c.saldo_inicial_nota}"), icon=":material/flag:")
if cuenta["a_favor"] > 0:
    st.info(md(f"Tiene {pesos(cuenta['a_favor'])} a su favor (pagó de más)."))

col_pend, col_mov = st.columns(2, gap="large")
with col_pend:
    st.markdown("**Lo que debe** · lo más viejo se paga primero")
    if cuenta["cargos"]:
        st.dataframe(pd.DataFrame({
            "Fecha": [fecha_corta(x.fecha) if x.fecha else "Antes" for x in cuenta["cargos"]],
            "Qué se llevó": [x.descripcion for x in cuenta["cargos"]],
            "Falta": [pesos(x.pendiente) for x in cuenta["cargos"]],
            "Vence": ["Vencido" if x.vence is None or x.vence <= hoy() else fecha_corta(x.vence)
                      for x in cuenta["cargos"]],
        }), hide_index=True, width="stretch")
    else:
        st.caption("No debe nada.")

with col_mov:
    st.markdown("**Movimientos**")
    movimientos = pd.concat([
        pd.DataFrame([{"Fecha": None, "Concepto": "Saldo anterior", "Cargo": float(c.saldo_inicial), "Abono": 0.0}])
        if c.saldo_inicial > 0 else None,
        pd.DataFrame({"Fecha": e.fecha, "Concepto": e.descripcion, "Cargo": float(e.monto), "Abono": 0.0}
                     for e in entregas[entregas.cliente_id == cliente_id].itertuples()),
        pd.DataFrame({"Fecha": a.fecha, "Concepto": "Pago" if a.metodo == "sin_dato" else f"Pago ({a.metodo})",
                      "Cargo": 0.0, "Abono": float(a.monto)}
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
        }), hide_index=True, width="stretch", height=300)

# ---------------------------------------------------------------------
# Ventana abierta (si hay)
# ---------------------------------------------------------------------
if ventana := st.session_state.get("cred_ventana"):
    tipo, vid = ventana
    VENTANAS = {"recordar": recordar, "editar": editar_cliente, "entrega": registrar_entrega, "pago": registrar_pago}
    if tipo == "nuevo":
        nuevo_cliente()
    elif tipo in VENTANAS and vid in nombres:
        VENTANAS[tipo](saldos[saldos.cliente_id == vid].iloc[0])
    else:
        cerrar_ventana()
