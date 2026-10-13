#!/usr/bin/env bash
# Checks a built saas image against the app <-> infra contract (aws README, «Imagen»):
#   bash docker/image.test.sh erplora/saas:<tag>
# Every container runs without network and with a read-only root filesystem (only /tmp is
# writable), as in ECS: nothing may need the database, a secret or a write outside /tmp.
set -uo pipefail

IMAGE="${1:?usage: docker/image.test.sh <image>}"
failures=0

# The variables production must provide with DEBUG=False (config/settings.py), all dummies.
PROD_ENV=(
  -e DEBUG=False
  -e SECRET_KEY=x
  -e ALLOWED_HOSTS=erplora.com
  -e INTERNAL_SHARED_SECRET=x
  -e GOOGLE_OAUTH_CLIENT_ID=x
  -e GOOGLE_OAUTH_CLIENT_SECRET=x
  -e "HUB_CALLBACK_TEMPLATE=https://{slug}.erplora.com/auth/callback"
  -e DB_HOST=db.invalid -e DB_PORT=5432 -e DB_NAME=saas -e DB_USER=x -e DB_PASSWORD=x
)

run() { docker run --rm --network none --read-only --tmpfs /tmp "$@"; }

check() {
  local name="$1" out
  shift
  if out=$("$@" 2>&1); then
    echo "ok   - $name"
  else
    echo "FAIL - $name"
    printf '%s\n' "$out" | tail -n 15 | sed 's/^/       /'
    failures=$((failures + 1))
  fi
}

inspect() { docker image inspect -f "$1" "$IMAGE"; }

check "image is linux/arm64" \
  test "$(inspect '{{.Os}}/{{.Architecture}}')" = "linux/arm64"
check "runs as uid 10001" \
  test "$(run "$IMAGE" id -u)" = "10001"
check "python is on the PATH" \
  run "$IMAGE" sh -c 'command -v python'
check "erplora-live is installed (import live)" \
  run "$IMAGE" python -c "import live"
check "live ships its compiled Spanish catalogue" \
  run "$IMAGE" python -c "import live, pathlib; assert (pathlib.Path(live.__file__).parent / 'locale/es/LC_MESSAGES/django.mo').is_file()"
check "the project's Spanish catalogue is compiled" \
  run "$IMAGE" test -s locale/es/LC_MESSAGES/django.mo
# Each compiled catalogue says what its .po says (a stale .mo whose mtime looks newer than the .po
# is skipped by compilemessages). Singular, non-fuzzy entries without context.
MO_MATCHES_PO='
import ast, gettext, sys
from pathlib import Path

import live


def entries(po):
    found, entry, key = {}, {}, None
    for line in po.read_text(encoding="utf-8").splitlines() + [""]:
        if not line.strip():
            if entry.get("msgid") and entry.get("msgstr") and not entry.get("skip"):
                found[entry["msgid"]] = entry["msgstr"]
            entry, key = {}, None
        elif line.startswith("#,") and "fuzzy" in line or line.startswith(("msgctxt", "msgid_plural")):
            entry["skip"] = True
        elif line.startswith(("msgid ", "msgstr ")):
            key, _, rest = line.partition(" ")
            entry[key] = ast.literal_eval(rest)
        elif line.startswith("\"") and key:
            entry[key] += ast.literal_eval(line)
        else:
            key = None
    return found


bad = []
for base in (Path("locale"), Path(live.__file__).parent / "locale"):
    for po in sorted(base.glob("*/LC_MESSAGES/django.po")):
        expected = entries(po)
        with open(po.with_suffix(".mo"), "rb") as mo:
            catalogue = gettext.GNUTranslations(mo)
        stale = [msgid for msgid, msgstr in expected.items() if catalogue.gettext(msgid) != msgstr]
        print(f"{po}: {len(expected)} entries, {len(stale)} stale")
        if not expected or stale:
            bad.append((str(po), stale[:3]))
sys.exit(f"stale or empty catalogues: {bad}" if bad else 0)
'
check "every compiled catalogue matches its .po" \
  run "$IMAGE" python -c "$MO_MATCHES_PO"
check "the Vite manifest is in frontend/dist" \
  run "$IMAGE" test -s frontend/dist/.vite/manifest.json
check "STATIC_ROOT holds the admin and every file of the Vite manifest" \
  run -e DEBUG=1 "$IMAGE" python -c '
import json
from pathlib import Path

import django

django.setup()
from django.conf import settings

root = Path(settings.STATIC_ROOT)
assert (root / "admin" / "css" / "base.css").is_file(), "admin static files missing"
manifest = json.loads(Path(settings.LIVE["spa"]["manifest"]).read_text())
files = {c["file"] for c in manifest.values()} | {f for c in manifest.values() for f in c.get("css", [])}
missing = sorted(f for f in files if not (root / "spa" / f).is_file())
assert files, "the Vite manifest lists no file"
assert not missing, f"not collected: {missing}"
'
check "the RDS CA bundle is at /etc/ssl/certs/rds-global-bundle.pem, mode 644" \
  run "$IMAGE" sh -c 'test "$(stat -c %a /etc/ssl/certs/rds-global-bundle.pem)" = 644 && grep -q "BEGIN CERTIFICATE" /etc/ssl/certs/rds-global-bundle.pem'
check "no pgbouncer nor PostgreSQL client (hub only)" \
  run "$IMAGE" sh -c '! command -v pgbouncer && ! command -v pg_isready && ! command -v psql'
check "no secret nor DEBUG baked into the image environment" \
  sh -c "! docker image inspect -f '{{json .Config.Env}}' '$IMAGE' | grep -Eq 'SECRET|PASSWORD|DEBUG'"
check "no .env file in the project" \
  run "$IMAGE" sh -c '! test -e .env'
check "manage.py check passes with DEBUG=False and no database" \
  run "${PROD_ENV[@]}" "$IMAGE" python manage.py check
# Daphne first, then its flags in any order.
daphne_cmd() {
  local cmd
  cmd=$(inspect '{{json .Config.Cmd}}')
  echo "CMD $cmd, exposed $(inspect '{{json .Config.ExposedPorts}}')"
  case "$cmd" in '["daphne",'*) ;; *) return 1 ;; esac
  for arg in '"--proxy-headers"' '"0.0.0.0"' '"8000"' '"config.asgi:application"'; do
    grep -qF -- "$arg" <<<"$cmd" || return 1
  done
  inspect '{{json .Config.ExposedPorts}}' | grep -qF '"8000/tcp"'
}
check "CMD is Daphne on 0.0.0.0:8000 with --proxy-headers and port 8000 exposed" daphne_cmd

# The container health check of the task definition: GET /healthz on 127.0.0.1:8000, no database.
healthz() {
  local cid ok=1
  cid=$(docker run -d --network none --read-only --tmpfs /tmp "${PROD_ENV[@]}" "$IMAGE") || return 1
  for _ in $(seq 1 30); do
    if docker exec "$cid" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)" 2>/dev/null; then
      ok=0
      break
    fi
    sleep 1
  done
  [ "$ok" = 0 ] || docker logs "$cid" 2>&1 | tail -n 15
  docker rm -f "$cid" >/dev/null
  return "$ok"
}
check "the default CMD answers /healthz without a database" healthz

if [ "$failures" -ne 0 ]; then
  echo "$failures check(s) failed"
  exit 1
fi
echo "all checks passed"
