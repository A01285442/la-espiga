"""Flujo de encargos como mostrador, contra la base real. Limpia lo que crea."""

from datetime import timedelta

import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from lib.db import motor
from lib.formato import hoy

LUPITA = {"id": 2, "nombre": "Lupita", "rol": "mostrador"}
CLIENTE_PRUEBA = "Cliente Prueba Automática"


@pytest.fixture(autouse=True)
def limpiar():
    yield
    with motor("duena").begin() as conn:   # la dueña sí puede borrar
        conn.execute(text("""DELETE FROM encargos WHERE cliente_id IN
                             (SELECT id FROM clientes WHERE nombre = :n)"""), {"n": CLIENTE_PRUEBA})
        conn.execute(text("DELETE FROM clientes WHERE nombre = :n"), {"n": CLIENTE_PRUEBA})


def pagina_encargos(vista: str = "➕ Nuevo encargo") -> AppTest:
    at = AppTest.from_file("paginas/encargos.py", default_timeout=30)
    at.session_state["usuario"] = LUPITA
    at.session_state["enc_vista"] = vista
    return at.run()


def boton(at: AppTest, etiqueta: str):
    return next(b for b in at.button if b.label == etiqueta)


def test_alta_de_encargo_con_cliente_nuevo_y_anticipo():
    at = pagina_encargos()
    at.selectbox(key="enc_cliente").set_value(-1).run()
    at.text_input(key="enc_nombre").input(CLIENTE_PRUEBA)
    at.text_input(key="enc_tel").input("81-0000-1111")
    at.date_input(key="enc_entrega").set_value(hoy() + timedelta(days=1))
    at.text_area(key="enc_desc").input("Pastel 3 leches 20 personas")
    at.number_input(key="enc_total").set_value(650.0)
    at.number_input(key="enc_anticipo").set_value(300.0).run()
    boton(at, "Guardar encargo").click().run()

    assert not at.exception
    assert "Falta cobrar $350" in at.success[0].value

    with motor("duena").connect() as conn:
        fila = conn.execute(text("""SELECT e.total, e.pagado, e.saldo, e.estado, c.telefono
                                    FROM v_encargos e JOIN clientes c ON c.id = e.cliente_id
                                    WHERE c.nombre = :n"""), {"n": CLIENTE_PRUEBA}).one()
    assert (fila.total, fila.pagado, fila.saldo, fila.estado) == (650, 300, 350, "pendiente")
    assert fila.telefono == "8100001111"            # se guardó normalizado

    # Aparece en "Mañana sale"
    manana = AppTest.from_file("paginas/manana.py", default_timeout=30)
    manana.session_state["usuario"] = LUPITA
    manana.run()
    assert any("Pastel 3 leches 20 personas" in m.value for m in manana.markdown)


def test_anticipo_mayor_al_total_no_deja_guardar():
    at = pagina_encargos()
    at.selectbox(key="enc_cliente").set_value(1).run()
    at.text_area(key="enc_desc").input("Rosca")
    at.number_input(key="enc_total").set_value(180.0)
    at.number_input(key="enc_anticipo").set_value(500.0).run()
    assert "El anticipo no puede ser mayor que el total." in [e.value for e in at.error]
    assert boton(at, "Guardar encargo").disabled


def test_avisa_si_el_cliente_ya_existe():
    at = pagina_encargos()
    at.selectbox(key="enc_cliente").set_value(-1).run()
    at.text_input(key="enc_nombre").input("mariana lopez").run()
    assert "Mariana López" in at.warning[0].value
