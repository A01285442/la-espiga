"""Genera docs/diagrama.svg (tablas y relaciones) para el documento de entrega.

    python docs/diagrama.py
"""

from pathlib import Path

ALTO_FILA, ALTO_TITULO = 12, 15

# nombre: (x, y, ancho, filas, fase2)
TABLAS = {
    "cliente_alias":    (8, 44, 104, ["alias PK", "cliente_id FK"], False),
    "clientes":         (140, 22, 122, ["id PK", "nombre (único)", "telefono 10 dígitos", "es_credito",
                                        "dias_credito", "saldo_inicial"], False),
    "encargos":         (300, 22, 132, ["id PK", "cliente_id FK", "fecha_entrega", "descripcion",
                                        "total", "estado"], False),
    "pagos_encargo":    (470, 22, 124, ["encargo_id FK", "monto", "tipo (anticipo…)", "metodo"], False),
    "abonos_credito":   (140, 138, 122, ["cliente_id FK", "fecha", "monto"], False),
    "entregas_credito": (300, 138, 132, ["cliente_id FK", "fecha", "descripcion", "monto"], False),
    "producto_alias":   (8, 232, 104, ["alias PK", "producto_id FK"], False),
    "productos":        (140, 210, 122, ["id PK", "nombre (único)", "categoria", "unidad", "precio"], False),
    "venta_lineas":     (300, 210, 132, ["venta_id FK", "producto_id FK", "cantidad",
                                         "precio_unitario (copia)", "subtotal (calculado)"], False),
    "ventas":           (470, 210, 124, ["id PK", "fecha", "capturado_por FK", "captura_incompleta"], False),
    "receta_insumos":   (140, 312, 122, ["producto_id FK", "insumo_id FK", "cantidad"], True),
    "insumos":          (300, 312, 132, ["id PK", "cantidad", "minimo", "proveedor_id FK"], False),
    "proveedores":      (470, 312, 124, ["id PK", "nombre"], False),
    "compras":          (622, 312, 96, ["proveedor_id FK", "total", "estado_factura",
                                         "posible_duplicado"], False),
}

# (desde, hacia, lado_desde, lado_hacia): "1" en la tabla del PK, "N" en la del FK
RELACIONES = [
    ("cliente_alias", "clientes", "N", "1"),
    ("clientes", "encargos", "1", "N"),
    ("encargos", "pagos_encargo", "1", "N"),
    ("clientes", "abonos_credito", "1", "N"),
    ("clientes", "entregas_credito", "1", "N"),
    ("producto_alias", "productos", "N", "1"),
    ("productos", "venta_lineas", "1", "N"),
    ("venta_lineas", "ventas", "N", "1"),
    ("productos", "receta_insumos", "1", "N"),
    ("receta_insumos", "insumos", "N", "1"),
    ("insumos", "proveedores", "N", "1"),
    ("proveedores", "compras", "1", "N"),
]


def caja(nombre):
    x, y, w, filas, _ = TABLAS[nombre]
    return x, y, w, ALTO_TITULO + ALTO_FILA * len(filas) + 3


def punto_de_union(a, b):
    """Punto en el borde de la caja a, en dirección a la caja b (horizontal o vertical)."""
    ax, ay, aw, ah = caja(a)
    bx, by, bw, bh = caja(b)
    if bx >= ax + aw:                        # b a la derecha
        return ax + aw, ay + min(ah, bh) / 2 + 4
    if bx + bw <= ax:                        # b a la izquierda
        return ax, by + min(ah, bh) / 2 + 4
    if by >= ay + ah:                        # b abajo
        return ax + aw / 2, ay + ah
    return ax + aw / 2, ay                   # b arriba


def svg() -> str:
    partes = []
    for a, b, la, lb in RELACIONES:
        x1, y1 = punto_de_union(a, b)
        x2, y2 = punto_de_union(b, a)
        if a == "clientes" and b == "entregas_credito":     # sale de la esquina inferior derecha
            x1, y1 = 262, 100
            x2, y2 = 300, 160
        if y1 != y2 and x1 != x2 and not (a == "clientes" and b == "entregas_credito"):
            y2 = y1                           # mismas filas: línea recta
        partes.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="rel"/>')
        dx = 1 if x2 > x1 else -1 if x2 < x1 else 0
        dy = 1 if y2 > y1 else -1 if y2 < y1 else 0
        partes.append(f'<text x="{x1 + dx * 5 + (2 if dx == 0 else 0)}" y="{y1 + dy * 9 - (2 if dy == 0 else 0)}" '
                      f'class="card">{la}</text>')
        partes.append(f'<text x="{x2 - dx * 9 + (2 if dx == 0 else 0)}" y="{y2 - dy * 3 - (2 if dy == 0 else 0)}" '
                      f'class="card">{lb}</text>')
    for nombre, (x, y, w, filas, fase2) in TABLAS.items():
        _, _, _, h = caja(nombre)
        clase = "tabla fase2" if fase2 else "tabla"
        partes.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" class="{clase}"/>')
        partes.append(f'<rect x="{x}" y="{y}" width="{w}" height="{ALTO_TITULO}" rx="3" class="titulo-fondo"/>')
        partes.append(f'<text x="{x + 5}" y="{y + 11}" class="titulo">{nombre}{" (fase 2)" if fase2 else ""}</text>')
        for i, fila in enumerate(filas):
            clave = " clave" if fila.endswith((" PK", " FK")) else ""
            partes.append(f'<text x="{x + 5}" y="{y + ALTO_TITULO + 10 + i * ALTO_FILA}" class="campo{clave}">'
                          f'{fila}</text>')
    partes.append('<text x="612" y="34" class="nota">usuarios se relaciona con</text>')
    partes.append('<text x="612" y="45" class="nota">todo vía capturado_por /</text>')
    partes.append('<text x="612" y="56" class="nota">registrado_por / creado_por</text>')
    partes.append('<text x="612" y="76" class="nota">1 — N: un cliente tiene</text>')
    partes.append('<text x="612" y="87" class="nota">muchos encargos, etc.</text>')
    partes.append('<text x="8" y="12" class="grupo">CLIENTES: ENCARGOS Y CRÉDITO</text>')
    partes.append('<text x="8" y="200" class="grupo">MOSTRADOR, COMPRAS E INSUMOS</text>')
    estilo = """<style>
      .tabla { fill: #fff; stroke: #9a4f12; stroke-width: 1; }
      .fase2 { stroke-dasharray: 4 2; }
      .titulo-fondo { fill: #f3e6d8; stroke: #9a4f12; stroke-width: 1; }
      .titulo { font: 600 9.5px 'Segoe UI', sans-serif; fill: #5a2d08; }
      .campo { font: 8.5px 'Segoe UI', sans-serif; fill: #333; }
      .clave { fill: #9a4f12; font-weight: 600; }
      .rel { stroke: #888; stroke-width: 1; }
      .card { font: 600 8px 'Segoe UI', sans-serif; fill: #9a4f12; }
      .nota { font: italic 8px 'Segoe UI', sans-serif; fill: #666; }
      .grupo { font: 600 8px 'Segoe UI', sans-serif; fill: #888; letter-spacing: .5px; }
    </style>"""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 378" width="720" height="378" '
            f'role="img" aria-label="Diagrama de tablas y relaciones">{estilo}{"".join(partes)}</svg>')


if __name__ == "__main__":
    destino = Path(__file__).with_name("diagrama.svg")
    destino.write_text(svg(), encoding="utf-8")
    print(f"Escrito {destino}")
