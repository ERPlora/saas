# `public` — la web pública de erplora.com

App de plataforma (`LiveAppConfig`, `kind = "platform"`) que sirve la web pública con plantillas de Django (sin Vue,
sin SSR y sin prefijo `/es/`; ronda 16 y spec `docs/superpowers/specs/2026-10-13-saas-public-web-and-app-catalog-design.md`
§8). Es la excepción de PLAN-SAAS §6 «Rutas con vistas»: tiene `urls.py` y vistas, montadas en la raíz por
`config/urls.py` delante del comodín de la SPA; sus primeros segmentos son `PUBLIC_PREFIXES`.

- Flujos y comportamiento: `WORKBOOK.md` (y su traducción `WORKBOOK.en.md`, con el hash de la parte de usuario en la
  cabecera, el mismo esquema que `translate_workbooks` del Hub).
- Un módulo por área: `landing.py` (portada y contacto), `pricing.py` (planes), `industries.py` (sectores),
  `product.py`, `company.py`, `compliance.py`, `resources.py`, `help.py`, `legal.py`, `declaracion.py`, `store.py`
  (tienda `/apps/` y redirecciones viejas), `appdist.py`/`downloads.py` (la app y descargas), `demo.py`,
  `language.py`, `seo.py` (robots y `llms.txt`), `sitemaps.py`, `structured_data.py` y `indexnow.py`.
- Datos: ninguna vista importa modelos; lee por operaciones (`hubs.plan.list`, `hubs.sector.list`,
  `hubs.business_type.list`, `apps.app.list`…) con `run_operation_sync`.
- Idioma: catálogo propio en `public/locale/es/` (inglés fuente). El `.po` se mantiene a mano por secciones:
  `makemessages` lo reordena entero, así que se usa para descubrir los `msgid` nuevos y se añaden a mano antes de
  compilar (`msgfmt --check`).
- Estilos: CSS propio en `public/static/public/` (con tokens `--ep-*`) y las utilidades que generan las plantillas
  (`scripts/build_ionic_utilities.py`, cuyo test falla si una plantilla gana una clase sin regenerar).

## Decisiones

- **Precios (PUBLIC-F02–F04):** el ahorro anual sale de los dos precios del plan (`annual_months_free`), nunca de un
  «2 meses gratis» escrito; el año de Colabora vale el precio anual. El precio pintado es el del `Plan` y el cobro
  usa el mismo (`billing.services.plan_sale`); el admin rechaza un precio de Stripe que no case (BILLING-F28).
- **Promesas (PUBLIC-F07, F08):** solo lo que hacen hoy las apps del Hub y la infraestructura de ERPlora/aws; las
  listas de frases vetadas viven en `tests/test_product.py`.
- **Cumplimiento (PUBLIC-F09, APP-PUBLIC-1, 2026-10-21):** vuelve `/compliance/`, que la spec aplazó (§11.1).
  Decidido con el mercado (Odoo y Business Central publican su lista de países con el producto; Lightspeed, Holded,
  fiskaly y Mollie dicen el sistema fiscal concreto de cada país; Shopify POS y Zettle limitan por país): una lista
  fija en el código, que se publica con las apps que describe. Los países son los del alta (`hubs.schemas.COUNTRIES`)
  y el sistema conectado, hoy solo VeriFactu en España; el País Vasco (TicketBAI) y Navarra se dicen fuera y no se
  nombran normativas extranjeras que nadie ha comprobado. Sustituye al `CountryCompliance` del SaaS viejo, que una
  persona marcaba «Cubierto» en el admin.
- **Idioma (PUBLIC-F13):** selector en el pie de todas las páginas, un formulario POST por idioma a
  `/set-language/` (como Stripe, Shopify o Square).
- **Datos estructurados (PUBLIC-F14):** `OPERATING_SYSTEMS` = los sistemas que se distribuyen (web, Windows, Linux y
  Android).

## Pruebas

- `uv run pytest -q public` (y `public/tests/test_<módulo>.py` por módulo).
- e2e: `tests/e2e/public-web.spec.ts` (flujo a flujo, tres tamaños, CSP sin violaciones), `public-dark.spec.ts`,
  `demo-door.spec.ts` y `store-docs.spec.ts`; antes, `pnpm build` (el proyecto `public` sirve el build).
