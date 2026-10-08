-- =====================================================================
-- Vistas: aquí viven los cálculos (saldos, totales). La app solo lee.
-- security_invoker = true -> Postgres revisa los permisos de QUIEN consulta,
-- no del dueño de la vista. Sin esto, una vista sería un hoyo para
-- saltarse los permisos de las tablas.
-- =====================================================================

-- Encargos con lo pagado y el saldo (mostrador la necesita para cobrar al entregar)
CREATE VIEW v_encargos WITH (security_invoker = true) AS
SELECT e.id,
       e.fecha_pedido,
       e.fecha_entrega,
       e.cliente_id,
       c.nombre                       AS cliente,
       c.telefono,
       e.descripcion,
       e.total,
       coalesce(p.pagado, 0)          AS pagado,
       e.total - coalesce(p.pagado, 0) AS saldo,
       e.estado,
       e.requiere_revision,
       e.nota_revision
FROM encargos e
JOIN clientes c ON c.id = e.cliente_id
LEFT JOIN (
    SELECT encargo_id, sum(monto) AS pagado
    FROM pagos_encargo
    GROUP BY encargo_id
) p ON p.encargo_id = e.id;

-- Lo que Toño tiene que hornear para mañana
CREATE VIEW v_manana_sale WITH (security_invoker = true) AS
SELECT *
FROM v_encargos
WHERE fecha_entrega = current_date + 1
  AND estado IN ('pendiente', 'listo');

-- Lo que capturó la persona en sesión hoy, sin precios ni totales.
-- Esta vista NO es security_invoker a propósito: mostrador no puede leer
-- ventas/venta_lineas directamente; solo esta ventana filtrada.
-- app.usuario_id lo fija la app al inicio de cada transacción.
CREATE VIEW v_mis_capturas_hoy AS
SELECT vl.id,
       v.creado_en,
       p.nombre AS producto,
       vl.cantidad
FROM venta_lineas vl
JOIN ventas v    ON v.id = vl.venta_id
JOIN productos p ON p.id = vl.producto_id
WHERE v.fecha = current_date
  AND v.capturado_por = nullif(current_setting('app.usuario_id', true), '')::int;

-- ---------------------------------------------------------------------
-- Solo dueña
-- ---------------------------------------------------------------------

-- Cuánto debe cada cliente de crédito y cuánto ya está vencido.
-- Los abonos se aplican a lo más viejo primero, así que:
--   vencido = (saldo inicial + entregas ya vencidas) - abonos, sin pasar del saldo total.
CREATE VIEW v_saldos_credito WITH (security_invoker = true) AS
WITH ent AS (
    SELECT e.cliente_id,
           sum(e.monto) AS entregado,
           sum(e.monto) FILTER (WHERE e.fecha + c.dias_credito <= current_date) AS entregado_vencido,
           max(e.fecha) AS ultima_entrega
    FROM entregas_credito e
    JOIN clientes c ON c.id = e.cliente_id
    GROUP BY e.cliente_id
), ab AS (
    SELECT cliente_id, sum(monto) AS abonado, max(fecha) AS ultimo_abono
    FROM abonos_credito
    GROUP BY cliente_id
), base AS (
    SELECT c.id AS cliente_id,
           c.nombre,
           c.telefono,
           c.dias_credito,
           c.saldo_inicial,
           c.saldo_inicial_nota,
           coalesce(ent.entregado, 0)         AS entregado,
           coalesce(ab.abonado, 0)            AS abonado,
           coalesce(ent.entregado_vencido, 0) AS entregado_vencido,
           ent.ultima_entrega,
           ab.ultimo_abono
    FROM clientes c
    LEFT JOIN ent ON ent.cliente_id = c.id
    LEFT JOIN ab  ON ab.cliente_id  = c.id
    WHERE c.es_credito
)
SELECT cliente_id, nombre, telefono, dias_credito,
       saldo_inicial, saldo_inicial_nota,
       entregado, abonado,
       saldo_inicial + entregado - abonado AS saldo,
       greatest(0, least(saldo_inicial + entregado - abonado,
                         saldo_inicial + entregado_vencido - abonado)) AS saldo_vencido,
       ultima_entrega, ultimo_abono
FROM base;

-- Venta de mostrador por día
CREATE VIEW v_ventas_diarias WITH (security_invoker = true) AS
SELECT v.fecha,
       sum(vl.subtotal)          AS total,
       sum(vl.cantidad)          AS piezas,
       count(*)                  AS lineas,
       bool_or(v.captura_incompleta) AS captura_incompleta
FROM ventas v
JOIN venta_lineas vl ON vl.venta_id = v.id
GROUP BY v.fecha;

-- Venta de mostrador por producto y mes (qué se vende más)
CREATE VIEW v_ventas_producto_mes WITH (security_invoker = true) AS
SELECT date_trunc('month', v.fecha)::date AS mes,
       p.id   AS producto_id,
       p.nombre AS producto,
       p.categoria,
       sum(vl.cantidad) AS cantidad,
       sum(vl.subtotal) AS total
FROM ventas v
JOIN venta_lineas vl ON vl.venta_id = v.id
JOIN productos p     ON p.id = vl.producto_id
GROUP BY 1, 2, 3, 4;

-- Insumos en o por debajo del mínimo
CREATE VIEW v_insumos_por_pedir WITH (security_invoker = true) AS
SELECT i.id, i.nombre, i.unidad, i.cantidad, i.minimo, pr.nombre AS proveedor
FROM insumos i
LEFT JOIN proveedores pr ON pr.id = i.proveedor_id
WHERE i.cantidad IS NOT NULL
  AND i.minimo IS NOT NULL
  AND i.cantidad <= i.minimo;
