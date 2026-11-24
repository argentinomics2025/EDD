#!/usr/bin/env bash
# EC-021.5: permanent GitHub Issues alert on IPC CI failure; safe dry-run.
set -euo pipefail

: "${GH_REPO:?GitHub repository is required}"
: "${EC0215_ALERT_SOURCE_URL:?Source URL is required}"
mode="${EC0215_ALERT_MODE:-failure}"

case "$mode" in
  failure)
    title="EC-021.5 | Falla IPC automatizado"
    heading="Fallo real del proceso IPC (INDEC / Supabase)"
    ;;
  rehearsal)
    title="EC-021.5 | PRUEBA de alerta IPC"
    heading="PRUEBA CONTROLADA - NO HAY FALLO DEL IPC"
    ;;
  *)
    echo "Unknown EC0215_ALERT_MODE" >&2
    exit 2
    ;;
esac

if [[ "$GH_REPO" != "argentinomics2025/EDD" ]]; then
  echo "Unexpected repository; refusing to open an alert" >&2
  exit 2
fi

if [[ "$EC0215_ALERT_SOURCE_URL" != https://github.com/argentinomics2025/EDD/* ]]; then
  echo "Unexpected source URL" >&2
  exit 2
fi

body="$(cat <<EOF
## $heading

**Evidencia:** $EC0215_ALERT_SOURCE_URL

**Acción:** revisar el job fallido y la fuente oficial INDEC, validar el período almacenado y no corregir históricos automáticamente.

**Seguridad:** este mecanismo NO habilita escrituras ni utiliza credenciales de Supabase. El kill-switch \`EC0215_IPC_WRITES_ENABLED\` se controla por separado.

_Esta incidencia se actualiza en nuevos fallos para evitar duplicados._
EOF
)"

if [[ "${EC0215_ALERT_DRY_RUN:-false}" == "true" ]]; then
  printf '%s\n%s\n' "$title" "$body"
  exit 0
fi

: "${GH_TOKEN:?GitHub Actions token required}"
issue="$(gh issue list --repo "$GH_REPO" --state open --limit 200 --json number,title --jq ".[] | select(.title == \"$title\") | .number" | head -n 1)"

if [[ -n "$issue" ]]; then
  gh issue comment "$issue" --repo "$GH_REPO" --body "$body"
  echo "[ALERTA] Se agregó evidencia al issue #$issue"
else
  gh issue create --repo "$GH_REPO" --title "$title" --body "$body" --assignee argentinomics2025
  echo "[ALERTA] Issue creado y asignado al responsable"
fi
