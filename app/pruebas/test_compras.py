"""Compras e insumos (solo dueña), contra la base real. Deshace lo que cambia."""

from datetime import date

from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from lib.db import motor
from lib.formato import pesos

CARMEN = {"id": 1, "nombre": "Carmen Rodríguez", "rol": "duena"}


def pagina(vista: str) -> AppTest:
    at = AppTest.from_file("../paginas/compras.py", default_timeout=30)
    at.session_state["usuario"] = CARMEN
    at.session_state["com_vista"] = vista
    return at.run()


def cifra(sql: str):
    with motor("duena").connect() as conn:
        return conn.execute(text(sql)).scalar_one()


SEPTIEMBRE = "fecha >= '2026-09-01' AND fecha < '2026-10-01'"


def test_compras_de_septiembre():
    # Contra la base (no contra cifras fijas): en la app se pueden borrar duplicados
    at = pagina("Gasto del mes")
    assert not at.exception
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Gastado en el mes"] == pesos(cifra(f"SELECT sum(total) FROM compras WHERE {SEPTIEMBRE}"))
    assert metricas["Posibles duplicados"] == str(
        cifra(f"SELECT count(*) FROM compras WHERE posible_duplicado AND {SEPTIEMBRE}"))
    assert metricas["Con cosas de la casa"] == "2"


def test_mes_sin_compras_no_truena():
    at = pagina("Gasto del mes")
    at.selectbox[0].set_value(date(2026, 10, 1)).run()
    assert not at.exception
    assert {m.label: m.value for m in at.metric}["Gastado en el mes"] == "$0"


def test_confirmar_duplicado():
    with motor("duena").connect() as conn:
        dup = conn.execute(text("SELECT min(id) FROM compras WHERE posible_duplicado")).scalar_one()
    antes = cifra("SELECT count(*) FROM compras WHERE posible_duplicado")
    at = pagina("Por revisar")
    assert {m.label: m.value for m in at.metric}["Posibles duplicados"] == str(antes)
    at.button(key=f"dup_ok_{dup}").click().run()
    try:
        assert not at.exception
        assert "confirmado" in at.success[0].value
        assert {m.label: m.value for m in at.metric}["Posibles duplicados"] == str(antes - 1)
    finally:
        with motor("duena").begin() as conn:
            conn.execute(text("UPDATE compras SET posible_duplicado = true WHERE id = :i"), {"i": dup})


def test_insumos_marca_lo_que_hay_que_pedir():
    at = pagina("Bodega")
    assert not at.exception
    assert {m.label: m.value for m in at.metric}["Por pedir"] == "2"     # cocoa y crema para batir
    assert "Cocoa" in at.error[0].value


def test_mostrador_no_entra():
    at = AppTest.from_file("../paginas/compras.py", default_timeout=30)
    at.session_state["usuario"] = {"id": 2, "nombre": "Lupita", "rol": "mostrador"}
    at.run()
    assert at.error[0].value == "No tienes acceso a esta sección."
