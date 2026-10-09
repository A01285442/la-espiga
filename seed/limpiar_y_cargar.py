"""Limpia el Excel de La Espiga Dorada y lo carga a Postgres.

Uso (desde la carpeta la-espiga, con `docker compose up -d` corriendo):
    python seed/limpiar_y_cargar.py "ruta/Panaderia_La_Espiga_Control.xlsx"
    python seed/limpiar_y_cargar.py "ruta/...xlsx" --nube     # a Neon (NEON_ADMIN_URL en .env)

Es repetible: borra los datos de negocio y los vuelve a cargar en una sola
transacción. Si algo no se reconoce (un cliente o producto nuevo), truena en
vez de adivinar. Al final escribe docs/reporte_limpieza.md con cada decisión.

Principio: no se inventa dinero. Solo se registran pagos que el Excel
afirma; lo que no cuadra se marca para revisar con Carmen.
"""

import re
import secrets
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import openpyxl
import psycopg

RAIZ = Path(__file__).resolve().parent.parent
ANIO = 2026
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
         "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}

reporte: dict[str, list[str]] = defaultdict(list)


# ---------------------------------------------------------------------
# Normalización (debe coincidir con normalizar() en 01_schema.sql)
# ---------------------------------------------------------------------
def normalizar(texto: str) -> str:
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", sin_acentos.strip()).lower()


def a_fecha(valor) -> date | None:
    """datetime, '01/sep', '17/09', '23 de sep' -> date."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    m = re.fullmatch(r"(\d{1,2})\s*(?:/|de)\s*([a-z]+|\d{1,2})", normalizar(valor))
    if not m:
        return None
    dia, mes = m.groups()
    mes = int(mes) if mes.isdigit() else MESES[mes[:3]]
    return date(ANIO, mes, int(dia))


def a_dinero(valor) -> float | None:
    """192, '$16', '520 pesos' -> número. Fórmulas ('=C5*D5') -> None."""
    if valor is None or (isinstance(valor, str) and valor.startswith("=")):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    limpio = re.sub(r"[^\d.]", "", valor)
    return float(limpio) if limpio else None


def a_telefono(valor) -> str | None:
    digitos = re.sub(r"\D", "", str(valor or ""))
    return digitos if len(digitos) == 10 else None


# ---------------------------------------------------------------------
# Catálogos: decisiones de unificación, explícitas y revisables.
# canónico -> (atributos, [formas en que aparece en el Excel])
# ---------------------------------------------------------------------
PRODUCTOS = {
    "Bolillo":                 ("pan_salado", "pieza", ["bolillo"]),
    "Telera":                  ("pan_salado", "pieza", ["telera"]),
    "Concha vainilla":         ("pan_dulce", "pieza", ["concha vainilla"]),
    "Concha chocolate":        ("pan_dulce", "pieza", ["concha chocolate"]),
    # "Concha" / "CONCHAS" sin sabor: no se puede saber cuál era. Se guarda aparte
    # y se desactiva para que en la app solo se capture con sabor.
    "Concha (sabor no anotado)": ("pan_dulce", "pieza", ["concha", "conchas"]),
    "Cuernito":                ("pan_dulce", "pieza", ["cuernito", "cuerno"]),
    "Dona azúcar":             ("pan_dulce", "pieza", ["dona azucar"]),
    "Dona chocolate":          ("pan_dulce", "pieza", ["dona chocolate"]),
    "Empanada de piña":        ("pan_dulce", "pieza", ["empanada de pina", "empanada pina"]),
    "Oreja":                   ("pan_dulce", "pieza", ["oreja"]),
    "Polvorón":                ("pan_dulce", "pieza", ["polvoron"]),
    "Pan de muerto":           ("pan_dulce", "pieza", ["pan de muerto"]),
    "Rebanada de pastel":      ("pasteles", "pieza", ["rebanada pastel"]),
    "Pastel 3 leches chico":   ("pasteles", "pieza", ["pastel 3 leches chico"]),
    "Galletas surtidas":       ("galletas", "kg", ["galletas (kilo)", "galleta surtida kg"]),
}
PRODUCTOS_INACTIVOS = {"Concha (sabor no anotado)"}

# (teléfono —se toma del Excel—, es_crédito, días de crédito, saldo inicial, nota del saldo, notas, alias)
CLIENTES = {
    "Abarrotes Don Chuy": (None, True, 7, 2400,
        "Saldo de agosto aproximado ('debe como 2,400'). Por confirmar con Don Chuy.",
        None, ["don chuy", "abarrotes don chuy"]),
    "Cafetería El Portal": (None, True, 7, 0, None, None,
        ["cafeteria el portal", "el portal"]),
    "Restaurante La Fogata": (None, True, 15, 0, None,
        "Paga a 15 días aunque se le cobre los viernes.",
        ["rest. la fogata", "restaurante la fogata", "la fogata"]),
    "Escuela Benito Juárez": (None, True, 7, 0, None, None,
        ["escuela benito juarez", "escuela b. juarez", "la escuela"]),
    "Oxxo Mitras (Sr. Beto)": (None, True, 7, 0, None, None,
        ["oxxo mitras (senor beto)", "beto oxxo"]),
    "Tienda Lupita": (None, True, 7, 0, None,
        "En el Excel también aparece como 'tienda de la esquina (Lupita)'.",
        ["tienda lupita", "tienda de la esquina (lupita)"]),
    # Particulares (encargos de pasteles)
    "Jorge Salinas":   (None, False, None, 0, None, None, ["jorge salinas"]),
    "Mariana López":   (None, False, None, 0, None, None, ["mariana lopez"]),
    "Fernanda Garza":  (None, False, None, 0, None, None, ["fernanda garza"]),
    "Paty (vecina)":   (None, False, None, 0, None, None, ["paty (vecina)"]),
    "Ana Sofía":       (None, False, None, 0, None, None, ["ana sofia"]),
    "Carlos Treviño":  (None, False, None, 0, None, None, ["carlos trevino"]),
    "Lic. Ramírez":    (None, False, None, 0, None, "Sin teléfono en el Excel.", ["lic. ramirez"]),
    "Sra. Georgina":   (None, False, None, 0, None, None, ["sra. georgina"]),
}

PROVEEDORES = {
    "Harinera del Norte": ["harinera del norte (proveedor)", "harinera del norte"],
    "Costco": ["costco"],
    "HEB": ["heb"],
    "Walmart": ["walmart"],
    "Mercado Juárez": ["mercado juarez", "mercado", "mercado / heb"],
    "Gas Monterrey": ["gas monterrey"],
}


def indice_alias(catalogo: dict) -> dict[str, str]:
    indice = {}
    for canonico, datos in catalogo.items():
        for alias in datos[-1]:
            indice[normalizar(alias)] = canonico
        indice[normalizar(canonico)] = canonico
    return indice


IDX_PRODUCTO = indice_alias(PRODUCTOS)
IDX_CLIENTE = indice_alias(CLIENTES)
IDX_PROVEEDOR = {normalizar(a): c for c, aliases in PROVEEDORES.items() for a in aliases}


def buscar(indice: dict, texto: str, que: str, fila: str) -> str:
    try:
        return indice[normalizar(texto)]
    except KeyError:
        sys.exit(f"ERROR: {que} no reconocido '{texto}' ({fila}). Agrégalo al catálogo del script.")


def filas(ws, desde: int):
    for n, fila in enumerate(ws.iter_rows(min_row=desde, values_only=True), start=desde):
        if any(v is not None for v in fila):
            yield n, fila


# ---------------------------------------------------------------------
# Lectura y limpieza por hoja
# ---------------------------------------------------------------------
def leer_ventas(ws):
    lineas, dias_incompletos, ultima_fecha = [], set(), None
    variantes, recalculados, inconsistentes, texto_fecha = Counter(), 0, 0, 0
    for n, (f, prod, cant, precio, total, *_) in filas(ws, 4):
        if prod and str(prod).startswith("(se fue la luz"):
            dias_incompletos.add(ultima_fecha)
            continue
        if cant is None:          # fila del TOTAL MES u otra nota
            continue
        fecha = a_fecha(f)
        if isinstance(f, str):
            texto_fecha += 1
        canon = buscar(IDX_PRODUCTO, prod, "producto", f"Ventas!B{n}")
        variantes[(canon, str(prod).strip())] += 1
        p = a_dinero(precio)
        t = a_dinero(total)
        if t is None:
            recalculados += 1
        elif abs(t - cant * p) > 0.01:
            inconsistentes += 1
            reporte["ventas"].append(f"Fila {n}: total escrito {t} ≠ {cant}×{p}; se usa cantidad×precio.")
        lineas.append((fecha, canon, cant, p))
        ultima_fecha = fecha

    precios = defaultdict(Counter)
    for _, canon, _, p in lineas:
        precios[canon][p] += 1

    r = reporte["ventas"]
    r.insert(0, f"{len(lineas)} líneas de venta en {len({l[0] for l in lineas})} días.")
    r.insert(1, f"{texto_fecha} fechas escritas como texto ('01/sep') convertidas a fecha.")
    r.insert(2, f"{recalculados} totales vacíos o con fórmula: el total se calcula siempre como cantidad×precio "
                f"(la base lo hace sola con una columna calculada). {inconsistentes} totales escritos no cuadraban.")
    r.insert(3, f"{len({v for _, v in variantes})} nombres de producto distintos unificados en {len(precios)} productos: "
                + "; ".join(f"{c} ← {', '.join(sorted({v for cc, v in variantes if cc == c}))}"
                            for c in sorted(precios) if len({v for cc, v in variantes if cc == c}) > 1) + ".")
    r.insert(4, "'Concha' y 'CONCHAS' sin sabor se guardan como 'Concha (sabor no anotado)' y ese producto "
                "queda desactivado: de aquí en adelante solo se captura vainilla o chocolate.")
    r.insert(5, "Días con '(se fue la luz, no se apuntó todo)' marcados como captura incompleta: "
                + ", ".join(d.strftime("%d/%m") for d in sorted(dias_incompletos))
                + " (la nota aparece después de las ventas de ese día).")
    return lineas, dias_incompletos, {c: cnt.most_common(1)[0][0] for c, cnt in precios.items()}


def leer_encargos(ws):
    encargos = []
    telefonos = defaultdict(set)
    precio_por_descripcion = {}
    crudos = list(filas(ws, 3))
    for _, fila in crudos:
        if fila[6] is not None:
            precio_por_descripcion[normalizar(fila[4])] = a_dinero(fila[6])

    for n, fila in crudos:
        f_ped, f_ent, cliente, tel, desc, anticipo, total, pagado = fila[:8]
        if cliente is None:       # nota al pie
            if f_ped:
                reporte["encargos"].append(f"Nota al pie no importada: «{f_ped}». Pedir a Lupita la libreta de agosto.")
            continue
        canon = buscar(IDX_CLIENTE, cliente, "cliente", f"Encargos!C{n}")
        revision = []
        total_n = a_dinero(total)
        if total_n is None:
            total_n = precio_por_descripcion[normalizar(desc)]
            revision.append(f"El Excel no tenía total; se usó ${total_n:,.0f}, el precio de otros '{desc}'.")
        anticipo_n = a_dinero(anticipo) or 0
        estado_txt = normalizar(pagado or "")
        liquidacion, metodo = 0, "sin_dato"

        if estado_txt in ("si", "pago en efectivo", "transferencia"):
            liquidacion = total_n - anticipo_n
            metodo = {"pago en efectivo": "efectivo", "transferencia": "transferencia"}.get(estado_txt, "sin_dato")
        elif m := re.fullmatch(r"falta (\d+)", estado_txt):
            falta = float(m.group(1))
            if abs((total_n - anticipo_n) - falta) > 0.01:
                revision.append(
                    f"El Excel decía '{pagado}', pero total ${total_n:,.0f} − anticipo ${anticipo_n:,.0f} "
                    f"= ${total_n - anticipo_n:,.0f}. Se respetan los números; confirmar con Carmen.")
        # 'no', 'pendiente', 'falta el resto': solo el anticipo, el resto queda como saldo.

        if telefono := a_telefono(tel):
            telefonos[canon].add(telefono)

        encargos.append(dict(
            fila=n, cliente=canon, fecha_pedido=a_fecha(f_ped), fecha_entrega=a_fecha(f_ent),
            descripcion=str(desc).strip(), total=total_n, anticipo=anticipo_n,
            liquidacion=liquidacion, metodo=metodo, texto_pagado=pagado,
            revision=" ".join(revision) or None))

    r = reporte["encargos"]
    r.insert(0, f"{len(encargos)} encargos importados.")
    r.insert(1, "La columna 'Pagado?' (texto libre) se convirtió en pagos: el anticipo es un pago; "
                "'SI', 'pagó en efectivo' y 'transferencia' significan que se liquidó el resto el día de entrega; "
                "'NO', 'pendiente' y 'falta el resto' dejan el saldo pendiente.")
    r.insert(2, "Todos los encargos tienen fecha de entrega anterior a hoy: se marcan como entregados. "
                "Si el saldo no es cero, es dinero que el cliente quedó debiendo.")
    for e in encargos:
        if e["revision"]:
            r.append(f"Fila {e['fila']} ({e['cliente']}, {e['descripcion']}): {e['revision']}")

    # Teléfono por cliente: se guarda solo con 10 dígitos ('81-2233-4455' -> '8122334455').
    tel_por_cliente = {}
    for cliente, tels in telefonos.items():
        if len(tels) > 1:
            r.append(f"{cliente} tiene varios teléfonos: {', '.join(sorted(tels))}; se usa el primero.")
        tel_por_cliente[cliente] = sorted(tels)[0]
    compartidos = defaultdict(list)
    for cliente, tel in tel_por_cliente.items():
        compartidos[tel].append(cliente)
    for tel, clientes in compartidos.items():
        if len(clientes) > 1:
            r.append(f"El teléfono {tel} aparece en clientes distintos ({' y '.join(clientes)}). "
                     "Se dejan como clientes separados; preguntar si es la misma familia o un error de captura.")
    r.insert(3, "Teléfonos normalizados a 10 dígitos (venían como '81-2233-4455', '81 9988 7766', etc.).")
    return encargos, tel_por_cliente


def leer_mayoristas(ws):
    entregas = []
    nombres = Counter()
    for n, fila in filas(ws, 3):
        cliente, f, que, monto, pagado, f_pago = fila[:6]
        if monto is None:         # notas al pie
            if cliente:
                reporte["mayoristas"].append(f"Nota al pie: «{cliente}».")
            continue
        canon = buscar(IDX_CLIENTE, cliente, "cliente", f"Mayoristas!A{n}")
        nombres[(canon, str(cliente).strip())] += 1
        fecha = a_fecha(f)
        monto_n = a_dinero(monto)
        estado = normalizar(pagado or "")
        abono, fecha_abono, nota = 0, None, None
        if estado.startswith("si"):
            abono = monto_n
        elif m := re.fullmatch(r"parcial (\d+)", estado):
            abono = float(m.group(1))
        if abono:
            fecha_abono = a_fecha(f_pago) if isinstance(f_pago, datetime) else None
            if fecha_abono is None and normalizar(f_pago or "") == "oct":
                fecha_abono = date(ANIO, 10, 1)
                nota = "El Excel solo dice 'oct'; día exacto desconocido."
            elif fecha_abono is None:
                fecha_abono = fecha
                nota = "Sin fecha de pago en el Excel; se usó la fecha de entrega."
        entregas.append(dict(
            fila=n, cliente=canon, fecha=fecha, descripcion=str(que).strip(), monto=monto_n,
            abono=abono, fecha_abono=fecha_abono,
            metodo="efectivo" if "efectivo" in estado else "sin_dato", nota=nota))

    r = reporte["mayoristas"]
    r.insert(0, f"{len(entregas)} entregas a crédito importadas.")
    r.insert(1, f"{len({v for _, v in nombres})} formas de escribir a los clientes unificadas en "
                f"{len({c for c, _ in nombres})} clientes: "
                + "; ".join(f"{c} ← {', '.join(sorted({v for cc, v in nombres if cc == c}))}"
                            for c in sorted({c for c, _ in nombres})) + ".")
    r.insert(2, "La columna 'Saldo' del Excel se ignora: tenía fórmulas aun en filas pagadas. "
                "El saldo lo calcula la base: saldo inicial + entregas − abonos.")
    r.insert(3, "'si' y 'si (efectivo)' = abono por el monto completo; 'parcial 300' = abono de $300; "
                "vacío o 'no' = sin pago.")
    r.insert(4, "Don Chuy arranca con saldo inicial de $2,400 (agosto), marcado 'por confirmar'. "
                "La Fogata queda con 15 días de crédito; los demás con 7 (cobro semanal).")
    return entregas


def leer_compras(ws):
    compras = []
    for n, fila in filas(ws, 3):
        f, donde, total, que, factura = fila[:5]
        if f is None or not isinstance(total, (int, float)):
            if f and isinstance(f, str):
                reporte["compras"].append(f"Nota al pie: «{f}».")
            continue
        estado = {"si": "facturada", "pedir": "por_pedir", "no": "sin_factura"}.get(
            normalizar(factura or ""), "sin_dato")
        compras.append(dict(
            fila=n, fecha=a_fecha(f), proveedor=buscar(IDX_PROVEEDOR, donde, "proveedor", f"Compras!B{n}"),
            total=float(total), descripcion=str(que).strip(), factura=estado,
            personal="cosas de la casa" in normalizar(que), duplicado=False))

    # Posible duplicado: mismo proveedor, a 1 día o menos, monto ±10%.
    for a in compras:
        for b in compras:
            if (a is not b and a["proveedor"] == b["proveedor"]
                    and abs((a["fecha"] - b["fecha"]).days) <= 1
                    and abs(a["total"] - b["total"]) <= 0.10 * max(a["total"], b["total"])):
                a["duplicado"] = True
    r = reporte["compras"]
    dup = [c for c in compras if c["duplicado"]]
    r.insert(0, f"{len(compras)} tickets importados, total ${sum(c['total'] for c in compras):,.0f}.")
    r.insert(1, f"{len(dup)} tickets marcados como posible duplicado (mismo proveedor, ≤1 día, monto ±10%). "
                "No se borran: Carmen confirma. "
                + "; ".join(f"{c['proveedor']} {c['fecha']:%d/%m} ${c['total']:,.0f}" for c in dup) + ".")
    r.insert(2, f"{sum(c['personal'] for c in compras)} tickets dicen 'cosas de la casa': marcados como "
                "'incluye gastos personales' (el contador ya advirtió que no deberían facturarse completos).")
    return compras


def leer_insumos(ws):
    insumos = []
    for n, fila in filas(ws, 3):
        nombre, unidad, cant, minimo, prov = fila[:5]
        if unidad is None:        # nota al pie
            reporte["insumos"].append(f"Nota al pie: «{nombre}». Las recetas se documentan en la fase 2.")
            continue
        nota = None
        if isinstance(cant, str):
            numero = a_dinero(cant)
            nota = f"El conteo decía '{cant}'."
            cant = numero
        insumos.append(dict(
            nombre=str(nombre).strip(), unidad=str(unidad).strip(), cantidad=cant,
            minimo=a_dinero(minimo) if minimo is not None else None,
            proveedor=IDX_PROVEEDOR.get(normalizar(prov)) if prov else None, nota=nota))
    r = reporte["insumos"]
    r.insert(0, f"{len(insumos)} insumos importados. Sin mínimo definido: "
                + ", ".join(i["nombre"] for i in insumos if i["minimo"] is None)
                + " (no generan aviso hasta que Carmen defina el mínimo).")
    return insumos


# ---------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------
def leer_env() -> dict[str, str]:
    env = {}
    for linea in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in linea and not linea.startswith("#"):
            k, v = linea.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def asegurar_passwords_demo(env: dict) -> dict[str, str]:
    """Contraseñas de los usuarios de la app; se generan una vez y quedan en .env."""
    nuevas = {}
    for clave in ("PWD_CARMEN", "PWD_LUPITA", "PWD_KARLA"):
        if clave not in env:
            nuevas[clave] = env[clave] = "Espiga-" + secrets.token_hex(3)
    if nuevas:
        with open(RAIZ / ".env", "a", encoding="utf-8", newline="\n") as f:
            f.write("".join(f"{k}={v}\n" for k, v in nuevas.items()))
    return env


def cargar(conn, ventas, dias_incompletos, precios, encargos, telefonos, entregas, compras, insumos, env):
    cur = conn.cursor()
    cur.execute("""
        TRUNCATE venta_lineas, ventas, pagos_encargo, encargos, entregas_credito, abonos_credito,
                 compras, receta_insumos, insumos, proveedores, producto_alias, productos,
                 cliente_alias, clientes
        RESTART IDENTITY CASCADE""")

    for usuario, nombre, rol, clave in (("carmen", "Carmen Rodríguez", "duena", "PWD_CARMEN"),
                                        ("lupita", "Lupita", "mostrador", "PWD_LUPITA"),
                                        ("karla", "Karla", "mostrador", "PWD_KARLA")):
        cur.execute("""
            INSERT INTO usuarios (usuario, nombre, rol, password_hash)
            VALUES (%s, %s, %s, crypt(%s, gen_salt('bf')))
            ON CONFLICT (usuario) DO UPDATE
               SET nombre = EXCLUDED.nombre, rol = EXCLUDED.rol, password_hash = EXCLUDED.password_hash""",
            (usuario, nombre, rol, env[clave]))

    ids_prod = {}
    for nombre, (cat, unidad, aliases) in PRODUCTOS.items():
        cur.execute("INSERT INTO productos (nombre, categoria, unidad, precio, activo) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (nombre, cat, unidad, precios[nombre], nombre not in PRODUCTOS_INACTIVOS))
        ids_prod[nombre] = cur.fetchone()[0]
        for alias in {normalizar(a) for a in aliases + [nombre]}:
            cur.execute("INSERT INTO producto_alias VALUES (%s, %s)", (alias, ids_prod[nombre]))

    ids_cli = {}
    for nombre, (tel, credito, dias, saldo, nota_saldo, notas, aliases) in CLIENTES.items():
        cur.execute("""INSERT INTO clientes (nombre, telefono, es_credito, dias_credito, saldo_inicial,
                                             saldo_inicial_nota, notas)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (nombre, telefonos.get(nombre, tel), credito, dias, saldo, nota_saldo, notas))
        ids_cli[nombre] = cur.fetchone()[0]
        for alias in {normalizar(a) for a in aliases + [nombre]}:
            cur.execute("INSERT INTO cliente_alias VALUES (%s, %s)", (alias, ids_cli[nombre]))

    por_dia = defaultdict(list)
    for fecha, canon, cant, precio in ventas:
        por_dia[fecha].append((canon, cant, precio))
    for fecha in sorted(por_dia):
        incompleto = fecha in dias_incompletos
        cur.execute("""INSERT INTO ventas (fecha, origen, captura_incompleta, nota)
                       VALUES (%s, 'excel', %s, %s) RETURNING id""",
                    (fecha, incompleto,
                     "Se fue la luz, no se apuntó todo." if incompleto else "Captura de cierre del Excel."))
        venta_id = cur.fetchone()[0]
        cur.executemany("INSERT INTO venta_lineas (venta_id, producto_id, cantidad, precio_unitario) "
                        "VALUES (%s, %s, %s, %s)",
                        [(venta_id, ids_prod[c], q, p) for c, q, p in por_dia[fecha]])

    for e in encargos:
        cur.execute("""INSERT INTO encargos (cliente_id, fecha_pedido, fecha_entrega, descripcion, total,
                                             estado, requiere_revision, nota_revision, origen)
                       VALUES (%s, %s, %s, %s, %s, 'entregado', %s, %s, 'excel') RETURNING id""",
                    (ids_cli[e["cliente"]], e["fecha_pedido"], e["fecha_entrega"], e["descripcion"],
                     e["total"], e["revision"] is not None, e["revision"]))
        enc_id = cur.fetchone()[0]
        if e["anticipo"]:
            cur.execute("INSERT INTO pagos_encargo (encargo_id, fecha, monto, tipo, metodo) "
                        "VALUES (%s, %s, %s, 'anticipo', 'sin_dato')",
                        (enc_id, e["fecha_pedido"], e["anticipo"]))
        if e["liquidacion"]:
            cur.execute("INSERT INTO pagos_encargo (encargo_id, fecha, monto, tipo, metodo) "
                        "VALUES (%s, %s, %s, 'liquidacion', %s)",
                        (enc_id, e["fecha_entrega"], e["liquidacion"], e["metodo"]))

    for e in entregas:
        cur.execute("""INSERT INTO entregas_credito (cliente_id, fecha, descripcion, monto, origen)
                       VALUES (%s, %s, %s, %s, 'excel')""",
                    (ids_cli[e["cliente"]], e["fecha"], e["descripcion"], e["monto"]))
        if e["abono"]:
            cur.execute("""INSERT INTO abonos_credito (cliente_id, fecha, monto, metodo, nota, origen)
                           VALUES (%s, %s, %s, %s, %s, 'excel')""",
                        (ids_cli[e["cliente"]], e["fecha_abono"], e["abono"], e["metodo"],
                         f"Pago de la entrega del {e['fecha']:%d/%m}. " + (e["nota"] or "")))

    ids_prov = {}
    for nombre in PROVEEDORES:
        cur.execute("INSERT INTO proveedores (nombre) VALUES (%s) RETURNING id", (nombre,))
        ids_prov[nombre] = cur.fetchone()[0]
    for c in compras:
        cur.execute("""INSERT INTO compras (fecha, proveedor_id, total, descripcion, estado_factura,
                                            incluye_gastos_personales, posible_duplicado, origen)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, 'excel')""",
                    (c["fecha"], ids_prov[c["proveedor"]], c["total"], c["descripcion"], c["factura"],
                     c["personal"], c["duplicado"]))
    for i in insumos:
        cur.execute("""INSERT INTO insumos (nombre, unidad, cantidad, minimo, proveedor_id, nota)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (i["nombre"], i["unidad"], i["cantidad"], i["minimo"],
                     ids_prov.get(i["proveedor"]), i["nota"]))

    # Cifras de control, calculadas por la base ya cargada
    cur.execute("SELECT sum(total), count(*) FILTER (WHERE captura_incompleta) FROM v_ventas_diarias")
    total_ventas, incompletos = cur.fetchone()
    cur.execute("SELECT sum(total), sum(saldo) FROM v_encargos")
    total_enc, saldo_enc = cur.fetchone()
    cur.execute("SELECT nombre, saldo, saldo_vencido FROM v_saldos_credito ORDER BY saldo DESC")
    saldos = cur.fetchall()
    cur.execute("SELECT sum(monto) FROM entregas_credito")
    total_cred = cur.fetchone()[0]
    cur.execute("SELECT sum(total) FROM compras")
    total_compras = cur.fetchone()[0]
    reporte["cifras"] = [
        f"Ventas de mostrador capturadas: ${total_ventas:,.0f} ({incompletos} días con captura incompleta).",
        f"Encargos: ${total_enc:,.0f} vendidos; ${saldo_enc:,.0f} sin cobrar según el Excel.",
        f"Entregas a crédito: ${total_cred:,.0f}.",
        f"Total registrado en septiembre: ${total_ventas + total_enc + total_cred:,.0f}, contra ~$180,000 "
        "que Carmen dice facturar. La diferencia es venta que nunca llegó al Excel.",
        f"Compras: ${total_compras:,.0f}.",
        "Saldo por cliente de crédito (al día de la carga): "
        + "; ".join(f"{n} ${s:,.0f} (vencido ${v:,.0f})" for n, s, v in saldos) + ".",
    ]


def escribir_reporte():
    titulos = {"cifras": "Cifras de control", "ventas": "Ventas de mostrador", "encargos": "Encargos",
               "mayoristas": "Clientes de crédito", "compras": "Compras", "insumos": "Insumos"}
    texto = ["# Reporte de limpieza del Excel", "",
             f"Generado por `seed/limpiar_y_cargar.py` el {datetime.now():%d/%m/%Y %H:%M}.", ""]
    for clave, titulo in titulos.items():
        texto += [f"## {titulo}", ""] + [f"- {l}" for l in reporte[clave]] + [""]
    destino = RAIZ / "docs" / "reporte_limpieza.md"
    destino.write_text("\n".join(texto), encoding="utf-8")
    return destino


def main():
    rutas = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(rutas) != 1:
        sys.exit(__doc__)
    wb = openpyxl.load_workbook(rutas[0])
    ventas, dias_incompletos, precios = leer_ventas(wb["Ventas"])
    encargos, telefonos = leer_encargos(wb["Encargos"])
    entregas = leer_mayoristas(wb["Mayoristas"])
    compras = leer_compras(wb["Compras"])
    insumos = leer_insumos(wb["Insumos"])

    env = asegurar_passwords_demo(leer_env())
    # NEON_ADMIN_URL (en .env) carga a la base en la nube; si no existe, a la de Docker local
    dsn = env.get("NEON_ADMIN_URL") if "--nube" in sys.argv else (
        f"host=127.0.0.1 port=5432 dbname={env['DB_NAME']} "
        f"user={env['DB_ADMIN_USER']} password={env['DB_ADMIN_PASSWORD']}")
    if not dsn:
        sys.exit("Falta NEON_ADMIN_URL en .env para cargar a la nube.")
    with psycopg.connect(dsn) as conn:   # una sola transacción: o carga todo o nada
        cargar(conn, ventas, dias_incompletos, precios, encargos, telefonos, entregas, compras, insumos, env)

    destino = escribir_reporte()
    print("\n".join(reporte["cifras"]))
    print(f"\nReporte completo: {destino}")
    print(f"Usuarios: carmen / {env['PWD_CARMEN']} (dueña) · lupita / {env['PWD_LUPITA']} · "
          f"karla / {env['PWD_KARLA']} (mostrador)")


if __name__ == "__main__":
    main()
