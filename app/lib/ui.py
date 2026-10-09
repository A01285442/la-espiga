"""Piezas de interfaz compartidas: estilo, encabezados, avisos, subpestañas y renglones de tabla."""

import streamlit as st

from lib.formato import md

# Ajustes finos que el tema de config.toml no cubre
_CSS = """
<style>
.block-container { padding-top: 1rem; padding-bottom: 3rem; max-width: 1240px; }
header[data-testid="stHeader"] { display: none; }
/* Barra de menú */
.st-key-barra_menu { border-bottom: 1px solid #e4e2de; padding-bottom: 0.6rem; margin-bottom: 0.8rem; }
.st-key-barra_menu p { white-space: nowrap; }
h1 { letter-spacing: -0.015em; margin-bottom: 0 !important; }
[data-testid="stCaptionContainer"] { color: #6b6862; }
/* Indicadores: etiqueta discreta, cifra marcada */
[data-testid="stMetric"] { background: #ffffff; }
[data-testid="stMetricLabel"] p { font-size: 0.8rem; color: #6b6862; text-transform: uppercase;
                                  letter-spacing: 0.04em; }
/* Renglones de las tablas hechas a mano (crédito, por revisar) */
[class*="st-key-fila_"] { border-bottom: 1px solid #ecebe8; padding: 0.35rem 0; }
[class*="st-key-encabezado_"] { border-bottom: 1px solid #d9d6d1; padding-bottom: 0.2rem; }
[class*="st-key-encabezado_"] p { font-size: 0.78rem; color: #6b6862; text-transform: uppercase;
                                  letter-spacing: 0.04em; font-weight: 600; }
/* Caja: tarjetas de producto sin barra de desplazamiento interna */
[class*="st-key-tarjeta_"] { overflow: hidden !important; }
/* Caja: el total del ticket */
.total-ticket { font-size: 2.1rem; font-weight: 700; letter-spacing: -0.02em; line-height: 1.1; }
.total-etiqueta { font-size: 0.8rem; color: #6b6862; text-transform: uppercase; letter-spacing: 0.04em; }
/* En celular las columnas se apilan: el ticket va primero para ver el total sin bajar */
@media (max-width: 640px) {
  [data-testid="stColumn"]:has(.st-key-caja_ticket_panel) { order: -1; }
}
</style>
"""


def estilo() -> None:
    st.html(_CSS)


def encabezado(titulo: str, detalle: str | None = None) -> None:
    st.title(titulo)
    if detalle:
        st.caption(detalle)


def aviso(clave: str) -> None:
    """Muestra el mensaje que dejó la acción anterior (sobrevive al st.rerun)."""
    if texto := st.session_state.pop(clave, None):
        st.success(md(texto), icon=":material/check_circle:")


def subpestanas(opciones: list[str], key: str) -> str:
    """Botones para cambiar de vista dentro de una página. Con key, la vista se conserva al recargar."""
    if st.session_state.get(key) not in opciones:
        st.session_state.pop(key, None)
    return st.segmented_control("Vista", opciones, default=opciones[0], required=True, key=key,
                                label_visibility="collapsed")


def encabezado_tabla(clave: str, columnas: list[str], anchos: list[float]) -> None:
    with st.container(key=f"encabezado_{clave}"):
        for col, titulo in zip(st.columns(anchos, vertical_alignment="bottom"), columnas):
            col.markdown(titulo)


def fila(clave: str, anchos: list[float]) -> list:
    """Un renglón de tabla con botones (st.dataframe no admite botones por renglón)."""
    with st.container(key=f"fila_{clave}"):
        return st.columns(anchos, vertical_alignment="center")
