# `apps` — el catálogo de apps del Hub y lo que el SaaS vende de cada una

App de plataforma del SaaS (`LiveAppConfig`, `kind = "platform"`), antes `marketplace` (ronda 16, PLAN §21.1
punto 10). `hubs`, `billing` y `public` la leen; ella solo llama a otras desde el admin de `Module` (`billing` para
comprobar los precios y nombrar a quien lo tiene, `hubs` para avisar a los negocios de su plan) y a `accounts` para el
registro de cambios. El manual y los flujos están en `WORKBOOK.md` (APPS-F01 a APPS-F07, app completa desde el
2026-10-27); el contrato, en PLAN §21 y PLAN-SAAS §2.6 y §9, con el detalle en
`docs/superpowers/specs/2026-10-13-saas-public-web-and-app-catalog-design.md`; el cierre, en PLAN-SAAS §12.

## Qué hay

| Pieza | Qué hace |
|---|---|
| `models.py` | `App` y `AppDoc`: el esquema `shared` de la BD `saas` (`live.shared_catalog`). El SaaS es dueño de las tablas y de sus migraciones; las escribe el worker del Hub (`register_apps`, rol `hub_shared`) con cada release, y aquí solo se leen. `Module`: lo comercial de una app de pago (`slug`, `tier`, precios netos en céntimos, ids de Stripe, `is_active`), escrito a mano en el admin; su `clean()` exige una app de pago del catálogo |
| `queries.py` | Las operaciones públicas (`auth=None`, sin permiso) `apps.app.list`, `apps.app.get`, `apps.app.doc` y `apps.app.sitemap`, en el idioma del contexto (`es` → columnas `_es`, cualquier otro → `_en`), y `apps.doc.list` (`ai=INTERNAL`: el markdown de cada app listada en cada idioma, lo que indexa el asistente del panel, `assistant/knowledge.py`); `cards_of` (las tarjetas de unas apps, también retiradas, para `billing`) y `known_verticals` (para `BusinessType.clean()` de `hubs`) |
| `schemas.py` | Entrada y salida de las operaciones; los filtros que no se entienden se ignoran (nunca 422) |
| `api.py` | `GET /api/apps`, `/api/apps/get`, `/api/apps/doc` y `/api/apps/sitemap`, cada una ligada a su operación |
| `icons.py` | Limpieza del `icon_svg` que manda el Hub (nh3, solo formas) y el icono de respaldo |
| `checks.py` | `apps.E001`: un `Module.slug` sin app en `shared.app`; corre con `manage.py check --database default` |
| `admin.py` | `App` y `AppDoc` de solo lectura para todos; `Module` editable con `ModuleForm`, que comprueba en Stripe los precios pegados (APPS-F04, `billing.services.module_price_problems`), que al guardar uno nuevo o con otro `tier` lo hace llegar a los negocios de su plan (HUBS-F34, `hubs.services.owe_module_rights`), y con el borrado de un módulo que algún negocio tiene rechazado (saas#2568) |
| `auditlog.py` | Registro de cambios de `Module` con django-auditlog (ACCOUNTS-F36, sin `updated_at`); `App` y `AppDoc` no se registran |

## Reglas

- Nada del SaaS escribe `shared.app` ni `shared.app_doc` (`tests/test_lint.py` lo vigila).
- Sin `live.py`: el catálogo cambia con un despliegue del Hub, que no avisa a nadie.
- La documentación se pinta con `live.markdown` y se guarda en caché un día por `app:idioma:hash`
  (`DOC_RENDER_VERSION` se sube cuando cambia lo que deja pasar el renderizador).
- Sin `services.py`: esta app no tiene escrituras propias; el admin de `Module` es la única, y su comprobación de Stripe es de `billing`.
- Desde la ronda 2026-10-24b (PLAN §32, PLAN-SAAS §9) ningún módulo es `premium`: `Module`, su comprobación de Stripe y
  la compra en la Tienda siguen construidos y probados, pero sin uso (APPS-F03, F04, F05 y F07; contradicción señalada en
  PLAN-SAAS §12).

## Tests

`TEST_DB_NAME=test_saas_next_<tema> uv run pytest -q apps` (y, porque la leen, `hubs`, `billing` y `public`).
Cada test cita su flujo `APPS-Fnn` en el nombre o en el docstring cuando lo añade un porte.

## Huecos conocidos

- Ninguno. El de APPS-F07 (la página de apps del Hub no mandaba a comprar a la Tienda, BASE-G74) se cerró con BASE-F20
  (hub#229; el enlace se llama «Mejorar plan» desde hub#256).
