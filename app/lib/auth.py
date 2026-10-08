"""Inicio de sesión y control de acceso por rol."""

import threading
from datetime import datetime, timedelta

import streamlit as st
from sqlalchemy import text

from lib.db import motor

MAX_INTENTOS = 5
BLOQUEO = timedelta(minutes=5)
NOMBRE_ROL = {"duena": "Dueña", "mostrador": "Mostrador"}


@st.cache_resource
def _intentos() -> tuple[dict, threading.Lock]:
    """Intentos fallidos por usuario, compartidos entre sesiones (vive en memoria)."""
    return {}, threading.Lock()


def _bloqueado_hasta(usuario: str) -> datetime | None:
    registro, candado = _intentos()
    with candado:
        fallos, hasta = registro.get(usuario, (0, None))
    return hasta if hasta and hasta > datetime.now() else None


def _registrar_fallo(usuario: str) -> None:
    registro, candado = _intentos()
    with candado:
        fallos, _ = registro.get(usuario, (0, None))
        fallos += 1
        hasta = datetime.now() + BLOQUEO if fallos >= MAX_INTENTOS else None
        registro[usuario] = (0 if hasta else fallos, hasta)


def _limpiar_fallos(usuario: str) -> None:
    registro, candado = _intentos()
    with candado:
        registro.pop(usuario, None)


def iniciar_sesion(usuario: str, password: str) -> str | None:
    """Devuelve None si entró, o el mensaje de error a mostrar."""
    usuario = usuario.strip().lower()
    if not usuario or not password:
        return "Escribe tu usuario y contraseña."
    if hasta := _bloqueado_hasta(usuario):
        return f"Demasiados intentos. Intenta de nuevo después de las {hasta:%H:%M}."

    # app_login solo tiene permiso de ejecutar autenticar(): no puede leer usuarios ni hashes
    with motor("login").connect() as conn:
        fila = conn.execute(
            text("SELECT id, nombre, rol FROM autenticar(:u, :p)"), {"u": usuario, "p": password}
        ).mappings().first()

    if fila is None:
        _registrar_fallo(usuario)
        return "Usuario o contraseña incorrectos."   # mismo mensaje: no revela si el usuario existe

    _limpiar_fallos(usuario)
    # session_state vive en el servidor: el navegador no puede cambiar su rol
    st.session_state["usuario"] = {"id": fila["id"], "nombre": fila["nombre"], "rol": fila["rol"]}
    return None


def cerrar_sesion() -> None:
    st.session_state.clear()


def usuario_actual() -> dict | None:
    return st.session_state.get("usuario")


def requerir_rol(*roles: str) -> dict:
    """Primera línea de cada página: si el rol no corresponde, la página no se ejecuta.

    El menú ya oculta las páginas de otros roles; esto cubre a quien intente
    entrar escribiendo la URL directo.
    """
    usuario = usuario_actual()
    if usuario is None or usuario["rol"] not in roles:
        st.error("No tienes acceso a esta sección.")
        st.stop()
    return usuario


def pantalla_login() -> None:
    st.title("🥐 La Espiga Dorada")
    with st.form("login"):
        usuario = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        entrar = st.form_submit_button("Entrar", type="primary", use_container_width=True)
    if entrar:
        error = iniciar_sesion(usuario, password)
        if error:
            st.error(error)
        else:
            st.rerun()
