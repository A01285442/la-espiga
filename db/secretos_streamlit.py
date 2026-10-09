"""Genera secretos_streamlit.toml (no se sube a git) para pegarlo en Streamlit Cloud.

    python db/secretos_streamlit.py

Toma el host y la base de NEON_ADMIN_URL y las contraseñas de los roles de .env.
Solo incluye lo que la app necesita: NUNCA la contraseña de administrador.
Streamlit Cloud expone estos valores como variables de entorno, que es como
los lee app/lib/db.py.
"""

from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parent.parent

env = {}
for linea in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in linea and not linea.startswith("#"):
        k, v = linea.split("=", 1)
        env[k.strip()] = v.strip()

url = urlparse(env["NEON_ADMIN_URL"])
secretos = {
    "DB_HOST": url.hostname,
    "DB_PORT": str(url.port or 5432),
    "DB_NAME": url.path.lstrip("/"),
    "DB_SSLMODE": "require",
    "APP_LOGIN_PASSWORD": env["APP_LOGIN_PASSWORD"],
    "APP_MOSTRADOR_PASSWORD": env["APP_MOSTRADOR_PASSWORD"],
    "APP_DUENA_PASSWORD": env["APP_DUENA_PASSWORD"],
}
destino = RAIZ / "secretos_streamlit.toml"
destino.write_text("".join(f'{k} = "{v}"\n' for k, v in secretos.items()), encoding="utf-8")
print(f"Escrito {destino.name}: copia su contenido en Streamlit Cloud → App settings → Secrets.")
