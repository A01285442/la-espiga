"""Encargos de pasteles: alta con anticipo, cobro del saldo y entrega."""

from urllib.parse import quote

import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from lib.auth import requerir_rol
from lib.db import leer, mensaje_error, transaccion
from lib.formato import ESTADOS, cuando, fecha_corta, fecha_larga, hoy, manana, md, normalizar, pesos, telefono
from lib.ui import aviso, encabezado, subpestanas

usuario = requerir_rol("duena", "mostrador")
es_duena = usuario["rol"] == "duena"

METODOS = {"Efectivo": "efectivo", "Transferencia": "transferencia", "Tarjeta": "tarjeta"}
CLIENTE_NUEVO = -1
CAMPOS_NUEVO = ["enc_cliente", "enc_nombre", "enc_tel", "enc_entrega", "enc_desc",
                "enc_total", "enc_anticipo", "enc_metodo", "enc_confirma_nuevo"]

encabezado("Encargos", "Pasteles por encargo: lo urgente, lo que falta entregar y el historial.")
aviso("enc_aviso")


def guardar_y_recargar(aviso: str, sentencias: list[tuple[str, dict]], mantener_abierto: int | None = None) -> None:
    """Ejecuta varias sentencias en una sola transacción y recarga la página.

    mantener_abierto: id del encargo cuyo panel debe seguir abierto (p. ej. tras
    cobrar, para entregar enseguida). Streamlit reinicia la selección de la tabla
    cuando cambian sus datos, así que el encargo abierto se recuerda aparte.
    """
    try:
        with transaccion() as conn:
            for sql, params in sentencias:
                conn.execute(text(sql), params)
    except DBAPIError as error:
        st.error(md(mensaje_error(error)))
        return
    st.session_state["enc_aviso"] = aviso
    st.session_state.pop("tabla_pendientes", None)
    st.session_state["enc_abierto"] = mantener_abierto
    st.rerun()


URGENTES, POR_ENTREGAR, NUEVO, TODOS = "Urgentes", "Por entregar", "Nuevo encargo", "Historial"
vista = subpestanas([URGENTES, POR_ENTREGAR, NUEVO, TODOS], key="enc_vista")


def abrir(encargo_id: int) -> None:
    """Desde Urgentes: ir a Por entregar con el encargo abierto (callback, antes de dibujar)."""
    st.session_state["enc_vista"] = POR_ENTREGAR
    st.session_state["enc_abierto"] = encargo_id
    st.session_state.pop("tabla_pendientes", None)


# ---------------------------------------------------------------------
# Urgentes: atrasados, hoy y mañana (lo que Toño tiene que hornear)
# ---------------------------------------------------------------------
if vista == URGENTES:
    pendientes = leer("""
        SELECT id, cliente, descripcion, estado, saldo, fecha_entrega, requiere_revision
        FROM v_encargos
        WHERE estado IN ('pendiente', 'listo') AND fecha_entrega <= :m
        ORDER BY fecha_entrega, id""", m=manana())
    grupos = [
        ("Atrasados", "Ya pasó la fecha y no se han marcado como entregados.", pendientes.fecha_entrega < hoy()),
        ("Hoy", fecha_larga(hoy()), pendientes.fecha_entrega == hoy()),
        ("Mañana", fecha_larga(manana()), pendientes.fecha_entrega == manana()),
    ]
    for col, (titulo, _, filtro) in zip(st.columns(3), grupos):
        col.metric(titulo, int(filtro.sum()), border=True)

    for titulo, detalle, filtro in grupos:
        grupo = pendientes[filtro]
        if titulo == "Atrasados" and grupo.empty:
            continue
        st.subheader(titulo)
        st.caption(detalle.capitalize())
        if grupo.empty:
            st.caption("Sin encargos.")
        for e in grupo.itertuples():
            with st.container(border=True, horizontal=True, vertical_alignment="center"):
                pago = "pagado" if e.saldo <= 0 else f"falta cobrar {pesos(e.saldo)}"
                revisar = " · revisar con Carmen" if e.requiere_revision else ""
                st.markdown(md(f"**{e.descripcion}**  \n{e.cliente} · #{e.id} · {pago}{revisar}"), width="stretch")
                if e.estado == "listo":
                    st.badge("Listo", color="green")
                st.button("Abrir", key=f"urg_abrir_{e.id}", icon=":material/open_in_new:",
                          on_click=abrir, args=(int(e.id),))

    # Lista para el panadero: por default la de mañana
    st.subheader("Lista para Toño")
    dia = st.date_input("Día", value=manana(), format="DD/MM/YYYY", key="urg_dia", width=220)
    del_dia = leer("""
        SELECT id, cliente, descripcion FROM v_encargos
        WHERE fecha_entrega = :d AND estado IN ('pendiente', 'listo') ORDER BY id""", d=dia)
    if del_dia.empty:
        st.caption("No hay encargos pendientes para ese día.")
    else:
        lista = "\n".join(f"{n}. {e.descripcion} ({e.cliente})" for n, e in enumerate(del_dia.itertuples(), 1))
        mensaje = f"Encargos para {fecha_larga(dia)}:\n{lista}"
        st.code(mensaje, language=None, wrap_lines=True)
        with st.container(horizontal=True):
            # wa.me abre WhatsApp con el mensaje escrito; quien lo manda elige a Toño. Sin costo ni API.
            st.link_button("Mandar por WhatsApp", f"https://wa.me/?text={quote(mensaje)}",
                           icon=":material/send:", type="primary")
            st.download_button("Descargar lista", mensaje, file_name=f"encargos_{dia:%Y-%m-%d}.txt",
                               icon=":material/download:", on_click="ignore")

# ---------------------------------------------------------------------
# Por entregar
# ---------------------------------------------------------------------
if vista == POR_ENTREGAR:
    pendientes = leer("""
        SELECT * FROM v_encargos
        WHERE estado IN ('pendiente', 'listo')
        ORDER BY fecha_entrega, id""")

    atrasados = (pendientes.fecha_entrega < hoy()).sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Para hoy", int((pendientes.fecha_entrega == hoy()).sum()), border=True)
    c2.metric("Para mañana", int((pendientes.fecha_entrega == manana()).sum()), border=True)
    c3.metric("Atrasados", int(atrasados), border=True)
    if atrasados:
        st.warning(f"Hay {atrasados} encargo(s) con fecha de entrega pasada que no se han marcado como entregados.")

    if pendientes.empty:
        st.info("No hay encargos pendientes. Los nuevos aparecen aquí.")
    else:
        tabla = pendientes.assign(
            Cuándo=pendientes.fecha_entrega.map(cuando),
            Entrega=pendientes.fecha_entrega.map(fecha_corta),
            Estado=pendientes.estado.map(ESTADOS),
            Total=pendientes.total.map(pesos),
            Saldo=pendientes.saldo.map(lambda s: pesos(s) if s > 0 else "Pagado"),
        ).rename(columns={"id": "#", "cliente": "Cliente", "descripcion": "Pedido"})
        st.caption("Toca un renglón para cobrar, marcar listo o entregar.")
        evento = st.dataframe(
            tabla[["#", "Cuándo", "Entrega", "Cliente", "Pedido", "Total", "Saldo", "Estado"]],
            hide_index=True, width="stretch",
            on_select="rerun", selection_mode="single-row", key="tabla_pendientes",
        )

        if evento.selection.rows:
            st.session_state["enc_abierto"] = int(pendientes.iloc[evento.selection.rows[0]].id)
        abierto = pendientes[pendientes.id == st.session_state.get("enc_abierto")]

        if not abierto.empty:
            enc = abierto.iloc[0]
            saldo = float(enc.saldo)
            detalle = st.container(border=True)
            titulo, cerrar = detalle.columns([5, 1], vertical_alignment="center")
            titulo.subheader(f"Encargo #{enc.id} · {enc.cliente}")
            if cerrar.button("Cerrar", key=f"cerrar_{enc.id}", icon=":material/close:", type="tertiary"):
                st.session_state["enc_abierto"] = None
                st.session_state.pop("tabla_pendientes", None)
                st.rerun()
            detalle.markdown(md(f"**{enc.descripcion}**"))
            detalle.caption(f"Entrega: {fecha_corta(enc.fecha_entrega)} · {ESTADOS[enc.estado]} · "
                            f"Tel. {enc.telefono or 'sin teléfono'}")
            m1, m2, m3 = detalle.columns(3)
            m1.metric("Total", pesos(enc.total), border=True)
            m2.metric("Pagado", pesos(enc.pagado), border=True)
            m3.metric("Falta", pesos(saldo), border=True)
            if enc.requiere_revision:
                detalle.warning(md(f"Revisar con Carmen: {enc.nota_revision}"), icon=":material/flag:")

            col_pago, col_estado = detalle.columns(2, gap="large")
            with col_pago:
                st.markdown("**Registrar pago**")
                if saldo <= 0:
                    st.success("Ya está pagado completo.")
                else:
                    monto = st.number_input("Monto", min_value=0.0, max_value=saldo, value=saldo,
                                            step=10.0, key=f"pago_monto_{enc.id}")
                    metodo = st.selectbox("Forma de pago", list(METODOS), key=f"pago_metodo_{enc.id}")
                    if st.button("Registrar pago", icon=":material/payments:", key=f"pagar_{enc.id}", disabled=monto <= 0):
                        guardar_y_recargar(
                            f"Pago de {pesos(monto)} registrado en el encargo #{enc.id}.",
                            [("""INSERT INTO pagos_encargo (encargo_id, monto, tipo, metodo, registrado_por)
                                 VALUES (:e, :m, :t, :mp, :u)""",
                              {"e": int(enc.id), "m": monto, "mp": METODOS[metodo], "u": usuario["id"],
                               "t": "liquidacion" if monto >= saldo else "abono"})],
                            mantener_abierto=int(enc.id))

            with col_estado:
                st.markdown("**Estado**")
                if enc.estado == "pendiente" and st.button("Marcar como listo", icon=":material/check:", key=f"listo_{enc.id}"):
                    guardar_y_recargar(f"Encargo #{enc.id} listo.", [
                        ("UPDATE encargos SET estado = 'listo' WHERE id = :e", {"e": int(enc.id)})],
                        mantener_abierto=int(enc.id))

                con_saldo = saldo > 0 and st.checkbox(
                    f"Entregar aunque falten {pesos(saldo)}", key=f"con_saldo_{enc.id}")
                if st.button("Entregado al cliente", key=f"entregar_{enc.id}", type="primary", icon=":material/done_all:",
                             disabled=saldo > 0 and not con_saldo):
                    guardar_y_recargar(f"Encargo #{enc.id} entregado.", [
                        ("UPDATE encargos SET estado = 'entregado', entregado_en = now() WHERE id = :e",
                         {"e": int(enc.id)})])
                if saldo > 0 and not con_saldo:
                    st.caption("Cobra el saldo antes de entregar, o marca la casilla si queda a deber.")

                with st.expander("Cambiar fecha de entrega"):
                    nueva = st.date_input("Nueva fecha", value=max(enc.fecha_entrega, hoy()), min_value=hoy(),
                                          format="DD/MM/YYYY", key=f"fecha_{enc.id}")
                    if st.button("Guardar fecha", key=f"guardar_fecha_{enc.id}"):
                        guardar_y_recargar(f"Encargo #{enc.id} ahora se entrega el {fecha_corta(nueva)}.", [
                            ("UPDATE encargos SET fecha_entrega = :f WHERE id = :e",
                             {"f": nueva, "e": int(enc.id)})])

                if es_duena:
                    with st.expander("Cancelar encargo"):
                        st.write("El encargo deja de aparecer en la lista. Los pagos se conservan.")
                        if st.button("Cancelar encargo", key=f"cancelar_{enc.id}"):
                            guardar_y_recargar(f"Encargo #{enc.id} cancelado.", [
                                ("UPDATE encargos SET estado = 'cancelado' WHERE id = :e",
                                 {"e": int(enc.id)})])

# ---------------------------------------------------------------------
# Nuevo encargo
# ---------------------------------------------------------------------
if vista == NUEVO:
    if st.session_state.pop("enc_limpiar", False):
        for campo in CAMPOS_NUEVO:
            st.session_state.pop(campo, None)

    clientes = leer("SELECT id, nombre, telefono FROM clientes ORDER BY nombre")
    etiquetas = {CLIENTE_NUEVO: "Cliente nuevo (dar de alta)"} | {
        r.id: f"{r.nombre} · {r.telefono}" if r.telefono else r.nombre for r in clientes.itertuples()}

    cliente_id = st.selectbox("Cliente", list(etiquetas), format_func=etiquetas.get, index=None,
                              placeholder="Escribe para buscar…", key="enc_cliente")

    nombre_nuevo, tel_nuevo, puede_guardar_cliente = None, None, cliente_id is not None
    if cliente_id == CLIENTE_NUEVO:
        c1, c2 = st.columns(2)
        nombre_nuevo = c1.text_input("Nombre del cliente", key="enc_nombre").strip()
        tel_texto = c2.text_input("Teléfono (10 dígitos)", key="enc_tel")
        tel_nuevo = telefono(tel_texto)
        if tel_texto and not tel_nuevo:
            c2.error("El teléfono debe tener 10 dígitos.")
        # Evitar el problema del Excel: el mismo cliente escrito de varias formas
        mismo_nombre = clientes.nombre.map(normalizar).str.contains(normalizar(nombre_nuevo), regex=False)
        mismo_tel = clientes.telefono == tel_nuevo
        parecidos = clientes[(mismo_nombre & (len(nombre_nuevo) >= 3)) | (mismo_tel & bool(tel_nuevo))]
        if not parecidos.empty:
            st.warning("¿Es alguno de estos clientes? Si sí, búscalo arriba en la lista:  \n"
                       + "  \n".join(f"- {etiquetas[i]}" for i in parecidos.id))
            puede_guardar_cliente = st.checkbox("No, es un cliente nuevo", key="enc_confirma_nuevo")
        puede_guardar_cliente = puede_guardar_cliente and bool(nombre_nuevo) and not (tel_texto and not tel_nuevo)

    fecha_entrega = st.date_input("Fecha de entrega", value=manana(), min_value=hoy(),
                                  format="DD/MM/YYYY", key="enc_entrega")
    if fecha_entrega == hoy():
        st.warning("Es para hoy: avísale a Toño en persona.")
    descripcion = st.text_area("¿Qué pidió?", placeholder="Ej. Pastel 3 leches 20 personas, fresas, letrero 'Feliz cumple Dani'",
                               key="enc_desc").strip()
    c1, c2, c3 = st.columns(3)
    total = c1.number_input("Precio total", min_value=0.0, step=10.0, key="enc_total")
    anticipo = c2.number_input("Anticipo que dejó", min_value=0.0, step=10.0, key="enc_anticipo")
    metodo = c3.selectbox("Forma de pago del anticipo", list(METODOS), key="enc_metodo")

    errores = []
    if anticipo > total:
        errores.append("El anticipo no puede ser mayor que el total.")
    for e in errores:
        st.error(e)
    if total > 0:
        st.info(md(f"Saldo a cobrar al entregar: **{pesos(total - anticipo)}**"))

    listo = puede_guardar_cliente and descripcion and total > 0 and not errores
    if st.button("Guardar encargo", type="primary", disabled=not listo):
        try:
            with transaccion() as conn:
                if cliente_id == CLIENTE_NUEVO:
                    cliente_id = conn.execute(
                        text("INSERT INTO clientes (nombre, telefono) VALUES (:n, :t) RETURNING id"),
                        {"n": nombre_nuevo, "t": tel_nuevo}).scalar_one()
                encargo_id = conn.execute(text("""
                    INSERT INTO encargos (cliente_id, fecha_entrega, descripcion, total, creado_por)
                    VALUES (:c, :f, :d, :t, :u) RETURNING id"""),
                    {"c": cliente_id, "f": fecha_entrega, "d": descripcion, "t": total, "u": usuario["id"]}
                ).scalar_one()
                if anticipo > 0:
                    conn.execute(text("""
                        INSERT INTO pagos_encargo (encargo_id, monto, tipo, metodo, registrado_por)
                        VALUES (:e, :m, 'anticipo', :mp, :u)"""),
                        {"e": encargo_id, "m": anticipo, "mp": METODOS[metodo], "u": usuario["id"]})
        except DBAPIError as error:
            st.error(md(mensaje_error(error)))
        else:
            st.session_state["enc_limpiar"] = True
            st.session_state["enc_aviso"] = (
                f"Encargo #{encargo_id} guardado para el {fecha_corta(fecha_entrega)}. "
                f"Falta cobrar {pesos(total - anticipo)}.")
            st.rerun()
    elif not listo:
        st.caption("Para guardar: elige el cliente, escribe qué pidió y el precio total.")

# ---------------------------------------------------------------------
# Todos (historial)
# ---------------------------------------------------------------------
if vista == TODOS:
    c1, c2, c3 = st.columns([2, 2, 1])
    estados = c1.multiselect("Estado", list(ESTADOS), format_func=ESTADOS.get, default=list(ESTADOS))
    buscar = c2.text_input("Buscar cliente o pedido")
    por_revisar = c3.checkbox("Solo por revisar")

    todos = leer("SELECT * FROM v_encargos ORDER BY fecha_entrega DESC, id DESC")
    todos = todos[todos.estado.isin(estados)]
    if buscar:
        b = normalizar(buscar)
        todos = todos[(todos.cliente.map(normalizar) + " " + todos.descripcion.map(normalizar))
                      .str.contains(b, regex=False)]
    if por_revisar:
        todos = todos[todos.requiere_revision]

    st.caption(f"{len(todos)} encargos")
    st.dataframe(
        todos.assign(
            Entrega=todos.fecha_entrega.map(fecha_corta),
            Estado=todos.estado.map(ESTADOS),
            Total=todos.total.map(pesos), Pagado=todos.pagado.map(pesos), Saldo=todos.saldo.map(pesos),
            Revisar=todos.nota_revision.fillna(""),
        ).rename(columns={"id": "#", "cliente": "Cliente", "descripcion": "Pedido"})
        [["#", "Entrega", "Cliente", "Pedido", "Total", "Pagado", "Saldo", "Estado", "Revisar"]],
        hide_index=True, width="stretch",
    )
