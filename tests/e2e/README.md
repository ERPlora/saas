# e2e del SaaS (`saas-next/tests/e2e/`)

Playwright con **un** `playwright.config.ts` y dos proyectos, cada uno contra su propio servidor:

| Proyecto | Specs | Servidor | Para qué |
|---|---|---|---|
| `public` | `*.spec.ts` de esta carpeta (hoy `store-docs.spec.ts`) | `runserver 127.0.0.1:8011` con `DEBUG=False`, `--insecure`, sin Vite | La web pública (plantillas de Django) con la CSP de producción. Pide `pnpm build` antes |
| `panel` | `panel/*.spec.ts` | `runserver 127.0.0.1:8012 --novite --noreload` propio, con `DEBUG=True`, `HUB_INTERNAL_URL` a un puerto sin nadie (`:8019`) y el correo a ficheros, + Vite (`pnpm run dev`) en `:5174` | El panel (la SPA de `erplora.com`) tal como se sirve en desarrollo |

## Cómo se corre

Desde `saas-next/` (o con `pnpm --filter saas …` desde la raíz):

```bash
uv run python manage.py migrate      # la e2e no migra la BD local: la comparten las sesiones
pnpm e2e                             # los dos proyectos, en Chrome visible
pnpm e2e --project=panel             # solo el panel
pnpm e2e --project=public            # solo la web pública (antes, `pnpm build`)
pnpm e2e --project=panel panel/login.spec.ts   # una spec
```

- **Siempre en el Chrome de Ioan, visible** (`channel: 'chrome'`, `headless: false`, `slowMo` 150 ms),
  como la de `hub-next`. Nunca un navegador oculto en local.
- `pnpm e2e:ci` pone `CI=1`: sin ventana y sin `slowMo`. **Solo para la CI**.
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
- **`:5174` (Vite)**: si ya hay uno levantado, la e2e **lo reutiliza** y no lo para.
- **`:8011`**: el servidor de producción de `public`, siempre propio (`reuseExistingServer: false`):
  si el puerto está ocupado, la ejecución no arranca. Se levanta en toda ejecución, también con
  `--project=panel` (Playwright arranca todos los `webServer`).
- **La e2e de la PoC del Hub** (`hub-next/tests/e2e/`) usa el SaaS de `:8001`; la del panel ya no lo
  toca.

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
- `signInThroughPage(page, credenciales)`: el login de verdad, en la página `/login` ya abierta.
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
