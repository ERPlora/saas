# `apps` — el catálogo de apps del Hub y lo que el SaaS vende de cada una

App de plataforma del SaaS (`LiveAppConfig`, `kind = "platform"`), antes `marketplace` (ronda 16, PLAN §21.1
punto 10). Es una hoja del grafo: `hubs`, `billing` y `public` la leen; ella no lee a nadie. El manual y los
flujos están en `WORKBOOK.md` (APPS-F01 a APPS-F07); el contrato, en PLAN §21 y PLAN-SAAS §2.6, con el detalle en
`docs/superpowers/specs/2026-10-13-saas-public-web-and-app-catalog-design.md`.

## Qué hay

| Pieza | Qué hace |
|---|---|
| `models.py` | `App` y `AppDoc`: el esquema `shared` de la BD `saas` (`live.shared_catalog`). El SaaS es dueño de las tablas y de sus migraciones; las escribe el worker del Hub (`register_apps`, rol `hub_shared`) con cada release, y aquí solo se leen. `Module`: lo comercial de una app de pago (`slug`, `tier`, precios netos en céntimos, ids de Stripe, `is_active`), escrito a mano en el admin; su `clean()` exige una app de pago del catálogo |
| `queries.py` | Las operaciones públicas (`auth=None`, sin permiso) `apps.app.list`, `apps.app.get`, `apps.app.doc` y `apps.app.sitemap`, en el idioma del contexto (`es` → columnas `_es`, cualquier otro → `_en`); `cards_of` (las tarjetas de unas apps, también retiradas, para `billing`) y `known_verticals` (para `BusinessType.clean()` de `hubs`) |
| `schemas.py` | Entrada y salida de las operaciones; los filtros que no se entienden se ignoran (nunca 422) |
| `api.py` | `GET /api/apps`, `/api/apps/get`, `/api/apps/doc` y `/api/apps/sitemap`, cada una ligada a su operación |
| `icons.py` | Limpieza del `icon_svg` que manda el Hub (nh3, solo formas) y el icono de respaldo |
| `checks.py` | `apps.E001`: un `Module.slug` sin app en `shared.app`; corre con `manage.py check --database default` |
| `admin.py` | `App` y `AppDoc` de solo lectura para todos; `Module` editable con `ModuleForm`, que comprueba en Stripe los precios pegados (APPS-F04, `billing.services.module_price_problems`), y con el borrado de un módulo que algún negocio tiene rechazado (saas#2568) |

## Reglas

- Nada del SaaS escribe `shared.app` ni `shared.app_doc` (`tests/test_lint.py` lo vigila).
- Sin `live.py`: el catálogo cambia con un despliegue del Hub, que no avisa a nadie.
- La documentación se pinta con `live.markdown` y se guarda en caché un día por `app:idioma:hash`
  (`DOC_RENDER_VERSION` se sube cuando cambia lo que deja pasar el renderizador).
- Sin `services.py`: esta app no tiene escrituras propias; el admin de `Module` es la única, y su comprobación de Stripe es de `billing`.

## Tests

`TEST_DB_NAME=test_saas_next_<tema> uv run pytest -q apps` (y, porque la leen, `hubs`, `billing` y `public`).
Cada test cita su flujo `APPS-Fnn` en el nombre o en el docstring cuando lo añade un porte.

## Huecos conocidos

- APPS-F07: la página de apps del Hub aún no manda a comprar a la Tienda (BASE-G74 del Hub).
