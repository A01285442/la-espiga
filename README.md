# La Espiga Dorada — control de operación

Sistema para la Panadería La Espiga Dorada (caso práctico Ocean X): encargos de pasteles,
clientes de crédito, ventas de mostrador, compras e insumos, con dos roles (dueña y mostrador).

**App:** https://green-coleslaw-perkiness.ngrok-free.dev · **Documento de entrega:** [`docs/entrega.pdf`](docs/entrega.pdf)

| Rol | Ve y hace |
|---|---|
| Dueña (Carmen) | Todo: resumen de ventas, crédito, compras, insumos; cancelar encargos, borrar ventas |
| Mostrador (Lupita, Karla) | Captura ventas y encargos, cobra y entrega encargos. **No** ve compras, crédito ni totales de venta |

## Arquitectura

```
Navegador ──HTTPS──▶ ngrok (túnel, dominio fijo) ──▶ app: Streamlit (Python)
                                                         │  se conecta con el rol de BD
                                                         ▼  de quien inició sesión
                                                     db: PostgreSQL 16
                                                     roles: app_login · app_mostrador · app_duena
```

Todo corre con `docker compose` en una computadora: sin costos de hosting. Los puertos de la app
y de la base solo escuchan en `localhost`; lo único expuesto a internet es la app, por el túnel.

**La seguridad vive en la base de datos.** La app nunca usa al administrador: antes de iniciar
sesión solo puede ejecutar `autenticar()`, y después se conecta como `app_mostrador` o
`app_duena`. Los permisos (`GRANT` por tabla y por columna, vistas `security_invoker`, triggers)
hacen que mostrador reciba *permission denied* aunque se brinque una pantalla.

## Levantarlo

Requisitos: Docker Desktop, Python 3.12+ (solo para cargar el Excel) y una cuenta gratis de ngrok.

```bash
cp .env.example .env              # y llenar contraseñas, NGROK_AUTHTOKEN y NGROK_DOMAIN
docker compose up -d --build      # db + app + túnel
pip install -r seed/requirements.txt
python seed/limpiar_y_cargar.py "ruta/Panaderia_La_Espiga_Control.xlsx"
```

- App local: http://localhost:8501 · pública: el dominio de `NGROK_DOMAIN`.
- La carga crea los usuarios `carmen` (dueña), `lupita` y `karla` (mostrador); sus contraseñas
  se generan una vez y quedan en `.env` (`PWD_*`). Es repetible: borra y vuelve a cargar todo
  en una sola transacción, y escribe [`docs/reporte_limpieza.md`](docs/reporte_limpieza.md).
- El Excel no está en el repo (datos del cliente).
- Los scripts de `db/init/` solo corren con la base vacía. Para aplicar cambios al esquema:
  `docker compose down -v && docker compose up -d` y volver a cargar el Excel.

## Pruebas

```bash
# Permisos y reglas de la base (32 verificaciones; todo se deshace al final)
docker compose exec -T db psql -U espiga_admin -d espiga -v ON_ERROR_STOP=1 -f - < db/pruebas/permisos.sql

# App: login, acceso por rol y flujos de cada módulo contra la base real (26 pruebas)
set -a && . ./.env && set +a
docker compose exec -T -e PWD_CARMEN="$PWD_CARMEN" -e PWD_LUPITA="$PWD_LUPITA" app \
  python -m pytest -q -p no:cacheprovider pruebas
```

## Estructura

```
docker-compose.yml          db (Postgres) + app (Streamlit) + tunel (ngrok)
db/init/00_roles.sh         crea los roles app_login, app_mostrador, app_duena
db/init/01_schema.sql       tablas, restricciones y triggers
db/init/02_vistas.sql       saldos y totales calculados (v_encargos, v_saldos_credito, …)
db/init/03_permisos.sql     qué puede leer/escribir cada rol
db/pruebas/permisos.sql     pruebas de permisos y reglas de negocio
seed/limpiar_y_cargar.py    limpia el Excel (alias, fechas, montos) y lo carga
app/Inicio.py               login y menú según el rol
app/lib/db.py               conexión con el rol del usuario; errores sin detalles internos
app/lib/auth.py             autenticación, bloqueo por intentos, requerir_rol() por página
app/lib/credito.py          antigüedad del saldo (los abonos pagan primero lo más viejo)
app/lib/formato.py          pesos, fechas en español, teléfonos
app/paginas/                resumen, credito, encargos, manana, ventas, compras
app/pruebas/                pruebas de la app (AppTest de Streamlit)
docs/                       documento de entrega, diagrama, reporte de limpieza, acordeón Postgres↔SQL Server
```

## Decisiones y supuestos

- **Los saldos no se guardan, se calculan** desde pagos y abonos (vistas en `02_vistas.sql`).
- **Un cliente/producto es una sola fila**; las formas en que se escribió en el Excel viven en
  `cliente_alias` / `producto_alias`.
- **El precio se copia a cada línea de venta** y lo pone la base desde el catálogo.
- Todos los supuestos sobre datos ambiguos (crédito a cuenta, "falta 200", saldo de agosto de
  Don Chuy, compras duplicadas…) están en `docs/entrega.pdf` y en `docs/reporte_limpieza.md`.

## Limitaciones conocidas

- Recargar la página (F5) cierra la sesión: Streamlit guarda la sesión en memoria del servidor.
- En desarrollo, Streamlit no siempre recarga el código de las páginas al editarlas en Windows:
  `docker compose restart app`.
- El plan gratis de ngrok muestra una página de aviso antes de entrar ("Visit Site").
- Para que la app siga arriba, la computadora no debe suspenderse y Docker Desktop debe
  arrancar al iniciar sesión.
