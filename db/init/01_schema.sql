-- =====================================================================
-- Panadería La Espiga Dorada — esquema
-- Reglas de diseño:
--   * Los saldos NUNCA se guardan: se calculan desde los movimientos
--     (pagos, abonos). Nada de "falta 200" en texto.
--   * Un cliente/producto es una sola fila; las formas en que lo
--     escribieron en el Excel viven en tablas *_alias.
--   * El precio se copia a cada línea de venta: si sube la concha,
--     las ventas viejas no cambian.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- crypt()/gen_salt() para contraseñas
CREATE EXTENSION IF NOT EXISTS unaccent;   -- "Juárez" = "Juarez" al buscar alias

CREATE TYPE rol_app        AS ENUM ('duena', 'mostrador');
CREATE TYPE estado_encargo AS ENUM ('pendiente', 'listo', 'entregado', 'cancelado');
CREATE TYPE tipo_pago      AS ENUM ('anticipo', 'abono', 'liquidacion');
CREATE TYPE metodo_pago    AS ENUM ('efectivo', 'transferencia', 'tarjeta', 'sin_dato');
CREATE TYPE origen_dato    AS ENUM ('app', 'excel');
CREATE TYPE estado_factura AS ENUM ('facturada', 'por_pedir', 'sin_factura', 'sin_dato');

-- Normaliza texto para comparar alias: minúsculas, sin acentos, espacios simples.
CREATE FUNCTION normalizar(t text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT lower(regexp_replace(trim(unaccent(t)), '\s+', ' ', 'g'))
$$;

-- ---------------------------------------------------------------------
-- Usuarios de la app (no confundir con los roles de Postgres)
-- ---------------------------------------------------------------------
CREATE TABLE usuarios (
    id            int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario       text NOT NULL UNIQUE CHECK (usuario = lower(usuario)),
    nombre        text NOT NULL,
    rol           rol_app NOT NULL,
    password_hash text NOT NULL,              -- bcrypt vía crypt(pw, gen_salt('bf'))
    activo        boolean NOT NULL DEFAULT true,
    creado_en     timestamptz NOT NULL DEFAULT now()
);

-- Única puerta de entrada antes de iniciar sesión. Corre con permisos del
-- dueño de la función (SECURITY DEFINER) para que app_login no necesite
-- leer la tabla usuarios ni ver los hashes.
CREATE FUNCTION autenticar(p_usuario text, p_password text)
RETURNS TABLE (id int, nombre text, rol rol_app)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp AS $$
    SELECT u.id, u.nombre, u.rol
    FROM usuarios u
    WHERE u.usuario = lower(trim(p_usuario))
      AND u.activo
      AND u.password_hash = crypt(p_password, u.password_hash)
$$;

-- ---------------------------------------------------------------------
-- Clientes (particulares de pasteles y negocios a crédito en una sola tabla:
-- la Escuela Benito Juárez y El Portal son ambas cosas)
-- ---------------------------------------------------------------------
CREATE TABLE clientes (
    id                 int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre             text NOT NULL,
    telefono           text CHECK (telefono ~ '^\d{10}$'),   -- solo 10 dígitos
    es_credito         boolean NOT NULL DEFAULT false,
    dias_credito       int CHECK (dias_credito BETWEEN 0 AND 60),
    saldo_inicial      numeric(10,2) NOT NULL DEFAULT 0 CHECK (saldo_inicial >= 0),
    saldo_inicial_nota text,                                 -- ej. "agosto, por confirmar"
    notas              text,
    activo             boolean NOT NULL DEFAULT true,
    creado_en          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT credito_con_plazo CHECK (NOT es_credito OR dias_credito IS NOT NULL)
);
CREATE UNIQUE INDEX clientes_nombre_uq ON clientes (lower(nombre));

CREATE TABLE cliente_alias (
    alias      text PRIMARY KEY,          -- ya normalizado (normalizar())
    cliente_id int NOT NULL REFERENCES clientes(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- Productos de mostrador
-- ---------------------------------------------------------------------
CREATE TABLE productos (
    id        int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre    text NOT NULL,
    categoria text NOT NULL CHECK (categoria IN ('pan_dulce', 'pan_salado', 'pasteles', 'galletas')),
    unidad    text NOT NULL DEFAULT 'pieza' CHECK (unidad IN ('pieza', 'kg')),
    precio    numeric(10,2) NOT NULL CHECK (precio > 0),
    activo    boolean NOT NULL DEFAULT true
);
CREATE UNIQUE INDEX productos_nombre_uq ON productos (lower(nombre));

CREATE TABLE producto_alias (
    alias       text PRIMARY KEY,
    producto_id int NOT NULL REFERENCES productos(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- Ventas de mostrador: encabezado + líneas
-- ---------------------------------------------------------------------
CREATE TABLE ventas (
    id                 int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fecha              date NOT NULL DEFAULT current_date,
    capturado_por      int REFERENCES usuarios(id),          -- NULL = importado del Excel
    origen             origen_dato NOT NULL DEFAULT 'app',
    captura_incompleta boolean NOT NULL DEFAULT false,      -- "se fue la luz"
    nota               text,
    creado_en          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ventas_fecha_idx ON ventas (fecha);

CREATE TABLE venta_lineas (
    id              int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    venta_id        int NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
    producto_id     int NOT NULL REFERENCES productos(id),
    cantidad        numeric(10,2) NOT NULL CHECK (cantidad > 0),   -- decimal: galletas por kg
    precio_unitario numeric(10,2) NOT NULL CHECK (precio_unitario >= 0),
    subtotal        numeric(12,2) GENERATED ALWAYS AS (cantidad * precio_unitario) STORED
);
CREATE INDEX venta_lineas_venta_idx ON venta_lineas (venta_id);

-- El precio lo pone la base de datos desde el catálogo, no quien captura.
-- (mostrador ni siquiera tiene permiso sobre la columna precio_unitario)
CREATE FUNCTION fijar_precio_linea() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, pg_temp AS $$
BEGIN
    IF NEW.precio_unitario IS NULL THEN
        SELECT precio INTO NEW.precio_unitario FROM productos WHERE id = NEW.producto_id;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER venta_lineas_precio
BEFORE INSERT ON venta_lineas
FOR EACH ROW EXECUTE FUNCTION fijar_precio_linea();

-- ---------------------------------------------------------------------
-- Encargos de pasteles + sus pagos (anticipo, abonos, liquidación)
-- ---------------------------------------------------------------------
CREATE TABLE encargos (
    id                int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cliente_id        int NOT NULL REFERENCES clientes(id),
    fecha_pedido      date NOT NULL DEFAULT current_date,
    fecha_entrega     date NOT NULL,
    descripcion       text NOT NULL CHECK (length(trim(descripcion)) > 0),
    total             numeric(10,2) NOT NULL CHECK (total > 0),
    estado            estado_encargo NOT NULL DEFAULT 'pendiente',
    requiere_revision boolean NOT NULL DEFAULT false,      -- datos del Excel que no cuadran
    nota_revision     text,
    origen            origen_dato NOT NULL DEFAULT 'app',
    creado_por        int REFERENCES usuarios(id),
    creado_en         timestamptz NOT NULL DEFAULT now(),
    entregado_en      timestamptz,
    CONSTRAINT entrega_despues_de_pedido CHECK (fecha_entrega >= fecha_pedido)
);
CREATE INDEX encargos_entrega_idx ON encargos (fecha_entrega);

CREATE TABLE pagos_encargo (
    id             int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    encargo_id     int NOT NULL REFERENCES encargos(id) ON DELETE CASCADE,
    fecha          date NOT NULL DEFAULT current_date,
    monto          numeric(10,2) NOT NULL CHECK (monto > 0),
    tipo           tipo_pago NOT NULL,
    metodo         metodo_pago NOT NULL DEFAULT 'efectivo',
    registrado_por int REFERENCES usuarios(id),
    creado_en      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX pagos_encargo_encargo_idx ON pagos_encargo (encargo_id);

-- Nadie puede cobrar más de lo que cuesta el pastel.
CREATE FUNCTION validar_pago_encargo() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, pg_temp AS $$
DECLARE
    v_total  numeric;
    v_pagado numeric;
BEGIN
    SELECT total INTO v_total FROM encargos WHERE id = NEW.encargo_id FOR UPDATE;
    SELECT coalesce(sum(monto), 0) INTO v_pagado
    FROM pagos_encargo
    WHERE encargo_id = NEW.encargo_id AND id IS DISTINCT FROM NEW.id;

    IF v_pagado + NEW.monto > v_total THEN
        RAISE EXCEPTION 'El pago de $% excede el saldo pendiente de $%',
            NEW.monto, v_total - v_pagado;
    END IF;
    RETURN NEW;
END $$;

-- Mostrador puede marcar listo/entregado y cambiar la fecha, pero cancelar
-- o tocar un encargo ya cerrado es decisión de la dueña.
-- (Sin SECURITY DEFINER a propósito: current_user debe ser quien hace el cambio.)
CREATE FUNCTION validar_cambio_encargo() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF current_user = 'app_mostrador' THEN
        IF OLD.estado IN ('entregado', 'cancelado') THEN
            RAISE EXCEPTION 'Solo la dueña puede modificar un encargo entregado o cancelado';
        END IF;
        IF NEW.estado = 'cancelado' THEN
            RAISE EXCEPTION 'Solo la dueña puede cancelar un encargo';
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER encargos_validar_cambio
BEFORE UPDATE ON encargos
FOR EACH ROW EXECUTE FUNCTION validar_cambio_encargo();

CREATE TRIGGER pagos_encargo_validar
BEFORE INSERT OR UPDATE ON pagos_encargo
FOR EACH ROW EXECUTE FUNCTION validar_pago_encargo();

-- ---------------------------------------------------------------------
-- Clientes de crédito: lo que se llevan (entregas) y lo que pagan (abonos).
-- Los abonos van contra la cuenta del cliente, no contra una nota:
-- saldo = saldo_inicial + entregas - abonos.
-- ---------------------------------------------------------------------
CREATE TABLE entregas_credito (
    id             int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cliente_id     int NOT NULL REFERENCES clientes(id),
    fecha          date NOT NULL DEFAULT current_date,
    descripcion    text NOT NULL,
    monto          numeric(10,2) NOT NULL CHECK (monto > 0),
    nota_remision  text,
    origen         origen_dato NOT NULL DEFAULT 'app',
    registrado_por int REFERENCES usuarios(id),
    creado_en      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX entregas_credito_cliente_idx ON entregas_credito (cliente_id, fecha);

CREATE TABLE abonos_credito (
    id             int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cliente_id     int NOT NULL REFERENCES clientes(id),
    fecha          date NOT NULL DEFAULT current_date,
    monto          numeric(10,2) NOT NULL CHECK (monto > 0),
    metodo         metodo_pago NOT NULL DEFAULT 'efectivo',
    nota           text,
    origen         origen_dato NOT NULL DEFAULT 'app',
    registrado_por int REFERENCES usuarios(id),
    creado_en      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX abonos_credito_cliente_idx ON abonos_credito (cliente_id, fecha);

-- Solo se le puede entregar a crédito a un cliente marcado como de crédito.
CREATE FUNCTION validar_cliente_credito() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, pg_temp AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM clientes WHERE id = NEW.cliente_id AND es_credito) THEN
        RAISE EXCEPTION 'El cliente % no tiene crédito autorizado', NEW.cliente_id;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER entregas_credito_validar
BEFORE INSERT OR UPDATE OF cliente_id ON entregas_credito
FOR EACH ROW EXECUTE FUNCTION validar_cliente_credito();

-- ---------------------------------------------------------------------
-- Compras e insumos (solo dueña)
-- ---------------------------------------------------------------------
CREATE TABLE proveedores (
    id     int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre text NOT NULL UNIQUE
);

CREATE TABLE compras (
    id                       int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fecha                    date NOT NULL DEFAULT current_date,
    proveedor_id             int NOT NULL REFERENCES proveedores(id),
    total                    numeric(10,2) NOT NULL CHECK (total > 0),
    descripcion              text,
    estado_factura           estado_factura NOT NULL DEFAULT 'sin_dato',
    incluye_gastos_personales boolean NOT NULL DEFAULT false,  -- "cosas de la casa"
    posible_duplicado        boolean NOT NULL DEFAULT false,   -- marcado al importar, Carmen confirma
    nota                     text,
    origen                   origen_dato NOT NULL DEFAULT 'app',
    registrado_por           int REFERENCES usuarios(id),
    creado_en                timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX compras_fecha_idx ON compras (fecha);

CREATE TABLE insumos (
    id             int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre         text NOT NULL UNIQUE,
    unidad         text NOT NULL,
    cantidad       numeric(10,2) CHECK (cantidad >= 0),   -- NULL = no se cuenta (ej. fresas del día)
    minimo         numeric(10,2) CHECK (minimo >= 0),     -- NULL = falta definirlo con Carmen
    proveedor_id   int REFERENCES proveedores(id),
    nota           text,
    actualizado_en timestamptz NOT NULL DEFAULT now()
);

-- Fase 2 (sin datos todavía): receta = cuánto de cada insumo lleva una unidad
-- de producto. Con esto y el precio de compra se obtiene el costo por pieza.
CREATE TABLE receta_insumos (
    producto_id         int NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
    insumo_id           int NOT NULL REFERENCES insumos(id),
    cantidad_por_unidad numeric(10,4) NOT NULL CHECK (cantidad_por_unidad > 0),
    PRIMARY KEY (producto_id, insumo_id)
);
