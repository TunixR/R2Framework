#!/bin/sh
# Runs once, when the data volume is first initialised. Creates the read-only
# role the otel-agent's postgresql receiver uses (pg_monitor: statistics only).
#
# The image's entrypoint may source this file instead of executing it, so it
# must not call `exit` or change shell options; the entrypoint already stops on
# the first error.

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v monitor_user="$POSTGRES_MONITOR_USER" \
  -v monitor_password="$POSTGRES_MONITOR_PASSWORD" <<'SQL'
CREATE ROLE :"monitor_user" WITH LOGIN PASSWORD :'monitor_password';
GRANT pg_monitor TO :"monitor_user";
SQL
