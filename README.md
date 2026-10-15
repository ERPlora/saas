# saas-next

`erplora.com` de ERPlora Next (en local, `http://localhost:8001`). Los hubs son `<slug>.erplora.com`
(en local, `a.localhost:8000`) y `hubs.erplora.com` es el admin del Hub para el personal (PLAN §18;
en local, `hubs.localhost:8000`): los sirve `hub-next`, nunca el SaaS. Planes: `../PLAN-SAAS.md` (contrato con el Hub en §2, flujos en §3, qué se
porta en §6).

## Fase 1 (S1): entrar y saltar a un hub

Solo lo que necesita el salto al Hub (PLAN-SAAS §2.1 y §3.1, pasos 4–6; PLAN §16.12):

- **Login de allauth con las plantillas del SaaS de hoy** (`templates/account/`, portadas de
  `ERPlora/saas` `origin/develop` `c5ca8cae8`): mismo marcado Ionic, mismos estilos, Ionic e Iconify
  servidos desde `static/vendor/` (sin CDN). **Nota:** son plantillas Django; la versión de la
  ronda 9 (páginas Ionic Vue con `allauth.headless`) llega en el **bloque 1a** y sustituye a estas.
- **«Continuar con Google»** (`allauth.socialaccount`, portado del SaaS de hoy; ver «Google» abajo).
- `/launch` (página Ionic Vue `accounts/frontend/pages/LaunchPage.vue`, lee
  `accounts.hub.list` = `GET /api/accounts/hubs`): con un hub, salta a él; con varios, selector; con
  ninguno, lo dice. `GET /launch/` (la dirección de antes) solo redirige a `/launch`.
- `/login/error?code=…` (página Ionic Vue `LoginErrorPage.vue`): todo inicio de sesión o salto
  rechazado (`invalid_hub`, `not_a_member`, `google_no_account`, `authentication_error`,
  `login_cancelled`), con los textos de las plantillas que sustituye.
- `GET /hub-login/?hub=<slug>&next=<ruta>`: slug no válido → `/login/error?code=invalid_hub` (regla
  compartida con el Hub, `live.slugs`: una etiqueta DNS de 3 a 63 caracteres —1 en local, por los
  hubs `a` y `b`— y nunca un nombre reservado como `hub`, `www` o `admin`); sin sesión →
  `/accounts/login/?next=…`; sin ser miembro → `/login/error?code=not_a_member&hub=<slug>`; si no, acuña un `AuthExchangeCode` (32 bytes, guardado como SHA-256, audiencia
  `hub-session`, 60 s, un uso) y responde un formulario auto-enviado (`POST` a
  `HUB_CALLBACK_TEMPLATE`, campos `code` y `next`).
- `POST /internal/auth/redeem` (servidor a servidor, firmado): cuerpo `{"code", "hub", "audience"?}`,
  cabeceras `X-Erplora-Timestamp` y `X-Erplora-Signature` (v1: HMAC-SHA256 hex de `"{timestamp}.{cuerpo}"`,
  la que firma hoy el Hub) o, si viene, `X-Erplora-Signature-V2` (cubre también método y ruta; entonces decide
  solo ella), con `INTERNAL_SHARED_SECRET` o, durante una rotación, `INTERNAL_SHARED_SECRET_PREVIOUS`, ±300 s
  (`accounts/signing.py`, L1-A2). Sin `audience` es `hub-session` (un miembro entra en su hub);
  con `"hub-admin"` canjea el salto del personal al admin del Hub (ronda 13, PLAN §18). 200 →
  `{user_id, email, name, locale, role}` (`hub_*` del miembro, o `platform_admin`/`platform_support`
  con `hub-admin`); 401 `unauthorized`; 400 `invalid_code` (también si `hub` no es un slug válido,
  es reservado o es `hubs`, o si el código es de la otra audiencia) o `invalid_request`.
- **«Abrir en el admin del Hub»** (admin del SaaS, ronda 13, PLAN §18.1.6): en cada fila de
  `/admin/accounts/hubmembership/` y en la página «Hubs» (`/admin/accounts/hubs/`, un hub por fila).
  `GET /admin/accounts/hubmembership/open-hub-admin/<slug>/` acuña un código `hub-admin` (solo
  personal activo con rol de plataforma; sin pertenencia al hub) y responde el mismo formulario
  auto-enviado: `POST` a `HUB_ADMIN_CALLBACK_URL` con `code` y `next=/admin/hub/<slug>/`. Con
  `ACCOUNTS_MFA_ENABLED` activo exige además el segundo factor en la sesión (ver «Segundo factor (2FA)»).
- Cierre de sesión: `POST /accounts/logout/` (allauth).

## SPA Ionic Vue (ronda 11): paso 1, login

El SaaS es también una SPA Ionic Vue, igual que `hub-next` (`base/`, `frontend/main.ts`,
`vite.config.ts`, `<app>/frontend/`). Sus apps (`accounts/` Cuenta, `hubs/` Negocios y uso, `billing/`
Tienda, Facturación y Stripe, `fiscal/` la documentación fiscal de VeriFactu, más `apps/`, el catálogo de
módulos de la ronda 16, y `public/`, la web pública) viven en la raíz, junto a `base/`: `saas-next` no tiene carpeta de módulos (PLAN §20.2), y cada app
con `frontend/` se nombra en los globs de `frontend/main.ts` y en `FRONTEND_APPS` de `vite.config.ts`
(guardarraíles en `frontend/main.test.ts` y `vite.config.test.ts`). Las páginas de cuenta pasan
de plantilla a Vue **una a una**, sobre `allauth.headless` (cliente `browser`, `/_allauth/browser/v1/…`); mientras tanto las
plantillas siguen vivas (`HEADLESS_ONLY = False`) y `LOGIN_URL` sigue siendo `/accounts/login/`.

- `/login`: `accounts/frontend/pages/LoginPage.vue`, la misma página que
  `templates/account/login.html` (mismos msgids, `frontend/locale/{en,es}.json`). Sin «Mantener la
  sesión iniciada»: headless no recibe `remember` y la sesión dura `SESSION_COOKIE_AGE`.
  «¿Olvidaste tu contraseña?» lleva a `/accounts/password/reset/` hasta que exista su página Vue;
  «Continuar con Google» es un formulario `POST` normal a `/auth/google/login/` (con el token CSRF de
  la cookie), visible si `spa-config.googleEnabled`.
- `base`: `base.session.me` (ámbito = el usuario, `UserContextBuilder`), `GET /api/me`, el HTML de la
  SPA (`base/spa.py`, sobre `live.spa`) para toda ruta sin URL propia de Django y `/healthz` como
  primer middleware.
- `HEADLESS_FRONTEND_URLS` se rellena **con cada página**: allauth construye con ellas los enlaces de
  sus correos aunque `HEADLESS_ONLY` sea `False`, y una ruta de la SPA sin página sería un enlace muerto.
- Vite en el puerto **5174** (el 5173 es del Hub): `runserver` lo arranca (`--novite` lo omite).

## Segundo factor (2FA)

App autenticadora (TOTP) y códigos de recuperación con `allauth.mfa`, como el SaaS de hoy
(`accounts/mfa.py`, tests en `accounts/tests/test_mfa.py`). `allauth.mfa` está siempre
instalado (su tabla existe siempre); lo enciende el flag `ACCOUNTS_MFA_ENABLED`, **apagado por
defecto en la fase 1**.

- **Encenderlo**: `ACCOUNTS_MFA_ENABLED=true` en `saas-next/.env` (o en el entorno del proceso) y
  reiniciar. Apagarlo es quitar la línea: las cuentas conservan sus autenticadores, pero ningún login
  pide el código.
- **Apagado** (por defecto): ningún login pide código, ni a una cuenta que ya tenga app
  (`MFAAdapter`). Los endpoints de 2FA responden 404: los de headless
  (`/_allauth/browser/v1/account/authenticators…` y `…/auth/2fa/…`) con el JSON `{"status": 404}`, que
  es como la SPA sabe que está apagado, y las plantillas `/accounts/2fa/…` con el 404 de Django. El
  salto a un hub y el admin, como siempre.
- **Encendido**:
  - Una cuenta con app, tras la contraseña (o Google), queda pendiente del código: headless responde
    401 con el flujo `mfa_authenticate` pendiente y el código va a
    `POST /_allauth/browser/v1/auth/2fa/authenticate` (vale también un código de recuperación, de un
    solo uso). Una cuenta sin app entra como siempre.
  - «Segundo factor completado» (`mfa_completed`) = la cuenta tiene app **y** la sesión registra un
    código de uno de sus autenticadores, dado al entrar o al reautenticarse.
  - `/hub-login/`: si la cuenta tiene app y la sesión no completó el segundo factor (p. ej. entró por
    el `/admin/login/` de Django), no acuña código y redirige a
    `/reauthenticate?method=totp&flows=mfa_reauthenticate&next=<ruta y query>`, la página Vue que pide
    el código con `POST /_allauth/browser/v1/auth/2fa/reauthenticate` y vuelve a `next`. `flows` limita
    lo que ofrece: reautenticarse con la contraseña no completa el segundo factor. Una cuenta sin app
    salta como siempre.
  - «Abrir en el admin del Hub» (`hub-admin`) exige siempre el segundo factor completado: si no, no
    hay código, sale el mensaje «Activa la verificación en dos pasos y vuelve a iniciar sesión antes de
    abrir el admin del Hub.» y vuelve a la lista de pertenencias.
  - `/admin/login/` deja de ser el login de Django (no pide código): redirige a
    `/accounts/login/?next=…` (allauth, con su paso del código en `/accounts/2fa/authenticate/`, de
    momento con la plantilla por defecto de allauth). No inicia sesión ni por `POST`; con sesión y sin
    permiso de admin, 403 (el login de allauth devolvería a `/admin/` en bucle).
- **Activarlo un usuario** (con el flag encendido), en la SPA, `/2fa`: escanear el QR con la app (o
  teclear la clave manual), confirmar con un código y guardar los códigos de recuperación (10, de 8
  cifras, un uso cada uno). Al entrar, el código de la app o, sin el móvil, uno de recuperación. Para
  desactivarlo, `/2fa` pide antes reautenticarse. allauth no deja activarlo con un email sin verificar
  (409 `unverified_email`).
- Ajustes: `MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]`, emisor `ERPlora`, ±1 periodo (30 s) de
  desfase del reloj del móvil; sin llaves de acceso (passkeys) ni «confiar en este navegador».

## Google

Mismo comportamiento que el SaaS de hoy (ADR-0154; `accounts/{google,adapters,context_processors}.py`,
`templates/account/login.html`, `templates/socialaccount/`):

- **Rutas**: `POST /auth/google/login/` (el botón; un `GET` solo pinta la pasarela que se auto-envía,
  `SOCIALACCOUNT_LOGIN_ON_GET=False`) y `GET /auth/google/callback/`. Llevan los nombres de allauth
  (`google_login`, `google_callback`), declarados después de `allauth.urls`, para que el
  `redirect_uri` de la autorización y el del canje del código sean los dos `/auth/google/callback/`.
  Ojo: en el SaaS de hoy (allauth 65.18) la autorización salía con `/accounts/google/login/callback/`
  aunque la vista fijaba otra ruta.
- **Credenciales**: `GOOGLE_OAUTH_CLIENT_ID` y `GOOGLE_OAUTH_CLIENT_SECRET` (entorno o `saas-next/.env`,
  nunca una fila `SocialApp`). En local son opcionales: sin ellas el botón no aparece, las dos rutas
  dan 404 y `check` lo avisa (`accounts.I001`). En producción (`DEBUG=False`) son obligatorias: sin
  ellas el proceso no arranca.
- **URI de redirección autorizadas** en Google Cloud Console (cliente OAuth «Aplicación web»):
  `https://erplora.com/auth/google/callback/` (producción) y
  `http://localhost:8001/auth/google/callback/` (local). No hace falta tocar `Site`: la URI se
  construye con el `Host` de la petición, y en producción con `https`
  (`ACCOUNT_DEFAULT_HTTP_PROTOCOL`). En local el SaaS vive en `localhost` y no en un subdominio
  porque Google rechaza las URI de subdominios de `.localhost` («must end with a public top-level
  domain»); como el login y `/hub-login/` comparten host, el salto a un hub local también se
  prueba entrando con Google.
- **Reglas**: ámbitos `profile email`, `access_type=online`, PKCE (`S256`), sin guardar tokens. Un
  Google cuyo email **verificado por Google** es el de una cuenta entra en ella y queda vinculado
  (se avisa al dueño por correo); si esa cuenta nunca verificó su email, allauth le borra la
  contraseña (defensa de allauth, igual que hoy: desde entonces, Google o «¿Has olvidado tu
  contraseña?»). Un email sin cuenta **no** crea ninguna (el alta está cerrada): redirige a
  `/login/error?code=google_no_account&email=…` («No hay ninguna cuenta de ERPlora para esta cuenta
  de Google»); cualquier otro fallo, a `/login/error?code=authentication_error`. No hay pantalla para
  «conectar» Google con la sesión abierta (`/accounts/3rdparty/` → `/launch`, saas#2552). Cancelar en
  Google vuelve al login Vue (`/login`) conservando `next`, así que `/hub-login/?hub=…&next=…` sigue
  funcionando tras Google.

## Panel único (ronda 17): Stripe, facturas y uso

El panel de `erplora.com` (Negocios · Tienda · Facturación · Cuenta; plan
`../docs/plans/2026-10-13-panel-saas-unificado.md`, PLAN-SAAS §3.6). Detalle por app en
`accounts/README.md`, `hubs/README.md` y `billing/README.md`.

- **Variables nuevas** (todas con valor por defecto; en AWS, las claves de Stripe vienen de Secrets
  Manager): `STRIPE_SECRET_KEY` (en producción, **restringida** `rk_live_…`; con `sk_live_…`
  `check --deploy` falla con `billing.E001`), `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`,
  `STRIPE_TIMEOUT_SECONDS`, `STRIPE_PORTAL_CONFIGURATION` (`bpc_…`; vacía, el portal no abre),
  `PLATFORM_INVOICING_ENABLED` (por defecto `false`: ninguna clave live cobra hasta que el hub de
  plataforma emite las facturas), `VIES_ENDPOINT`, `VIES_CONNECT_TIMEOUT_SECONDS`, `VIES_TIMEOUT_SECONDS`,
  `VAT_CHECK_RATE`, `VAT_CHECK_GLOBAL_RATE`, `PROMO_CHECK_RATE` e `INTERNAL_SHARED_SECRET_PREVIOUS`.
- **Tareas programadas** (`saas-cron`, `aws-next/stacks/prod/scheduler.tf`): `sweep_unpaid` (cada hora),
  `reconcile_platform_invoices` (cada 15 min) y `collect_hub_usage` (01:15 UTC), además de
  `reconcile_hub_states`, `push_hub_snapshots` y `report_seal_expiry`. En `saas-migrate`, tras `migrate`:
  `sync_hub_plans` y `seed_taxonomy`. Todas idempotentes y con advisory lock (una segunda ejecución vuelve
  al momento).
- **Local**: con claves de prueba de Stripe en `.env` y `stripe listen --forward-to
  localhost:8001/webhooks/stripe/` (su `whsec_…` en `STRIPE_WEBHOOK_SECRET`); sin clave, la Tienda dice que
  los pagos no están disponibles (503 `billing.payments_unavailable`).

## Documentación fiscal (VeriFactu): `fiscal/`

La autorización que firma un negocio para que ERPlora remita sus registros VeriFactu a la AEAT (Anexo I del
convenio 017, representación directa; plan `../docs/plans/2026-10-15-saas-revision-documentacion-fiscal.md`).
El cliente la sube desde el módulo VeriFactu de su Hub, que la envía firmada a
`POST /internal/hubs/{id}/representation` (hasta cuatro PDF de 5 MB en base64; el cuerpo lo lee la propia
vista, con su tope de 32 MB, y el resto del sitio conserva el de Django); `GET /internal/representation/model`
sirve el modelo en blanco. El staff la revisa en `/admin/fiscal/representationgrant/` (aprobar, devolver o
retirar, siempre con motivo para el cliente, por los servicios de `fiscal/services.py`); el grupo `support`
solo la ve. El estado viaja al Hub en la foto (`verifactu.representation` de `PUT /internal/hubs/{id}/state`)
y el panel lo enseña en la ficha del negocio (`fiscal.representation.status`).

- **Variable**: `FISCAL_DOCUMENTS_KEY`, clave Fernet con la que se cifran los documentos en la BD
  (`fiscal/crypto.py`). Obligatoria en producción (Secrets Manager): un documento guardado con una clave
  perdida se pierde; `check` avisa si no es una clave Fernet (`fiscal.E001`). Con `DEBUG` hay una clave local
  fija.

## Entornos y ramas: `prod` y `pre`

`ERPLORA_ENVIRONMENT` dice qué despliegue es el proceso: `prod` (`erplora.com`; también por defecto en local
y en los tests) o `pre`, la preproducción del equipo en `pre.erplora.com`, en el mismo cluster, ALB, Aurora y
Valkey que prod (plan `../docs/plans/2026-10-14-entorno-pre.md`). Cualquier otro valor no arranca. En `pre`:

- la caché de Valkey usa el prefijo `pre-saas` (prod, `saas`): no comparten límites ni claves;
- nada se indexa: `robots.txt` responde `Disallow: /` sin `Sitemap`, toda respuesta lleva `X-Robots-Tag:
  noindex, nofollow, noarchive` e `indexnow_submit` falla;
- Stripe va solo en modo test: una clave live (`sk_live_`, `rk_live_` o `pk_live_`) falla `check --deploy`
  (`billing.E002`) y la pasarela no la usa (503, como sin clave). Detalle en `billing/README.md`;
- las direcciones son las de pre, por entorno (las pone `aws-next`, `stacks/prod/pre_apps.tf`): `PUBLIC_HOST`
  (`pre.erplora.com`), `HUB_CALLBACK_TEMPLATE` (`https://{slug}.pre.erplora.com/auth/callback`),
  `HUB_ADMIN_CALLBACK_URL` y `HUB_STATIC_BASE_URL` (`hubs.pre.erplora.com`), `HUB_INTERNAL_URL`
  (`http://hub-pre.erplora.internal:8000`), BD `pre_saas` con los roles `pre_saas_app` y `pre_saas_migrator`,
  y HSTS de un día.

**Flujo de ramas** (CI/CD):

1. Se trabaja en una rama propia; cada push corre `test / test` (`ci.yml`, que llama a `test.yml`).
2. Si `pre` avanzó, se integra `origin/pre` en la rama y se empuja otra vez.
3. Con el check en verde, `git push origin <rama>:pre` (fast-forward). `deploy.yml` prueba, construye la imagen
   en `erplora/saas-pre` y despliega `saas-pre` (`ecs-deploy.sh` con `ENVIRONMENT=pre`: familias
   `erplora-pre-saas` y `erplora-pre-saas-migrate`, sin `saas-cron`; `/erplora/pre/saas/image_tag`). Si pre
   estaba apagado, lo enciende. Sin release.
4. Probado, PR `pre` → `main` con «Create a merge commit»: despliega prod como siempre, con su release
   `saas-v…`.
5. Después, `git push origin main:pre` (fast-forward) para que `pre` no se separe de `main`.

Relanzar pre: `gh workflow run deploy.yml --repo ERPlora/saas --ref pre -f environment=pre`. Volver a la revisión
anterior: `gh workflow run rollback.yml --repo ERPlora/saas --ref pre -f environment=pre -f confirm=ROLLBACK`
(en prod, `--ref main -f environment=prod`). Una ejecución manual tiene que nombrar el entorno de su rama, y
las releases solo se redespliegan en prod (`.github/scripts/deploy-env.sh`). prod y pre no se esperan entre
sí: el grupo de concurrencia es por rama.

**Guarda de entorno.** `ecs-deploy.sh` y `ecs-rollback.sh` solo copian o restauran revisiones con la etiqueta
`Environment=<entorno>` y los roles `erplora-<entorno>-*`; si no, fallan sin registrar ni cambiar nada (el rol
de despliegue de un entorno puede registrar revisiones en cualquier familia: `ecs:RegisterTaskDefinition` no
admite recurso). Por eso el primer despliegue de prod con esta CI exige antes el `apply` de `aws-next` que
etiqueta las revisiones de prod (paso H1 del plan).

**Variables del repo:** `AWS_REGION`, `ALB_DNS_NAME` (el mismo ALB para los dos), `AWS_DEPLOY_ROLE_ARN`
(`gha-deploy-saas`, confía en `main`), `AWS_DEPLOY_ROLE_ARN_PRE` (`gha-deploy-saas-pre`, confía en `pre`) y,
opcional, `BUILD_RUNNER`. Sin la variable del entorno, el despliegue falla; nunca toma la del otro.

## Arrancar en local

Postgres del `compose.yaml` raíz (BD `saas`). El SaaS lee solo el entorno del proceso y
`saas-next/.env`, nunca el `.env` raíz (su `DB_NAME` es el del Hub). `DEBUG` está apagado por defecto
(producción): en local, `cp .env.example .env`, que lo enciende (`DEBUG=True`); `demo_seed` se niega a
correr sin él. Los tests no lo necesitan: `pytest.ini` usa `config/settings_pytest.py`. Variables propias:
`INTERNAL_SHARED_SECRET` (por defecto local, la misma que el Hub; `INTERNAL_SHARED_SECRET_PREVIOUS`, vacía
salvo durante una rotación), `HUB_CALLBACK_TEMPLATE`
(`http://{slug}.localhost:8000/auth/callback`), `HUB_ADMIN_CALLBACK_URL`
(`http://hubs.localhost:8000/auth/callback`; en producción `https://hubs.erplora.com/auth/callback`),
`FISCAL_DOCUMENTS_KEY` (con `DEBUG`, una clave local; ver «Documentación fiscal») y, para ver el botón de
Google,
`GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET`; ver `.env.example`. El
segundo factor se enciende con `ACCOUNTS_MFA_ENABLED=true` en `saas-next/.env` (por defecto `false`;
ver «Segundo factor (2FA)»).

Todo se corre dentro de este repo (`saas-next/`), que monta `ERPlora/live` y `ERPlora/ui` como submódulos en
`packages/`:

```bash
git submodule update --init && uv sync && pnpm install   # tras clonar o cambiar de rama
cp .env.example .env                     # la primera vez: DEBUG=True y los valores locales
uv run python manage.py migrate
uv run python manage.py demo_seed        # (de hubs) negocios a y b adoptados; owner@example.com / owner (hub_owner de a y b, sin admin), employee@example.com / employee (hub_employee de a y b: solo ve Demo, DEMO-F06) y platform@example.com / platform (superusuario, sin hubs)
uv run python manage.py create_platform_user <email> --role admin|support [--password …]   # staff de plataforma
uv run python manage.py runserver 127.0.0.1:8001   # también Vite (`pnpm run dev`) en :5174 (`--novite` lo omite)
# http://localhost:8001/login (Vue) · http://localhost:8001/accounts/login/ (plantilla)
# Admin del Hub de un hub: http://localhost:8001/admin/ con platform@example.com / platform → Hubs
# → «Abrir en el admin del Hub» → http://hubs.localhost:8000/admin/hub/a/ (el lado del Hub llega con
# la ronda 13 del carril de hub-next)
uv run pytest -q
pnpm test     # y typecheck, lint, build
pnpm e2e --project=panel   # e2e del panel, sin ventana (`pnpm e2e:headed` la abre)
```

## Fuera de la fase 1

Cada punto tiene su borrador de issue en `docs/issues/` (pendiente de abrir en `ERPlora/saas`):

- Alta (pantalla única de ADR-0154): cerrada por el adapter; las cuentas las crea el staff
  (`signup-closed.md`).
- Del segundo factor: «confiar en este navegador» 14 días (`MFA_TRUST`), llaves de acceso
  (WebAuthn/passkeys) y las plantillas de marca de `/accounts/2fa/…` (hoy, las de allauth por
  defecto). Sin borrador de issue todavía.
- Recuperación de contraseña con las plantillas del SaaS (el enlace lleva a la de allauth por
  defecto) y el correo de marca (`password-reset-default-template.md`).
- Cerrar las sesiones del Hub al cerrar sesión o cambiar la contraseña en el SaaS (L3-A). Al quitar un
  miembro, cambiarle el rol o aceptar un traspaso ya se cierran, con reintentos (`hubs.SessionRevocation`,
  L1-A2; `member-removal-keeps-hub-session.md`).
- Que el salto lea `HubMember` y retirar `HubMembership(user, hub_slug, role)`, que desde L1-A2 es solo el
  espejo de los miembros de cada negocio (`hubs/README.md`, «Pendiente»; `membership-by-slug.md`).
- Selector con el último hub usado primero (`hub-selector-last-used.md`); throttling de login
  (`login-lockout.md`) y «recordarme» deslizante (`remember-me-not-sliding.md`).
