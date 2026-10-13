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

Plan: `docs/plans/2026-10-13-panel-saas-unificado.md` (lote L1-A).

## Pendiente L1-A2

- Migración de datos `accounts.HubMembership` → `Hub` + `HubMember` (los hubs del seed de la fase 1) y borrado de `HubMembership`.
- Mover el salto a `hubs` (`/hub-login/`, `issue_code`/`redeem_code`, `AuthExchangeCode` con `destination_hub`, `/internal/auth/redeem`) y quitar el espejo `services.sync_access`.
- `SessionRevocation` con reintentos (L3-A): hoy `revoke_sessions` es best effort y la siguiente foto quita al miembro.
- Dos secretos vivos para rotar `INTERNAL_SHARED_SECRET` y firma que cubra método y ruta, no solo el cuerpo (L0-E, `live.internal`).
- Liberar una cuenta cuyo correo nunca se verificó al invitarla (`test_invite_unverified_account`): es de `accounts`.
- Admin de Django de los modelos nuevos (`Hub`, `HubMember`, `BillingProfile`, `Subscription`…).
- VIES del NIF del pagador (L2-A): hoy `validate_tax_id` solo mira la forma.
- Cancelar la suscripción de Stripe al eliminar un negocio y mover el pagador de Stripe en un traspaso (L2).
