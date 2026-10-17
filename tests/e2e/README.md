# e2e del SaaS (`saas-next/tests/e2e/`)

Playwright con **un** `playwright.config.ts` y dos proyectos, cada uno contra su propio servidor:

| Proyecto | Specs | Servidor | Para qué |
|---|---|---|---|
| `public` | `*.spec.ts` de esta carpeta (hoy `store-docs.spec.ts` y `public-dark.spec.ts`, el modo claro/oscuro del sistema con sus capturas en `.artifacts/public-dark/`) | `runserver 127.0.0.1:8011` con `DEBUG=False`, `--insecure`, sin Vite | La web pública (plantillas de Django) con la CSP de producción. Pide `pnpm build` antes |
| `panel` | `panel/*.spec.ts` | `runserver 127.0.0.1:8012 --novite --noreload` propio, con `DEBUG=True`, `HUB_INTERNAL_URL` a un puerto sin nadie (`:8019`) y el correo a ficheros, + Vite (`pnpm run dev`) en `:5174` (o en `VITE_DEV_PORT`) | El panel (la SPA de `erplora.com`) tal como se sirve en desarrollo |

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
  `panel/audit2.spec.ts` con el código bien (2026-10-16).
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
- Un solo worker (`workers: 1`): los proyectos comparten la BD local.
- Trazas y capturas de los fallos en `.artifacts/test-results/<id de la ejecución>/`
  (`retain-on-failure`; se abren con `pnpm exec playwright show-trace <ruta>/trace.zip`). Las capturas
  que dejan las specs, en `.artifacts/` (las del panel, en `.artifacts/panel/`). Todo ignorado por git.

## Puertos y servidores

- **`:8012` (Django del panel)**: siempre propio (`reuseExistingServer: false`), sin autorecarga y con
  `HUB_INTERNAL_URL=http://127.0.0.1:8019`: las llamadas al Hub se quedan pendientes, como con el Hub
  caído, y las specs hacen de Hub (su callback `ready` firmado). Así ni el `runserver` de `:8001` de otra
  sesión (que se reinicia con cada `.py` guardado) ni un Hub en `:8000` cambian el resultado, y la
  e2e no deja BD de hub huérfanas. Se arranca y se para en cada ejecución.
- **`:8019` (el Hub de las specs)**: nadie escucha salvo mientras una spec hace de Hub con
  `startHubDouble()` (hoy `members.spec.ts`): registra cada llamada a `/internal` y responde 200 a la
  foto (`PUT /internal/hubs/{id}/state`) y a la revocación (`POST /internal/sessions/revoke`), y 503 al
  resto (sigue pendiente). Si el puerto está ocupado, esa spec no arranca.
- **Correo**: el Django del panel usa el backend de ficheros de Django (`EMAIL_BACKEND` +
  `EMAIL_FILE_PATH`, que `config/settings.py` pasa a `MAILERS`) y escribe cada correo en
  `.artifacts/panel/mail/`; `waitForMail(destinatario, desde, enlace)` espera el que llega tras una
  acción y devuelve su enlace (invitación, contraseña). Los de ejecuciones anteriores se quedan y se
  saltan por fecha.
- **`:5174` (Vite)**, o el puerto de `VITE_DEV_PORT` si se exporta (lo leen igual `config/settings.py`,
  `vite.config.ts` y `panel/project.ts`; el Django de `:8012` lo recibe también): si ya hay uno levantado,
  la e2e **lo reutiliza** y no lo para, **pero solo si es de este árbol**. Cada respuesta del Vite de
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
- Los puertos fijos de la e2e (`:8011`, `:8012`, `:8019`) no cambian: dos e2e del SaaS a la vez chocan
  ahí, y Playwright lo dice al arrancar (`reuseExistingServer: false`).

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
