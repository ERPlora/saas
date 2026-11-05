#!/usr/bin/env bash
# The report of the nightly e2e run (nightly.yml, saas#296): lists what came out red, from Playwright's
# JSON report, in the run's summary, and on main keeps ONE open issue about it: a red night opens it
# (or comments on it when it is already open) and the first green night closes it.
#   RESULT=<e2e job's result> REPORT=<json report> RUN_URL=<run> SHA=<commit> PUBLISH=true|false \
#     GH_REPO=<owner/repo> GH_TOKEN=<token> bash .github/scripts/e2e-report.sh
# Every result other than `success` is red (a timeout or a cancel included). A missing report is said,
# not hidden: the run stopped before or outside the specs. Only PUBLISH=true writes issues (main);
# elsewhere the summary is all. A gh call that fails fails the step. Optional: DAY (the night's date,
# default today in UTC) and GITHUB_STEP_SUMMARY.
# The jq programs and the markdown are single-quoted on purpose: their $ and backticks are literal (SC2016).
# shellcheck disable=SC2016
set -euo pipefail

TITLE="Pruebas de navegador del SaaS en rojo en la pasada nocturna"
: "${RESULT:?}" "${REPORT:?}" "${RUN_URL:?}" "${SHA:?}"
PUBLISH="${PUBLISH:-false}"
DAY="${DAY:-$(date -u +%F)}"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/null}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# The red tests and the run's own errors, one markdown line each, without colour codes; the first
# line of each error, cut at 200 characters.
LINES_JQ='
def plain: gsub("\u001b\\[[0-9;]*m"; "") | split("\n")[0] | .[0:200];
def specs($path): (.specs[]? | {path: ($path + [.title]), spec: .}),
                  (.suites[]? as $suite | $suite | specs($path + [$suite.title]));
(.suites[]? | specs([]) | .path as $path | .spec as $spec | $spec.tests[]
  | select(.status == "unexpected")
  | ((.results | last | .error.message) // "" | plain) as $error
  | "- `[\(.projectName)] \($spec.file):\($spec.line)` › \($path | join(" › "))"
    + (if $error == "" then "" else " — \($error)" end)),
(.errors[]? | "- Error de la ejecución: \(.message // "" | plain)")
'
STATS_JQ='.stats | "\(.unexpected) en rojo · \(.expected) bien · \(.skipped) saltadas"'

details="$work/details.md"
if [ -s "$REPORT" ] && jq -e . "$REPORT" > /dev/null 2>&1; then
  {
    jq -r "$STATS_JQ" "$REPORT"
    echo
    jq -r "$LINES_JQ" "$REPORT"
  } > "$details"
  if ! grep -q '^- ' "$details" && [ "$RESULT" != success ]; then
    printf '\nEl informe no tiene ninguna prueba en rojo, pero la ejecución terminó en `%s`: el log del run dice por qué.\n' \
      "$RESULT" >> "$details"
  fi
else
  printf 'La ejecución terminó en `%s` sin informe de las pruebas: lo que falló está antes o fuera de las specs (preparación, servidores, tiempo agotado). El log del run lo dice.\n' \
    "$RESULT" > "$details"
fi

# The open issue of exactly that title, if any (the newest when there were two).
open_issue() {
  gh issue list --state open --limit 200 --json number,title \
    | jq -r --arg title "$TITLE" '[.[] | select(.title == $title) | .number] | max // empty'
}

if [ "$RESULT" = success ]; then
  printf '## Pruebas de navegador: en verde\n\nLa pasada del %s ha salido en verde: %s\n' "$DAY" "$RUN_URL" >> "$SUMMARY"
  if [ "$PUBLISH" = true ]; then
    number="$(open_issue)"
    if [ -n "$number" ]; then
      gh issue close "$number" --reason completed \
        --comment "La pasada del $DAY ha salido entera en verde: $RUN_URL (commit \`${SHA:0:7}\`). Se cierra."
    fi
  fi
  exit 0
fi

{
  printf '## Pruebas de navegador: en rojo\n\n%s (commit `%s`)\n\n' "$RUN_URL" "${SHA:0:7}"
  cat "$details"
  if [ "$PUBLISH" != true ]; then
    printf '\nFuera de main: no se escribe ninguna issue.\n'
  fi
} >> "$SUMMARY"
[ "$PUBLISH" = true ] || exit 0

body="$work/body.md"
number="$(open_issue)"
if [ -n "$number" ]; then
  {
    printf 'La pasada del %s sigue en rojo: %s (commit `%s`).\n\n' "$DAY" "$RUN_URL" "${SHA:0:7}"
    cat "$details"
  } > "$body"
  gh issue comment "$number" --body-file "$body"
  exit 0
fi

{
  cat <<EOF
## Qué pasa
Cada noche se prueban solas, en un navegador, todas las pantallas del SaaS (el panel de erplora.com y la web pública) sobre la última versión, y esta noche alguna ha fallado. Puede ser un fallo real que ya está en producción o una prueba que se ha quedado vieja: hasta que alguien lo mire no se sabe.

## Propuesta
Mirar cada prueba de la lista: si el fallo es del producto, arreglarlo con su prueba; si la prueba se quedó vieja, ponerla al día. Esta issue se cierra sola la primera noche en que la pasada salga entera en verde.

## Detalle técnico
- Pasada del $DAY: $RUN_URL (commit \`${SHA:0:7}\`). Las trazas y capturas de cada fallo, en su artefacto \`e2e-test-results\`.
- Se repite una prueba desde \`saas/\` con \`pnpm e2e:ci <spec>\` (\`tests/e2e/README.md\`).

EOF
  cat "$details"
  cat <<EOF

## Origen
- Cómo se llegó: la pasada nocturna de las pruebas de navegador (\`.github/workflows/nightly.yml\`).
- Sale de #296
- La introdujo una PR: no comprobado — la pasada no sabe qué cambio la rompió; se busca entre los commits desde la última noche en verde.

## Cómo se reproduce
- Run: $RUN_URL

## Flujo
- Flujo: ninguno — la pasada no sabe qué flujo prueba cada spec; el triaje lo pone al leerla.
EOF
} > "$body"
gh issue create --title "$TITLE" --label prio:P1 --body-file "$body"
