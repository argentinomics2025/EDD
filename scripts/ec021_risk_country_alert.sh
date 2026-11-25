#!/usr/bin/env bash
# EC-021: Notify internally when new risk-country source data cannot be published.
# Never publishes EMBI values, never requests secrets and never touches Supabase.
set -euo pipefail
: "${GH_TOKEN:?Missing GitHub issue token}"
: "${GH_REPO:?Missing repository}"
: "${EC021_RISK_SOURCE_DATE:?Missing source date}"
: "${EC021_RISK_STORED_DATE:?Missing stored date}"
[[ "$GH_REPO" == "argentinomics2025/EDD" ]] || exit 2
[[ "$EC021_RISK_SOURCE_DATE" =~ ^20[0-9]{2}-[01][0-9]-[0-3][0-9]$ ]] || exit 2
[[ "$EC021_RISK_STORED_DATE" =~ ^20[0-9]{2}-[01][0-9]-[0-3][0-9]$ ]] || exit 2
[[ "$EC021_RISK_SOURCE_DATE" > "$EC021_RISK_STORED_DATE" ]] || exit 0
title="EC-021 | Riesgo País: fuente adelantada, publicación bloqueada"
body="$(cat <<EOF
## Novedad detectada sin publicación automática

- Último período consultado en ArgentinaDatos: **$EC021_RISK_SOURCE_DATE**
- Último período almacenado en Economía Criolla: **$EC021_RISK_STORED_DATE**
- Estado: **SOLO LECTURA**. No escribir valores EMBI ni alterar históricos sin acreditar derechos de redistribución de terceros.
- Proveedor: ArgentinaDatos; origen informado: Ámbito; índice asociado: J.P. Morgan EMBI.
- Evidencia: https://github.com/argentinomics2025/EDD/actions
- Contexto y decisiones: https://github.com/argentinomics2025/EDD/issues/5

La atribución en el frontend no reemplaza licencia sobre la serie. No copiar ni publicar automáticamente números de mercado.
EOF
)"
if [[ "${EC021_RISK_ALERT_DRY_RUN:-false}" == "true" ]]; then
  printf '%s\n%s\n' "$title" "$body"
  exit 0
fi
# Use GitHub REST, not 'gh issue list/view', which requires GraphQL.
issue="$(gh api "repos/$GH_REPO/issues?state=open&per_page=100" --jq '.[] | select(.title == "EC-021 | Riesgo País: fuente adelantada, publicación bloqueada" and .pull_request == null) | .number' | head -n 1)"
if [[ -z "$issue" ]]; then
  gh api -X POST "repos/$GH_REPO/issues" -f title="$title" -f body="$body" -f "assignees[]=argentinomics2025" --jq '.html_url'
else
  previous="$(gh api "repos/$GH_REPO/issues/$issue" --jq '.body')"
  previous="$previous"$'\n'"$(gh api "repos/$GH_REPO/issues/$issue/comments?per_page=100" --jq '.[].body')"
  if ! grep -Fq "$EC021_RISK_SOURCE_DATE" <<< "$previous"; then
    gh api -X POST "repos/$GH_REPO/issues/$issue/comments" -f body="$body" --jq '.html_url'
  fi
fi
