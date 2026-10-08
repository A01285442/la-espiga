"""Captura de ventas (mostrador) y resumen (dueña), contra la base real. Limpia lo que crea."""

import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from lib.db import motor

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


def test_mostrador_captura_venta_con_precio_del_catalogo():
    concha, precio_concha = producto("Concha chocolate")
    galletas, precio_kg = producto("Galletas surtidas")

    at = AppTest.from_file("paginas/ventas.py", default_timeout=30)
    at.session_state["usuario"] = LUPITA
    at.run()
    at.number_input(key=f"ven_cant_{concha}").set_value(6.0)
    at.number_input(key=f"ven_cant_{galletas}").set_value(1.5).run()
    esperado = 6 * precio_concha + 1.5 * precio_kg
    next(b for b in at.button if b.label == "Guardar venta").click().run()

    assert not at.exception
    assert "Venta guardada: 2 producto(s)" in at.success[0].value
    assert at.number_input(key=f"ven_cant_{concha}").value == 0      # se limpió para la siguiente
    # "Lo que capturaste hoy" muestra cantidades, no dinero
    capturado = at.dataframe[0].value
    assert set(capturado.columns) == {"Producto", "Cantidad"}
    assert dict(zip(capturado.Producto, capturado.Cantidad)) == {"Concha chocolate": 6, "Galletas surtidas": 1.5}

    with motor("duena").connect() as conn:
        venta = conn.execute(text("""SELECT v.capturado_por, v.fecha = current_date AS es_hoy, sum(vl.subtotal) AS total
                                     FROM ventas v JOIN venta_lineas vl ON vl.venta_id = v.id
                                     WHERE v.origen = 'app' GROUP BY v.id""")).one()
    assert venta.capturado_por == LUPITA["id"] and venta.es_hoy
    assert float(venta.total) == pytest.approx(esperado)


def test_sin_cantidades_no_se_puede_guardar():
    at = AppTest.from_file("paginas/ventas.py", default_timeout=30)
    at.session_state["usuario"] = LUPITA
    at.run()
    assert next(b for b in at.button if b.label == "Guardar venta").disabled


def test_resumen_de_septiembre():
    at = AppTest.from_file("paginas/resumen.py", default_timeout=30)
    at.session_state["usuario"] = CARMEN
    at.run()
    assert not at.exception
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Mostrador"] == "$36,790"            # igual que el reporte de limpieza
    assert metricas["Negocios a crédito"] == "$26,610"
    assert metricas["Compras"] == "$108,339"
    assert any("Insumos por pedir" in w.value for w in at.warning)
