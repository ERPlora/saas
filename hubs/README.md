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

## Lo que añadió APP-HUBS-1 (2026-10-21): crear, esperar, la lista, entrar y el QR

Flujos en `WORKBOOK.md` (`HUBS-F01`…`HUBS-F14`, parte 1 de 4 de la migración; las partes siguientes añaden los suyos).

- **«… ya está listo»** (`emails.send_ready`): el aviso `POST /internal/hubs/{id}/ready` que pasa un negocio de
  preparándose a activo manda al propietario, una sola vez y tras el COMMIT, el correo con la entrada al negocio
  (`accounts.queries.hub_start_url`) y su página en el panel.
- **La app instalada** (`ERPlora/app`) arranca en `/shell/`, que es el lanzador (alias de `/launch` en
  `frontend/routes.ts`); su «Abrir» pide `hubs.business.open` con `shell: true` y el salto lleva `&shell=1`, la marca
  con la que la app enlaza el terminal al negocio. `GET /shell/open/<id>/` (`shell.py`) es la misma puerta para un
  enlace: sin sesión, al inicio de la app; negocio ajeno o desconocido, 404; uno que no abre ahora, vuelta al lanzador.
- **Direcciones viejas** (`redirects.py`, 301): `/dashboard/`, `/dashboard/hubs/{,active/,inactive/}` → `/businesses`;
  `/dashboard/hubs/create/` → `/businesses?create=1`; `/dashboard/hubs/<id>/qr/` → el Resumen del negocio («En tus
  dispositivos»). Los filtros de las viejas se descartan.
- **El país del alta** sale sugerido por los idiomas del navegador (`frontend/regions.ts`, `suggestedCountry`), entre
  los países que ERPlora sirve; si ninguno encaja, España.
- **Planes**: los textos de cada plan (nombre, descripción, características, etiqueta) se escriben en inglés y en
  español en el admin. No hay API de escritura de planes para el personal: el admin es su única escritura (decisión
  de APP-HUBS-1, propuesta como ronda de PLAN-SAAS).

## Lo que añadió APP-HUBS-2 (2026-10-22): ajustes, dirección, baja, suspendidos, uso y admin

Flujos `HUBS-F15`…`HUBS-F23` del `WORKBOOK.md` (parte 2 de 4).

- **Cambiar la dirección web** (F16; PLAN-SAAS §1.1, ronda 2026-10-15b): `hubs.business.change_address`
  (`POST /api/hubs/businesses/address`, solo el propietario, `can.change_address`), validada como la valida el Hub
  (`live.slugs`). Sube `registry_version` (el Hub la registra con `PUT /internal/hubs/{id}`) y `state_version` (la
  foto lleva el `slug`), y `sync_access(hub, previous_slug=…)` mueve el espejo del salto. La dirección que deja queda
  en `Hub.previous_slug` (migración `0015`): `queries.slug_taken`/`free_slug` la dan por cogida para los demás, así
  que nadie recibe los enlaces y QR viejos; se libera cuando la dirección vuelve a cambiar. Evento
  `hubs.business.address_changed`. Panel: «Cambiar dirección» en Ajustes (`AddressDialog.vue`).
- **Suspendidos por impago** (F20; PLAN-SAAS §1.1, «dentro de `sweep_unpaid`»): `Hub.suspended_at`,
  `suspension_warned_at`, `suspension_final_notice_at` (migración `0016`, que pone en marcha el reloj de los que
  ya estaban suspendidos el día del despliegue). `_apply_standing` fecha la suspensión y la
  olvida al pagar. `services.age_suspended()` (lo llama `billing.services.sweep_unpaid`, cada hora; sus cuentas
  `warned`, `final_notice`, `expired`, `undated` se suman a las de la pasada) corre por negocio la operación de
  sistema `hubs.business.age_suspension`: aviso a los 30 días, último a los 150 (`emails.send_suspension_notice`, al
  propietario, solo marcado si el correo salió) y, con el último enviado, la baja a los 180 por `_delete_business`,
  el mismo camino que `hubs.business.delete` (90 días para recuperarlo). Una suspensión sin fecha no se borra: log
  `hubs.suspension.undated`.
- **Admin** (F23): las acciones de plataforma llevan `@traced`, que deja en el historial del admin de cada fila
  quién ejecutó qué («Ran «…»» / «Ejecutó «…»»).
- **Eliminar** (F18): el texto ya no promete el enlace de descarga de los datos, que el correo no lleva: llega con
  el export por negocio de la fase 2 (PLAN-DB «Exports»).
- **Dominio propio** (F17): no se porta en la fase 1; decisión de mercado y ronda propuesta en la PR de APP-HUBS-2.

## Lo que añadió APP-HUBS-3 (2026-10-23): las personas de cada negocio

Flujos `HUBS-F24`…`HUBS-F30` del `WORKBOOK.md` (parte 3 de 4): invitar, aceptar o rechazar, cambiar el rol, quitar,
traspasar la propiedad, la pestaña «Miembros» y los accesos en el admin. El código ya estaba (L1-B, L1-A2); esta parte
lo revisa flujo a flujo con su e2e en 3 tamaños (`tests/e2e/panel/hubs-people.spec.ts`) y arregla lo que no cuadraba:

- **El correo de la oferta de propiedad** enlazaba a `/ownership/<id>`, una página que el panel no tiene: ahora lleva a
  `/businesses`, donde está la tarjeta «… te ofrece …» con «Aceptar la propiedad». El de la aceptación, que mandaba a
  los Ajustes del negocio (donde el pagador no se cambia), lleva a `/businesses/<id>` y, con un plan de pago, dice
  que la tarjeta del saliente ya no lo renueva y hasta cuándo está pagado (F28; `hubs/tests/test_emails.py`).
- **El pie de «Te han invitado»** prometía «Podrás salir de un negocio cuando quieras desde el panel.» y no hay forma de
  salir uno mismo (como en Square, Toast o Shopify: quita el propietario o un administrador); ahora dice quién puede
  quitar el acceso (`InvitationPage.test.ts`).
- **El Hub cierra las sesiones** (hub, `MIGRATION-TASK: APP-HUBS-3`, BASE-F13): quitar, cambiar el rol y aceptar un
  traspaso encolan `POST /internal/sessions/revoke` tras el COMMIT y lo reintentan (`SessionRevocation`); el Hub borra
  esas sesiones por su índice (`base.SessionOwner`), su pestaña abierta deja de recibir y la foto aplica `members`
  (rol al día, baja fuera). e2e de los dos juntos: `tests/e2e/base-session-revoke.spec.ts` del Hub.
- **Mover el pagador** (F28, decisión de mercado: Wix, Shopify, Lightspeed, Squarespace, Fresha): el plan es del negocio
  y la tarjeta no. `hubs.ownership.accept` llama a `billing.end_renewal_after_hand_over` en su transacción: el plan que
  aún cobra la tarjeta de otra cuenta deja de renovarse (Stripe `cancel_at_period_end`; Stripe caído = 503 y el
  negocio no cambia de manos). El nuevo propietario lo mantiene con su tarjeta en Facturación › Suscripciones
  (`billing.plan.take_over`: Embedded Checkout con los mismos precios, `billing_cycle_anchor` = fin del periodo pagado
  y sin prorrateo); el webhook pasa el negocio a la suscripción nueva y termina la anterior sin reembolso. Un cliente de
  Stripe enviado sin su suscripción ya no pisa el de una suscripción viva (`hubs.subscription.apply`), y
  `retax_subscription` no recalcula el impuesto de un plan que cobra otra cuenta. Tests:
  `billing/tests/test_plan_take_over.py`; e2e: `tests/e2e/panel/hubs-people.spec.ts` («HUBS-G82 (F28)»).
- **Sin página global de personas** (G86, G34, G115 del SaaS viejo): ronda 17, cada negocio enseña las suyas en
  «Miembros». «Usuarios del Terminal» (G24) era esa misma página del SaaS viejo, no los empleados con PIN del Hub.

## Lo que añadió APP-HUBS-4 (2026-10-23): el plan, los derechos, quién llama y la taxonomía

Flujos `HUBS-F31`…`HUBS-F37` del `WORKBOOK.md` (parte 4 de 5; la revisión flujo a flujo de los `hecho`, en la 5).

- **VeriFactu en todos los planes** (F31; PLAN §30, ronda 2026-10-22b): `verifactu.live_paid` de la foto va siempre
  `true`; ya no depende de un plan de pago ni del módulo `verifactu`. Se queda en la foto mientras el Hub lea esa
  condición (`apps/verifactu`, 409 `verifactu.live_option_unpaid`); cuando el Hub la retire, se quita de aquí.
- **Lo que da un plan, cambiado en el admin** (F31; trampa de SAAS_DASHBOARD-F53/F54): los campos de `plan` de la foto
  son `queries.SNAPSHOT_PLAN_FIELDS` (una sola lista para la foto y el admin). Al guardar un `Plan` con alguno cambiado,
  `PlanAdmin.save_model` llama a `services.owe_plan_rights(plan)`: por cada negocio vivo con ese plan o con su prueba,
  `sync_plan_modules` y, si su foto cambia, `bump_state`. No empuja en la petición (un plan puede tener miles de
  negocios): lo entrega la siguiente pasada de `reconcile_hub_states` (15 min), y el admin dice cuántos negocios lo
  reciben («… negocios con este plan reciben el cambio en los próximos 15 minutos.»). Textos, orden o precio no deben
  nada. Tests: `tests/test_plan_rights_reach_businesses.py`.
- **Guardarraíl de `/internal`** (F35): `tests/test_internal_doors.py` recorre el resolver de URLs y comprueba que cada
  puerta `internal/…` (hoy 14, de `accounts`, `hubs`, `fiscal`, `fiscal_gateway` y `whatsapp`) contesta 401 o 405 sin
  firma, con la firma de otro secreto, con una marca de hace 10 minutos o con la sesión de un superusuario. Una puerta
  nueva que se salte `accounts.signing` lo rompe.
- **Taxonomía en el admin, en el idioma del personal** (F36): los campos de `Sector` y `BusinessType` (`code`, `icon`,
  `color`, `display_order`, `is_active`, `created_at`, `updated_at`, `sector`, `vertical`) tienen nombre traducible
  (migración `0017`, solo de estado, sin SQL); antes la lista decía «Code» y «Por is active».
- **Un módulo nuevo, o que cambia de nivel, en el admin** (F34; era una línea FIX de esta parte): `apps.admin.ModuleAdmin.
  save_model` llama a `services.owe_module_rights(tier, previous_tier)`: `sync_plan_modules` de cada negocio vivo cuyo plan
  o prueba alcanza el nivel nuevo o el anterior y `bump_state` si cambian; el admin dice cuántos lo reciben. Antes no
  llegaba a nadie hasta el siguiente aviso de Stripe de cada negocio.
- **El admin de Planes en el idioma del personal** (F31, pantalla de F05; era una línea FIX de esta parte): nombres
  traducibles en los campos de `Plan` (migración `0018`, solo de estado), `__str__` en el idioma activo («Starter · 29,99
  €/mes») y el nivel y el soporte por sus nombres traducidos en `PlanForm`. Antes, «PRICE MONTHLY» y «Por is active».
- **Descartado** (G23, G105, G106): el Hub no da de alta, comprueba ni quita personas en el SaaS. El SaaS es la fuente
  de quién tiene cuenta y acceso (PLAN-SAAS §2, «Quién sabe qué»), lo empuja en `members` de la foto y el Hub lo aplica
  (BASE-F13); los empleados con PIN viven en la BD del hub; «Invitar desde el Hub» sigue en PLAN-SAAS §8.
- **Lo que falta en el Hub** (F32 y F34, `parcial`): aplicar `max_devices`/`max_users` (llega con `DeviceSession`, fase 2)
  y frenar una app `premium` sin derecho en `modules[]` (402 `app_entitlement_blocked`). El SaaS ya los manda en la foto.
  Los mensajes del asistente (F33, `hecho`) los cuenta y los frena el turno de `assistant` (ASSISTANT-F18).
- e2e: `tests/e2e/panel/hubs-rights.spec.ts` (la ficha del plan y su aviso, la entrega al Hub doble tras la pasada, y
  las listas y fichas de la taxonomía; en `en` y `es`, a 390, 834 y 1440).

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
- El SDK (`@erplora/ui`, `ApiError`) solo conserva `code`, `message` y `fields` del sobre de error: para pintar
  `limit` y `used` de `hubs.seat_limit` el panel (L1-D) necesita que los conserve; hoy los tiene en `seats` de la
  lista y en el mensaje.
- Los usuarios solo con PIN del Hub no pasan por el SaaS: el tope de `max_users` de la foto lo aplica el Hub en
  sus propias altas (el SaaS ya no recibe el recuento del latido); llega con `DeviceSession` (fase 2, HUBS-F32).
- Mover el pagador de Stripe en un traspaso (L2). Cancelar la suscripción de Stripe al eliminar un negocio lo
  hace `billing` en su siguiente `sweep_unpaid` (L2-B), no `hubs.business.delete` en el acto.

## Lo que añadió L2-B (2026-10-14)

- `hubs.subscription.apply` (operación de sistema, la llama `billing`): escribe lo que dice la suscripción
  **viva** de Stripe (plan, periodicidad, estado, ids, periodo, prueba, módulos comprados y su `valid_until`,
  y el motivo del impago). Un campo que no se envía no se toca. Lo que ve el Hub (plan efectivo, estado
  comercial y `modules[]`) sube `state_version` y se empuja tras el COMMIT; cualquier cambio anota
  `hubs.subscription.changed`, que re-ejecuta la lista y la página. `standing` mueve el negocio (`good` →
  `active`, `grace` → `past_due`, `suspended`); uno eliminado no se mueve. Pagar un plan acaba con la prueba de
  Starter del alta; comprar solo módulos la conserva.
- `Subscription.unpaid_reason` / `unpaid_since` / `unpaid_invoice_url` (migración `0008`): la fila de
  Negocios y la página dan `unpaid_reason`, `unpaid_since` y `pay_url` (este, solo al propietario).
- `hubs.billing_profile.update` escribe el NIF con la puerta de `billing` (`validate_vat_for_profile`: forma
  de facturación y veredicto de VIES anotado; uno que VIES no conoce se guarda como identificación) y exige
  cinco dígitos al código postal español (`schemas.postal_code_problem`). Sin país del pagador, el NIF se lee
  en el del negocio.

## Lo que añadió L4-A (2026-10-14): uso de cada negocio

- **`HubUsageDaily`** (migración `0010`): una fila por negocio y día, tal como lo midió el Hub esa noche
  (PLAN-SAAS §5): `s3_bytes` (sus ficheros en S3), `db_bytes` (su BD; solo para el admin), `active_users_1d` y
  `active_users_30d`, más `collected_at`. Única escritora: la operación de sistema `hubs.usage.record`; volver a
  recoger un día sustituye sus cifras y, si son las mismas, no escribe ni avisa.
- **`manage.py collect_hub_usage [--day AAAA-MM-DD]`** (`saas-cron`, cada noche): por defecto, el día de **ayer en
  UTC**; `--day` recoge otro (relleno), nunca uno que no ha acabado en UTC. Lee todas las páginas de
  `GET /internal/usage`; una fila rota o que falla no para la pasada. Lock `hashtext('erplora.saas.collect_hub_usage')`
  (`services.run_exclusively`: una segunda pasada sale al momento). Sale con error **después** de la pasada si el
  Hub no contestó o se negó (`unreachable`, `refused`), si respondió fuera del contrato (`invalid`: fila, página,
  otro día o un cursor repetido) o si una fila reventó (`failed`). Un hub que el SaaS no vendió (el de plataforma,
  las plantillas) cuenta como `unknown`, en el log, sin error.
- **Evento `hubs.business.usage_collected`** (`{business_id}`), en el canal del propietario y de cada administrador
  (`notify_people`), solo cuando el día es nuevo o cambia: re-ejecuta `hubs.business.get`, `hubs.usage.get` y
  `hubs.usage.series` (no la lista de negocios). `hubs.subscription.changed` también re-ejecuta las dos de uso (el
  espacio depende del plan).
- **`hubs.usage.get {business_id}`** → `{day, storage: {used_bytes, limit_bytes|null, percent|null},
  active_users: {on_day, last_30_days}, stale}`: el último día medido. `used_bytes` = `s3_bytes` (el cliente ve
  ficheros en porcentaje, nunca la BD); `percent` redondeado (mitad hacia arriba) y por encima de 100 si se pasa;
  `stale` = el día no es el de ayer en UTC (también en el rato entre medianoche UTC y la pasada nocturna). Sin
  ningún día medido: 404 `hubs.usage_not_collected`. `hubs.business.get` lleva lo mismo en `usage` (`null` hasta
  la primera noche). **Cambio de nombre frente al encargo**: `active_users.on_day` en vez de `today`, porque la
  cifra es del día medido (ayer), como dice la maqueta («Activos ayer»).
- **`hubs.usage.series {business_id, days=30}`** (1–365) → `{business_id, limit_bytes, points: [{day, storage,
  active_users}]}`: los días medidos de la ventana que acaba ayer (UTC), del más antiguo al más reciente, contra el
  espacio del plan de hoy; los huecos no se rellenan (para la gráfica que vendrá).
- Las dos de uso: propietario y administradores (como la página del negocio; matriz de
  `tests/test_permission_matrix.py`), vivas, en `/api/hubs/usage` y `/api/hubs/usage/series`, y abiertas a una
  clave de API con `hubs.read`.
- **Admin**: `HubUsageDaily` de solo lectura (solo superusuarios; `support` no lo ve todavía), con los tamaños
  legibles, la BD incluida, búsqueda por dirección o nombre y navegación por días.
- **Panel** (`frontend/components/BusinessSummary.vue`): la tarjeta «Uso» de la maqueta, con
  `UsageMeter` (almacenamiento en %, con aviso desde el 80 % y al llenarse) y dos `UsageCounter` (activos ayer o
  ese día, últimos 30 días), y «Datos de ayer: se actualizan cada noche» o «Datos del <día>»; sin datos, «Sin
  datos todavía». Las personas frente a las plazas siguen siendo una línea de la tarjeta del plan.

### Espacio incluido en cada plan (decisión de L4-A, **a confirmar por Ioan**)

PLAN-SAAS §1 quitó de `Plan` los límites de tamaño (`max_database_size_gb`) y §5 enseña al cliente un
porcentaje «del espacio de su plan» sin decir de cuánto. Para no reabrir §1 (y su guardarraíl
`test_a_plan_sizes_no_infrastructure`), el espacio sale del **nivel de módulos del plan** (`Plan.included_level`,
`queries.STORAGE_LIMIT_GIB`): Gratis 1 GiB, Básico 5 GiB (Starter y Standard), Pro 20 GiB, Enterprise 50 GiB
(también Max, que en el SaaS antiguo no tenía tope de BD). Solo cuentan los ficheros (S3), no la BD. No se aplica
ningún tope: es un aviso. Si Ioan quiere un espacio por plan editable en el admin, va una columna
`Plan.storage_limit_gb` (y una nota que corrija PLAN-SAAS §1).

### Contrato para el Hub (carril Hub): `GET /internal/usage`

```
GET /internal/usage?day=YYYY-MM-DD[&cursor=<opaco>]
X-Erplora-Timestamp, X-Erplora-Signature (v1) y X-Erplora-Signature-V2 (cubre método y ruta con la query)

200 {"day": "2026-10-13",
     "hubs": [{"id": "<UUID del hub>", "s3_bytes": 0, "db_bytes": 0,
               "active_users_1d": 0, "active_users_30d": 0}],
     "next_cursor": "<opaco>" | null}
```

- `day`: el día en **UTC** que se pide; la respuesta lo repite (otro día = fuera de contrato).
- Una fila por hub y día, como mucho, en todas las páginas: `s3_bytes` (los objetos del prefijo `hub-{id}/`, del
  inventario de S3 de ese día), `db_bytes` (`pg_database_size` de `hub_<hex>`), `active_users_1d` (personas
  distintas con sesión o PIN usado ese día) y `active_users_30d` (en los 30 días que acaban ese día; nunca menos
  que `active_users_1d`). Enteros ≥ 0. Un hub sin medir ese día no sale.
- Paginación por cursor: `next_cursor` opaco (1–512 caracteres) que el SaaS devuelve tal cual; `null` en la última
  página. Tamaño de página a elección del Hub (se recomienda ≤ 500). Repetir un cursor es un error.
- Un día que el Hub aún no ha medido: 409 `usage_not_ready` (el SaaS falla la pasada y avisa; se rellena con
  `--day`). Sin `day` o con un día mal escrito: 422. Firma mala: 401, como el resto de `/internal`.
- Doble del Hub en los tests: `tests/hub_double.py` (`usage[day]`, `usage_page_size`).

### Pendiente tras L4-A

- **Carril Hub**: implementar `GET /internal/usage` (medición nocturna del worker y la respuesta de arriba). Necesita la
  BD por hub: `db_bytes` es `pg_database_size(hub_<hex>)` (fase 2, `docs/plans/2026-10-22-fase-2-tenencia.md`).
- **`aws-next`**: programar `python manage.py collect_hub_usage` cada noche en `scheduler.tf` (`saas-cron`), después
  de la medición del Hub (propuesta: 01:15 UTC; `push_hub_snapshots` va a las 00:30).
- La gráfica del panel con `hubs.usage.series` (bloque 8 de PLAN-SAAS; no está en la maqueta).
- `support` sin acceso al uso en el admin (si se quiere, migración de datos como `0007`).

## Demo (ronda 2026-10-17; PLAN-SAAS §3.5)

Plan: `docs/plans/2026-10-17-demo-hubs-fase-1.md` (§1.6 y §1.8). Una demo es un hub **vacío** del Hub
(`demo-<8 hex>`, 60 minutos); el SaaS **no guarda ninguna fila**: solo la sesión del navegador sabe cuál es
(`session["demo"] = {slug, expires_at}`). El código vive en `public/demo.py` (sin ORM) y en dos llamadas de
`hub_client.py`.

- **Entrada**, el mismo salto con `state` que un negocio (§2.1), sin cuenta del SaaS: `/demo/` (GET, **nunca
  crea**) → botón → `/demo/start/` (POST con CSRF) → `hub_client.create_demo` → 302 a
  `accounts.queries.hub_start_url(slug)` (`/auth/login?next=/` del hub demo) → el Hub pone su cookie de `state` y
  vuelve a `/demo/enter/?hub&next&state` → si la sesión es dueña de esa demo, `hub_client.create_demo_code` →
  formulario auto-enviado `accounts/hub_login_form.html` («Opening your demo…», variable `demo_jump`) al
  `/auth/callback` de la demo (el código nunca va en una URL). Sin `state` → 302 a `hub_start_url` (empieza el baile); un `state` de más de 128 caracteres →
  `/demo/?state=failed`; otra demo o ninguna en la sesión → `/demo/`.
- **Quién es el navegador para el Hub** (`session_key` del contrato): el sha256 hex de un token aleatorio que se
  guarda en la sesión (`session["demo_owner"]`), nunca la cookie. **Cambio frente al plan** (que decía el sha256
  de la clave de sesión): la clave rota al iniciar sesión en el SaaS (`cycle_key`) y el visitante perdería su
  demo con un 403; el token viaja con los datos de la sesión y la conserva (test
  `test_the_demo_survives_signing_in_to_the_saas`).
- **Contrato con el Hub** (firmado v1 + v2, como todo `/internal`):

  | Llamada | Cuerpo | Respuesta |
  |---|---|---|
  | `POST /internal/demos` (`create_demo`) | `{session_key, vertical: null, language}` | 201 `{id, slug, expires_at, created: true}`; 200 la viva de ese navegador (`created: false`); 503 `base.demo_full` |
  | `POST /internal/demos/{slug}/codes` (`create_demo_code`) | `{session_key, language}` | 201 `{code, expires_at}`; 404; 410 `base.hub_gone`; 403 `base.demo_not_owner` |

  `503 base.demo_full` es el **único 5xx** que el cliente trata como negativa (`HubRefused`, por
  `hub_client.DEMO_REFUSALS`) y solo en `create_demo`; el resto de 5xx siguen siendo `HubUnavailable`. Una
  respuesta que no nombra un hub `demo-…` con su `expires_at` (con zona) no se sigue nunca: estado `unavailable`.
- **Estados de `/demo/`** (siempre 200, `data-testid="demo-state-<estado>"`): `off` (`DEMO_ENABLED=False`),
  `idle`, `ready` (demo viva: «Back to my demo» y los minutos que le quedan), `expired` (la sesión guardaba una
  vencida, que se borra al decirlo, el Hub respondió 410/404, o se llega desde la página 410 de la demo), `full`,
  `throttled`, `unavailable` (Hub caído u otra negativa, que se registra en el log) y `failed` (el callback del Hub
  no aceptó el código: `/demo/?state=failed`). El `?state=` de la dirección solo elige uno de esos mensajes; nunca
  hace pasar por `ready` a quien no tiene demo.
- **Caducidad antes de su hora** (`demo_expire`, «Expire now» del admin del Hub): la sesión solo sabe
  `expires_at`, así que la página 410 de la demo enlaza a `/demo/?state=expired`, que **borra** `session["demo"]` y
  pinta `expired`. `/demo/` no consulta al Hub en ninguna visita: es una página pública (rastreadores, recargas) y
  una llamada firmada por visita no compensa, porque quien vuelve directo a `/demo/` y pulsa «Back to my demo» ya
  aterriza en `expired` (`/demo/enter/` oye el 410). Un enlace `?state=expired` engañoso no cuesta nada: el token
  `demo_owner` se queda y «Try the demo» devuelve la misma demo si seguía viva.
- **Límites**: `DEMO_ENABLED` (interruptor único) y `DEMO_SPAWN_RATELIMIT` (`3/h` por dirección, django-ratelimit
  sobre la caché como el formulario de contacto, y **solo demos nuevas**: la función de la tasa devuelve `None`
  si el navegador ya tiene una viva). El tope global de demos vivas y «una por navegador» los aplica el Hub. El
  WAF limita además `/demo` por IP.
- **CSP**: `/demo/` y `/demo/enter/` fijan su propia política (la pública con
  `form-action 'self' <HUB_ORIGIN_PATTERN>`) y `PublicCSPMiddleware` la respeta: el formulario de `/demo/enter/` va
  al origen de los hubs, y el de `/demo/` va a `/demo/start/`, que responde con un 302 al host de la demo, y Chrome
  aplica `form-action` también a esa redirección (con `'self'` solo, el botón no hacía nada; visto en prod el
  2026-10-17). El resto de la web pública sigue con `form-action 'self'`.
- **SEO**: `/demo/` está en el sitemap (0.6) y es indexable (su GET no crea nada); `/demo/enter/` lleva `noindex`
  (meta y `X-Robots-Tag`) y `no-store`.
- **Direcciones `demo-`**: `live.slugs` (≥ `cc36065`) reserva el prefijo para los clientes, así que un slug elegido
  `demo-…` es 409 `hubs.slug_reserved`, y `queries.base_slug` quita el guion del prefijo al proponer
  (`Demo Bar` → `demobar`, `Demo` → `demostore`) en vez de caer en `my-business`.
- **CTA**: «Try the demo» en el hero, en la banda final de la portada y en la barra para el visitante sin sesión.

### e2e

La de punta a punta es la del Hub (`hub/tests/e2e/demo.spec.ts`, cómo correrla en `hub/tests/e2e/README.md`, «La
demo»): necesita este SaaS con su `HUB_INTERNAL_URL` en el Hub de la pila. La del SaaS
(`tests/e2e/demo-door.spec.ts`) cubre la puerta sin Hub.
