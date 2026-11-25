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
issue="$(gh issue list --repo "$GH_REPO" --state open --limit 200 --json number,title --jq ".[] | select(.title == \"$title\") | .number" | head -n 1)"
if [[ -z "$issue" ]]; then
  gh issue create --repo "$GH_REPO" --title "$title" --body "$body" --assignee "argentinomics2025"
else
  # Avoid repeated notifications for the same source period.
  if ! gh issue view "$issue" --repo "$GH_REPO" --json body,comments \
      --jq '[.body, (.comments[].body)] | join("\n")' | grep -Fq "$EC021_RISK_SOURCE_DATE"; then
    gh issue comment "$issue" --repo "$GH_REPO" --body "$body"
  fi
fi
