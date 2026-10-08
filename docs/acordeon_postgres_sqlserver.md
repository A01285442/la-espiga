# Acordeón: nuestro esquema en Postgres ↔ cómo sería en SQL Server

Para la revisión de código: qué hace cada pieza y su equivalente en T-SQL.

## Tipos y columnas

| Postgres (`01_schema.sql`) | SQL Server | Nota |
|---|---|---|
| `int GENERATED ALWAYS AS IDENTITY` | `int IDENTITY(1,1)` | `ALWAYS` = no se puede insertar el id a mano (como no usar `SET IDENTITY_INSERT`) |
| `boolean` | `bit` | |
| `text` | `nvarchar(max)` | En Postgres `text` no tiene penalización de rendimiento |
| `numeric(10,2)` | `decimal(10,2)` | Igual. Nunca `float` para dinero |
| `timestamptz` | `datetimeoffset` | Guarda el instante exacto; se muestra en hora de Monterrey |
| `CREATE TYPE estado_encargo AS ENUM (...)` | `CHECK (estado IN ('pendiente', ...))` | SQL Server no tiene enums |
| `subtotal ... GENERATED ALWAYS AS (cantidad * precio_unitario) STORED` | `subtotal AS (cantidad * precio_unitario) PERSISTED` | Columna calculada guardada |
| `CHECK (telefono ~ '^\d{10}$')` | `CHECK (telefono NOT LIKE '%[^0-9]%' AND LEN(telefono) = 10)` | `~` es expresión regular |
| `CREATE UNIQUE INDEX ... ON clientes (lower(nombre))` | Collation `_CI_` ya ignora mayúsculas; índice único normal | Postgres distingue mayúsculas por default |
| `CREATE EXTENSION unaccent` | Collation `Modern_Spanish_CI_AI` | `AI` = accent insensitive |

## Consultas

| Postgres | SQL Server |
|---|---|
| `INSERT ... RETURNING id` | `INSERT ... OUTPUT inserted.id VALUES ...` |
| `LIMIT 10` | `TOP 10` / `OFFSET ... FETCH` |
| `sum(monto) FILTER (WHERE ...)` | `SUM(CASE WHEN ... THEN monto END)` |
| `fecha + 7`, `current_date + 1` | `DATEADD(day, 7, fecha)`, `DATEADD(day, 1, CAST(GETDATE() AS date))` |
| `coalesce(x, 0)` | `COALESCE(x, 0)` / `ISNULL(x, 0)` |
| `greatest(a, b)` / `least(a, b)` | `GREATEST` / `LEAST` (solo SQL Server 2022+) |
| `date_trunc('month', fecha)` | `DATETRUNC(month, fecha)` (2022+) o `DATEFROMPARTS(YEAR(f), MONTH(f), 1)` |
| `bool_or(x)` | `MAX(CAST(x AS int)) = 1` |
| `TRUNCATE ... RESTART IDENTITY CASCADE` | `TRUNCATE` no acepta FKs: `DELETE` + `DBCC CHECKIDENT` |
| `ON CONFLICT (usuario) DO UPDATE` | `MERGE` |
| `WITH v AS (INSERT ... RETURNING id) INSERT ...` | Dos sentencias con `OUTPUT INTO @tabla` |

## Funciones y triggers (la diferencia más grande)

**Postgres** — trigger por fila, `BEFORE`, con `NEW`:
```sql
CREATE TRIGGER pagos_encargo_validar
BEFORE INSERT OR UPDATE ON pagos_encargo
FOR EACH ROW EXECUTE FUNCTION validar_pago_encargo();
-- dentro: NEW.monto, NEW.encargo_id; RAISE EXCEPTION cancela el insert
```

**SQL Server** — trigger por sentencia, `AFTER`, con la tabla `inserted` (puede traer varias filas):
```sql
CREATE TRIGGER pagos_encargo_validar ON pagos_encargo AFTER INSERT, UPDATE AS
BEGIN
    IF EXISTS (
        SELECT 1 FROM encargos e
        JOIN (SELECT encargo_id FROM inserted GROUP BY encargo_id) i ON i.encargo_id = e.id
        WHERE (SELECT SUM(monto) FROM pagos_encargo p WHERE p.encargo_id = e.id) > e.total)
    BEGIN
        THROW 50001, 'El pago excede el saldo pendiente', 1;   -- THROW deshace la transacción
    END
END
```

- `fijar_precio_linea` (pone el precio si viene vacío) en SQL Server sería `INSTEAD OF INSERT` o un `DEFAULT` no sirve (depende de otra tabla).
- `RAISE EXCEPTION` ↔ `THROW`.
- `LANGUAGE plpgsql` ↔ T-SQL. `DECLARE v_total numeric;` ↔ `DECLARE @v_total decimal(10,2);`.

## Seguridad

| Postgres | SQL Server | Para qué |
|---|---|---|
| `CREATE ROLE app_mostrador LOGIN PASSWORD ...` | `CREATE LOGIN` + `CREATE USER ... FOR LOGIN` | Postgres junta login y usuario en "rol" |
| `GRANT SELECT (id, nombre, telefono) ON clientes TO app_mostrador` | Igual: `GRANT SELECT (id, nombre, telefono) ON clientes TO app_mostrador` | Permiso por columna |
| `REVOKE ... FROM PUBLIC` | `REVOKE ... FROM public` | Quitar el permiso que todos tienen por default |
| `SECURITY DEFINER` en `autenticar()` | `EXECUTE AS OWNER` en un procedimiento | Corre con permisos del dueño, no de quien lo llama |
| Vista **con** `security_invoker = true` | No existe: SQL Server siempre usa *ownership chaining* | Revisar permisos de quien consulta |
| Vista **sin** `security_invoker` (`v_mis_capturas_hoy`) | Comportamiento normal de SQL Server | Dar acceso a una parte filtrada de una tabla prohibida |
| `current_setting('app.usuario_id')` | `SESSION_CONTEXT(N'usuario_id')` + `sp_set_session_context` | Saber qué persona de la app está conectada |
| `crypt(pw, gen_salt('bf'))` (pgcrypto) | No hay bcrypt: se hace en Python (`bcrypt`) | Contraseñas con hash lento + sal |
| Row Level Security (`CREATE POLICY`) | Row Level Security (`CREATE SECURITY POLICY`) | No lo usamos; los permisos por columna y vistas bastaron |

## Frases útiles para la entrevista

- "Ocean X usa Supabase, que es Postgres. No quise generar costos, así que usé Postgres en Docker y repliqué lo que haría Supabase con RLS usando roles y `GRANT` por columna."
- "La seguridad está en la base: aunque alguien se brinque la pantalla, Postgres le contesta *permission denied*. Está probado en `db/pruebas/permisos.sql`."
- "Los saldos no se guardan, se calculan desde los pagos. Así nunca puede haber un 'falta 200' que no cuadre."
