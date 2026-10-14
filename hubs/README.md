# `hubs` — los negocios del SaaS

App de plataforma (`LiveAppConfig`, `kind = "platform"`) del plano de cuenta: los negocios de cada cuenta
(`Hub`), quién está en ellos y con qué rol (`HubMember`, cuatro roles `hub_*`), los traspasos de propiedad
(`HubOwnershipTransfer`), quién paga (`BillingProfile`), qué plan y módulos tienen (`Subscription`,
`SubscriptionItem`), los planes (`Plan`) y la taxonomía (`Sector`, `BusinessType`).

- Operaciones en `queries.py` (lecturas) y `services.py` (escrituras), rutas en `api.py` bajo `/api/hubs/`
  (y `/api/plans`, `/api/catalog/*`, públicas); consultas vivas en `live.py`.
- Hacia el Hub: `hub_client.py` (llamadas firmadas a `/internal/*` de hub-next), empuje tras el COMMIT
  (`services.sync_hub`) y los comandos de `saas-cron`: `reconcile_hub_states` (cada 15 min) y
  `push_hub_snapshots` (cada noche, todos los negocios; `--behind-only`, solo los atrasados).
- Del Hub: `POST /internal/hubs/{id}/ready` (`internal.py`).
- «Abrir» (`hubs.business.open`) ya no emite el código: comprueba el miembro y el estado del negocio, sella
  `last_opened_at` y devuelve `{url}`, el inicio del salto en el Hub (`https://<slug>.erplora.com/auth/login?next=/`;
  en local `http://<slug>.localhost:8000/…`). El Hub pone su `state` ligado al navegador y rebota a `/hub-login/`,
  que emite el código y pide el segundo factor si la cuenta lo tiene. La URL la arma
  `accounts.queries.hub_start_url` (un solo sitio para el salto).
- Miembros (L1-B): `hubs.member.list` devuelve `seats: {used, limit}` (`limit: null` = sin tope) y, por fila,
  `is_me` y `actions` (lista en este orden: `change_role`, `remove`, `resend`, `cancel`, `transfer`), calculadas
  en el servidor con las mismas reglas que las escrituras: el panel no adivina. El tope de asientos es
  `Plan.max_users` del plan efectivo (la prueba de Starter no topa): invitar (y renovar una invitación
  caducada) gasta el asiento y una invitación viva lo ocupa; aceptar solo se frena si ya no cabe nadie más
  (invitaciones de la prueba aceptadas en Gratis). La negativa es el 409 `hubs.seat_limit` con `limit` y
  `used` en el sobre de error.
- Negocios: cada fila de `hubs.business.list` lleva `can: {open, manage, restore, delete}` y la página
  (`hubs.business.get`) las mismas claves en `can` más `country_locked`; el país no cambia desde `ready_at`
  (409 `hubs.country_locked`). Una negativa del Hub (o su arreglo) se graba con la operación de sistema
  `hubs.business.record_hub_error` y el evento `hubs.business.hub_error_changed`, que re-ejecuta la lista y la
  página en el canal del propietario.
- Taxonomía: `hubs.sector.list` y `hubs.business_type.list` ordenan por `display_order` y luego `code`, en
  global (sin agrupar por sector), como el `catalog` de origen; `?sector=` filtra.
- Los comandos de `saas-cron` toman el advisory lock `hashtext('erplora.saas.<comando>')` (el espacio de
  nombres de `base`), de sesión: la pasada abarca muchas transacciones y llamadas al Hub (ver
  `services.run_exclusively`).
- Personas en vivo (L1-A2): toda escritura de miembros, invitaciones o traspasos, además de su evento en el canal de
  quien la hace, anota `hubs.member.changed` u `hubs.ownership.changed` (`{business_id}`) en el canal del
  propietario, de cada administrador y de la cuenta afectada (`services.notify_people` → la operación de sistema
  `hubs.business.notify_people`, una por canal, tras el COMMIT; nunca el del actor). `hubs.member.list`,
  `hubs.business.get`, `hubs.business.list` y `hubs.invitation.list_mine` se re-ejecutan con ellos: el propietario
  ve al momento que otro acepta, sin esperar los 300 s.

## Lo que añadió L1-A2 (2026-10-14)

- **Espejo del acceso**: `accounts.HubMembership` es solo el espejo de los miembros respondidos de cada negocio
  que lee el salto (`issue_code`/`redeem_code`). Su **único escritor** es `services.sync_access` (guardarraíl AST
  en `tests/test_access_mirror.py`); el admin de `accounts` lo enseña de solo lectura. `queries.verify_access_mirror()`
  dice dónde discrepan y el check `hubs.W001` (`hubs/checks.py`, de base de datos: `manage.py check --database
  default` y `migrate`; aviso, nunca error; calla mientras falten migraciones) lo avisa.
- **Migración de datos `0006_adopt_seed_hubs`**: cada slug de `HubMembership` sin `Hub` (los hubs del seed de la
  fase 1) pasa a negocio **adoptado**, tal como ya corre en el Hub: `active`, `ready_at` = ahora, nada debido al
  Hub (`pending_hub_call` vacío y `pushed_state_version` = `state_version` = 1, así que no se registra ni se sondea
  otra vez), `provision_requested_at` vacío (el SaaS nunca pidió aprovisionarlo), nombre = slug, país `ES`, idioma
  del propietario y suscripción Gratis si el plan está sembrado. Propietario: su `hub_owner` (el más antiguo; los
  demás pasan a `hub_admin`) o, si no hay, la pertenencia más antigua, ascendida. Un slug que no es de hub
  (`live.slugs`) no abría nada: sus filas se borran. Después, el espejo de todos los negocios queda como lo deja
  `sync_access`. Idempotente; la vuelta atrás conserva los negocios (son filas válidas del esquema anterior).
- **`demo_seed` vive en `hubs`** (`management/commands/demo_seed.py`): crea las cuentas (`accounts.services.
  seed_demo_customer`, `seed_demo_platform_admin`) y adopta `a` y `b` con `services.seed_demo_business`, igual que
  la migración.
- **`SessionRevocation`** (`models.py`, migración `0005`): quitar a un miembro, cambiarle el rol (el rol viaja en la
  sesión del Hub), aceptar un traspaso (los dos lados) o liberar una cuenta no verificada (todos sus negocios) la
  encola en la transacción; se entrega tras el COMMIT (`POST /internal/sessions/revoke`) y, si el Hub no está o la
  rechaza, `reconcile_hub_states` la reintenta cuando vence su espera (15 min, doblando, tope 6 h;
  `sessions_ended`/`sessions_pending`, y la pasada falla con alguna pendiente). Una entregada no se reenvía; la de un
  negocio purgado se da por entregada sin llamar. Sobrevive al borrado de la cuenta (`user` sin restricción de BD).
  La siguiente foto ya no lista al miembro quitado.
- **Firma de `/internal`** (`accounts/signing.py`): dos secretos vivos (`INTERNAL_SHARED_SECRET` e
  `INTERNAL_SHARED_SECRET_PREVIOUS`, vacío fuera de una rotación; se firma con el actual) y, además de la v1 de solo
  cuerpo (`X-Erplora-Signature`, la que firma hoy el Hub), la v2 `X-Erplora-Signature-V2`, HMAC de
  `v2\n{ts}\n{MÉTODO}\n{ruta?query}\n{cuerpo}`. El SaaS firma toda llamada con las dos; al verificar, una llamada
  con v2 se juzga solo por v2 (sin degradar a v1) y una sin v2, por v1. Rotación en tres pasos y paso a solo v2:
  docstring de `accounts/signing.py`.
- **Admin** de `Hub` (con sus miembros), `HubMember`, `HubOwnershipTransfer`, `BillingProfile`, `Subscription`,
  `SubscriptionItem` y `SessionRevocation`: de solo lectura (las escrituras son las operaciones), con las acciones
  de superusuario «Enviar al Hub el estado más reciente», «Reintentar lo que el Hub tiene pendiente» y «Cerrar ya
  las sesiones en el Hub»; `support` los ve (migración `0007`) y no actúa.
- **Invitar una cuenta que nunca verificó su correo** (saas#2541, `tests/test_invite_unverified_account.py`):
  `accounts.queries.email_is_proven` decide; si no, `accounts.services.release_unproven_account` le quita
  contraseña (y con ella las sesiones del SaaS), segundo factor y Google, y se encolan los cierres de sesión de
  todos sus negocios; el correo de la invitación lleva el camino para reclamar la cuenta
  (`accounts.queries.has_no_way_in`). Aceptar exige el correo verificado: 403 `hubs.email_unverified`.

Plan: `docs/plans/2026-10-13-panel-saas-unificado.md` (lotes L1-A, L1-B y L1-A2).

- Panel (`frontend/`, L1-C): las acciones de fila de Negocios y Miembros son solo icono, con nombre accesible y `title` que incluyen la fila («Abrir Panadería López», «Quitar a Marta Gil»), como pide la regla de la DataTable de SaaS y Hub (2026-10-14); las maquetas, que las pintan con texto, no obligan en esto.

## Pendiente (lotes siguientes)

- **Retirar `accounts.HubMembership`**, en este orden: (1) el salto pasa a `hubs` (`/hub-login/`,
  `issue_code`/`redeem_code`, `AuthExchangeCode` con `destination_hub`, `/internal/auth/redeem`) y lee `HubMember`
  de negocios abiertos; (2) `accounts.queries.hub_slugs_of`/`hubs_with_members` (página «Hubs» del admin) y
  `create_platform_user` leen `HubMember`; (3) `queries.slug_taken`/`free_slug` dejan de mirar el espejo; (4) se
  quitan `sync_access`, `verify_access_mirror`, el check `hubs.W001` y el guardarraíl; (5) migración que borra
  `HubMembership` (y su inline y su admin). `tests/e2e/panel/panel_seed.py` escribe hoy el espejo a mano: que llame a
  `sync_access` (carril front).
- El Hub (carril Hub): verificar la v2 y los dos secretos en su `/internal`, firmar con v2 su canje, y adoptar por
  `id` los negocios que le llegan en la foto (los `a`/`b` adoptados aquí traen un UUID nuevo). Cuando los dos lados
  firmen v2, dejar de aceptar llamadas solo v1. `aws-next`: añadir `INTERNAL_SHARED_SECRET_PREVIOUS` (vacío) al
  secreto `erplora/prod/internal` y a las tres tareas para poder rotar sin despliegue de código.
- Las páginas de Cuenta (L3-B) deben ofrecer verificar el correo: hoy una cuenta con su dirección sin verificar no
  puede aceptar una invitación (403 `hubs.email_unverified`) y el SaaS no tiene aún la página que lo pida.
- El SDK (`@erplora/ui`, `ApiError`) solo conserva `code`, `message` y `fields` del sobre de error: para pintar
  `limit` y `used` de `hubs.seat_limit` el panel (L1-D) necesita que los conserve; hoy los tiene en `seats` de la
  lista y en el mensaje.
- Los usuarios solo con PIN del Hub no pasan por el SaaS: el tope de `max_users` de la foto lo aplica el Hub en
  sus propias altas (el SaaS ya no recibe el recuento del latido).
- VIES del NIF del pagador (L2-A): hoy `validate_tax_id` solo mira la forma.
- Cancelar la suscripción de Stripe al eliminar un negocio y mover el pagador de Stripe en un traspaso (L2).
