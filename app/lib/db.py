"""Conexión a Postgres con el rol de base de datos de quien inició sesión.

La app nunca usa al administrador. Cada persona entra con el rol que le toca:
    sin sesión -> app_login      (solo puede llamar autenticar())
    mostrador  -> app_mostrador  (sin acceso a compras, crédito ni totales)
    dueña      -> app_duena
Así, si una pantalla tuviera un error, la base igual niega lo que no corresponde.
"""

import os
from contextlib import contextmanager

import pandas as pd
import streamlit as st
from sqlalchemy import URL, create_engine, text

_PASSWORD_ENV = {
    "login": "APP_LOGIN_PASSWORD",
    "mostrador": "APP_MOSTRADOR_PASSWORD",
    "duena": "APP_DUENA_PASSWORD",
}


@st.cache_resource
def motor(rol: str):
    """Un pool de conexiones por rol, compartido por todas las sesiones."""
    url = URL.create(
        "postgresql+psycopg",
        username=f"app_{rol}",
        password=os.environ[_PASSWORD_ENV[rol]],
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        database=os.environ["DB_NAME"],
    )
    return create_engine(url, pool_size=3, max_overflow=2, pool_pre_ping=True)


@contextmanager
def transaccion():
    """Transacción con el rol del usuario en sesión.

    Fija app.usuario_id (solo para esta transacción) para que la base sepa
    qué persona está capturando, p. ej. en la vista v_mis_capturas_hoy.
    """
    usuario = st.session_state.get("usuario")
    if usuario is None:
        raise PermissionError("No hay sesión iniciada")
    with motor(usuario["rol"]).begin() as conn:
        conn.execute(text("SELECT set_config('app.usuario_id', :id, true)"), {"id": str(usuario["id"])})
        yield conn


def leer(sql: str, **params) -> pd.DataFrame:
    with transaccion() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def ejecutar(sql: str, **params):
    """INSERT/UPDATE. Devuelve la primera fila si la sentencia tiene RETURNING."""
    with transaccion() as conn:
        resultado = conn.execute(text(sql), params)
        return resultado.mappings().first() if resultado.returns_rows else None
