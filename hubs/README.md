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

Plan: `docs/plans/2026-10-13-panel-saas-unificado.md` (lotes L1-A y L1-B).

## Pendiente (L1-A2 y lotes siguientes)

- Migración de datos `accounts.HubMembership` → `Hub` + `HubMember` (los hubs del seed de la fase 1) y borrado de `HubMembership`.
- Mover el salto a `hubs` (`/hub-login/`, `issue_code`/`redeem_code`, `AuthExchangeCode` con `destination_hub`, `/internal/auth/redeem`) y quitar el espejo `services.sync_access`.
- `SessionRevocation` con reintentos (L3-A): hoy `revoke_sessions` es best effort y la siguiente foto quita al miembro.
- Dos secretos vivos para rotar `INTERNAL_SHARED_SECRET` y firma que cubra método y ruta, no solo el cuerpo (L0-E, `live.internal`).
- Liberar una cuenta cuyo correo nunca se verificó al invitarla (`test_invite_unverified_account`): es de `accounts`.
- El SDK (`@erplora/ui`, `ApiError`) solo conserva `code`, `message` y `fields` del sobre de error: para pintar
  `limit` y `used` de `hubs.seat_limit` el panel (L1-D) necesita que los conserve; hoy los tiene en `seats` de la
  lista y en el mensaje.
- Los usuarios solo con PIN del Hub no pasan por el SaaS: el tope de `max_users` de la foto lo aplica el Hub en
  sus propias altas (el SaaS ya no recibe el recuento del latido).
- Admin de Django de los modelos nuevos (`Hub`, `HubMember`, `BillingProfile`, `Subscription`…).
- VIES del NIF del pagador (L2-A): hoy `validate_tax_id` solo mira la forma.
- Cancelar la suscripción de Stripe al eliminar un negocio y mover el pagador de Stripe en un traspaso (L2).
