# e2e del SaaS (`saas-next/tests/e2e/`)

Playwright con **un** `playwright.config.ts` y dos proyectos, cada uno contra su propio servidor:

| Proyecto | Specs | Servidor | Para qué |
|---|---|---|---|
| `public` | `*.spec.ts` de esta carpeta (hoy `store-docs.spec.ts`) | `runserver 127.0.0.1:8011` con `DEBUG=False`, `--insecure`, sin Vite | La web pública (plantillas de Django) con la CSP de producción. Pide `pnpm build` antes |
| `panel` | `panel/*.spec.ts` (hoy `panel/login.spec.ts`) | `runserver 127.0.0.1:8001 --novite --noreload` con `DEBUG=True` + Vite (`pnpm run dev`) en `:5174` | El panel (la SPA de `erplora.com`) tal como se sirve en desarrollo |

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

- **`:8001` (Django) y `:5174` (Vite)**: si ya hay uno levantado (el `runserver` de Ioan o de otra
  sesión), la e2e **lo reutiliza** (`reuseExistingServer: true`) y no lo para. Si no, lo arranca y lo
  para al acabar. Django va sin autorecarga: un `.py` que guarde otra sesión no lo reinicia a mitad
  de la ejecución (uno reutilizado sí puede reiniciarse).
- **`:8011`**: el servidor de producción de `public`, siempre propio (`reuseExistingServer: false`):
  si el puerto está ocupado, la ejecución no arranca. Se levanta en toda ejecución, también con
  `--project=panel` (Playwright arranca todos los `webServer`).
- **Ojo con la e2e de la PoC del Hub** (`hub-next/tests/e2e/`): usa este SaaS en `:8001` para el login.
  Si la e2e del panel arranca su propio `:8001`, lo para al acabar; no se lanza mientras la del Hub
  dependa de él.

## Datos sembrados

- **Panel**: `manage.py demo_seed` (una vez por worker, fixture `owner`; necesita `DEBUG=True`, que la
  fixture fija). No cambia nada si ya existen:
  - `owner@example.com` / `owner`: cliente, dueño de los hubs locales `a` y `b`, sin admin.
  - `employee@example.com` / `employee`: cliente, empleado de `a` y `b`.
  - `platform@example.com` / `platform`: administrador de la plataforma, sin hubs.
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

El idioma del proyecto `panel` es `en-US` sea cual sea el del equipo: las specs leen los textos en
inglés.
