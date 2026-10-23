# accounts

App de plataforma (`LiveAppConfig`, `kind = "platform"`) del plano de cuenta: quién entra (allauth, headless),
el salto a un negocio (`handoff.py`, `/internal/auth/redeem`) y **Cuenta** (Perfil · Seguridad · Preferencias ·
Claves de API; PLAN-SAAS §3.6, ronda 17). Este README recoge el lote **L3-A** (back) del plan
`docs/plans/2026-10-13-panel-saas-unificado.md`; el front (`frontend/`) es de L3-B. Los flujos de la app, en
lenguaje de usuario, están en `WORKBOOK.md` (y `WORKBOOK.en.md`), que crece por partes (MIGRATION-TASK
APP-ACCOUNTS-1…5).

## Operaciones de Cuenta (L3-A)

Todas con la sesión del SaaS (cookie + CSRF), permisos `accounts.view` / `accounts.manage` (rol `account`) y
solo sobre la cuenta que llama. Ninguna está expuesta a claves de API.

| Operación | Ruta | Qué hace |
|---|---|---|
| `accounts.profile.get` (viva) | `GET /api/accounts/profile` | Correo, `email_verified` (la regla de las invitaciones, `email_is_proven`), `pending_email`, nombres, `photo` (data URL), `has_password`, alta |
| `accounts.profile.update` | `POST /api/accounts/profile` | Nombre y apellidos (el correo tiene su puerta) |
| `accounts.profile.delete` | `POST /api/accounts/profile/delete` | 409 `accounts.owns_businesses` o `accounts.pays_businesses` (con `businesses`) si es propietario o pagador de algún negocio no eliminado; luego reautenticación; cierra todas sus sesiones, anonimiza su rastro en el outbox y borra la cuenta; sus pagadores (`hubs.BillingProfile`) y su cliente de Stripe los borra `billing.services.forget_departed_payer` tras el COMMIT, salvo lo que aún se puede cobrar (ACCOUNTS-F27) |
| `accounts.email.change` | `POST /api/accounts/email/change` | Código de 6 cifras al correo nuevo (o al propio, si no está verificado) |
| `accounts.email.verify` | `POST /api/accounts/email/verify` | El código, en la misma sesión: `verified` y `attempts_left` (un código incorrecto no es error: 200 con `verified: false`); si es bueno, la cuenta pasa al correo nuevo, verificado, y se avisa al antiguo |
| `accounts.photo.upload` / `.remove` | `POST /api/accounts/photo`, `…/photo/remove` | Foto (JPEG, PNG o WebP) limpia de metadatos |
| `accounts.preferences.get` (viva) / `.update` | `GET`/`POST /api/accounts/preferences` | `theme_mode` (`system`/`light`/`dark`), `language` (`User.language`), `hub_alerts` (avisos de mis negocios) |
| `accounts.data.export` | `GET /api/accounts/export` | «Descargar mis datos» (RGPD art. 20, ACCOUNTS-F26): un JSON con la cuenta, preferencias, foto, direcciones, Google enlazado, sesiones, claves (sin secreto), sus negocios (`hubs.business.list`) y las facturas de ERPlora que ve (`billing.invoice.get`); nada de otra cuenta |
| `accounts.session.list` (viva) | `GET /api/accounts/sessions` | Una página (`limit` ≤ 100, `offset`) de las sesiones vivas: `device` (código), `browser` + versión o `app_version`, `ip`, último uso, `is_current` (primero); `total` y `others` (las demás) cuentan todas |
| `accounts.session.close` / `.close_others` | `POST /api/accounts/sessions/close`, `…/close_others` | Cierra una (la propia también: cierra la sesión) o todas las demás |
| `accounts.browser_trust.get` | `GET /api/accounts/browser-trust` | `trusted_until`: hasta cuándo este navegador se salta el código de la app, o `null` (sin app, con `ACCOUNTS_MFA_ENABLED` apagado o con una huella de antes de otra contraseña o de dejar de confiar) |
| `accounts.browser_trust.revoke` | `POST /api/accounts/browser-trust/revoke` | Deja de confiar en todos los navegadores de la cuenta (ver «Segundo factor»); esta sesión sigue dentro |
| `accounts.apikey.list` (viva) | `GET /api/accounts/api-keys` | Claves no revocadas (las caducadas, marcadas) y el catálogo de `scopes` con su rótulo |
| `accounts.apikey.create` | `POST /api/accounts/api-keys` (201) | Reautenticación; devuelve la clave entera **una vez** (`secret`) y avisa por correo a la cuenta (sin la clave) |
| `accounts.apikey.revoke` | `POST /api/accounts/api-keys/revoke` | La corta al momento; dos veces no cambia nada |
| `accounts.support.report` | `POST /api/accounts/support/report` | «Reportar un problema» (ACCOUNTS-F38): un correo en inglés a `SUPPORT_EMAIL` con «Reply-To» la cuenta, el texto y debajo la cuenta, sus negocios (`HubMembership`), la página de la que viene y el navegador; 422 por campo, 429 `accounts.too_many_attempts` pasado `SUPPORT_REPORT_RATELIMIT` (5/h por cuenta), 503 `accounts.report_not_sent` si el correo no sale; no guarda nada ni registra el texto |

Eventos (`events.py`): `accounts.profile.updated`, `accounts.profile.deleted`, `accounts.email.change_requested`,
`accounts.preferences.updated`, `accounts.session.closed`, `accounts.browser_trust.revoked`,
`accounts.apikey.created`, `accounts.apikey.revoked`.
Sin ruta: `accounts.apikey.issue_any`, la «Añadir clave de API» del admin (solo el superusuario y solo para una
cuenta del equipo, ACCOUNTS-F31: `services.issue_api_key` desde `ApiKeyAdmin`, que enseña la clave una vez),
`accounts.apikey.revoke_any`, la «Revocar» del admin, y `accounts.session.close_any`, las dos acciones
«Cerrar sesiones» del admin (ACCOUNTS-F19: todas las de una cuenta y la confianza de sus navegadores, o las
elegidas en «Sesiones de usuario»; `services.close_sessions`), con contexto de sistema en el canal del dueño (su
lista viva se refresca); ningún rol tiene su permiso y en el admin solo las ve el superusuario.

## Decisiones

- **Entrada y código por correo en cada inicio de sesión** (Ioan, 2026-10-15): el formulario del lanzador
  `/launch` (`frontend/components/SignInForm.vue`) tiene dos pestañas estrictas (FIX-LAUNCH-TABS, PLAN-SAAS
  §3.7): «Entrar», por defecto, es el login de allauth y nunca crea cuenta (un correo desconocido recibe el
  mismo error que una contraseña errónea, con el enlace «¿Es tu primera vez? Crea tu cuenta»); «Crear cuenta»
  (`/launch?tab=signup`, adonde llevan `/accounts/signup/` y `HEADLESS_FRONTEND_URLS["account_signup"]`) es
  el alta de allauth y nunca entra (un correo ya registrado no se delata). Tras la contraseña, allauth manda siempre un código de 6 cifras a la cuenta,
  que se teclea en `/verify-email`: el que prueba el correo (`verify_email`) para un alta o una dirección nunca
  probada, y el de inicio de sesión (`login_by_code`, `ACCOUNT_LOGIN_BY_CODE_REQUIRED = {"password"}`) para el
  resto; `AccountAdapter.is_login_by_code_required` evita pedir los dos. Valores de allauth: 3 intentos, 3
  minutos; sin reenvío del de inicio de sesión (allauth solo lo reenvía con `ACCOUNT_LOGIN_BY_CODE_ENABLED`,
  que abriría la entrada solo con el código, sin contraseña): se pide otro entrando de nuevo. Google no pide
  código. Con la app autenticadora encendida, primero el código por correo y luego el de la app (orden de
  allauth). `/admin/login/` también pasa por este login. En local cada correo queda en `saas-next/.mail/`
  (`EMAIL_FILE_PATH`): el código se lee de ahí; las e2e, con `readMailCode` de `@erplora/ui/testing/mail`.
- **Reautenticación** (lo destructivo y lo que da acceso: eliminar la cuenta, crear una clave, cambiar a otro
  correo): un inicio de sesión de hace menos de 5 min (`ACCOUNT_REAUTHENTICATION_TIMEOUT`), según los registros
  de allauth. Más estricta que `did_recently_authenticate`, que deja pasar sin nada a una cuenta sin contraseña
  ni 2FA: aquí una cuenta solo de Google confirma entrando otra vez con Google (el redirect de proveedor de
  headless, `callback_url` = la misma página, que allauth registra). Si falta, 401 `reauthentication_required` con `flows` (`reauthenticate`,
  `mfa_reauthenticate`, `provider_redirect`) y `providers` (`google`); el panel confirma y repite. Una petición
  con clave de API nunca cuenta (403). `ACCOUNT_REAUTHENTICATION_REQUIRED = True` pide lo mismo a las puertas de
  allauth.headless que quedan (desconectar Google).
- **Puertas propias sobre allauth** (`doors.py`, montadas en `config/urls.py` antes del `include` de headless; en
  modo solo headless allauth no tiene páginas): `/_allauth/browser/v1/account/email` responde 404 a todo método
  (el correo solo cambia con el código de Cuenta) y `account/password/change` responde 403 a una cuenta sin
  contraseña (con la sola sesión no se pone una: se pone con «¿Has olvidado tu contraseña?»; con contraseña se
  cambia como siempre). `auth/login` y `auth/signup` son las dos pestañas de la entrada, servidas con una regla
  que headless deja fuera (APP-ACCOUNTS-1): la entrada pliega el correo como el alta (`adapters.plain_email`:
  NFKC, sin espacios y en minúsculas; «ana@ｅxample.com» es Ana, nunca otra cuenta, ERPlora/saas#1018) y el alta
  comprueba la contraseña contra su propio correo (headless la validaba sin cuenta y el validador de parecido
  no veía nada; saas#2542).
- **La contraseña nueva nunca es la actual** (`AccountAdapter.clean_password`, saas#2612): en «Cambiar
  contraseña» y en el enlace de «¿Has olvidado tu contraseña?», `password_unchanged` debajo del campo. La página
  del enlace enseña la misma pista y fuerza que Cuenta (`frontend/password.ts`, contra el correo que devuelve
  la comprobación del enlace).
- **Términos aceptados** (ACCOUNTS-F10): `User.terms_accepted_at`, `terms_version` y `privacy_version`
  (solo lectura en el admin). `services.accept_legal_texts` escucha `user_signed_up` (allauth, también el alta
  con Google) y `user_logged_in` (Django): guarda la fecha y las versiones vigentes (`models.TERMS_VERSION` y
  `PRIVACY_VERSION`, la fecha de «Last updated» de cada página legal) si la cuenta no las tenía; la primera
  fecha se queda mientras no cambien. Al actualizar `/legal/terms/` o `/legal/privacy/`, se cambia su fecha en
  `models.py` en el mismo cambio (`tests/test_terms.py` lo exige) y cada cuenta acepta la nueva al entrar.
- **Sesiones = `allauth.usersessions`** (encaja con headless: tiene `auth/sessions`). `SessionActivityMiddleware`
  apunta dirección, navegador y último uso como mucho cada 5 min (marca en la caché, releída antes de escribir:
  con Valkey caído no apunta nada en vez de escribir en cada petición; los límites sobre esa caché quedan
  abiertos, `RATELIMIT_FAIL_OPEN`), solo si la petición ya usó su sesión (cargarla borraría una cookie ilegible
  en la web pública, saas#975), solo la cuenta de esa sesión (nunca la de una clave de API) y recoge las
  sesiones abiertas por otra vía. La lista solo enseña las vivas
  (sesión existente, sin caducar y con el hash de la contraseña actual), sin escribir: una consulta trae las sin
  caducar con sus datos y el hash se comprueba en memoria (nada de cargar una sesión por fila), y el servidor la
  pagina, la actual primero (con más sesiones de las que caben en un resultado vivo no cargaba). Ubicación = IP
  (GeoIP fuera, plan §6). `UserSessionsAdapter` hace que cerrar por cualquier puerta avise a los negocios.
- **Segundo factor** (PLAN-SAAS, nota 2026-10-13 y ronda 19; ACCOUNTS-F05, F14–F17 y F20): `allauth.mfa` sobre
  headless, TOTP + códigos de recuperación, sin passkeys, detrás de `ACCOUNTS_MFA_ENABLED` (apagado por defecto en
  la fase 1: `MFAFlagMiddleware` responde 404 en sus rutas y `mfa.mfa_completed` es falso; nunca se cambia el
  valor por defecto sin decisión de fase). Las páginas son Vue (`/2fa`, `/2fa/authenticate`, `/reauthenticate`);
  las plantillas de allauth no existen. **Confiar en este navegador 14 días** = `MFA_TRUST_ENABLED` de allauth
  (etapa `mfa_trust` tras el código; cookie firmada solo en el host de erplora.com, `MFA_TRUST_COOKIE_DOMAIN =
  None`), lo que el SaaS viejo hacía con `TrustedDevice` + `MFA_TRUST_ENABLED`: aquí no hay modelo propio.
  `mfa.mfa_completed` cuenta la sesión que pasó la app **o** un navegador de confianza (lo lee el salto al Hub,
  `handoff.py`). La huella liga contraseña y autenticadores, así que «Dejar de confiar en todos»
  (`forget_trusted_browsers`, portado de `_invalidate_mfa_trust`) los vuelve a crear con otro id y los mismos
  datos y fechas: la app y los códigos siguen valiendo; `_follow_new_authenticator_ids` mueve los registros de
  esta sesión a los ids nuevos para que no pierda lo que probó. No hay lista de navegadores: allauth no guarda
  nada en el servidor. La página responde la etapa con `auth.mfaTrust` del SDK (ui#16); sin entrada esperando la
  pregunta allauth responde 401 sin flujo pendiente (nunca 409), y la página lee la sesión: dentro desde otra
  pestaña → sigue; caducada → la entrada. **Personal**: con el interruptor encendido,
  `admin_has_permission` (`admin.site.has_permission`, en `config/urls.py`) exige un TOTP (los códigos de
  recuperación solos no) y `admin_login` lleva al personal sin él a `/2fa?next=<ruta del admin>`, que ofrece
  «Continue» cuando la app está activa; el salto `hub-admin` lo exige siempre (`_needs_second_factor`).
- **Nombres en el índice del admin** (`AccountsConfig.ready`): la sección de la app `account` de allauth se llama
  «Email addresses» (solo guarda los correos; se llamaba «Accounts», como esta) y los autenticadores y las sesiones
  de allauth llevan nombre traducible (salía el de su clase, sin `es`). Solo lo que se ve: ni etiqueta, ni tabla,
  ni migración. Lo vigila `config/tests/test_admin_index.py` para toda app.
- **Señales hacia `hubs`** (`signals.py`; `accounts` nunca importa `hubs`): `sessions_ended(user_id)` al cerrar
  sesiones, eliminar la cuenta o poner contraseña nueva (`password_changed/set/reset` de allauth; PLAN-SAAS
  §2.1) y `account_deleting(user_id)` antes de borrar la cuenta. Al cambiar el correo se envía `email_changed`
  de allauth. Los propietarios se leen con la operación `hubs.business.list` (por nombre, `can.delete`).
- **Claves de API**: `erps_live_` + 48 base62 (se distinguen de las `erpk_live_` del Hub; plan §7 punto 12),
  SHA-256 y prefijo de 8 indexado; caducidad 30/90 días o nunca (90 por defecto); tope de 50 vivas por cuenta;
  `last_used_at` cada 10 min como mucho. Scopes `hubs.read`, `hubs.write`, `billing.read` (`<app>.read` abre
  las consultas de la app, `<app>.write` sus comandos), **solo** en operaciones con `expose_api=True`.
  `api_auth.install_api_key_auth(api)` (en `config/api.py`) pone delante de cada ruta con auth
  `ApiKeyBearer` (`Authorization: Bearer erps_live_…`) y `ApiKeyHeader` (`X-Api-Key`) si está expuesta, o
  `refuse_api_keys` (403 `api_key_not_allowed`) si no: una clave nunca gestiona la cuenta ni crea claves.
  Errores: 401 `api_key_invalid`, 403 `api_key_missing_scope` (nombra el scope), 429 `rate_limited` (600/min
  por clave; 30 claves malas/min por IP). Exponer una operación cuya app no tiene scope falla al arrancar.
- **Correo por código propio**: el SaaS antiguo usaba la verificación por código de allauth, que exige
  `ACCOUNT_EMAIL_VERIFICATION = "mandatory"` (check CRITICAL) y eso pararía en el login a toda cuenta sin
  correo verificado; el enlace de allauth dejaría que quien lo pulse (un correo mal escrito) se quede la cuenta.
  El cambio espera en `EmailChangeRequest` (uno por cuenta, atado a la sesión, hash del código, 15 min) y la
  cuenta conserva su correo hasta escribir el código, así que «¿Has olvidado tu contraseña?» no llega al nuevo.
  Los intentos se cuentan en la BD con un `UPDATE … attempts = attempts + 1` condicional (3 por código; dos
  peticiones a la vez no suman más), más 5/min y 20/h por cuenta y 3 códigos/h por dirección (caché). Un código
  incorrecto responde 200 `verified: false`: un error desharía el intento gastado. Dos cuentas verificando la
  misma dirección: 409 `accounts.email_taken`, también si lo detecta la BD. Pide contraseña y reautenticación
  salvo para verificar el propio correo.
- **Foto en la BD** (`ProfilePhoto`): el SaaS no tiene almacenamiento de media (`STORAGES["default"]` es el
  disco de la tarea, que se pierde en cada despliegue) y no hay librería de imágenes. `photos.py` reconoce el
  tipo por los bytes, limita a 150 KB y 2048 px por lado, rechaza animaciones y quita EXIF, XMP, IPTC, textos y
  comentarios, también entre los barridos de un JPEG progresivo, y lo que sigue al final del JPEG (un JPEG
  conserva solo la orientación). El panel debe reducir la foto antes de enviarla.
- **Preferencias**: solo el modo del tema y «Avisos de mis negocios» (la paleta, la moneda, el orden del menú y el
  modo desarrollador no siguen: una paleta, se cobra en euros, ronda 17). El idioma es `User.language`, el que ya
  leen los correos y el salto al Hub; siempre tiene valor.
- **Avisos por correo** (ACCOUNTS-F23): cada interruptor gobierna un correo que el SaaS manda de verdad.
  `hub_alerts` es el correo «tu negocio está listo» (`hubs.emails.send_ready` pregunta a
  `queries.receives_business_notices`). Sin interruptor, como GitHub y Stripe: códigos y avisos de seguridad,
  facturas y pagos fallidos (`billing.emails`), el negocio eliminado con su fecha de recuperación y lo que pide
  actuar (volver a conectar WhatsApp); las invitaciones y los traspasos van a quien los recibe. «Novedades de
  ERPlora» (`marketing_emails`) no gobernaba ningún correo y sale (como el SaaS viejo, SAAS_DASHBOARD-F211): la
  migración 0009 la quita del modelo y deja su columna con valor por defecto en la BD (expand/contract: las
  tareas de la versión anterior aún la leen durante el despliegue); su `DROP COLUMN` es el paso de contrato, en
  una versión posterior.

## Retención, auditoría y documentación de la API (parte 4)

- **`/api/docs`** (ACCOUNTS-F34): ReDoc de ninja servido por `accounts/api_docs.py` con el nonce de la CSP, sin
  CDN y solo con sesión (sin ella, a la entrada); `/api/openapi.json` sigue abierto (Postman, tests de otras apps).
- **`manage.py anonymize_old_users`** (F35, semanal) y **`manage.py cleanup_old_logs`** (F37, diaria): sin Celery,
  con candado de sesión propio (`services.run_exclusively`, gemelo del de `hubs`) y `--dry-run`. Los lanza
  `saas-cron` con sus valores por defecto: `anonymize-old-users-weekly` los lunes a las 00:35 UTC y
  `cleanup-old-logs-nightly` cada noche a las 00:45 UTC (`aws/stacks/prod/scheduler.tf`).
- **Registro de auditoría** (F36): `django-auditlog` (`accounts/auditlog.py`, desde `AccountsConfig.ready`) sobre
  `User` (sin `password` ni `last_login`), `HubMembership`, `ApiKey` (sin `key_hash` ni `last_used_at`) y
  `allauth.usersessions.UserSession` (sin `session_key`, `data` ni `last_seen_at`), todos con
  `serialize_auditlog_fields_only` (trampa #957 del viejo). `AuditActorMiddleware` sustituye al de la librería: la
  dirección es `REMOTE_ADDR` (ya resuelta por `public.client_ip`, nunca el primer `X-Forwarded-For`) y el autor se
  lee al escribir cada entrada, no al entrar la petición. `services.forget_deleted_actor` (`post_delete` de la
  cuenta) suelta el autor de las entradas escritas durante su borrado. Las etiquetas del admin del paquete, que no
  trae español, están en `locale/es` del proyecto.
- **Auditoría de cobro y fiscal** (F36, PLAN-SAAS §1.1): cada app registra los suyos con `accounts.auditlog.audit`
  (siempre `serialize_auditlog_fields_only`) desde su `ready()`: `billing/auditlog.py` (reglas y categorías de IVA,
  política fiscal sin sus acumulados OSS, datos de ERPlora, códigos promocionales sin su contador y sus usos, compras
  sin `client_secret`, cobros fallidos y facturas sin el enlace de Stripe, facturas sin su cola de envío, sus líneas y
  los cambios de plan que esperan; fuera, con su motivo en el test: `VatCheck`, `WebhookEvent`, `InvoiceCounter`,
  `OssNotice`), `fiscal/auditlog.py` (autorización y sello, sin sus documentos cifrados), `hubs/auditlog.py` (planes,
  pagador, suscripción sin `unpaid_invoice_url` y sus partidas) y `apps/auditlog.py` (`Module`). Sin `updated_at`. El
  registro solo lee un registro fiscal: escribe su propia tabla, y `cleanup_old_logs` poda también estas entradas.

## Plataforma del SaaS (parte 5)

La plataforma no vive en `accounts/` sino en `base/` y `config/`; su manual es `accounts/WORKBOOK.md`
(ACCOUNTS-F39–F48, con el detalle en «Para quien lo mantiene»).

- **Política de contenido** (F39): la del panel, `settings.SECURE_CSP` sobre `live.csp.base_policy` (y
  `base/csp.py`); la de la web pública, `public/csp.py`; la del admin, `base.csp.admin_policy` (la del panel sin
  Trusted Types, que el jQuery del admin de Django no soporta; trampa saas#1828 del viejo). `config/tests/test_csp_policy.py` las lee directiva a
  directiva con los ajustes de producción. Informes del navegador: `base/csp_report.py`, con
  `CSP_REPORT_RATELIMIT` (60/h por dirección).
- **Registro sin datos personales** (F40): `base/logging.py` (`GDPRSafeFormatter`), en `LOGGING`.
- **Arranque** (F41): `config/asgi.py` cierra el saludo de un WebSocket (`refuse_websockets`); `config/wsgi.py`.
- **Páginas de error y admin** (F42): `public.errors` y `templates/{404,500}.html`; la marca del admin, en
  `config/urls.py`.
- **Mantenimiento** (F43): `base.models.SiteSettings` (fila única, migración `base/0001`), su admin en
  `base/admin.py`, `base.queries.maintenance_state` y `base/maintenance.py`, con `templates/503.html`.
- **`manage.py purge_expired_sessions`** (F44, diaria): sesiones caducadas, filas de «Sesiones activas» sin sesión,
  códigos de salto y cambios de correo caducados (`services.purge_expired_sign_in_leftovers`), con candado y
  `--dry-run`. Sustituye a `clearsessions_task` y `flush_expired_tokens_task` del viejo (aquí no hay JWT). La lanza
  `saas-cron` cada noche a las 00:20 UTC (`purge-expired-sessions-nightly` de `aws/stacks/prod/scheduler.tf`).
- **Correos** (F46): `AWS_SES_CONFIG` en `config/settings.py` (3 s + 10 s, dos intentos); cada correo, en texto y en
  HTML sobre `templates/emails/base.html` con `base/emails.py` (`branded_message`); los de allauth, por
  `AccountAdapter.render_mail`, y sus avisos propios con su `_message.html` (`templates/account/email/`,
  `templates/socialaccount/email/`).
- No se portan `apps/core/circuit_breaker.py` (G06/G75) ni `templatetags/cards.py` (G27): motivo en el WORKBOOK.

## Tests portados de ERPlora/saas (`origin/develop`)

- `dashboard/profile/tests`: `test_api` (16) y `test_views` (27) → `test_profile`, `test_photos`,
  `test_delete_account` (sin dirección de facturación ni modo desarrollador: Facturación y ronda 17);
  `test_change_email` (24) → `test_email_change` (sin las páginas de plantilla ni «usar otro correo» del alta);
  `test_change_password_rate_limit` (10) → `test_password_change` (allauth.headless, una sola puerta);
  `test_delete_account_sole_owner` (15) → `test_delete_account` (un propietario por negocio: los casos de
  copropietario pasan a «administrador de otro negocio»). Fuera: `test_vendor_identity`, `test_view_mode*`,
  `test_account_surface*` (la superficie es de `base`).
- `dashboard/settings/tests`: `test_api` (17) y `test_views` (33) → `test_preferences` (solo modo, idioma y
  avisos); `test_theme_palette` (18) → solo el modo; `test_language_cache` (5) fuera (no hay caché: el idioma va
  en la fila de la cuenta); `test_language_unset_until_chosen` (9) fuera (`User.language` siempre tiene valor).
- `dashboard/settings` «Descargar mis datos» (`export_data`) → `test_export` (ACCOUNTS-F26; sin lo del vendedor:
  no hay marketplace); los avisos (SAAS_DASHBOARD-F211, cuyos interruptores no leía nadie) → `test_notices`
  (ACCOUNTS-F23).
- `auth/apikeys/tests` (80) → `test_models`, `test_api_keys`, `test_api_auth`, `test_admin`. Fuera: claves de
  hub y su gracia (hub-next), entorno `pre`, scopes de flota/vendedor y el script de emisión.
- `tests/unit/test_gdpr_retention_policy.py`, `test_gdpr_retention_noinput.py` y
  `apps/auth/users/tests/test_anonymize_skips_hub_owners.py` → `test_anonymize_old_users` y `test_cleanup_old_logs`
  (sin `--no-input`: nunca preguntan); `tests/unit/test_auditlog_coverage.py` → `test_auditlog` de `accounts`,
  `billing`, `fiscal`, `hubs` y `apps` (sin `Payout` ni `StripeConnectAccount`: no hay marketplace); «Reportar un problema» (SAAS_DASHBOARD-F219) →
  `test_support_report`.
- Parte 5: `apps/core/tests/test_logging.py` → `base/tests/test_logging.py`; la CSP, con tests nuevos
  (`config/tests/test_csp_policy.py`, una directiva por test, panel y web pública); el `MaintenanceModeMiddleware` y el `SiteSettingsAdmin` →
  `base/tests/test_maintenance.py`, `test_models.py` y `test_admin.py`, con sus dos huecos cerrados (la salud en 503
  y el segundo factor del personal cortado); `apps/core/tests/test_branded_emails.py` → `base/tests/test_emails.py`
  (cada familia por su remitente, en `en` y `es`, y cada correo de allauth hallado en disco). Fuera: los tests del
  breaker y de la etiqueta `card`, que no se portan.

## Pendiente (de otros carriles)

- **`hubs`**: sus correos (`hubs/emails.py`: personas, invitaciones, roles y traspaso) pasan a la plantilla común
  (`base/emails.py`, ACCOUNTS-F46) con su porte; hoy salen en texto.

- **`hubs`** conecta `signals.sessions_ended` → `revoke_after_commit(user_id)` y `account_deleting` (en curso en
  su carril); también puede escuchar `allauth.account.signals.email_changed` para refrescar la foto del negocio.
- **`live`**: `record_event` guarda `actor=str(ctx.actor)`, el correo de la cuenta. El arreglo bueno es guardar
  el id en `live.outbox` (próximo lote de `live`); mientras, eliminar una cuenta pasa sus filas al id
  (`services.forget_in_outbox`).
