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
- **Ayuda y documentación (PUBLIC-F15, APP-PUBLIC-2):** `/documentation/` deja de ser «Muy pronto» y es un 301 a
  `/help/`, como `/company/` → `/about/`: la documentación que existe son las guías y la pestaña de cada app. Soporte
  ya no manda a «Ayuda y soporte › Reportar un problema» del Hub, que no existe.
- **Contacto (PUBLIC-F16–F18, APP-PUBLIC-2):** el correo al buzón de soporte lleva «Reply-To» la persona; un mensaje
  rechazado o que falla vuelve con lo escrito (borrador en la sesión, se enseña una vez); `?subject=<tema>` de
  `CONTACT_TOPICS` (`collaborate`, `security`) viaja al asunto y cualquier otro se ignora. El correo, el chat y el
  plazo (`SUPPORT_EMAIL`, `SUPPORT_WHATSAPP_URL`, `SUPPORT_REPLY_HOURS`) salen del procesador de contexto: ni
  «info@» ni «4 horas» escritos a mano. Como Intercom, HubSpot o Zendesk.
- **Cookies (PUBLIC-F19, APP-PUBLIC-2):** el aviso solo sale si hay un rastreador opcional configurado
  (`GA_MEASUREMENT_ID` o `CLARITY_PROJECT_ID`); sin ninguno (producción hoy) la web solo pone cookies técnicas, que
  no piden consentimiento (AEPD, ICO, CNIL; GitHub retiró su aviso por lo mismo). Los grupos de `init_cookie_groups`
  y `/cookies/` siguen: son la política y la elección el día que se mida.
- **Desde la app instalada (PUBLIC-F26, APP-PUBLIC-2):** los textos legales que enlaza la entrada de la SPA llevan
  `?surface=desktop|mobile|account` y se ven en modo aplicación (barra «Volver», sin menú, pie, aviso de cookies ni
  analítica), guardado en la sesión; como el visor in-app de Shopify POS o Square POS. Sin tocar ERPlora/app.
- **Correo de soporte (PUBLIC-F18):** también las páginas de error (`{% support_email %}`) y la SPA (`support-email`).
- **Descargas (PUBLIC-F24):** los dispositivos y usuarios del hub gratis de `/download/` son los del plan Gratis
  (`pricing.free_plan` y el parcial `pricing/_plan_limits.html`, el de la tabla de precios); sin plan Gratis, ninguno.

## Pruebas

- `uv run pytest -q public` (y `public/tests/test_<módulo>.py` por módulo).
- e2e: `tests/e2e/public-web.spec.ts` (parte 1) y `public-web-2.spec.ts` (parte 2; flujo a flujo, tres tamaños,
  CSP sin violaciones; los correos del formulario van a `.artifacts/public/mail*/`), `public-dark.spec.ts`,
  `demo-door.spec.ts` y `store-docs.spec.ts`; antes, `pnpm build` (el proyecto `public` sirve el build).
