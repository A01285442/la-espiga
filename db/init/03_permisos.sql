-- =====================================================================
-- Permisos por rol. La seguridad vive aquí, en la base de datos:
-- aunque alguien se salte una pantalla de la app, Postgres le niega la consulta.
-- =====================================================================

-- Punto de partida: nadie tiene nada.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
-- Postgres da EXECUTE a PUBLIC por default en toda función nueva.
REVOKE EXECUTE ON FUNCTION
    autenticar(text, text), normalizar(text),
    validar_pago_encargo(), validar_cliente_credito(), fijar_precio_linea(),
    validar_cambio_encargo()
FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO app_login, app_mostrador, app_duena;

-- ---------------------------------------------------------------------
-- app_login: solo puede intentar iniciar sesión
-- ---------------------------------------------------------------------
GRANT EXECUTE ON FUNCTION autenticar(text, text) TO app_login;

-- ---------------------------------------------------------------------
-- app_mostrador (Lupita, Karla): captura ventas y encargos.
-- NO ve: compras, insumos, crédito, totales de venta, usuarios.
-- NO puede borrar nada.
-- ---------------------------------------------------------------------
GRANT SELECT ON productos TO app_mostrador;

-- De clientes solo lo necesario para un encargo (ni crédito ni saldos)
GRANT SELECT (id, nombre, telefono)  ON clientes TO app_mostrador;
GRANT INSERT (nombre, telefono)      ON clientes TO app_mostrador;
GRANT UPDATE (telefono)              ON clientes TO app_mostrador;

GRANT SELECT ON encargos TO app_mostrador;
GRANT INSERT (cliente_id, fecha_pedido, fecha_entrega, descripcion, total, creado_por)
    ON encargos TO app_mostrador;
GRANT UPDATE (estado, fecha_entrega, descripcion, entregado_en)
    ON encargos TO app_mostrador;

GRANT SELECT ON pagos_encargo TO app_mostrador;
GRANT INSERT (encargo_id, monto, tipo, metodo, registrado_por)
    ON pagos_encargo TO app_mostrador;

-- Ventas: puede registrar (fecha = hoy por default) pero no leer.
-- SELECT(id) solo para que INSERT ... RETURNING id funcione.
GRANT INSERT (capturado_por, captura_incompleta, nota) ON ventas TO app_mostrador;
GRANT SELECT (id)                                      ON ventas TO app_mostrador;
GRANT INSERT (venta_id, producto_id, cantidad)         ON venta_lineas TO app_mostrador;

GRANT SELECT ON v_encargos, v_manana_sale, v_mis_capturas_hoy TO app_mostrador;

-- ---------------------------------------------------------------------
-- app_duena (Carmen): todo, menos los hashes de contraseñas
-- ---------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON
    clientes, cliente_alias, productos, producto_alias,
    ventas, venta_lineas, encargos, pagos_encargo,
    entregas_credito, abonos_credito,
    proveedores, compras, insumos, receta_insumos
TO app_duena;

GRANT SELECT (id, nombre, rol, activo) ON usuarios TO app_duena;

GRANT SELECT ON
    v_encargos, v_manana_sale, v_mis_capturas_hoy,
    v_saldos_credito, v_ventas_diarias, v_ventas_producto_mes, v_insumos_por_pedir
TO app_duena;

GRANT EXECUTE ON FUNCTION normalizar(text) TO app_duena;
