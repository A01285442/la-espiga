"""Formato para Carmen: pesos, fechas en español, teléfonos."""

import re
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("America/Monterrey")
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
ESTADOS = {"pendiente": "Pendiente", "listo": "Listo", "entregado": "Entregado", "cancelado": "Cancelado"}


def hoy() -> date:
    return datetime.now(ZONA).date()


def pesos(valor) -> str:
    valor = float(valor or 0)
    return f"${valor:,.0f}" if valor == int(valor) else f"${valor:,.2f}"


def fecha_larga(d: date) -> str:
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


def fecha_corta(d: date) -> str:
    return f"{DIAS[d.weekday()][:3]} {d:%d/%m}"


def cuando(d: date) -> str:
    """Etiqueta relativa a hoy para la lista de encargos."""
    dias = (d - hoy()).days
    if dias < 0:
        return f"⚠️ Atrasado {-dias} d"
    return {0: "🔴 Hoy", 1: "🟠 Mañana"}.get(dias, fecha_corta(d))


def normalizar(texto: str) -> str:
    """Igual que normalizar() en la base: minúsculas, sin acentos, espacios simples."""
    sin_acentos = "".join(c for c in unicodedata.normalize("NFKD", str(texto))
                          if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_acentos.strip()).lower()


def telefono(texto: str) -> str | None:
    """'81-2233-4455' -> '8122334455'. None si no son 10 dígitos."""
    digitos = re.sub(r"\D", "", texto or "")
    return digitos if len(digitos) == 10 else None


def manana() -> date:
    return hoy() + timedelta(days=1)
