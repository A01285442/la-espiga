# Placeholder: verifica que la app llega a la base con el rol app_login.
import os

import streamlit as st
from sqlalchemy import create_engine, text

url = (
    f"postgresql+psycopg://app_login:{os.environ['APP_LOGIN_PASSWORD']}"
    f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"
)
st.title("La Espiga Dorada")
with create_engine(url).connect() as conn:
    st.write("Conexión a la base:", conn.execute(text("select current_user")).scalar())
