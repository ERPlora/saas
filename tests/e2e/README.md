# e2e del SaaS (`saas-next/tests/e2e/`)

Playwright con **un** `playwright.config.ts` y dos proyectos, cada uno contra su propio servidor:

| Proyecto | Specs | Servidor | Para qué |
|---|---|---|---|
| `public` | `*.spec.ts` de esta carpeta (hoy `store-docs.spec.ts`, `public-dark.spec.ts`, el modo claro/oscuro del sistema con sus capturas en `.artifacts/public-dark/`, y `demo-door.spec.ts`, la puerta `/demo/` en `en` y `es` con sus capturas en `.artifacts/demo/`) | `runserver 127.0.0.1:8011` (o el de su pila, «Dos e2e del SaaS a la vez») con `DEBUG=False`, `--insecure`, sin Vite | La web pública (plantillas de Django) con la CSP de producción. Pide `pnpm build` antes |
| `panel` | `panel/*.spec.ts` | `runserver 127.0.0.1:8012 --novite --noreload` propio (o el de su pila), con `DEBUG=True`, `HUB_INTERNAL_URL` a un puerto sin nadie (`:8019`) y el correo a ficheros, + su gemelo con el segundo factor encendido en `:8013`, + Vite (`pnpm run dev`) en `:5174` (o en `VITE_DEV_PORT`) | El panel (la SPA de `erplora.com`) tal como se sirve en desarrollo |

## Cómo se corre

Desde `saas-next/` (o con `pnpm --filter saas …` desde la raíz):

```bash
uv run python manage.py migrate      # la e2e no migra la BD local: la comparten las sesiones
pnpm e2e                             # los dos proyectos, en Chrome sin ventana (headless)
pnpm e2e:headed                      # lo mismo en un Chrome visible (E2E_HEADED=1), solo si se pide
pnpm e2e --project=panel             # solo el panel
pnpm e2e --project=public            # solo la web pública (antes, `pnpm build`)
pnpm e2e --project=panel panel/login.spec.ts   # una spec
```

- **La BD local tiene que estar migrada**: antes de sembrar nada, `globalSetup` (`global-setup.ts`) corre
  `manage.py migrate --check --plan`, que no aplica nada, y si falta alguna migración aborta la ejecución
  con la lista y el aviso de correr `uv run python manage.py migrate` desde un checkout de `main`. Las specs
  leen lo que siembran las migraciones (los planes de `hubs.0013`) y una BD que dejó otra rama hacía fallar
  `panel/audit2.spec.ts` con el código bien (2026-10-16). Una pila propia (`E2E_SAAS_PORT`) no usa esa BD: la suya
  la crea y la migra la propia e2e al arrancar (ver «Dos e2e del SaaS a la vez»).
- **Sin ventana por defecto** (Ioan, 2026-10-14: nunca se abre un Chrome visible si no se pide): Chrome
  (`channel: 'chrome'`) en modo `headless` y sin `slowMo`. Sustituye a la regla anterior de «siempre
  visible».
- **Ventana visible solo con `E2E_HEADED=1`** (`pnpm e2e:headed`): Chrome visible y `slowMo` de 150 ms
  para poder seguirlo. La decide `browserWindow()` de `playwright.config.ts` (guarda en
  `vite.config.test.ts`); ningún proyecto ni spec la cambia por su cuenta.
- `pnpm e2e:ci` pone `CI=1`: sin ventana y sin `slowMo` aunque se pida `E2E_HEADED=1`. Es la de la CI.
- **Depurar**: `DEBUG=pw:webserver pnpm e2e:ci <spec>` enseña el arranque y la salida de cada servidor
  (`DEBUG=pw:*`, todos los registros de Playwright). Los procesos de Django no heredan ese `DEBUG`, que leen
  como booleano: cada uno lleva el suyo por `django-env.ts` (`:8011` apagado; `:8012`, `globalSetup` y los
  seeds, encendido). El Vite sí lo hereda (`vite:*`).
- Un solo worker (`workers: 1`): los proyectos comparten la BD de la ejecución.
- Trazas y capturas de los fallos en `.artifacts/test-results/<id de la ejecución>/` (la hora de inicio y, en una
  pila propia, su puerto: `…-8030`)
  (`retain-on-failure`; se abren con `pnpm exec playwright show-trace <ruta>/trace.zip`). Las capturas
  que dejan las specs, en `.artifacts/` (las del panel, en `.artifacts/panel/`). Todo ignorado por git.

## Puertos y servidores

Son los de la pila compartida, la de toda ejecución que no exporta nada. `E2E_SAAS_PORT` los mueve juntos para una
segunda ejecución a la vez (`stack.ts`; ver «Dos e2e del SaaS a la vez»): `+1` el público, `+2` el panel, `+3` su
gemelo con el segundo factor, `+8` el doble de reCAPTCHA y `+9` el Hub de las specs (por defecto `8010`: `:8011`,
`:8012`, `:8013`, `:8018`, `:8019`).

- **`:8012` (Django del panel)**: siempre propio (`reuseExistingServer: false`), sin autorecarga y con
  `HUB_INTERNAL_URL=http://127.0.0.1:8019`: las llamadas al Hub se quedan pendientes, como con el Hub
  caído, y las specs hacen de Hub (su callback `ready` firmado). Así ni el `runserver` de `:8001` de otra
  sesión (que se reinicia con cada `.py` guardado) ni un Hub en `:8000` cambian el resultado, y la
  e2e no deja BD de hub huérfanas. Se arranca y se para en cada ejecución. Además sube los límites por
  dirección de la entrada (`E2E_RELAX_LOGIN_RATE_LIMIT=True`, `config/settings.py`): cada spec entra desde
  `127.0.0.1` con contraseña y código, y una spec repetida (`--repeat-each=6`) pasaba de los 30 por minuto (429 en
  el login); desde 2026-10-22 también las contraseñas falladas (5 en 5 minutos por dirección) y los códigos
  rechazados (10 en 5 minutos por dirección, `code_attempts`), y desde 2026-10-28 las altas (10 por hora por
  dirección: la 11.ª «Create account» de una ejecución caía con «Too many attempts»; `panel/signup-rate-limit.spec.ts`).
  Cada cuenta conserva su límite (5 contraseñas falladas en 5 minutos), y los enlaces de restablecer y «Enviar un
  código nuevo» los suyos; el servidor
  de desarrollo también (no depende de `DEBUG`), y sin `DEBUG` (producción) el Django se niega a arrancar con
  ella.
- **`:8013` (el gemelo del panel con el segundo factor)**: el mismo Django que `:8012` (misma BD, mismo Vite, misma
  carpeta de correo y mismo Hub de las specs) con `ACCOUNTS_MFA_ENABLED=True`, apagado por defecto en la fase 1: ahí
  juegan las specs de la app autenticadora, los navegadores de confianza y el segundo factor del personal
  (`PANEL_MFA_URL` de `panel/project.ts`; APP-ACCOUNTS-2). El panel de `:8012` queda como producción, con el segundo
  factor apagado. Las dos son `localhost`: cada contexto del navegador va a una sola de las dos, porque las cookies no
  distinguen el puerto.
- **`:8014` (el Hub del servidor público)**: el `HUB_INTERNAL_URL` del servidor público (`publicHubDoublePort` de
  `stack.ts`, base + 4). Nadie escucha (la demo dice «no disponible» al momento) salvo mientras `demo-wait.spec.ts`
  hace de Hub de las demos (`POST /internal/demos` 202 «requested» y `GET /internal/hubs/{id}` con el estado que
  pone el test). Con `E2E_DEMO_HUB` (abajo, «La demo contra un Hub de verdad») no se fija: manda el
  `HUB_INTERNAL_URL` exportado.
- **`:8019` (el Hub de las specs)**: nadie escucha salvo mientras una spec hace de Hub con
  `startHubDouble()` (hoy `members.spec.ts`): registra cada llamada a `/internal` y responde 200 a la
  foto (`PUT /internal/hubs/{id}/state`) y a la revocación (`POST /internal/sessions/revoke`), y 503 al
  resto (sigue pendiente). Si el puerto está ocupado, esa spec no arranca.
- **`:8018` (el doble de reCAPTCHA)**: `recaptcha-double.ts`, un servidor de Node que la ejecución arranca y para
  (`reuseExistingServer: false`). El servidor público, que es de producción, corre con reCAPTCHA **apagado**, como
  producción desde el 2026-10-23; con `E2E_RECAPTCHA=1` lo enciende (`recaptchaServerEnv`, `recaptcha.ts`) y le pide
  las evaluaciones (`RECAPTCHA_ENDPOINT`) con una clave que no es la de Google; lee los tokens de las specs
  (`e2e-human:<acción>` 0.9, `e2e-bot:<acción>` 0.1; el resto, mal formado) y guarda lo que le preguntan
  (`GET /assessments`). En el navegador, todas las specs del proyecto `public` importan `test` de `public-test.ts`,
  que cambia el `enterprise.js` de Google por uno falso (`recaptcha.ts`) que se carga como el de verdad (su versión
  desde `www.gstatic.com`, el nonce, la política `goog#html` de Trusted Types y la insignia): una CSP que bloqueara
  a Google bloquea también al falso. Una spec que necesita un bot o Google bloqueado llama
  `fakeGoogleRecaptcha(context, 'bot' | 'blocked')`. El panel (`:8012`, `:8013`) corre con reCAPTCHA apagado
  (`RECAPTCHA_ENABLED=False`): sus specs entran por la API, sin navegador que pida el token. `recaptcha.spec.ts`
  tiene las dos variantes: por defecto, apagado, comprueba que el contacto y la entrada con su código funcionan sin
  cargar nada de Google (ni script, ni aviso, ni estilo de la insignia, ni fuentes en la CSP); con
  `E2E_RECAPTCHA=1 pnpm e2e:ci recaptcha.spec.ts`, encendido, prueba el contacto, la demo y la entrada con su código
  contra el doble; su último test carga el **script real** de Google en
  `localhost` solo si el `.env` del checkout tiene las dos claves (`RECAPTCHA_SITE_KEY` de `localhost` y
  `RECAPTCHA_API_KEY`): comprueba que se genera el token bajo la CSP y los Trusted Types de producción y que Google
  lo da por válido y de su acción (la puntuación de un Chrome sin ventana no se mira). El servidor público sube el
  límite de demos por dirección (`DEMO_SPAWN_RATELIMIT=30/h`): la ejecución pulsa «Prueba la demo» más de 3 veces.
- **Correo**: el Django del panel usa el backend de ficheros de Django (`EMAIL_BACKEND` +
  `EMAIL_FILE_PATH`, que `config/settings.py` pasa a `MAILERS`) y escribe cada correo en
  `.artifacts/panel/mail/` (en una pila propia, `.artifacts/panel/mail-<E2E_SAAS_PORT>/`); `waitForMail(destinatario, desde, enlace)` espera el que llega tras una
  acción y devuelve su enlace (invitación, contraseña). Los de ejecuciones anteriores se quedan y se
  saltan por fecha.
- **`:5174` (Vite)**, o el puerto de `VITE_DEV_PORT` si se exporta (lo leen igual `config/settings.py`,
  `vite.config.ts` y `panel/project.ts`; el Django de `:8012` lo recibe también): si ya hay uno levantado,
  la e2e **lo reutiliza** y no lo para, **pero solo si es de este árbol** (y solo en la pila compartida: una
  pila propia arranca el suyo). Cada respuesta del Vite de
  desarrollo lleva la cabecera `x-erplora-vite-root` con el directorio que sirve, y `globalSetup`
  (`assertViteOfThisTree`) aborta la ejecución antes de tocar la BD si el Vite de ese puerto es de otro
  checkout o no la manda (un Vite de un commit anterior a `VITE_DEV_PORT`): las specs probarían el
  frontend de ese árbol y no el de la rama. El mensaje dice qué árbol lo sirve y cómo salir (otro puerto).
  Se comprueba en toda ejecución, también con `--project=public`.
- **`:8011`**: el servidor de producción de `public`, siempre propio (`reuseExistingServer: false`):
  si el puerto está ocupado, la ejecución no arranca. Se levanta en toda ejecución, también con
  `--project=panel` (Playwright arranca todos los `webServer`).
- **La e2e de la PoC del Hub** (`hub-next/tests/e2e/`) usa el SaaS de `:8001`; la del panel ya no lo
  toca.

## Dos SaaS a la vez

El Vite del SaaS escucha en `:5174` salvo que se defina `VITE_DEV_PORT`: `runserver` la lee del entorno o
del `.env` y se la pasa al Vite que arranca; `pnpm run dev` o la e2e sueltos solo la leen del entorno (Vite
no lee el `.env`), así que para la e2e hay que **exportarla**. Un segundo SaaS de desarrollo (otro
worktree, el de una rama) va con su
propio `runserver` y su propio Vite, nunca con el del primero:

```bash
VITE_DEV_PORT=5224 uv run python manage.py runserver 127.0.0.1:8051   # su Django y su Vite (5224)
VITE_DEV_PORT=5225 pnpm e2e:ci tests/e2e/panel/invitation.spec.ts     # su e2e, con su Vite (sin `--`)
```

- Fuera de rango (`0`, `70000`, `abc`, vacía), Django (`ImproperlyConfigured`) y Vite se niegan a arrancar.
- Con `VITE_DEV_PORT` exportada o en el `.env`, `uv run pytest` sigue leyendo el `5174` (`config/settings_pytest.py`) y la
  variable se prueba en un proceso aparte.
- Dos **e2e** del SaaS a la vez necesitan además sus propios puertos y su BD: el apartado siguiente.

## Dos e2e del SaaS a la vez

Cada ejecución a la vez es **una pila propia**: sus tres puertos, su Vite, su carpeta de correo, su carpeta de
resultados y **su BD**. Con una BD compartida, las dos siembran y borran las mismas cuentas (`e2e-*`, el dueño de
`demo_seed`) y una spec lee lo que escribió la otra.

| Variable | Qué aísla | Quién la lee |
|---|---|---|
| `E2E_SAAS_PORT` | los tres puertos (`+1` público, `+2` panel, `+9` Hub de las specs) y, con ellos, la BD `saas_e2e_<puerto>`, la carpeta de correo `mail-<puerto>/` y la de resultados `…-<puerto>` | `stack.ts` (y, por él, `playwright.config.ts`, `panel/project.ts`, `django-env.ts`, `database.ts`) |
| `VITE_DEV_PORT` | el Vite del panel | `panel/project.ts`, `vite.config.ts`, `config/settings.py` (ver arriba) |

Reglas que la e2e hace cumplir antes de arrancar ningún servidor (`stack.ts`):

- Con `E2E_SAAS_PORT` distinto de `8010`, la pila corre sobre **su propia BD e2e**: `saas_e2e_<puerto>`, o la BD e2e
  que se exporte en `DB_NAME` (un nombre `saas_…` con `e2e` como palabra). Con `DB_NAME=saas` o cualquier otra BD,
  la rechaza y dice qué hacer.
- En cualquier pila, una BD que no es del SaaS se rechaza: el caso típico es el `DB_NAME` del Hub
  (`hub_e2e_8030`) aún exportado en la consola, con el que el SaaS abría la BD del Hub y su login caía con
  `relation "django_site" does not exist`. La salida: `env -u DB_NAME`.
- **La BD se crea y se migra sola al arrancar**: el primer servidor que levanta Playwright (el público) corre antes
  `node tests/e2e/database.ts`, que crea `saas_e2e_<puerto>` si falta y la migra (idempotente: conserva sus filas;
  unos 10 s la primera vez). Solo toca BD e2e. La pila compartida sigue sin migrar nada: su BD es la `saas` de `.env`.
- **El Vite no se reutiliza** en una pila propia (`reuseExistingServer: false`): dos ejecuciones del mismo checkout
  con el mismo `VITE_DEV_PORT` no comparten uno (la primera lo pararía al acabar bajo la segunda). Si el puerto está
  ocupado, Playwright lo dice al arrancar; cada pila lleva su `VITE_DEV_PORT`.

Receta (dos pilas a la vez, desde el worktree del SaaS; cada una en su consola, o las dos en segundo plano):

```bash
for p in 8031 8032 8033 8039 5443 8041 8042 8043 8049 5444; do lsof -nP -iTCP:$p -sTCP:LISTEN; done   # nada en sus puertos
# Pila A (8031, 8032, 8033, 8039; Vite 5443; BD saas_e2e_8030)
env -u DB_NAME E2E_SAAS_PORT=8030 VITE_DEV_PORT=5443 pnpm e2e:ci tests/e2e/panel/login.spec.ts
# Pila B, a la vez (8041, 8042, 8043, 8049; Vite 5444; BD saas_e2e_8040)
env -u DB_NAME E2E_SAAS_PORT=8040 VITE_DEV_PORT=5444 pnpm e2e:ci tests/e2e/panel/members.spec.ts
# Al terminar las dos (Playwright ya paró sus servidores): borrar sus BD
env -u DB_NAME E2E_SAAS_PORT=8030 node tests/e2e/database.ts --drop
env -u DB_NAME E2E_SAAS_PORT=8040 node tests/e2e/database.ts --drop
```

- Sin `--` antes de la spec (con él corren todas). `env -u DB_NAME` sobra si la consola no exporta ninguno, pero no
  estorba.
- Sin `E2E_SAAS_PORT`, todo es como antes: `:8011`, `:8012`, `:8013`, `:8019`, la BD `saas` de `.env` y `.artifacts/panel/mail/`.
- `--drop` nunca fuerza: con un servidor aún conectado, falla y lo dice. Sin `E2E_SAAS_PORT` (pila compartida), no
  toca nada.
- Para la web pública (`--project=public`) en una pila propia, igual que en la compartida: antes, `pnpm build`.

## El Hub real de la e2e

Las specs del panel mandan las llamadas al Hub (`HUB_INTERNAL_URL`) al puerto `+9` de su pila, donde nadie escucha
salvo un doble (`startHubDouble`) mientras una spec lo pide: el negocio recién creado se queda «Preparando». Para
ver el salto de verdad (el Hub recibe el registro, avisa de que está listo y la ventana entra), una spec puede
correr contra **un Hub de verdad** en ese mismo puerto, con `E2E_REAL_HUB=1` (hoy, el bloque «against the real Hub»
de `panel/hubs-flows.spec.ts`). Sin la variable, esos tests salen saltados y lo dicen; con ella, los que necesitan
el negocio «Preparando» se saltan a su vez. Así la spec corre dos veces: una sin la variable y otra con ella.

El Hub sale de un worktree del Hub (`HUB_DIR`) con su BD e2e (`HUB_DB_NAME`) y escucha en el puerto `+9`, con el
mismo `INTERNAL_SHARED_SECRET` que el SaaS y su `SAAS_URL` apuntando al panel de la pila. El panel lleva
`HUB_CALLBACK_TEMPLATE` y `HUB_ADMIN_CALLBACK_URL` hacia ese Hub. Receta para la pila `8080` (`:8082` panel, `:8089`
Hub; Vites `5480` y `5750`), con el Hub levantado antes y parado después por su PID:

```bash
for p in 8081 8082 8089 5480 5750; do lsof -nP -iTCP:$p -sTCP:LISTEN; done   # nada en sus puertos
# En el worktree del Hub: su BD e2e y el Hub en :8089
DB_NAME=hub_e2e_8089 COMPOSE_FILE=<raíz>/compose.yaml node tests/e2e/database.ts
DEBUG=True DB_NAME=hub_e2e_8089 VITE_DEV_PORT=5750 SAAS_URL=http://localhost:8082 SAAS_INTERNAL_URL=http://127.0.0.1:8082 \
  INTERNAL_SHARED_SECRET=<el del SaaS> uv run python manage.py runserver 127.0.0.1:8089 --noreload &
# En el worktree del SaaS: la pasada con el Hub real
env -u DB_NAME E2E_SAAS_PORT=8080 VITE_DEV_PORT=5480 E2E_REAL_HUB=1 HUB_DIR=<worktree del Hub> HUB_DB_NAME=hub_e2e_8089 \
  HUB_CALLBACK_TEMPLATE='http://{slug}.localhost:8089/auth/callback' HUB_ADMIN_CALLBACK_URL='http://hubs.localhost:8089/auth/callback' \
  pnpm e2e:ci panel/hubs-flows.spec.ts --workers=1
# Al terminar: parar el Hub por su PID (o `lsof -tiTCP:8089 -sTCP:LISTEN | xargs kill`) y borrar las dos BD e2e
```

- `INTERNAL_SHARED_SECRET` es el de `settings` del SaaS de ese worktree (los dos lados firman con él).
- La spec toca la BD del Hub con su `manage.py shell` (`HUB_DIR`, `HUB_DB_NAME`): nunca con el `DB_NAME` de la pila,
  que `stack.ts` rechaza.
- La pasada sin la variable no necesita Hub: el puerto `+9` tiene que estar libre.

## La demo contra un Hub de verdad

`public-demo-hub.spec.ts` recorre la entrada en la demo (PUBLIC-F28): «Try the demo» → «Opening your demo…» → la
shell de la demo como «Demo» → la puerta «Your demo is running» → «Back to my demo», en los tres tamaños. Necesita un
Hub cuyo `SAAS_URL` sea el servidor **público** de la pila (el Hub manda ahí la vuelta de `/auth/login` de una demo),
y el servidor público con las variables del Hub exportadas (Playwright pone el entorno de la ejecución debajo del
suyo). Sin `E2E_DEMO_HUB` sale saltada y lo dice. No convive con `E2E_REAL_HUB` en la misma pasada: ese Hub apunta al
panel. Receta para la pila `8180` (`:8181` público) con el Hub en `:8710`:

```bash
for p in 8181 8182 8183 8710 5580 5910; do lsof -nP -iTCP:$p -sTCP:LISTEN; done   # nada en sus puertos
# En el worktree del Hub: su BD e2e y el Hub en :8710
DB_NAME=hub_e2e_8710 COMPOSE_FILE=<raíz>/compose.yaml node tests/e2e/database.ts
DB_NAME=hub_e2e_8710 VITE_DEV_PORT=5910 SAAS_URL=http://127.0.0.1:8181 uv run python manage.py runserver 127.0.0.1:8710 &
# En el worktree del SaaS
env -u DB_NAME E2E_SAAS_PORT=8180 VITE_DEV_PORT=5580 E2E_DEMO_HUB=http://localhost:8710 HUB_INTERNAL_URL=http://localhost:8710 \
  HUB_CALLBACK_TEMPLATE='http://{slug}.localhost:8710/auth/callback' HUB_ADMIN_CALLBACK_URL='http://hubs.localhost:8710/auth/callback' \
  pnpm e2e:ci tests/e2e/public-demo-hub.spec.ts
# Al terminar: parar el Hub por puerto (`lsof -tiTCP:8710 -sTCP:LISTEN | xargs kill`) y borrar las dos BD e2e
```

- El mismo `INTERNAL_SHARED_SECRET` en los dos (en local, el valor por defecto del Hub es el del `.env` del SaaS).
- Cada pasada deja una demo viva en la BD del Hub hasta su hora; se va con `node tests/e2e/database.ts --drop`.
- El recorrido hasta la demo terminada (410 → la puerta) es `tests/e2e/demo.spec.ts` del Hub, con un SaaS en
  `runserver` (su README, «La demo»).

## Datos sembrados

- **Panel**: `manage.py demo_seed` (una vez por worker, fixture `owner`; necesita `DEBUG=True`, que la
  fixture fija). No cambia nada si ya existen:
  - `owner@example.com` / `owner`: cliente, dueño de los hubs locales `a` y `b`, sin admin.
  - `employee@example.com` / `employee`: cliente, empleado de `a` y `b`.
  - `platform@example.com` / `platform`: administrador de la plataforma, sin hubs.
- **Panel de negocios**: `panel/panel_seed.py seed|clear` (`seedPanel()` en el `beforeAll` de cada spec
  y `clear` en su `afterAll`): las cuentas `e2e-*@example.com` (contraseña `e2e-panel`) con negocios en
  cada estado (activo, preparando, pago pendiente, encargado, invitaciones; `e2e-free`, un negocio en
  Gratis sin prueba, con el tope de plazas). `clear` borra esas cuentas y todo negocio de una de ellas,
  también las cuentas y negocios que crea una spec (`e2e-newcomer`, `e2e-seat-*`…: mismo patrón).
- **Web pública**: `store_docs_seed.py` (`globalSetup`) crea las apps `e2e_store_docs` y
  `e2e_store_base` y las borra al acabar, aunque falle una spec.

## El asistente con el modelo de verdad

La batería de QA del asistente del panel (`panel/assistant-battery.spec.ts`; plan
`docs/plans/2026-10-31-qa-asistente.md` de erplora-next: bloque A y las comprobaciones C35, C36 y C38) habla con el
**modelo de verdad** y con el **índice de verdad** de la documentación. Es una herramienta de QA local, **nunca de la
CI**: sin `QA_REAL_PROVIDER=1` sus tests se saltan, y con él en GitHub Actions (`GITHUB_ACTIONS=true`) la ejecución se
niega a arrancar (`realProviderMode`, `assistant-battery.ts`). Coste orientativo: unos 30 turnos de Qwen más las
huellas de las preguntas, céntimos.

- **Pila propia y BD e2e propia**: `assistant_seed.py real` solo escribe claves de verdad en una BD e2e
  (`saas_…_e2e…`); con la `saas` compartida se niega. Las claves se leen **solo** del entorno (`QA_QWEN_API_KEY`,
  `QA_OPENAI_API_KEY`): nada en el repo, en los registros ni en el informe.
- **Proveedores**, por las operaciones del gateway, como los tiene producción: «Qwen» (`qwen`, API de OpenAI en el
  espacio de Frankfurt de Alibaba) con `qwen3.7-plus` contestando, y «OpenAI» (`openai`, `assistant.credential.import`)
  con `gpt-5.4-mini` de reserva y las huellas de la búsqueda (`ASSISTANT_SERVICE_PROVIDER=openai`, que `panel/project.ts`
  pone con `QA_REAL_PROVIDER=1`, junto con los 30 mensajes al mes de producción). La cuenta es
  `e2e-assistant-qa-battery@example.com` (contraseña `e2e-panel`), dueña de «QA Base» en Gratis.
- **Documentación de las apps del Hub** (`apps.AppDoc`): la escribe el `register_apps` del Hub en el esquema `shared`
  de la BD del SaaS. Una vez por BD e2e, desde un árbol del Hub en `origin/main` con su `.env`:
  `SHARED_DB_NAME=saas_e2e_qa uv run python manage.py register_apps`.
- **El índice** (`assistant.DocChunk`): el `beforeAll` corre `manage.py index_docs`, que solo calcula las huellas de
  lo que cambió (la primera vez, unos 2 900 fragmentos, ~0,015 USD).
- **Al acabar, las claves fuera**: la BD e2e las guarda cifradas con la `FERNET_KEY` de desarrollo, que es pública.
  Se borran con `assistant.credential.delete` (como el admin) o se tira la BD (`node tests/e2e/database.ts --drop` con
  el mismo `DB_NAME`); la siguiente ejecución las vuelve a guardar desde el entorno.

Receta (desde el worktree del SaaS, con `pnpm build` hecho y el `.env` copiado; las claves, sin imprimirlas):

```bash
export QA_QWEN_API_KEY=…      # la del espacio ws-7mg2… de Alibaba (memoria assistant-prod-unconfigured-old-keys-location)
export QA_OPENAI_API_KEY=…
export COMPOSE_FILE=<erplora-next>/compose.yaml   # el Postgres con pgvector
env DB_NAME=saas_e2e_qa E2E_SAAS_PORT=8530 node tests/e2e/database.ts            # crea y migra la BD e2e
(cd <hub en origin/main> && SHARED_DB_NAME=saas_e2e_qa uv run python manage.py register_apps)
QA_REAL_PROVIDER=1 DB_NAME=saas_e2e_qa E2E_SAAS_PORT=8530 VITE_DEV_PORT=5530 pnpm e2e:ci assistant-battery
```

Cada pregunta, en una conversación nueva: se escribe en español, se sigue el turno hasta el final (la tarjeta de la
escritura esperada se confirma con la palabra que pide; cualquier otra se cancela) y se guarda lo que enseñó el panel:
la respuesta, las herramientas que corrieron (los frames del turno), la tarjeta, los fragmentos que devolvió la
búsqueda, los recibos, los avisos, los fallos y los mensajes del mes. El veredicto automático solo mira lo objetivo
(herramientas, tarjetas, avisos y la API), nunca la redacción del modelo. Salida, ignorada por git:
`.artifacts/qa/assistant-battery-A.md` (el informe que lee el chat supervisor, pregunta a pregunta),
`.artifacts/qa/A<n>-<slug>.png` (y `-card.png` donde hubo tarjeta) y `.artifacts/qa/results/<ejecución>/`.

## Sondas del asistente (capa 2)

La capa 2 de la QA del asistente (plan `docs/plans/2026-10-31-asistente-conocimiento-y-qa.md` de erplora-next, §1.5):
frases **nuevas**, escritas por quien hace la QA, para las herramientas del catálogo exportado, mandadas al chat real del
panel con el **modelo de verdad**. Mide que el modelo generaliza más allá de las `asks` de cada operación (la capa 1,
`base/tests/test_assistant_asks.py`, ya prueba que esas llegan). Mismas reglas que la batería: solo con
`QA_REAL_PROVIDER=1`, nunca en la CI, pila y BD e2e propias, la misma siembra (`assistant_seed.py real`).

- **Sonda**: `{id, app, tool, role: "account", surface: "web"|"app", language: "en"|"es", phrase, expect, decide?, notes?}`.
  `expect` es `read` (corre su herramienta, sin tarjeta), `card` (la tarjeta de su herramienta; `decide` `cancel` por
  defecto: no cambia nada en el outbox; `confirm`: corre), `refused` (sin tarjeta ni escritura, su herramienta no corre
  y la respuesta dice que no puede: lo que la superficie no ofrece, como la tienda en la app) o `docs`
  (`assistant.docs.search` corre y la respuesta cita la documentación). El formato es el mismo que el del Hub.
- **Corpus**: `qa/probes/*.json`, una lista de sondas por fichero (`<idioma>-<superficie>-<día>.json`). Vitest comprueba
  que cargan, que ningún `id` se repite y que toda frase está escrita (`assistant-probes.test.ts`).
- **Generador**: `pnpm qa:probes --language es [--surface web|app] [--apps hubs,billing] [--sample 2 | --all]
  [--out <fichero>]` lee `manage.py export_assistant_catalog` y escribe el esqueleto: N herramientas por app (2 por
  defecto; primero las que tienen menos sondas en ese idioma y superficie), la expectativa sacada de la herramienta
  (búsqueda de documentación → `docs`, lectura → `read`, escritura → `card` cancelada) y `refused` para las de la web
  que la superficie no ofrece. La frase queda vacía: se escribe a mano, nunca copiada de las `asks`.
- **La spec** (`panel/assistant-probes.spec.ts`) lee el corpus o `QA_PROBES` (ficheros o carpetas, separados por
  comas). Antes de preguntar comprueba cada sonda contra el catálogo de su idioma y superficie: una frase igual a una
  `ask` (sin mayúsculas, espacios ni signos de los extremos) o una expectativa que el catálogo contradice no se
  pregunta (n.a.) y falla. El idioma de la cuenta y la superficie (`?surface=account` es la app) siguen a cada sonda;
  los mensajes del mes se reponen al agotarse.
- **Salida**, ignorada por git: `.artifacts/qa/probes/<ejecución>/` con el JSON y las capturas de cada sonda y
  `report.md` (aprobadas, fallidas y n.a.; la herramienta que eligió el modelo; los primeros 300 caracteres de la
  respuesta; claves tapadas).
- **El ciclo**: generar el esqueleto, escribir las frases, correr la spec, abrir una issue por cada fallo de producto
  (con su sonda como reproducción) y proponer las sondas nuevas en una PR. El Hub hace lo mismo con su pila.

```bash
pnpm qa:probes --language es --surface app --apps billing        # esqueleto en qa/probes/es-app-<día>.json
QA_REAL_PROVIDER=1 DB_NAME=saas_e2e_qa E2E_SAAS_PORT=8530 VITE_DEV_PORT=5530 pnpm e2e:ci assistant-probes
QA_PROBES=tests/e2e/qa/probes/es-app-2026-11-01.json QA_REAL_PROVIDER=1 … pnpm e2e:ci assistant-probes   # un fichero
```

## Escribir una spec del panel

Va en `panel/` e importa `test` y `expect` de `./fixtures`, no de `@playwright/test`:

- `owner`: las credenciales del dueño sembrado.
- `signedInPage`: una página con la sesión del dueño abierta por la API de `allauth.headless`
  (`POST /_allauth/browser/v1/auth/login`), sin pasar por el formulario.
- `submitSignInForm(page, credenciales)`: rellena y envía el formulario único de entrada y alta del
  launcher (`/launch`) ya abierto; un correo desconocido abre una cuenta nueva.
- `signInThroughPage(page, credenciales)`: el login de verdad, en `/launch` ya abierto: el formulario y
  el código de 6 dígitos que llega por correo (`waitForMailCode`) en `/verify-email`.
- `sessionOf(page.request)`: lo que responde `GET /api/me` (`user` nulo sin sesión).
- `VIEWPORTS` (390, 834 y 1440 px), `watchPageErrors(page)` y `shot(nombre)`.
- `apiPost(request, ruta, datos)`: un POST a la API con el token CSRF de la sesión.
- `waitForMail(…)` y `startHubDouble()`: el correo y el Hub (ver «Puertos y servidores»).
- `djangoPrint(código)`: lo que imprime un trozo de Python con Django montado contra la BD local, para
  lo que ninguna página enseña.
- **Sin recarga en caliente**: el `context` de toda spec responde él mismo al WebSocket de Vite
  (`freezeFrontend`), así que lo que otra sesión guarda a mitad de una ejecución no remonta
  componentes bajo la spec (un diálogo abierto se quedaba huérfano); cada carga de página sí trae los
  ficheros como están. Un contexto creado a mano (`browser.newContext`) lo necesita también.

El idioma del proyecto `panel` es `en-US` sea cual sea el del equipo: las specs leen los textos en
inglés.

## Sin scroll horizontal

Toda comprobación de «nada se sale por la derecha» de las dos partes (`public` y `panel`) pasa por
`horizontalOverflow(page)` (`horizontal-overflow.ts`): los píxeles que quedan más allá del borde derecho de su caja, 0 si
todo cabe. Mide el documento **y la caja de scroll de cada `ion-content`** (la de la página del panel, la del menú
lateral fijo y la de una hoja abierta), en su shadow root (`part="scroll"`). Ionic fija el `body` a la ventana y cada
pantalla del panel se desplaza dentro de su `ion-content`, así que una que se sale por la derecha queda cortada ahí y el
documento nunca crece: mirar solo el documento (`documentElement.scrollWidth` contra la ventana) la daba por buena. Es la
misma medida que la del Hub (`horizontalOverflow` de su `tests/e2e/helpers.ts`). `panel/horizontal-overflow.spec.ts`
comprueba que la ve en la página, en el menú, en una hoja y en una página sin Ionic (la web pública).
`horizontal-overflow.test.ts` (Vitest), sin trinquete: ningún fichero de `tests/e2e` salvo `horizontal-overflow.ts` vuelve
a medir el documento a mano, ni por un nombre dado a su raíz (`const root = document.documentElement`,
`document.querySelector('html')`, `window.document.documentElement`), ni leyéndolo con `??` o `as` en línea o por un
`then()`, ni desestructurando su ancho (`const { scrollWidth } = document.documentElement`, también anidado), ni
con un localizador del raíz (`page.locator('html').evaluate(…)`, `page.$eval('body', …)`), ni partida en varias líneas,
ni un solo `ion-content` (su `getScrollElement()`, `.inner-scroll` o `part="scroll"` y su `scrollWidth`); su scroll
vertical (`scrollTop`, `scrollHeight`) sigue libre. Sus reglas son las del guardarraíl del Hub, línea por línea. `sidewaysScroll(page)` de `panel/fixtures.ts` nombra lo que se desplaza de
lado con la misma medida (`overflowingBoxes(page, 1)`: `document N > M`, `ion-content N > M`) y, además, las tablas.

## Tipos

Playwright solo quita los tipos de una spec al cargarla: no los comprueba. Los comprueba `pnpm typecheck`
(y la CI), que tras el `vue-tsc --build` de la raíz (la SPA, la configuración y los tests de Vitest; ver
`tsconfig.test.ts`) corre `tsc --noEmit -p tests/e2e` con `tests/e2e/tsconfig.json`:
**todo** `.ts` de esta carpeta (specs, `fixtures.ts`, `global-setup.ts`, ayudantes y sus tests de Vitest),
con `node` en sus `types` (`@types/node`); el proyecto de la SPA (`tsconfig.app.json`) no tiene los tipos de
Node, ni siquiera por un import. Un `.ts` nuevo, en cualquier
subcarpeta, entra solo; `typecheck.test.ts` falla si alguno se queda fuera, si un error plantado en una spec
del panel no sale o si `pnpm typecheck` deja de correr este proyecto.
