#!/usr/bin/env bash
# EC-021 RIPTE: deduplicated issues; no database credentials.
set -euo pipefail
: "${GH_TOKEN:?Missing GitHub issue token}"
: "${GH_REPO:?Missing repository}"
: "${EC021_RIPTE_ALERT_URL:?Missing triggering evidence}"
[[ "$GH_REPO" == "argentinomics2025/EDD" ]] || exit 2
[[ "$EC021_RIPTE_ALERT_URL" == https://github.com/argentinomics2025/EDD/* ]] || exit 2
if [[ "${EC021_RIPTE_ALERT_TEST:-false}" == "true" ]]; then
  title="EC-021 | PRUEBA alerta RIPTE"
  heading="PRUEBA CONTROLADA: no existe un fallo de RIPTE"
else
  title="EC-021 | Falla monitor RIPTE"
  heading="Fallo real del monitor o escritor restringido RIPTE"
fi
body="$(cat <<EOF
## $heading

Evidencia: $EC021_RIPTE_ALERT_URL

Revisar fuente oficial, validación de históricos y job afectado. No cambiar datos sin auditoría.
El robot de Riesgo País continúa bloqueado por licencia.
EOF
)"
if [[ "${EC021_RIPTE_ALERT_DRY_RUN:-false}" == "true" ]]; then
  printf '%s\n%s\n' "$title" "$body"
  exit 0
fi
issue="$(gh issue list --repo "$GH_REPO" --state open --limit 200 --json number,title --jq ".[] | select(.title == \"$title\") | .number" | head -n 1)"
if [[ -z "$issue" ]]; then
  gh issue create --repo "$GH_REPO" --title "$title" --body "$body" --assignee argentinomics2025
else
  gh issue comment "$issue" --repo "$GH_REPO" --body "$body"
fi
