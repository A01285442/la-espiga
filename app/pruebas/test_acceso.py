"""Pruebas de login y acceso por rol, contra la base real del contenedor.

Correr:  docker compose exec app python -m pytest -q pruebas
Usa las contraseñas de prueba de las variables PWD_* (ver docker-compose).
"""

import os

import pytest
from streamlit.testing.v1 import AppTest

PWD = {"carmen": os.environ.get("PWD_CARMEN"), "lupita": os.environ.get("PWD_LUPITA")}


def login(usuario: str, password: str) -> AppTest:
    at = AppTest.from_file("../Inicio.py", default_timeout=30).run()
    at.text_input[0].input(usuario)
    at.text_input[1].input(password)
    at.button[0].click().run()
    return at


def test_login_correcto_dueña():
    at = login("carmen", PWD["carmen"])
    assert at.session_state["usuario"]["rol"] == "duena"


def test_login_correcto_mostrador():
    at = login("lupita", PWD["lupita"])
    assert at.session_state["usuario"]["rol"] == "mostrador"


def test_password_incorrecta_no_entra():
    at = login("lupita", "no-es-esta")
    assert "usuario" not in at.session_state
    assert "incorrectos" in at.error[0].value


def test_usuario_inexistente_mismo_mensaje():
    at = login("nadie", "x")
    assert at.error[0].value == "Usuario o contraseña incorrectos."


def test_bloqueo_tras_cinco_intentos():
    for _ in range(5):
        login("karla", "mal")
    at = login("karla", "mal")
    assert "Demasiados intentos" in at.error[0].value


@pytest.mark.parametrize("pagina", ["paginas/credito.py", "paginas/compras.py", "paginas/resumen.py"])
def test_mostrador_no_abre_paginas_de_dueña(pagina):
    """Simula entrar directo al archivo de la página con sesión de mostrador."""
    at = AppTest.from_file(f"../{pagina}", default_timeout=30)
    at.session_state["usuario"] = {"id": 2, "nombre": "Lupita", "rol": "mostrador"}
    at.run()
    assert at.error[0].value == "No tienes acceso a esta sección."
    assert len(at.title) == 0          # no se dibujó nada de la página


@pytest.mark.parametrize("pagina", ["paginas/credito.py", "paginas/encargos.py"])
def test_sin_sesion_no_abre_nada(pagina):
    at = AppTest.from_file(f"../{pagina}", default_timeout=30).run()
    assert at.error[0].value == "No tienes acceso a esta sección."
