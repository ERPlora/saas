# accounts

App de plataforma (`LiveAppConfig`, `kind = "platform"`) del plano de cuenta: quién entra (allauth, headless),
el salto a un negocio (`handoff.py`, `/internal/auth/redeem`) y **Cuenta** (Perfil · Seguridad · Preferencias ·
Claves de API; PLAN-SAAS §3.6, ronda 17). Este README recoge el lote **L3-A** (back) del plan
`docs/plans/2026-10-13-panel-saas-unificado.md`; el front (`frontend/`) es de L3-B.

## Operaciones de Cuenta (L3-A)

Todas con la sesión del SaaS (cookie + CSRF), permisos `accounts.view` / `accounts.manage` (rol `account`) y
solo sobre la cuenta que llama. Ninguna está expuesta a claves de API.

| Operación | Ruta | Qué hace |
|---|---|---|
| `accounts.profile.get` (viva) | `GET /api/accounts/profile` | Correo, `email_verified` (la regla de las invitaciones, `email_is_proven`), `pending_email`, nombres, `photo` (data URL), `has_password`, alta |
| `accounts.profile.update` | `POST /api/accounts/profile` | Nombre y apellidos (el correo tiene su puerta) |
| `accounts.profile.delete` | `POST /api/accounts/profile/delete` | 409 `accounts.owns_businesses` o `accounts.pays_businesses` (con `businesses`) si es propietario o pagador de algún negocio no eliminado; luego reautenticación; cierra todas sus sesiones, anonimiza su rastro en el outbox y borra la cuenta |
| `accounts.email.change` | `POST /api/accounts/email/change` | Código de 6 cifras al correo nuevo (o al propio, si no está verificado) |
| `accounts.email.verify` | `POST /api/accounts/email/verify` | El código, en la misma sesión: `verified` y `attempts_left` (un código incorrecto no es error: 200 con `verified: false`); si es bueno, la cuenta pasa al correo nuevo, verificado, y se avisa al antiguo |
| `accounts.photo.upload` / `.remove` | `POST /api/accounts/photo`, `…/photo/remove` | Foto (JPEG, PNG o WebP) limpia de metadatos |
| `accounts.preferences.get` (viva) / `.update` | `GET`/`POST /api/accounts/preferences` | `theme_mode` (`system`/`light`/`dark`), `language` (`User.language`), `hub_alerts`, `marketing_emails` |
| `accounts.session.list` (viva) | `GET /api/accounts/sessions` | Sesiones vivas: `device` (código), `browser` + versión o `app_version`, `ip`, último uso, `is_current` (primero) |
| `accounts.session.close` / `.close_others` | `POST /api/accounts/sessions/close`, `…/close_others` | Cierra una (la propia también: cierra la sesión) o todas las demás |
| `accounts.apikey.list` (viva) | `GET /api/accounts/api-keys` | Claves no revocadas (las caducadas, marcadas) y el catálogo de `scopes` con su rótulo |
| `accounts.apikey.create` | `POST /api/accounts/api-keys` (201) | Reautenticación; devuelve la clave entera **una vez** (`secret`) y avisa por correo a la cuenta (sin la clave) |
| `accounts.apikey.revoke` | `POST /api/accounts/api-keys/revoke` | La corta al momento; dos veces no cambia nada |

Eventos (`events.py`): `accounts.profile.updated`, `accounts.profile.deleted`, `accounts.email.change_requested`,
`accounts.preferences.updated`, `accounts.session.closed`, `accounts.apikey.created`, `accounts.apikey.revoked`.
Sin ruta: `accounts.apikey.revoke_any`, la «Revocar» del admin, con contexto de sistema en el canal del dueño
(su lista viva se refresca); ningún rol tiene su permiso.

## Decisiones

- **Entrada y código por correo en cada inicio de sesión** (Ioan, 2026-10-15): un único formulario entra y da
  de alta, dentro del lanzador `/launch` (`frontend/components/SignInForm.vue`; `unified_login.py` decide entre
  el login y el alta de allauth). Tras la contraseña, allauth manda siempre un código de 6 cifras a la cuenta,
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
- **Puertas de allauth cerradas** (`doors.py`, montadas en `config/urls.py` antes del `include` de headless; en
  modo solo headless allauth no tiene páginas): `/_allauth/browser/v1/account/email` responde 404 a todo método
  (el correo solo cambia con el código de Cuenta), `auth/signup` también (el login da de alta) y
  `account/password/change` responde 403 a una cuenta sin contraseña (con la sola sesión no se pone una: se pone
  con «¿Has olvidado tu contraseña?»; con contraseña se cambia como siempre).
- **Sesiones = `allauth.usersessions`** (encaja con headless: tiene `auth/sessions`). `SessionActivityMiddleware`
  apunta dirección, navegador y último uso como mucho cada 5 min (marca en la caché, releída antes de escribir:
  con Valkey caído no apunta nada en vez de escribir en cada petición; los límites sobre esa caché quedan
  abiertos, `RATELIMIT_FAIL_OPEN`), solo si la petición ya usó su sesión (cargarla borraría una cookie ilegible
  en la web pública, saas#975), solo la cuenta de esa sesión (nunca la de una clave de API) y recoge las
  sesiones abiertas por otra vía. La lista solo enseña las vivas
  (sesión existente, sin caducar y con el hash de la contraseña actual), sin escribir. Ubicación = IP (GeoIP
  fuera, plan §6). `UserSessionsAdapter` hace que cerrar por cualquier puerta avise a los negocios.
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
- **Preferencias**: solo el modo del tema y los dos avisos (la paleta, la moneda, el orden del menú y el modo
  desarrollador no siguen: una paleta, se cobra en euros, ronda 17). El idioma es `User.language`, el que ya
  leen los correos y el salto al Hub; siempre tiene valor.

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
- `auth/apikeys/tests` (80) → `test_models`, `test_api_keys`, `test_api_auth`, `test_admin`. Fuera: claves de
  hub y su gracia (hub-next), entorno `pre`, scopes de flota/vendedor y el script de emisión.

## Pendiente (de otros carriles)

- **`hubs`** conecta `signals.sessions_ended` → `revoke_after_commit(user_id)` y `account_deleting` (en curso en
  su carril); también puede escuchar `allauth.account.signals.email_changed` para refrescar la foto del negocio.
- **`hubs`/`billing`** eligen qué operaciones abren a claves (`expose_api=True`, en curso): hasta entonces una
  clave no abre nada.
- **`live`**: `record_event` guarda `actor=str(ctx.actor)`, el correo de la cuenta. El arreglo bueno es guardar
  el id en `live.outbox` (próximo lote de `live`); mientras, eliminar una cuenta pasa sus filas al id
  (`services.forget_in_outbox`).
