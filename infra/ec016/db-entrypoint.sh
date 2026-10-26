#!/usr/bin/env bash
# Runs BEFORE the image entrypoint can initdb. No SQL before this context gate.
set -euo pipefail
marker=/run/ec016
[[ -f /.dockerenv && -f "$marker/preflight.ok" ]] || exit 80
run_id=$(cat "$marker/run-id")
owner=$(cat "$marker/owner-token")
[[ "$run_id" =~ ^[a-f0-9]{32}$ && "$owner" =~ ^[a-f0-9]{64}$ ]] || exit 81
[[ "${EC016_RUN_ID:-}" == "$run_id" && "${EC016_CONTAINER_ROLE:-}" == ec016-db ]] || exit 82
[[ "$(cat "$marker/scope")" == EC016_DISPOSABLE_SYNTHETIC_ONLY ]] || exit 83
grep -Fxq "$run_id:$owner" "$marker/preflight.ok" || exit 84
if [[ "$(cat "$marker/execution-provider")" == github-hosted ]]; then
  grep -Fxq "$run_id:$owner:bridge-default-deny-v1" "$marker/network-guard.ok" || exit 94
  grep -Fxq "$run_id:$owner" "$marker/security.ok" || exit 95
fi
[[ "$(readlink /proc/self/ns/net)" != "$(cat "$marker/host-netns")" ]] || exit 85
[[ "$(hostname)" == "ec016-$run_id-ec016-db" ]] || exit 86
awk '$5=="/run/ec016" && $6 ~ /(^|,)ro(,|$)/ {found=1} END {exit !found}' /proc/self/mountinfo || exit 87
awk '$5=="/var/lib/postgresql/data" && / - tmpfs / {found=1} END {exit !found}' /proc/self/mountinfo || exit 88
awk '/172[.]30[.]216[.]2$/ {candidate=1;next} candidate {if ($0 ~ /32 host LOCAL/) found=1;candidate=0} END {exit !found}' /proc/net/fib_trie || exit 89
awk 'NR>1 && $2=="00000000" {bad=1} END {exit bad}' /proc/net/route || exit 93
for name in $(compgen -e); do
  case "$name" in PGHOST|PGHOSTADDR|PGPORT|PGSERVICE|PGSERVICEFILE|PGPASSFILE|PGDATABASE|PGUSER|PGPASSWORD|PGOPTIONS|DATABASE_URL|SUPABASE_*) exit 92;; esac
done
[[ "${PGDATA:-}" == /var/lib/postgresql/data && "${POSTGRES_DB:-}" == ec016_disposable && "${POSTGRES_USER:-}" == ec016_admin && "${POSTGRES_PASSWORD:-}" == EC016_SYNTHETIC_ADMIN_ONLY ]] || exit 90
[[ -z "$(find "$PGDATA" -mindepth 1 -maxdepth 1 -print -quit)" ]] || exit 91
exec /usr/local/bin/docker-entrypoint.sh postgres
