"""Caja (mostrador) y resumen (dueña), contra la base real. Limpia lo que crea."""

import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from lib.db import motor
from lib.formato import pesos

LUPITA = {"id": 2, "nombre": "Lupita", "rol": "mostrador"}
CARMEN = {"id": 1, "nombre": "Carmen Rodríguez", "rol": "duena"}


@pytest.fixture(autouse=True)
def limpiar():
    yield
    with motor("duena").begin() as conn:
        conn.execute(text("DELETE FROM ventas WHERE origen = 'app'"))


def producto(nombre: str) -> tuple[int, float]:
    with motor("duena").connect() as conn:
        fila = conn.execute(text("SELECT id, precio FROM productos WHERE nombre = :n"), {"n": nombre}).one()
    return fila.id, float(fila.precio)


def caja() -> AppTest:
    at = AppTest.from_file("../paginas/ventas.py", default_timeout=30)
    at.session_state["usuario"] = LUPITA
    return at.run()


def test_cobrar_ticket_con_precio_del_catalogo():
    concha, precio_concha = producto("Concha chocolate")
    galletas, precio_kg = producto("Galletas surtidas")

    at = caja()
    for _ in range(6):
        at.button(key=f"caja_add_{concha}").click().run()
    at.number_input(key=f"caja_kg_{galletas}").set_value(1.5).run()
    at.button(key=f"caja_add_{galletas}").click().run()
    esperado = 6 * precio_concha + 1.5 * precio_kg
    assert at.session_state["caja_ticket"] == {concha: 6, galletas: 1.5}
    cobrar = at.button(key="caja_cobrar")
    assert cobrar.label == "Cobrar " + f"${esperado:,.0f}"            # el total va en el botón
    cobrar.click().run()

    assert not at.exception
    assert "cobrado: 2 producto(s)" in at.success[0].value
    assert at.session_state["caja_ticket"] == {}                      # listo para el siguiente cliente
    # "Tus tickets de hoy" muestra productos, no dinero
    tickets = at.dataframe[0].value
    assert list(tickets.columns) == ["Hora", "Productos"]
    assert tickets.Productos[0] == "6 Concha chocolate, 1.5 Galletas surtidas"

    with motor("duena").connect() as conn:
        venta = conn.execute(text("""SELECT v.capturado_por, v.fecha = current_date AS es_hoy, sum(vl.subtotal) AS total
                                     FROM ventas v JOIN venta_lineas vl ON vl.venta_id = v.id
                                     WHERE v.origen = 'app' GROUP BY v.id""")).one()
    assert venta.capturado_por == LUPITA["id"] and venta.es_hoy
    assert float(venta.total) == pytest.approx(esperado)


def test_cada_cobro_es_una_venta():
    bolillo, _ = producto("Bolillo")
    at = caja()
    for _ in range(2):                                   # dos clientes seguidos
        at.button(key=f"caja_add_{bolillo}").click().run()
        at.button(key="caja_cobrar").click().run()
    with motor("duena").connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM ventas WHERE origen = 'app'")).scalar_one() == 2


def test_quitar_y_vaciar_ticket():
    bolillo, _ = producto("Bolillo")
    at = caja()
    at.button(key=f"caja_add_{bolillo}").click().run()
    at.button(key=f"caja_mas_{bolillo}").click().run()
    assert at.session_state["caja_ticket"] == {bolillo: 2}
    at.button(key=f"caja_menos_{bolillo}").click().run()
    assert at.session_state["caja_ticket"] == {bolillo: 1}
    at.button(key="caja_vaciar").click().run()
    assert at.session_state["caja_ticket"] == {}
    assert at.button(key="caja_cobrar").disabled


def test_buscar_y_secciones_filtran_el_catalogo():
    concha, _ = producto("Concha chocolate")
    bolillo, _ = producto("Bolillo")
    at = caja()
    at.text_input(key="caja_buscar").input("concha").run()
    claves = {b.key for b in at.button}
    assert f"caja_add_{concha}" in claves and f"caja_add_{bolillo}" not in claves
    at.text_input(key="caja_buscar").input("").run()
    at.segmented_control(key="caja_seccion").set_value("Pan salado").run()
    claves = {b.key for b in at.button}
    assert f"caja_add_{bolillo}" in claves and f"caja_add_{concha}" not in claves


def test_ticket_vacio_no_se_puede_cobrar():
    assert caja().button(key="caja_cobrar").disabled


def test_resumen_de_septiembre():
    at = AppTest.from_file("../paginas/resumen.py", default_timeout=30)
    at.session_state["usuario"] = CARMEN
    at.run()
    assert not at.exception
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Mostrador"] == "$36,790"            # igual que el reporte de limpieza
    assert metricas["Negocios a crédito"] == "$26,610"
    with motor("duena").connect() as conn:
        compras = conn.execute(text("SELECT sum(total) FROM compras WHERE fecha >= '2026-09-01' "
                                    "AND fecha < '2026-10-01'")).scalar_one()
    assert metricas["Compras"] == pesos(compras)       # $108,339 con el Excel recién cargado
    assert any("Insumos por pedir" in w.value for w in at.warning)
