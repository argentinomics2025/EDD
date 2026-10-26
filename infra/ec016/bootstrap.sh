#!/usr/bin/env bash
# Also checked by schema.sql BEFORE DDL. No standalone, generic psql invocation.
set -euo pipefail
marker=/run/ec016
[[ -f /.dockerenv ]] || exit 80
# A local Unix socket is mandatory; no libpq endpoint inheritance.
for name in $(compgen -e); do
  case "$name" in PGPASSWORD) [[ "${PGPASSWORD}" == EC016_SYNTHETIC_ADMIN_ONLY ]] || exit 92;;
    PGHOST|PGHOSTADDR|PGPORT|PGSERVICE|PGSERVICEFILE|PGPASSFILE|PGDATABASE|PGUSER|PGOPTIONS|DATABASE_URL|SUPABASE_*) exit 92;; esac
done
[[ "$(cat "$marker/scope")" == EC016_DISPOSABLE_SYNTHETIC_ONLY ]] || exit 83
run_id=$(cat "$marker/run-id")
owner=$(cat "$marker/owner-token")
[[ "$run_id" =~ ^[a-f0-9]{32}$ && "$owner" =~ ^[a-f0-9]{64}$ ]] || exit 81
[[ "${EC016_RUN_ID:-}" == "$run_id" && "${EC016_CONTAINER_ROLE:-}" == ec016-db ]] || exit 82
grep -Fxq "$run_id:$owner" "$marker/preflight.ok" || exit 84
[[ "$(readlink /proc/self/ns/net)" != "$(cat "$marker/host-netns")" ]] || exit 85
awk '$5=="/run/ec016" && $6 ~ /(^|,)ro(,|$)/ {found=1} END {exit !found}' /proc/self/mountinfo || exit 87
export PGOPTIONS="-c ec016.run_id=$run_id -c ec016.owner_token=$owner"
psql --host=/var/run/postgresql --port=5432 --no-psqlrc --set=ON_ERROR_STOP=1 --username=ec016_admin --dbname=ec016_disposable --file=/opt/ec016/schema.sql
