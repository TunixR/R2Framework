#!/bin/sh
# Runs once, when the data volume is first initialised: seeds the server from
# the dumps in /dumps (docker/postgres/dumps, mounted by postgres/compose.dev.yaml).
# Each file is restored into the database named after it, created if missing:
#   gateway.dump    pg_dump custom format (pg_dump -Fc)
#   gateway.sql     plain SQL
#   gateway.sql.gz  gzipped plain SQL
# Ownership and grants are dropped: objects belong to POSTGRES_USER.
#
# The image's entrypoint may source this file instead of executing it, so it
# must not call `exit` or change shell options; the entrypoint already stops on
# the first error.

if [ -d /dumps ]; then
  for dump in /dumps/*.dump /dumps/*.sql /dumps/*.sql.gz; do
    [ -f "$dump" ] || continue
    db=$(basename "$dump")
    db=${db%.gz}
    db=${db%.sql}
    db=${db%.dump}
    echo "restore-dumps: $dump -> database \"$db\""
    if [ "$(psql --username "$POSTGRES_USER" --dbname postgres -Atc "SELECT 1 FROM pg_database WHERE datname = '$db'")" != "1" ]; then
      createdb --username "$POSTGRES_USER" "$db"
    fi
    case "$dump" in
      *.dump) pg_restore --username "$POSTGRES_USER" --dbname "$db" --no-owner --no-privileges --exit-on-error "$dump" ;;
      *.sql.gz) gunzip -c "$dump" | psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" -q ;;
      *.sql) psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" -q -f "$dump" ;;
    esac
  done
fi
