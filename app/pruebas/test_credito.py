"""Cuentas por cobrar: la antigüedad calculada en Python debe cuadrar con la vista SQL."""

from datetime import date

import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from lib.credito import pendientes_por_antiguedad, proximo_vencimiento, vencido
from lib.db import motor
from lib.formato import hoy

CARMEN = {"id": 1, "nombre": "Carmen Rodríguez", "rol": "duena"}


def test_abonos_pagan_primero_lo_mas_viejo():
    entregas = [(date(2026, 9, 10), "B", 300.0), (date(2026, 9, 1), "A", 200.0)]
    cargos, a_favor = pendientes_por_antiguedad(100.0, entregas, total_abonado=250.0, dias_credito=7)
    # 250 paga: saldo anterior 100, luego 150 de A (01/09) -> faltan 50 de A y 300 de B
    assert [(c.descripcion, c.pendiente) for c in cargos] == [("A", 50.0), ("B", 300.0)]
    assert a_favor == 0
    assert vencido(cargos, date(2026, 9, 12)) == 50.0          # B vence el 17/09
    assert proximo_vencimiento(cargos, date(2026, 9, 12)) == date(2026, 9, 17)


def test_pago_de_mas_queda_a_favor():
    cargos, a_favor = pendientes_por_antiguedad(0, [(date(2026, 9, 1), "A", 100.0)], 150.0, 7)
    assert cargos == [] and a_favor == 50.0


def test_python_cuadra_con_la_vista_sql():
    with motor("duena").connect() as conn:
        clientes = conn.execute(text("SELECT * FROM v_saldos_credito")).mappings().all()
        for c in clientes:
            entregas = conn.execute(text("SELECT fecha, descripcion, monto FROM entregas_credito "
                                         "WHERE cliente_id = :c"), {"c": c["cliente_id"]}).all()
            cargos, _ = pendientes_por_antiguedad(float(c["saldo_inicial"]),
                                                  [(f, d, float(m)) for f, d, m in entregas],
                                                  float(c["abonado"]), c["dias_credito"])
            assert sum(x.pendiente for x in cargos) == pytest.approx(max(float(c["saldo"]), 0)), c["nombre"]
            assert vencido(cargos, hoy()) == pytest.approx(float(c["saldo_vencido"])), c["nombre"]


def test_pagina_de_credito_carga_para_la_dueña():
    at = AppTest.from_file("paginas/credito.py", default_timeout=30)
    at.session_state["usuario"] = CARMEN
    at.run()
    assert not at.exception
    assert at.metric[0].label == "Te deben en total"
    assert any("Toca cobrar" in s.value for s in at.subheader)


def test_registrar_abono_baja_el_saldo():
    at = AppTest.from_file("paginas/credito.py", default_timeout=30)
    at.session_state["usuario"] = CARMEN
    at.run()
    cliente = at.selectbox(key="cred_cliente").value
    with motor("duena").connect() as conn:
        antes = conn.execute(text("SELECT saldo FROM v_saldos_credito WHERE cliente_id = :c"),
                             {"c": cliente}).scalar_one()
    at.number_input(key=f"abono_monto_{cliente}").set_value(100.0)
    next(b for b in at.button if b.label == "Guardar pago").click()
    at.run()
    try:
        assert not at.exception
        assert "registrado" in at.success[0].value
        with motor("duena").connect() as conn:
            despues = conn.execute(text("SELECT saldo FROM v_saldos_credito WHERE cliente_id = :c"),
                                   {"c": cliente}).scalar_one()
        assert despues == antes - 100
    finally:
        with motor("duena").begin() as conn:
            conn.execute(text("DELETE FROM abonos_credito WHERE origen = 'app' AND cliente_id = :c"),
                         {"c": cliente})
