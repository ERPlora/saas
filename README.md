# saas-next

`erplora.com` de ERPlora Next (en local, `http://localhost:8001`). Los hubs son `<slug>.erplora.com`
(en local, `a.localhost:8000`) y `hubs.erplora.com` es el admin del Hub para el personal (PLAN §18;
en local, `hubs.localhost:8000`): los sirve `hub-next`, nunca el SaaS. Planes: `../PLAN-SAAS.md` (contrato con el Hub en §2, flujos en §3, qué se
porta en §6).

## Fase 1 (S1): entrar y saltar a un hub

Solo lo que necesita el salto al Hub (PLAN-SAAS §2.1 y §3.1, pasos 4–6; PLAN §16.12):

- **Entrada en `/launch`** (Ioan, 2026-10-15; ver «SPA Ionic Vue» abajo): sin sesión, el lanzador es el
  propio login, un único formulario (`accounts/frontend/components/SignInForm.vue`) sobre `allauth.headless`
  en modo solo headless (`HEADLESS_ONLY = True`, PLAN-SAAS §2): allauth no sirve ninguna plantilla. El mismo
  formulario da de alta (ADR-0154): un correo sin cuenta crea la suya.
- **Código por correo en cada inicio de sesión** (segundo factor por email): tras la contraseña, allauth
  manda siempre un código de 6 cifras a la cuenta y se teclea en `/verify-email`. Una cuenta nueva (o una
  dirección nunca probada) recibe el código que prueba el correo (`verify_email`); cualquier otra, el código
  de inicio de sesión (`login_by_code`, `ACCOUNT_LOGIN_BY_CODE_REQUIRED = {"password"}`). Nunca dos códigos.
  Valores de allauth: 3 intentos y 3 minutos; el de inicio de sesión no se reenvía (allauth solo lo reenvía
  con el login solo-con-código encendido, que dejaría entrar sin contraseña): se pide otro iniciando sesión
  de nuevo. Google no pide código (ya es un inicio de sesión fuerte y prueba el correo).
- Las direcciones de antes, `/login`, `/accounts/login/` y `/accounts/signup/`, redirigen para siempre (301)
  a `/launch` en un solo salto, conservando `next` y el resto de la query; el resto de `/accounts/…` da 404.
- **«Continuar con Google»** (`allauth.socialaccount`, portado del SaaS de hoy; ver «Google» abajo).
- `/launch` (página Ionic Vue `hubs/frontend/pages/LaunchPage.vue`, lee `hubs.business.list`): sin sesión,
  el formulario de entrada en la tarjeta del login de siempre (`AuthShell`); con sesión, sus negocios (crear
  el primero, la invitación pendiente, abrir uno o elegir entre varios). Con sesión y un `next` del propio
  sitio, va directo a `next`, como el login de plantilla. `GET /launch/` (la dirección de antes) solo redirige a `/launch`.
- `/login/error?code=…` (página Ionic Vue `LoginErrorPage.vue`): todo inicio de sesión o salto
  rechazado (`invalid_hub`, `not_a_member`, `authentication_error`, `login_cancelled`), con los textos
  de las plantillas que sustituye.
- `GET /hub-login/?hub=<slug>&next=<ruta>`: slug no válido → `/login/error?code=invalid_hub` (regla
  compartida con el Hub, `live.slugs`: una etiqueta DNS de 3 a 63 caracteres —1 en local, por los
  hubs `a` y `b`— y nunca un nombre reservado como `hub`, `www` o `admin`); sin sesión →
  `/launch?next=…` (también mientras el código del login sigue pendiente); sin ser miembro → `/login/error?code=not_a_member&hub=<slug>`; si no, acuña un `AuthExchangeCode` (32 bytes, guardado como SHA-256, audiencia
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
- Cierre de sesión: `DELETE /_allauth/browser/v1/auth/session` (allauth.headless; el menú de usuario y la
  tarjeta del lanzador), y después `/launch`.

## SPA Ionic Vue (ronda 11): login

El SaaS es también una SPA Ionic Vue, igual que `hub-next` (`base/`, `frontend/main.ts`,
`vite.config.ts`, `<app>/frontend/`). Sus apps (`accounts/` Cuenta, `hubs/` Negocios y uso, `billing/`
Tienda, Facturación y Stripe, `fiscal/` la documentación fiscal de VeriFactu, más `apps/`, el catálogo de
módulos de la ronda 16, y `public/`, la web pública) viven en la raíz, junto a `base/`: `saas-next` no tiene carpeta de módulos (PLAN §20.2), y cada app
con `frontend/` se nombra en los globs de `frontend/main.ts` y en `FRONTEND_APPS` de `vite.config.ts`
(guardarraíles en `frontend/main.test.ts` y `vite.config.test.ts`). Todas las páginas de cuenta son
Vue, sobre `allauth.headless` (cliente `browser`, `/_allauth/browser/v1/…`), en modo solo headless
(`HEADLESS_ONLY = True`): el formulario de `/launch`, `/login/error`, `/verify-email`, `/password/reset`,
`/password/reset/key/<clave>`, `/2fa/authenticate`, `/2fa` y `/reauthenticate`
(`accounts/frontend/routes.ts`; `/login` solo redirige a `/launch`). `LOGIN_URL` es `/launch`.

- Formulario de entrada (`accounts/frontend/components/SignInForm.vue`, dentro de `LaunchPage.vue` con el
  marco `AuthShell`): el de la plantilla de login del SaaS de hoy (mismos msgids,
  `accounts/frontend/locale/{en,es}.json`). No pregunta si mantener la sesión: headless no recibe
  `remember` y toda sesión dura `SESSION_COOKIE_AGE`. Tras la contraseña va a `/verify-email` (el código
  por correo; la dirección viaja en el estado del historial, nunca en la URL) o a `/2fa/authenticate`; con
  sesión, vuelve a cargar `next` o el lanzador. «¿Olvidaste tu contraseña?» lleva a `/password/reset`, que
  manda por correo el enlace `/password/reset/key/<clave>` y vuelve con `?notice=password_reset`;
  «Continuar con Google» es un formulario `POST` normal al redirect de proveedor de headless
  (`/_allauth/browser/v1/auth/provider/redirect`, con el token CSRF de la cookie y `callback_url` =
  `next` o `/launch`), visible si `spa-config.googleEnabled`. Si Google vuelve con el login pendiente del
  segundo factor, el formulario sigue a `/2fa/authenticate` conservando `next`.
- `/verify-email`: la página de los dos códigos. Lee de la sesión cuál espera el login: `verify_email`
  (`POST …/auth/email/verify {key}`, con «Enviar un código nuevo») o `login_by_code`
  (`POST …/auth/code/confirm {code}`, sin reenvío: dice que se pide otro iniciando sesión de nuevo). Un
  código caducado o fallado tres veces (409) vuelve a `/launch?notice=code_expired`, que lo explica.
- `base`: `base.session.me` (ámbito = el usuario, `UserContextBuilder`), `GET /api/me`, el HTML de la
  SPA (`base/spa.py`, sobre `live.spa`) para toda ruta sin URL propia de Django y `/healthz` como
  primer middleware. Los iconos de la pestaña y de la pantalla de inicio del panel son los de la web pública
  (`img/favicon.ico` y `public/img/apple-touch-icon.png`), declarados en `LIVE["spa"]["icons"]`.
  Una ruta que nombra un fichero sin URL propia (`/favicon.ico`, `/wp-login.php`; `base.spa.NOT_A_FILE`) no es
  de la SPA: el 404 llano de Django, sin la SPA ni `csrftoken` (FIX-SAAS-SPA-STATIC-PROBES-SET-CSRF-COOKIE).
  Un stream vivo cuya sesión terminó (salir, «Cerrar las demás sesiones», contraseña nueva) acaba en su siguiente
  re-ejecución con `bye` (401 `base.session_ended`, el código del Hub) y la pestaña sale sola al login (ui#25).
- Los enlaces de los correos de allauth (`HEADLESS_FRONTEND_URLS`) son rutas de la SPA: `/password/reset`,
  `/password/reset/key/{key}` y `/launch` (el correo «no hay ninguna cuenta» de una recuperación invita a
  darse de alta, que es el mismo formulario). Sin `account_confirm_email`: el correo se confirma con un
  código, y allauth no construye ningún enlace.
- Vite en el puerto **5174** (el 5173 es del Hub; `VITE_DEV_PORT` lo mueve, para Django y Vite a la vez):
  `runserver` lo arranca (`--novite` lo omite). Dos SaaS a la vez: `tests/e2e/README.md`, «Dos SaaS a la vez».

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
  es como la SPA sabe que está apagado. El salto a un hub y el admin, como siempre.
- **Encendido**:
  - Una cuenta con app, tras la contraseña y el código por correo (o tras Google), queda pendiente del
    código de la app, en el orden de etapas de allauth: headless responde
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
- `/admin/login/` nunca es el login de Django (no pediría ningún código), ni con el flag apagado: redirige a
  `/launch?next=…` (el formulario, con el código por correo en `/verify-email` y, encendido el flag, el de
  la app en `/2fa/authenticate`). No inicia sesión ni por `POST`; con sesión y sin permiso de admin, 403
  (el login devolvería a `/admin/` en bucle).
- **Activarlo un usuario** (con el flag encendido), en la SPA, `/2fa`: escanear el QR con la app (o
  teclear la clave manual), confirmar con un código y guardar los códigos de recuperación (10, de 8
  cifras, un uso cada uno). Al entrar, el código de la app o, sin el móvil, uno de recuperación. Para
  desactivarlo, `/2fa` pide antes reautenticarse. allauth no deja activarlo con un email sin verificar
  (409 `unverified_email`).
- Ajustes: `MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]`, emisor `ERPlora`, ±1 periodo (30 s) de
  desfase del reloj del móvil; sin llaves de acceso (passkeys) ni «confiar en este navegador».

## Google

Mismo comportamiento que el SaaS de hoy (ADR-0154; `accounts/{google,adapters}.py`, el botón en
`SignInForm.vue`), sobre allauth.headless. Google no pide el código por correo (`ACCOUNT_LOGIN_BY_CODE_REQUIRED`
solo cubre la contraseña):

- **Rutas**: `POST /_allauth/browser/v1/auth/provider/redirect` (el botón: `provider=google`,
  `process=login`, `callback_url` = la página a la que volver; un `GET` da 405, así que un enlace no
  inicia sesión a nadie) y `GET /auth/google/callback/`, con el nombre de allauth (`google_callback`)
  para que el `redirect_uri` de la autorización y el del canje del código sean los dos
  `/auth/google/callback/`. Ojo: en el SaaS de hoy (allauth 65.18) la autorización salía con
  `/accounts/google/login/callback/` aunque la vista fijaba otra ruta.
- **Credenciales**: `GOOGLE_OAUTH_CLIENT_ID` y `GOOGLE_OAUTH_CLIENT_SECRET` (entorno o `saas-next/.env`,
  nunca una fila `SocialApp`). En local son opcionales: sin ellas el botón no aparece, las dos rutas
  dan 404 (el redirect, con el JSON de headless) y `check` lo avisa (`accounts.I001`). En producción (`DEBUG=False`) son obligatorias: sin
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
  contraseña?»). Un email sin cuenta crea la suya y entra (alta abierta, ADR-0154), solo si Google lo
  verificó; si no, ninguna cuenta y `/login/error?code=authentication_error`, como cualquier otro fallo.
  allauth rechaza el proceso «conectar» con la sesión abierta (saas#2552): Google se vincula entrando con
  él. Cuenta → Seguridad no tiene botón «Conectar» (explica cómo se vincula), y un `process=connect` enviado
  igualmente acaba en `/login/error?code=google_link_refused`. Cancelar en Google vuelve al formulario de `/launch` conservando `next`, así que
  `/hub-login/?hub=…&next=…` sigue funcionando tras Google. «Confirma que eres tú» de una cuenta solo de
  Google es entrar otra vez con Google (el mismo redirect, de vuelta a la página).

## Protección contra bots: límites de intentos y reCAPTCHA (apagado por defecto)

Ioan, 2026-10-22: «siempre que hay un form hay que meter recaptcha», «que no se vea en la pantalla» y «límites en
los registros de login para que no intenten sin parar». Vuelve reCAPTCHA, que ADR-0154 había retirado: ahora
**reCAPTCHA Enterprise por puntuación**, sin casilla ni puzle.

**Desde el 2026-10-23 reCAPTCHA está APAGADO por defecto** (Ioan: «quitamos el reCAPTCHA y aplicamos el WAF»). El
WAF del ALB (`ERPlora/aws`) frena el tráfico sospechoso en el borde y los **límites de intentos** (abajo, sin
cambios) frenan la fuerza bruta. El código se queda entero, detrás de un interruptor, para encenderlo sin
reconstruir nada si aparece spam:

- **Apagado** (`RECAPTCHA_ENABLED` ausente o `False`, lo normal en `prod`, `pre` y local): ningún formulario pide
  token ni se pregunta a Google; las páginas no cargan `enterprise.js`, no pintan el aviso, no llevan el estilo que
  oculta la insignia ni nombran a Google en la CSP ni en Trusted Types; `spa-config` no lleva `recaptchaSiteKey`. El
  registro avisa una vez por proceso (`recaptcha.disabled`).
- **Encenderlo**: `RECAPTCHA_ENABLED=true` en el entorno de las tareas `saas*` (la definición de tarea o el secreto
  `erplora/<env>/saas` de Secrets Manager, `ERPlora/aws`) más las dos claves (`RECAPTCHA_SITE_KEY` y
  `RECAPTCHA_API_KEY`, que siguen en el secreto) y un despliegue nuevo de las tareas para que lo lean al arrancar.
  Encendido, sin alguna de las dos claves el proceso **no arranca**. En local, lo mismo en `.env`. Todo lo que sigue
  describe cómo funciona encendido.

- **Formularios cubiertos y su acción** (el token se pide para esa acción y el servidor la exige): entrar
  (`login`), crear cuenta (`signup`), «¿Has olvidado tu contraseña?» (`password_reset`), la nueva contraseña del
  enlace (`password_reset_confirm`), el código que confirma el correo (`verify_email`) y «Enviar un código nuevo»
  (`verify_email_resend`), el código de cada entrada (`login_code`), el de la app autenticadora
  (`mfa_authenticate`), el formulario de contacto (`contact`) y «Prueba la demo» (`demo_request`). Fuera, a
  propósito: «Continuar con Google» (lo comprueba Google), el selector de idioma y la búsqueda de la tienda (no
  crean nada) y los formularios del panel, que ya piden una sesión.
- **Cómo funciona**: la página carga `enterprise.js` de Google con la clave pública; al enviar, pide un token de
  la acción (`frontend/recaptcha.ts`; en el panel lo añade el `fetch` del cliente de allauth,
  `accounts/frontend/recaptcha.ts`) y lo manda en `recaptcha_token`. El servidor pregunta a Google con
  `live.recaptcha.verify_or_raise` antes de hacer nada: las puertas de allauth.headless en
  `accounts/bot_check.py` (400 `recaptcha_failed` en el sobre de allauth), contacto en `public/landing.py` y la demo
  en `public/demo.py` (`?state=unverified`). Se rechaza sin token, con un token no válido o de otro formulario y con
  puntuación por debajo de `RECAPTCHA_MIN_SCORE`. Quien bloquea Google con una extensión no puede enviar estos
  formularios: ve «No hemos podido comprobar que eres una persona. Vuelve a intentarlo.».
- **Si no se puede preguntar a Google** (tiempo agotado, red, 5xx o respuesta ilegible; un 4xx también): falla
  cerrado en todos los formularios **salvo** la entrada (`login`) y sus segundos factores (`login_code`,
  `mfa_authenticate`), que ya protegen la contraseña o el código y sus límites: pasan, con un ERROR
  `recaptcha.unavailable` (o CRITICAL `recaptcha.misconfigured` si Google contestó 4xx) y una cuenta por acción, para
  que una caída de Google no deje fuera a nadie, tampoco al personal (`fail_open_on_unavailable` de
  `live.recaptcha`). Un veredicto de Google (token no válido, de otra acción o puntuación baja) sigue rechazando ahí,
  y sin token tampoco se entra: si el navegador no puede cargar el script de Google, no hay token que mandar.
- **Runbook: salta `recaptcha.unavailable` o `recaptcha.misconfigured`** (CloudWatch, el registro de las tareas
  `saas*`; mientras dure, el alta, la contraseña olvidada, los códigos del correo, el contacto y la demo rechazan a
  todos). 1) `misconfigured` (4xx): la clave de la API (que exista, que esté restringida a «reCAPTCHA Enterprise API»
  y no a otra cosa), la facturación y la cuota del proyecto `erplora` en Google Cloud; con la clave mala o borrada,
  rotarla (abajo). 2) `unavailable` (tiempo, red, 5xx): el estado de Google Cloud (status.cloud.google.com,
  «reCAPTCHA Enterprise») y la salida a Internet de las tareas (NAT, grupos de seguridad); si es Google, esperar:
  la entrada sigue abierta. 3) Si el registro dice `let_through=True` durante mucho rato, la entrada funciona solo
  con contraseña, código y límites: vigilar `too_many_login_attempts` en el mismo registro. Nada de esto pide
  desplegar código.
- **Aviso**: la insignia de Google va oculta (`.grecaptcha-badge`, con un estilo que `frontend/recaptcha.ts` mete
  junto al script de Google, nunca sin él), y por eso cada formulario lleva debajo «Este sitio está protegido por
  reCAPTCHA y se aplican la Política de Privacidad y las Condiciones del Servicio de Google.» (en + es), como pide
  Google.
- **Claves** (proyecto de Google Cloud `erplora`, tipo «puntuación»): `RECAPTCHA_SITE_KEY` (pública; la de
  producción vale para `erplora.com`, `erplora.es` y sus subdominios, y hay otra para `localhost`) y
  `RECAPTCHA_API_KEY` (secreta, la de la API de evaluaciones). En `prod` y `pre` viven en Secrets Manager y la
  definición de tarea las pasa a **todas** las tareas `saas*`; solo se leen con `RECAPTCHA_ENABLED=true`. En local,
  en `.env` (ver `.env.example`): tener las claves ya no lo enciende, hace falta `RECAPTCHA_ENABLED=true`; encendido,
  el login local también pasa por Google, y un `runserver` que automatiza un navegador (la e2e del Hub contra
  `:8001`) lo deja apagado, porque Google puntúa bajo a un Chrome sin ventana. Los tests lo apagan siempre
  (`config/settings_pytest.py`) y el fixture `recaptcha` hace de Google; la e2e corre apagada, como producción, y
  con `E2E_RECAPTCHA=1` lo enciende contra su doble (`tests/e2e/README.md`, `:8018`).
- **`RECAPTCHA_MIN_SCORE`**: 0.5 por defecto (el umbral de Google: 1.0 casi seguro una persona, 0.0 casi seguro un
  bot); se sube o se baja por entorno sin desplegar código. Una clave nueva da 0.9 las primeras 48 horas.
  `RECAPTCHA_PROJECT` (`erplora`) y `RECAPTCHA_ENDPOINT` (la e2e lo apunta a su doble) completan los ajustes.
- **Rotar la clave de la API**: crear una clave nueva en Google Cloud (API keys, restringida a «reCAPTCHA
  Enterprise API»), ponerla en Secrets Manager (`RECAPTCHA_API_KEY`), forzar un despliegue nuevo de las tareas
  `saas*` y, cuando estén sanas, borrar la vieja en Google Cloud. La clave del sitio no se rota: si hiciera falta,
  se crea otra, se cambia `RECAPTCHA_SITE_KEY` igual y se borra la vieja tras el despliegue.
- **CSP** (solo encendido; apagado, ninguna nombra a Google): la del panel y la de la web pública admiten
  `script-src` `https://www.google.com/recaptcha/` y
  `https://www.gstatic.com/recaptcha/`, `frame-src` `https://www.google.com/recaptcha/` y
  `https://recaptcha.google.com/recaptcha/` y `connect-src` `https://www.google.com/recaptcha/`
  (`live.recaptcha.with_recaptcha`); el panel mantiene nonce, `'strict-dynamic'` y Trusted Types, con la política
  `goog#html` que crea el script de Google y, en la política `default`, solo sus dos rutas
  `https://www.google.com/recaptcha/` y `https://www.gstatic.com/recaptcha/` (`frontend/main.ts`; el resto de esos
  orígenes, no).
- **Límites de intentos** (`ACCOUNT_RATE_LIMITS`, `config/settings.py`; por dirección de red, la que el ALB vio,
  `public.client_ip`, y por cuenta, en la caché compartida): 30 entradas por minuto por dirección; 5 contraseñas
  equivocadas en 5 minutos por dirección y por cuenta (la buena devuelve su intento); 10 altas por hora por
  dirección; 10 enlaces de restablecer por hora por dirección y 5 por cuenta; 20 envíos por minuto del formulario
  del enlace; un código nuevo cada 10 s; y 10 códigos rechazados en 5 minutos por dirección (uno bueno no gasta:
  `code_attempts`, `accounts/bot_check.py`; además de los 3 intentos de cada código). El contacto (10 por hora) y
  la demo (3 demos nuevas por hora) siguen con su límite por dirección, que va antes que reCAPTCHA: lo frenado no
  gasta evaluaciones. Solo el Django del panel de la e2e sube los límites por dirección de la entrada
  (`E2E_RELAX_LOGIN_RATE_LIMIT`: todas sus specs entran desde `127.0.0.1`); producción no arranca con él.

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
  `seed_taxonomy` (y, hasta que se aplique el Terraform de ERPlora/aws#4, también `sync_hub_plans`, hoy vacío).
  Todas idempotentes y con advisory lock (una segunda ejecución vuelve al momento).
- **Planes**: viven solo en la base de datos y se mantienen en el admin de Django (`/admin/hubs/plan/`). La
  siembra inicial es la migración `hubs/0013_plans_in_the_database` (siete planes: Free, Starter y Standard
  en venta, Pro, Enterprise y Max `upgrade_only`, y `payment-test` interno), sin periodo de prueba; ningún
  despliegue los vuelve a escribir. `sync_hub_plans` es desde el 2026-10-15 un comando vacío (no siembra ni toca la
  BD; `--update` se acepta y se ignora): sigue solo porque la tarea `saas-migrate` de pre y prod lo llama hasta que
  se aplique el Terraform de ERPlora/aws#4; después se borra.
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
y en los tests) o `pre`, la preproducción del equipo en `pre.erplora.com`, en su propio cluster ECS
(`erplora-pre`; PLAN-AWS, ronda 2026-10-16) y con el mismo ALB, Aurora y Valkey que prod (plan
`../docs/plans/2026-10-14-entorno-pre.md`). Cualquier otro valor no arranca. En `pre`:

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
   en `erplora/saas-pre` y despliega `saas-pre` (`ecs-deploy.sh` con `ENVIRONMENT=pre`: cluster `erplora-pre`,
   familias `erplora-pre-saas` y `erplora-pre-saas-migrate`, sin `saas-cron`; `/erplora/pre/saas/image_tag`). Si pre
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

**Correo en local**: con `DEBUG`, cada correo del SaaS queda en un fichero de `saas-next/.mail/` (fuera de
git; `EMAIL_FILE_PATH` cambia la carpeta y `EMAIL_BACKEND` el backend, p. ej. la consola). El código de
login se lee de ahí: el fichero más reciente para esa dirección, con las 6 cifras solas en su línea. Las
e2e (también las del Hub) lo leen con `readMailCode({ dir, to, since })` de `@erplora/ui/testing/mail`.

**Usuarios QA**: el `.env` raíz de erplora-next los lista (`QA_OWNER_*`, `QA_EMPLOYEE_*`,
`QA_PLATFORM_*` de `demo_seed`; `QA_BILLING_*`, `QA_STORE_*` y `QA_PANEL_PASSWORD` de las semillas de
`tests/e2e/panel/`), con los mismos valores que las semillas usan por defecto. Exportados
(`set -a; . ../.env; set +a`), las semillas y las e2e los usan; sin exportar, valen esos mismos.

Todo se corre dentro de este repo (`saas-next/`), que monta `ERPlora/live` y `ERPlora/ui` como submódulos en
`packages/`:

```bash
git submodule update --init && uv sync && pnpm install   # tras clonar o cambiar de rama
cp .env.example .env                     # la primera vez: DEBUG=True y los valores locales
uv run python manage.py migrate
uv run python manage.py demo_seed        # (de hubs) negocios a y b adoptados; owner@example.com / owner (hub_owner de a y b, sin admin), employee@example.com / employee (hub_employee de a y b: solo ve Demo, DEMO-F06) y platform@example.com / platform (superusuario, sin hubs)
uv run python manage.py create_platform_user <email> --role admin|support [--password …]   # staff de plataforma
uv run python manage.py runserver 127.0.0.1:8001   # también Vite (`pnpm run dev`) en :5174 (`--novite` lo omite)
VITE_DEV_PORT=5224 uv run python manage.py runserver 127.0.0.1:8051   # un segundo SaaS (otro worktree): su Vite en :5224 (runserver se lo pasa a su Vite; vale también en .env)
# http://localhost:8001/launch   (el código de cada login, en saas-next/.mail/)
# Admin del Hub de un hub: http://localhost:8001/admin/ con platform@example.com / platform → Hubs
# → «Abrir en el admin del Hub» → http://hubs.localhost:8000/admin/hub/a/ (el lado del Hub llega con
# la ronda 13 del carril de hub-next)
uv run pytest -q
pnpm test     # y typecheck, lint, build
pnpm e2e --project=panel   # e2e del panel, sin ventana (`pnpm e2e:headed` la abre)
```

## Fuera de la fase 1

Cada punto tiene su borrador de issue en `docs/issues/` (pendiente de abrir en `ERPlora/saas`):

- Del segundo factor: «confiar en este navegador» 14 días (`MFA_TRUST`) y llaves de acceso
  (WebAuthn/passkeys). Sin borrador de issue todavía.
- Que el salto lea `HubMember` y retirar `HubMembership(user, hub_slug, role)`, que desde L1-A2 es solo el
  espejo de los miembros de cada negocio (`hubs/README.md`, «Pendiente»; `membership-by-slug.md`).
- Que cinco contraseñas falsas de otra persona no dejen fuera al dueño de la cuenta durante 5 minutos
  (`login-lockout.md`; los límites ya están escritos y el WAF del ALB frena a los bots, «Protección contra bots») y la
  sesión que no se renueva con el uso (`remember-me-not-sliding.md`).

Ya no están fuera (PLAN-SAAS §1.1, ronda 2026-10-15b): el selector con el último negocio abierto primero
(`HubMember.last_opened_at`, que sella `hubs.business.open` y ordena `hubs/queries.py`) y el cierre de las sesiones
del Hub al cerrar sesión, poner o restablecer la contraseña o eliminar la cuenta (`accounts.signals.sessions_ended`
→ `hubs.services.end_account_sessions`, con los reintentos de `hubs.SessionRevocation`). Lo que la ronda añade al
SaaS (asistente, WhatsApp, correos HTML, RGPD, operación y admin) son los bloques 11–15 de PLAN-SAAS §7.
