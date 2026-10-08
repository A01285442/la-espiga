-- Pruebas de permisos por rol. Correr como admin:
--   docker compose exec -T db psql -U espiga_admin -d espiga -v ON_ERROR_STOP=1 -f - < db/pruebas/permisos.sql
-- Todo corre dentro de una transacción que se deshace al final: no deja datos.

BEGIN;

-- Debe fallar con "permission denied"; si la consulta funciona, la prueba truena.
CREATE FUNCTION pg_temp.debe_negar(rol text, consulta text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    EXECUTE format('SET LOCAL ROLE %I', rol);
    BEGIN
        EXECUTE consulta;
        RAISE EXCEPTION 'FALLA: % pudo ejecutar: %', rol, consulta;
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'ok  % NO puede: %', rol, consulta;
    END;
    RESET ROLE;
END $$;

CREATE FUNCTION pg_temp.debe_permitir(rol text, consulta text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    EXECUTE format('SET LOCAL ROLE %I', rol);
    EXECUTE consulta;
    RAISE NOTICE 'ok  % puede: %', rol, consulta;
    RESET ROLE;
END $$;

-- Datos mínimos
INSERT INTO usuarios (usuario, nombre, rol, password_hash)
VALUES ('prueba', 'Prueba', 'mostrador', crypt('secreta', gen_salt('bf')));
INSERT INTO clientes (nombre, es_credito, dias_credito) VALUES ('Cliente Prueba', true, 7);
INSERT INTO productos (nombre, categoria, precio) VALUES ('Concha prueba', 'pan_dulce', 18);

-- ---- app_login: solo autenticar ----
SELECT pg_temp.debe_permitir('app_login', $q$SELECT * FROM autenticar('prueba', 'secreta')$q$);
SELECT pg_temp.debe_negar('app_login', 'SELECT * FROM usuarios');
SELECT pg_temp.debe_negar('app_login', 'SELECT * FROM productos');

-- ---- app_mostrador: lo que SÍ puede ----
SELECT pg_temp.debe_permitir('app_mostrador', 'SELECT * FROM v_encargos');
SELECT pg_temp.debe_permitir('app_mostrador', 'SELECT * FROM v_manana_sale');
SELECT pg_temp.debe_permitir('app_mostrador', 'SELECT id, nombre, telefono FROM clientes');
SELECT pg_temp.debe_permitir('app_mostrador',
    $q$WITH v AS (INSERT INTO ventas (capturado_por) VALUES (1) RETURNING id)
       INSERT INTO venta_lineas (venta_id, producto_id, cantidad)
       SELECT v.id, (SELECT id FROM productos WHERE nombre = 'Concha prueba'), 3 FROM v$q$);
SELECT pg_temp.debe_permitir('app_mostrador', 'SELECT * FROM v_mis_capturas_hoy');

-- ---- app_mostrador: lo que NO puede ----
SELECT pg_temp.debe_negar('app_mostrador', 'SELECT * FROM compras');
SELECT pg_temp.debe_negar('app_mostrador', 'SELECT * FROM insumos');
SELECT pg_temp.debe_negar('app_mostrador', 'SELECT * FROM entregas_credito');
SELECT pg_temp.debe_negar('app_mostrador', 'SELECT * FROM abonos_credito');
SELECT pg_temp.debe_negar('app_mostrador', 'SELECT * FROM v_saldos_credito');
SELECT pg_temp.debe_negar('app_mostrador', 'SELECT * FROM v_ventas_diarias');
SELECT pg_temp.debe_negar('app_mostrador', 'SELECT * FROM v_ventas_producto_mes');
SELECT pg_temp.debe_negar('app_mostrador', 'SELECT * FROM venta_lineas');
SELECT pg_temp.debe_negar('app_mostrador', 'SELECT fecha FROM ventas');
SELECT pg_temp.debe_negar('app_mostrador', 'SELECT saldo_inicial FROM clientes');
SELECT pg_temp.debe_negar('app_mostrador', 'SELECT * FROM usuarios');
SELECT pg_temp.debe_negar('app_mostrador', 'DELETE FROM encargos');
SELECT pg_temp.debe_negar('app_mostrador', 'UPDATE encargos SET total = 1');
SELECT pg_temp.debe_negar('app_mostrador', 'UPDATE clientes SET es_credito = true');
SELECT pg_temp.debe_negar('app_mostrador',
    'INSERT INTO venta_lineas (venta_id, producto_id, cantidad, precio_unitario) VALUES (1, 1, 1, 0.01)');

-- ---- app_duena: ve todo menos los hashes ----
SELECT pg_temp.debe_permitir('app_duena', 'SELECT * FROM v_saldos_credito');
SELECT pg_temp.debe_permitir('app_duena', 'SELECT * FROM compras');
SELECT pg_temp.debe_negar('app_duena', 'SELECT password_hash FROM usuarios');

-- ---- reglas de negocio ----
DO $$
DECLARE v_enc int;
BEGIN
    INSERT INTO encargos (cliente_id, fecha_entrega, descripcion, total)
    VALUES ((SELECT id FROM clientes WHERE nombre = 'Cliente Prueba'), current_date + 1, 'Pastel prueba', 600)
    RETURNING id INTO v_enc;
    INSERT INTO pagos_encargo (encargo_id, monto, tipo) VALUES (v_enc, 300, 'anticipo');
    BEGIN
        INSERT INTO pagos_encargo (encargo_id, monto, tipo) VALUES (v_enc, 400, 'liquidacion');
        RAISE EXCEPTION 'FALLA: se aceptó un pago mayor al saldo';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM LIKE 'FALLA%' THEN RAISE; END IF;
        RAISE NOTICE 'ok  pago mayor al saldo rechazado: %', SQLERRM;
    END;
    IF (SELECT saldo FROM v_encargos WHERE id = v_enc) <> 300 THEN
        RAISE EXCEPTION 'FALLA: saldo calculado incorrecto';
    END IF;
    RAISE NOTICE 'ok  saldo calculado = 300';
    IF (SELECT vl.precio_unitario FROM venta_lineas vl JOIN productos p ON p.id = vl.producto_id
        WHERE p.nombre = 'Concha prueba') <> 18 THEN
        RAISE EXCEPTION 'FALLA: el precio no salió del catálogo';
    END IF;
    RAISE NOTICE 'ok  precio de la línea tomado del catálogo = 18';

    -- Mostrador no cancela ni reabre encargos
    SET LOCAL ROLE app_mostrador;
    UPDATE encargos SET estado = 'listo' WHERE id = v_enc;
    RAISE NOTICE 'ok  mostrador puede marcar listo';
    BEGIN
        UPDATE encargos SET estado = 'cancelado' WHERE id = v_enc;
        RAISE EXCEPTION 'FALLA: mostrador canceló un encargo';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM LIKE 'FALLA%' THEN RAISE; END IF;
        RAISE NOTICE 'ok  mostrador no puede cancelar: %', SQLERRM;
    END;
    UPDATE encargos SET estado = 'entregado', entregado_en = now() WHERE id = v_enc;
    BEGIN
        UPDATE encargos SET estado = 'pendiente' WHERE id = v_enc;
        RAISE EXCEPTION 'FALLA: mostrador reabrió un encargo entregado';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM LIKE 'FALLA%' THEN RAISE; END IF;
        RAISE NOTICE 'ok  mostrador no puede reabrir: %', SQLERRM;
    END;
    RESET ROLE;
END $$;

ROLLBACK;
