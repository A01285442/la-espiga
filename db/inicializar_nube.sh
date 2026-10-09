#!/bin/bash
# Crea en Neon (Postgres en la nube) lo mismo que db/init/ crea en Docker:
# roles de la app, tablas, vistas y permisos.
#
# ATENCIÓN: BORRA y recrea el esquema public de esa base. Después hay que
# volver a cargar el Excel:  python seed/limpiar_y_cargar.py "...xlsx" --nube
#
# Uso (desde la carpeta la-espiga, con Docker corriendo):  bash db/inicializar_nube.sh
# Lee NEON_ADMIN_URL y las contraseñas APP_* de .env. Usa psql de la imagen de Postgres.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
: "${NEON_ADMIN_URL:?Falta NEON_ADMIN_URL en .env}"

psql_nube() {
    docker run --rm -i postgres:16-alpine psql "$NEON_ADMIN_URL" -v ON_ERROR_STOP=1 -q "$@"
}

echo "1/2 Roles y esquema…"
psql_nube -v pw_login="$APP_LOGIN_PASSWORD" \
          -v pw_mostrador="$APP_MOSTRADOR_PASSWORD" \
          -v pw_duena="$APP_DUENA_PASSWORD" <<'EOSQL'
SELECT current_database() AS db \gset

DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;

-- Crear los roles si no existen y, en todo caso, fijarles la contraseña de .env
SELECT format('CREATE ROLE %I LOGIN', r) FROM unnest(ARRAY['app_login', 'app_mostrador', 'app_duena']) r
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) \gexec
SELECT format('ALTER ROLE app_login PASSWORD %L', :'pw_login') \gexec
SELECT format('ALTER ROLE app_mostrador PASSWORD %L', :'pw_mostrador') \gexec
SELECT format('ALTER ROLE app_duena PASSWORD %L', :'pw_duena') \gexec

-- El administrador puede "ponerse" en cada rol (SET ROLE) solo para las pruebas de
-- permisos; INHERIT FALSE: no hereda sus permisos sin pedirlo.
GRANT app_login, app_mostrador, app_duena TO CURRENT_USER WITH INHERIT FALSE, SET TRUE;

ALTER DATABASE :"db" SET timezone TO 'America/Monterrey';
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO app_login, app_mostrador, app_duena;
EOSQL

echo "2/2 Tablas, vistas y permisos…"
for archivo in db/init/01_schema.sql db/init/02_vistas.sql db/init/03_permisos.sql; do
    psql_nube < "$archivo"
done
echo "Listo. Ahora: python seed/limpiar_y_cargar.py \"ruta/...xlsx\" --nube"
