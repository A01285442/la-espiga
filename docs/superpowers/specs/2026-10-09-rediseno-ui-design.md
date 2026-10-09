# Rediseño de la interfaz (branch `ui-rework`)

Aprobado en la conversación del 8–9 de octubre de 2026. Objetivo: que la app se vea profesional y
sea más útil en el mostrador, sin tocar la base de datos ni los permisos.

## Restricciones

- Streamlit 1.65 (antes 1.45). Sin otros frameworks ni librerías de componentes.
- **Sin emojis** en ningún texto. Íconos de Material (`:material/...:`) solo en menú y botones.
- Tema neutro: fondo blanco, texto gris oscuro, un acento café apagado, fuente Inter, bordes finos.
- Permisos sin cambios: mostrador sigue sin ver crédito, compras ni totales (32 pruebas SQL igual).
- Se trabaja en un worktree (`../la-espiga-ui`) y se prueba en `localhost:8502`: la app pública
  lee el código de `la-espiga/` y no debe mostrar trabajo a medias.

## Navegación

- Menú arriba (`st.navigation(position="top")`); nombre y "Cerrar sesión" a la derecha. Sin sidebar.
- Mostrador: Caja · Encargos. Dueña: Resumen · Crédito · Encargos · Caja · Compras.
- Se elimina la página "Mañana sale" (`/manana`); su contenido pasa a Encargos → Urgentes.
- Subpestañas con `st.segmented_control(required=True, key=...)`: conservan la vista entre recargas.

## Pantallas

**Caja** (`paginas/ventas.py`): catálogo a la izquierda (buscador + subpestañas Todo / Pan dulce /
Pan salado / Pasteles / Galletas; tarjeta por producto con precio y "Agregar"; los de kg piden la
cantidad), ticket a la derecha (renglones con − / +, quitar, total grande, "Cobrar", "Vaciar",
nota e "incompleta" en un popover). Cada cobro es una venta (un ticket por persona). Debajo,
"Tus tickets de hoy" desde `v_mis_capturas_hoy`, sin precios.

**Encargos**: subpestañas Urgentes (atrasados, hoy, mañana; lista para Toño por WhatsApp y
descarga) · Por entregar (tabla con selección y detalle en recuadro) · Nuevo · Historial.

**Crédito**: 3 indicadores; barra con "Ver cuenta de" + botones Nuevo cliente / Editar cliente
(diálogos); tabla de todos los clientes (vencidos primero) con botón Recordar por renglón.
Recordar abre un diálogo con lo que debe según el sistema, monto y mensaje editables y botón a
WhatsApp. **Ajustar el monto solo cambia el mensaje**, no el saldo. Debajo, la cuenta del cliente.

**Compras**: subpestañas Gasto del mes · Por revisar (duplicados + facturas por pedir) ·
Registrar ticket · Bodega.

**Resumen**: mismo contenido, estilo nuevo.

## Código

- `lib/ui.py`: CSS, encabezado de página, aviso tras recarga, subpestañas, etiquetas de estado.
- `lib/formato.cuando()` deja de devolver emojis.

## Pruebas

- Se actualizan las 26 pruebas de la app (claves de subpestañas, Caja, Urgentes en vez de Mañana).
- Nuevas: Caja (agregar, total, cobrar, limpiar ticket), diálogo Recordar, Urgentes, `/manana` ya
  no existe en ningún menú, mostrador sin acceso a páginas de dueña.
- Revisión visual en escritorio y celular con capturas antes de unir a `main`.
