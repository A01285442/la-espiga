#!/bin/bash
# Crea los tres roles de base de datos que usa la app.
#   app_login     -> antes de iniciar sesión: solo puede ejecutar autenticar()
#   app_mostrador -> captura ventas y encargos, no ve dinero de la dueña
#   app_duena     -> ve y edita todo
# Los permisos concretos se otorgan en 03_permisos.sql.
set -euo pipefail

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v pw_login="$APP_LOGIN_PASSWORD" \
  -v pw_mostrador="$APP_MOSTRADOR_PASSWORD" \
  -v pw_duena="$APP_DUENA_PASSWORD" \
  -v db="$POSTGRES_DB" <<'EOSQL'
CREATE ROLE app_login     LOGIN PASSWORD :'pw_login';
CREATE ROLE app_mostrador LOGIN PASSWORD :'pw_mostrador';
CREATE ROLE app_duena     LOGIN PASSWORD :'pw_duena';

ALTER DATABASE :"db" SET timezone TO 'America/Monterrey';
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO app_login, app_mostrador, app_duena;
EOSQL
