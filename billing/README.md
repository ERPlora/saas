# `billing` — lo que una cuenta paga a ERPlora y su IVA

App de plataforma del SaaS (`LiveAppConfig`, `kind = "platform"`), detrás de `hubs` en `INSTALLED_APPS`
(grafo `accounts ← hubs ← billing`, plan `docs/plans/2026-10-13-panel-saas-unificado.md` §2 punto 15 y §3).
Lote **L2-A**: el motor de IVA de la UE, portado de `ERPlora/saas` `apps/dashboard/fiscal/` (`origin/develop`,
`c5ca8cae8`) con sus tests. Lote **L2-B**: Stripe (pago de planes y módulos, la suscripción de cada negocio, el
webhook único y el impago), portado de `hubs/subscriptions`, `hubs/main/webhooks.py`, `services/lifecycle.py` y
`apps/core/stripe_*`. Lote **L3-C**: las facturas de ERPlora a sus clientes (se registran del webhook, se numeran
aquí y las emite el hub de plataforma de `hub-next`) y la sección Facturación (Facturas · Suscripciones · Datos de
pago); detalle en «Facturas de ERPlora (L3-C)».

## Qué hay

| Pieza | Qué hace |
|---|---|
| `models.py` | `TaxCategory` (qué se vende), `TaxRule` (tipo por país/región/categoría con vigencia; `is_subject=False` = no sujeta), `FiscalPolicy` (emisor, alta en el ROI, OSS y su umbral; una sola fila), `CompanyConfig` (identidad fiscal de ERPlora, la del solicitante de VIES; una sola fila), `VatCheck` (bitácora de VIES: cada consulta es una fila nueva, nunca se edita) y `OssNotice` (los avisos al equipo del 80 % y del cruce del umbral OSS, uno por año y tipo) |
| `vat.py` | Calificación y desglose: `quote_vat` (lo que se SUMA a un neto; `None` = no se vende), `resolve_vat` (reparte lo ya cobrado, concilia el cero de Stripe en una venta sujeta), `add_vat`, `split_gross`, `vat_rate_for`, `BILLING_COUNTRIES`, `tax_id_type_for`. Sin ORM: lee la tabla por `queries.py` |
| `vies.py` | Cliente REST de VIES como solicitante identificado; nunca lanza: red caída, timeout, HTTP ≥ 400, JSON roto o «válido sin número de consulta» = `unavailable` |
| `services.py` | Las puertas: `check_vat_number`, `verify_customer_vat`, `clear_tax_id_for_stripe`, `record_manual_override`, `validate_vat_for_profile`, `sale_quote`, `sale_tax_rates`, `require_billing_location`; la operación `billing.vat_check.run` |
| `queries.py` | `tax_rule`, `fiscal_policy`, umbral OSS (`uses_destination_rate`/`destination_rate_applies`), `vies_requester`, `latest_vat_check`, `payer_of(hub)`; la operación `billing.tax.preview` |
| `stripe_tax_rates.py` | Qué `TaxRate` de Stripe necesita una venta (`TaxRateSpec`) y si uno existente lo es (`matches`). **No llama a Stripe**: el espejo (`TaxRate.list`/`create`, caché 24 h) es de L2-B (ver el docstring) |
| `seed.py` + `manage.py seed_tax_rules [--dry-run]` | Datos de hoy: tipos generales UE-27 de 2026, Canarias/Ceuta/Melilla no sujetas, Reino Unido no sujeto desde 2021-01-01, 6 categorías, la política y ERPlora (Modelo 036). Solo crea lo que falta; nunca pisa lo editado en el admin. Lo escribe también la migración `0002_seed_tax_data` |
| `admin.py` | Tabla de tipos editable, política y empresa como filas únicas, bitácora de VIES de solo lectura con forzado manual (autor y motivo) y la acción «Comprobar ahora en VIES» |

## Operaciones

- `billing.vat_check.run` — `POST /api/billing/vat-check` `{vat_number, country?}` → `{vat_number, status,
  valid, name, address, consultation_number, checked_at, is_current, reverse_charge, manual_override}`.
  Permiso propio `billing.vat_check` (toda cuenta con sesión; `billing.manage` no se da a nadie por defecto).
  Reutiliza una prueba vigente; si no, consulta y anota una fila (evento `billing.vat_check.completed`).
  `status`: `verified` · `invalid` · `unavailable` · `national` · `outside_vies`. `reverse_charge` es lo que
  hará la venta, con la misma regla que el motor (`vat.reverse_charge_applies`: ROI, país de la UE distinto
  del emisor, país informado y prueba de VIES). Errores: 422 `invalid_payload` (`fields.vat_number`), 429
  `billing.vat_check_throttled` o `billing.vat_check_in_progress` (una comprobación por persona a la vez),
  503 `billing.vat_check_not_recorded`. VIES caído es un 200 `unavailable`.
- `billing.tax.preview` — `GET /api/billing/tax-preview?country=&postal_code=&vat_number=&net=&category=plan|module`
  → tratamiento, tipo, cuota y total, `b2b`, `vat_status` (lo que diga la bitácora, más `absent` y
  `unchecked`) y `reverse_charge`. Consulta de solo lectura: nunca pregunta a VIES.

## Reglas que conviene saber

- **Código postal español**: solo cinco dígitos nombran provincia («3500» no es Las Palmas). Al vender, un
  lugar español sin código válido no se tarifica (409 `billing.billing_location_required`); al facturar lo
  ya cobrado, se trata como península (se cobra el IVA, con aviso en el log).
- **Reino Unido**: no sujeto; solo se vende a empresas (sin número de IVA británico, 409
  `billing.uk_business_required`).
- **Umbral OSS**: `queries.cross_border_b2c_cents` suma la base de las facturas B2C a otros estados de la UE emitidas
  aquí (L3-C; las rectificativas restan) a lo que `FiscalPolicy` guarda a mano del SaaS antiguo (año en curso
  y anterior, en céntimos). Sin esos importes el total es «desconocido» en el admin. Desde el año arrastrado
  (`oss_carried_year`) el total se sabe solo: los años siguientes son las facturas de aquí y el «año en curso»
  arrastrado pasa a ser el «año anterior», sin tocar el admin cada enero.
- **Revisión de la tabla** (`manage.py audit_tax_rules`, BILLING-F04, saas#1968/#1995): `queries.tax_rule_audit`
  comprueba que el emisor está en la TABLA (no solo en el respaldo `EU_VAT_RATES`), que IC/CE/ML resuelven «no
  sujeto» en la tabla y por el código postal (35001/51001/52001, la misma puerta que el cobro) y que cada
  territorio con un pagador en `hubs.BillingProfile` tiene tipo. Sale con error en el primer problema (alarma
  `task_failed`); un territorio que solo cubre el respaldo es un aviso.
- **Tipo de la suscripción viva** (`services.retax_subscription`, BILLING-F02/F06, saas#2293): al guardar los datos
  de facturación (`hubs.billing_profile.update`, tras el COMMIT, en `services.retax_payer`, que antes pone los
  datos en el cliente de Stripe con `services.push_payer_to_stripe`, BILLING-F01: los mismos parámetros que
  `ensure_customer`, nada si el pagador aún no es cliente; un fallo se anota `billing.customer_push_failed` y no
  impide el recálculo) y cada día (`manage.py retax_subscriptions`),
  cada item de una suscripción `active`/`trialing`/`past_due` recibe los `TaxRate` que el motor da hoy, sin
  prorrateo. Quitar un tipo es `tax_rates: ""` (una lista vacía la descarta el SDK y Stripe deja el tipo viejo;
  comprobado contra la API de prueba). Con una bajada programada (`PlanChangeSchedule`), la primera factura del
  plan nuevo la cobra la fase siguiente del calendario con los items que se fijaron al programarla:
  `_retax_schedule` re-declara cada fase que aún no terminó con los tipos de hoy (la actual conserva su
  `start_date`, su `trial_end` y su `end_date`; `end_behavior: release`; sin prorrateo). En las fases un tipo se
  quita con `tax_rates: []` y cambiar la fase actual cambia la suscripción en el acto (comprobado contra la API
  de prueba); un precio que ningún plan ni módulo tiene conserva su tipo. Un lugar que no se vende queda
  `refused` y el comando sale con error.
- **Avisos de la OSS** (`services.note_oss_threshold`, BILLING-F06, saas#2297/#2299): cada factura cobrada que
  cuenta para el umbral (B2C a otro estado de la UE, sin NIF-IVA comprobado) mira el total del año; la que lo
  lleva por encima del 80 % (`OSS_WARNING_PERCENT`) anota un `OssNotice` `near` y la que lo cruza (o la primera
  del año si el anterior cerró por encima) uno `crossed`, cada uno una vez al año (único por `(year, kind)`;
  el cruce primero, así un salto directo solo avisa del cruce). Sin avisos con el alta voluntaria en la OSS.
  El correo va a `SUPPORT_EMAIL` tras el COMMIT (cabecera `X-ERPlora-Notice: billing.oss_near|crossed`); uno
  que no salió se reenvía en `retax_subscriptions`, que sale con error mientras quede alguno
  (`notices_failed`). Anotar el aviso nunca rompe el cobro (`_note_oss_threshold_quietly`). Admin de solo
  lectura «Avisos de la OSS».

## VIES

- Por entorno: `VIES_ENDPOINT` (REST de la Comisión), `VIES_CONNECT_TIMEOUT_SECONDS` (3) y
  `VIES_TIMEOUT_SECONDS` (5); presupuesto por persona `VAT_CHECK_RATE` (`20/m`) y global
  `VAT_CHECK_GLOBAL_RATE` (`60/m`). Solo gasta presupuesto una consulta que de verdad sale hacia VIES.
- Como mucho 3 consultas a la vez por proceso (cada una tiene una conexión de BD esperando); la cuarta es
  `unavailable` en el acto, sin esperar.
- Sin cola de revalidación (ronda 11: sin `django.tasks`): solo se reutiliza una prueba vigente; lo demás se
  vuelve a preguntar en la siguiente necesidad.
- En los tests nunca se llama al servicio real: el `conftest.py` raíz apunta `VIES_ENDPOINT` a un puerto
  cerrado y `billing/tests/vies_double.py` falsea solo la red con respuestas grabadas.

## Stripe (L2-B)

**Una suscripción de Stripe por negocio**, con items: el plan y los módulos comprados, a precio **neto** más
**nuestros** `TaxRate` (uno por item, del motor de IVA; nunca `automatic_tax`). PLAN-SAAS §3.2–§3.4 y §4.

| Pieza | Qué hace |
|---|---|
| `stripe_service.py` | La única puerta a Stripe (el único módulo que importa `stripe`): `client()` con la clave del entorno (restringida `rk_live_` en prod; sin clave no se llama a nada), 1 reintento y `STRIPE_TIMEOUT_SECONDS`; devuelve dicts; errores `StripeUnavailable` (red, 429, 5xx) y `StripeRefused` (tarjeta, objeto inexistente, configuración); espejo de `TaxRate` (`tax_rate_ids`: reutiliza uno exacto y exclusivo, crea el que falta, 24 h en caché, nunca crea a ciegas si el listado falla); firma del webhook |
| `stripe_keys.py`, `stripe_period.py`, `stripe_checkout.py`, `stripe_test_clocks.py` | Modo de una clave (`sk_`/`rk_`), periodo de la suscripción (en el item desde la API de 2025), `ui_mode = embedded_page` y `metadata.kind`, relojes de prueba (rechaza una clave live) |
| `models.py` | `PromoCode` (días de prueba, ADR-0107), `CheckoutAttempt` (un Embedded Checkout por intención; la misma selección reutiliza su sesión abierta), `WebhookEvent` (cada evento una vez) y `PaymentFailure` (por qué no se cobró una renovación) |
| `webhooks.py` | `POST /webhooks/stripe/`: firma de Stripe → reclamo del evento → `services.process_stripe_event` |
| `management/commands/sweep_unpaid.py` | `saas-cron`: impagos que Stripe dejó de reintentar, suscripciones de negocios eliminados y pagadores de cuentas eliminadas (`payers_forgotten`) |
| `management/commands/retax_subscriptions.py` | `saas-cron` (diaria): el tipo de hoy en cada suscripción viva y en las fases de su bajada programada (cambio de dirección no empujado, umbral OSS) y el reenvío de los avisos de la OSS que no salieron |
| `management/commands/audit_tax_rules.py` | `saas-cron` (diaria) o a mano: la tabla de IVA cobra cada venta posible |

### Operaciones (solo el propietario del negocio; permiso `billing.pay`)

- `billing.checkout.start` — `POST /api/billing/checkout/start` `{hub_id, plan|module, interval, promo_code}`.
  Negocio sin suscripción de Stripe (Gratis): Embedded Checkout → `{flow: "checkout", client_secret, session_id,
  publishable_key}`. Con suscripción: `{flow: "confirm", preview: {amount_due_cents, tax_cents, currency,
  proration_date}}` (`invoices.create_preview`). Un plan comprado durante una prueba conserva los días que le
  quedan (`trial_end`); un código promocional los sustituye si da más; menos de 48 h no se arrastran. Desde el
  2026-10-15 ningún plan trae prueba (el plan Gratis es la entrada): el mecanismo queda dormido hasta que el staff
  dé días de prueba a un plan en el admin.
- `billing.checkout.confirm` — añade un módulo a la suscripción con el prorrateo de la vista previa: se cobra ya
  (`always_invoice`) o no se añade (`error_if_incomplete`; tarjeta rechazada → 409 `billing.card_declined`).
- `billing.plan.change` — cambia el precio del item del plan (y, si cambia la periodicidad, el de cada módulo),
  igual: ahora o nada. Gratis no es un cambio: 409 `billing.plan_is_free` (se cancela).
- `billing.plan.cancel` / `billing.plan.keep` — `cancel_at_period_end`; al vencer, el negocio vuelve a Gratis.
  `keep` con una factura sin pagar → 409 `billing.invoice_unpaid`.
- `billing.module.cancel` / `billing.module.keep` — el item sale sin prorrateo y el módulo vale hasta fin de
  periodo (`valid_until` en la foto); si es lo último que cobra la suscripción, se cancela al fin de periodo.
  `keep` de un módulo que ya no se vende (`Module.is_active` apagado) → 409 `billing.module_off_sale` (saas#2589:
  se cancela, nunca se recompra deshaciendo); uno terminado → 409 `billing.module_ended`. Un módulo terminado
  (`valid_until` pasado) ya no sale en la foto, en `billing.subscription.list` ni en la Tienda, que lo vuelve a
  vender; el aviso de Stripe de la renovación que ya no lo cobra borra su fila (BILLING-F34).
- `billing.portal.open` — sesión del Customer Portal (tarjetas y recibos de Stripe); `{url}`.
- `billing.promo.check` — `GET /api/billing/promo-check?code=` → `{code, valid, trial_days}`; presupuesto por
  persona `PROMO_CHECK_RATE` (429 `billing.promo_check_throttled`).

Lo que cambia la suscripción se lee de vuelta de Stripe y lo escribe `hubs.subscription.apply` (una app escribe
en otra solo por sus operaciones), que sube `state_version` y empuja la foto al Hub tras el COMMIT.

### Guardas de dinero (en este orden; ninguna llama a Stripe)

1. Sin clave usable: 503 `billing.payments_unavailable` (en live solo vale una clave **restringida**
   `rk_live_`; la secreta `sk_live_` se rechaza y `check --deploy` falla con `billing.E001`; en producción con
   `DEBUG` apagado una clave de test tampoco vale, `billing.E003`, para no vender planes por tarjetas de prueba). Con clave live,
   **sin ruta que envíe la factura** (reglas de trabajo §15): 409 `billing.invoicing_unavailable` mientras
   `PLATFORM_INVOICING_ENABLED` esté apagado (por defecto) o el hub de plataforma no conteste
   `GET /internal/platform/invoices/health` → 200 `{"status": "ok"}` (la respuesta buena se guarda 5 min; una mala
   se vuelve a preguntar la próxima vez). Después, **el total OSS sin cargar** (`oss_carried_year` vacío o
   posterior al año): 409 `billing.oss_total_unknown`. Una clave de test no mueve dinero real y no se frena.
   Antes de todo, la cuenta debe ser el **pagador** del negocio (`BillingProfile.owner`) y la suscripción debe
   cobrarse a su cliente de Stripe: tras un traspaso, 409 `billing.payer_required`.
2. Factura sin pagar (suscripción `past_due`/`unpaid` o negocio suspendido): 409 `billing.invoice_unpaid`.
3. Lugar del pagador (409 `billing.billing_location_required`), consumidor del Reino Unido, territorio sin regla.
4. Renovación de más de 400 € con IVA sin NIF del pagador (factura completa, RD 1619/2012 art. 4): 409
   `billing.tax_id_required`.
5. El NIF-IVA solo llega al cliente de Stripe si VIES lo probó (o es nacional); Stripe no lo recoge
   (`tax_id_collection` apagado).

### Webhook

Eventos a suscribir en Stripe: `checkout.session.completed`, `checkout.session.async_payment_succeeded`,
`checkout.session.async_payment_failed`, `checkout.session.expired`, `invoice.paid`, `invoice.payment_failed`,
`invoice.voided`, `invoice.marked_uncollectible`, `credit_note.created`, `charge.refunded` (los cuatro de L3-C),
`customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted` y
`customer.updated`. Sin firma válida, 400; sin `STRIPE_WEBHOOK_SECRET`, 503; duplicado, 200 `duplicate`; en curso
en otra entrega, 409; fallo, 500 (Stripe reintenta). Siempre se lee la suscripción **viva** con el negocio
bloqueado (el mismo orden de bloqueo que las operaciones: negocio y después `PaymentFailure`); si Stripe no
contesta, **no se aplica nada**: 500 y Stripe reintenta. Una factura que llega antes que su
`checkout.session.completed` encuentra el negocio por el `hub_id` de los metadatos de su suscripción. Las filas de
`WebhookEvent` se olvidan a los 30 días (`manage.py purge_webhook_events`, BILLING-F37: Stripe solo reenvía 3 días).
Un aviso que nunca llega lo corrige `manage.py sync_subscriptions [--dry-run]` (BILLING-F38): relee cada suscripción
con id de Stripe, bajo el cerrojo del negocio, con el mismo `live_state` que el webhook, y escribe por
`hubs.subscription.apply` solo si algo cambió (y anota `billing.subscription_drift` con los campos); una que Stripe
no conoce (`resource_missing`) o no se pudo leer no se toca y hace fallar la pasada (`task_failed`). Un segundo
checkout pagado para un negocio que ya paga no se aplica: esa suscripción se cancela al momento con el tiempo no
usado como crédito, y queda un ERROR para soporte. `invoice.paid` además registra la factura de ERPlora (L3-C)
con `vat.resolve_vat` + `clear_tax_id_for_stripe`: una venta sujeta sin impuesto es un ERROR
`fiscal.vat.stripe_charged_no_tax_on_subject_sale` y la factura saca el IVA de lo cobrado.

### Impago

7 días de gracia desde la **factura** fallida (no desde el periodo local): el negocio pasa a `past_due` («pago
pendiente», abre); pasados, o con `unpaid` de Stripe, `suspended`. Pagar lo devuelve a `active` al momento.
`unpaid_reason` en la fila de Negocios y en la página: `card_declined` (rechazo de verdad, tarjeta caducada o mal
escrita: «Pagar» espera a otra), `card_changed` (tarjeta nueva por el Portal: «Pagar» vuelve),
`authentication_required` y `payment_failed` (también los rechazos que la misma tarjeta puede pasar luego:
`insufficient_funds`, `try_again_later`…); `unpaid_since` y `pay_url` (solo para el **pagador**, no para el rol).
Un `payment_failed` reenviado de una factura ya pagada no la reabre.
**Avisos por correo** (BILLING-F16, saas#2593): tras el COMMIT de todo lo que deja el negocio en impago
(`apply_state` con `standing` `grace`/`suspended`), `notify_unpaid` escribe a quien paga (su correo de facturas o
el de su cuenta, en su idioma) una vez por factura no cobrada mientras dura la gracia (importe, día de la
suspensión y enlace a Facturación) y una vez al suspender (`PaymentFailure.notified_at` /
`suspension_notified_at`; cabecera `X-ERPlora-Notice`: `billing.payment_failed`, `billing.business_suspended`).
Un correo que no sale se reenvía en `sweep_unpaid` (`notified`, `mail_failed`; con `mail_failed` el comando falla).
El Hub no abre un negocio cuya foto dice `suspended`: 402 `base.hub_suspended`, también con sesión. `sweep_unpaid` repasa cada negocio en impago
con su factura abierta más antigua (si ya está pagada, aplica la suscripción viva) y cancela al momento la
suscripción de Stripe de todo negocio que se eliminó (`Subscription.cancel_requested_at`, que pone
`hubs.business.delete` y no deshace recuperarlo).

### Configuración

`STRIPE_SECRET_KEY` (`rk_live_` en producción), `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`,
`STRIPE_PORTAL_CONFIGURATION` (`bpc_…`, solo tarjetas y recibos; sin ella el Portal no abre: 503
`billing.portal_unavailable`), `STRIPE_TIMEOUT_SECONDS` (10), `PROMO_CHECK_RATE` (`20/m`) y
`PLATFORM_INVOICING_ENABLED` (L3-C; apagado: una clave live no cobra). Un código
promocional vale una vez por negocio y por pagador (`PromoRedemption`). Los precios: `Plan.stripe_price_id` / `stripe_price_id_annual` (admin; al guardarlos, `plan_price_problems` los
comprueba en Stripe: activo, euros, periodicidad, importe del plan, `exclusive` y producto, BILLING-F28) y
`apps.Module.stripe_price_id_monthly` / `_annual`, netos (`tax_behavior = exclusive` en Stripe). En los tests
nunca se llama a Stripe: `billing/tests/stripe_double.py` sustituye a `stripe_service.client()` y los
eventos se firman como los firma Stripe.

**Stripe en pre** (`ERPLORA_ENVIRONMENT=pre`, `pre.erplora.com`; plan `../docs/plans/2026-10-14-entorno-pre.md`):
solo modo test. Quien empuja a la rama `pre` ejecuta código con los secretos de pre, así que una clave live
(`sk_live_`, `rk_live_` o `pk_live_`) falla `check --deploy` con `billing.E002` y `stripe_service.key_mode()` la
trata como ninguna (`UNKNOWN`: 503 `billing.payments_unavailable`, nunca un cobro real). En el secreto
`erplora/pre/app` (lo carga `stripe-setup-pre.sh`, fuera del repo, gemelo de `stripe-setup-live.sh` en modo test):

- `STRIPE_SECRET_KEY`: una clave **restringida de test** `rk_test_…` con los mismos permisos que la live;
  `STRIPE_PUBLISHABLE_KEY`, la `pk_test_…`;
- `STRIPE_WEBHOOK_SECRET`: el `whsec_…` del endpoint de test `https://pre.erplora.com/webhooks/stripe/`, suscrito
  a los mismos 14 eventos que prod (los de «Webhook»). Con pre apagado, Stripe reintenta hasta 3 días;
- `STRIPE_PORTAL_CONFIGURATION`: el `bpc_…` de un Customer Portal de test, solo tarjetas y recibos, como prod;
- los precios: los ids de Stripe **test** en cada `Plan` y `apps.Module`, desde el admin de pre. Se paga con las
  tarjetas de prueba de Stripe (`4242 4242 4242 4242`).

`PLATFORM_INVOICING_ENABLED` se queda en `false` en pre.

## Fuera de L2-A

- **L2-B (hecho)**: `hubs.billing_profile.update` llama a `validate_vat_for_profile` y exige cinco dígitos al
  código postal español; checkout con `TaxRateSpec` → `TaxRate` de Stripe; webhook con `resolve_vat`; la suma
  OSS desconocida frena toda venta con clave live (409 `billing.oss_total_unknown`); umbral de factura completa
  (400 € con IVA). Sin portar: cliente de HMRC y `audit_tax_rules`.
- **L3-C (hecho)**: `Invoice`; `queries.cross_border_b2c_cents` suma sus facturas (el tripwire se sustituyó por
  los dos tests portados de `fiscal/tests/test_tax_rules.py` y cuatro más) y las pruebas de la factura de
  `test_vies_contract`, `test_payer_vat_reaches_the_invoice` y `test_reverse_charge_switch` están en
  `test_invoice_recording` y `test_invoice_models`.

## Pendiente tras L2-B

- **L2-D (front)**: hecho, ver «La Tienda (L2-D)» abajo; queda el bloqueo de Trusted Types que se cuenta allí.
- **L2-C**: `billing.module.list` y `hubs.module.list`; nadie escribe aún los items `source = plan` (módulos
  incluidos en un plan).
- **Eliminar un negocio** cancela su suscripción de Stripe en la siguiente pasada de `sweep_unpaid` (no en el
  acto: `hubs.business.delete` no llama a `billing`); **mover el pagador** de Stripe en un traspaso sigue
  pendiente.
- **Eliminar la cuenta** (ACCOUNTS-F27, RGPD art. 17): `payer_leaving` (señal `account_deleting`) pone a cada
  pagador de la cuenta su fecha de purga (`forget_after`, `PAYER_RETENTION` = los 90 días de `Hub.RETENTION`) y
  tras el COMMIT `forget_departed_payer` borra el cliente de Stripe, desliga sus negocios y borra la ficha, salvo
  que algo aún se pueda cobrar: una suscripción que Stripe sigue cobrando o una factura sin pagar, que espera
  hasta su fecha de purga y entonces se anula en Stripe. Una suscripción viva solo llega aquí en un negocio
  **eliminado**, y la termina la siguiente pasada de `sweep_unpaid`; la de un negocio vivo no llega nunca: quien
  aún lo paga (su pagador, o la tarjeta que paga el plan tras un traspaso, `hubs.queries.still_pays`) ni elimina
  su cuenta (409 `accounts.pays_businesses`) ni sale del negocio (409 `hubs.member_pays`). Las facturas emitidas
  guardan su copia del pagador. `sweep_unpaid` hace lo que el borrado no pudo (`payers_forgotten`; un fallo de
  Stripe cuenta en `errors`).
- **Configuración de Stripe** (a mano, una vez): endpoint `https://erplora.com/webhooks/stripe/` con los eventos
  de arriba; tras agotar los reintentos, «marcar la suscripción como impagada» (`unpaid`); Customer Portal solo
  con tarjetas y recibos (los cambios de plan van por el panel, que pone nuestros `TaxRate`); precios con
  `tax_behavior = exclusive` (no hay sincronización de productos: los ids se copian en el admin).
- **aws**: `sweep_unpaid` ya corre cada hora (`sweep-unpaid-hourly` en `stacks/prod/scheduler.tf`); falta programar
  `retax_subscriptions` y `audit_tax_rules` una vez al día (APP-BILLING-1; mientras no estén, BILLING-F04 y
  BILLING-F06 siguen `parcial`), y `sync_subscriptions` y `purge_webhook_events` cada noche (APP-BILLING-3;
  mientras no estén, BILLING-F38 y BILLING-F37 siguen `parcial`).

## La Tienda (L2-D)

Página `/store/:tab` (`plans` | `modules`, `?business=<id>`) de `billing/frontend/` (maqueta `store.html`, ronda
17 §2.10–§2.11). Solo web: dentro de las apps y con `?surface=account` la propia página dice «La tienda no está
en la app» sin enlace y no carga nada (`<WebOnly>`; el `NotInAppPage` de `meta.webOnly` del shell no puede
decir ese texto).

- `billing.store.catalog` — `GET /api/billing/store?hub_id=` (query, solo el propietario; 409
  `hubs.business_deleted`) → cada `apps.Module` a la venta (`slug`, `tier`, precios netos en céntimos, si el
  negocio lo tiene, `source`, `valid_until`) y el plan del negocio (`plan`, `billing_interval`, `status`,
  `paying` = Stripe ya lo cobra, `cancel_at_period_end`, `current_period_end`, `trial_plan`, `trial_end`).
  Nombre, resumen e icono los pone la página con `apps.app.list` (`premium=true`), unidos por `slug == app.id`;
  sin app `premium` o sin `Module`, no se vende. Cubre la parte de la Tienda de `billing.module.list` de L2-C.
  Un módulo retirado que el negocio aún tiene sigue en la lista con `on_sale=false` y su `name`, `summary` e
  `icon_svg` (de `apps.queries.cards_of`, aunque la app ya no esté `listed`), para poder cancelarlo
  (BILLING-F31, saas#2589); a los demás negocios no se les ofrece.
- Compra: negocio sin suscripción de Stripe → `CheckoutModal` (datos de facturación antes del primer pago,
  `hubs.billing_profile.get/update`; Embedded Checkout con `createEmbeddedCheckoutPage({fetchClientSecret})`; al
  terminar, «Pagando…» y la página del negocio con un aviso). Negocio que paga → un diálogo por módulo con su
  prorrateo (`ProrationDialog`: `billing.checkout.start` → `billing.checkout.confirm`/`billing.plan.change`) y
  `AnnualSwitchDialog` (total con IVA). «Bajar a Gratis» = `billing.plan.cancel` con confirmación; «Mantener»
  (`billing.plan.keep`, `billing.module.keep`, sin cobro hoy). Con una factura sin pagar, nada que cobre en ese
  negocio. Código promocional: `billing.promo.check`.
- «Cancelar el módulo» (`ModuleCard` lo emite, `StoreShop` lo confirma con un `ConfirmDialog`
  `store-cancel-module`: hasta cuándo funciona, que no se borra nada y que se deshace con «Mantener») →
  `billing.module.cancel`; un rechazo se queda en el diálogo con su motivo. Solo para un módulo comprado
  (`source=purchase`), nunca para uno que trae el plan.
- **Admin del catálogo** (`apps/admin.py`): un `Module` que algún negocio tiene no se borra (saas#2568; Stripe
  cobraría un precio que nadie vende): `get_deleted_objects` lo marca protegido con el negocio
  (`billing.queries.businesses_having_module`) y pide desmarcar «activo».
- **e2e**: `tests/e2e/panel/billing-apps.spec.ts` con `billing_apps_seed.py` (parte 2: módulos en todos sus estados,
  contratar, cancelar, terminado, llevar a otro negocio, la página de una factura, Suscripciones, planes y cambio de
  plan; Stripe en el borde de la API, como `store.spec.ts`).
- Stripe.js (`stripe-js.ts`): solo web, solo al abrir un pago, con el nonce de la página; su `src` es una cadena,
  como la de los trozos que carga el propio Stripe.js, y la admite la política `default` de Trusted Types (abajo).
- CSP (`base/csp.py`, aplicada por `base/spa.py` al HTML de la SPA salvo la superficie de cuenta): `script-src`
  `https://js.stripe.com https://*.js.stripe.com https://checkout.stripe.com`; `frame-src` `'self'` +
  `https://js.stripe.com https://*.js.stripe.com https://hooks.stripe.com https://checkout.stripe.com`;
  `connect-src https://api.stripe.com https://checkout.stripe.com https://merchant-ui-api.stripe.com`;
  `img-src https://*.stripe.com`; `trusted-types` queda como lo deja `live.csp`. La web pública nunca nombra
  Stripe.
- **Trusted Types (plan §7 punto 5, resuelto el 2026-10-14)**: el cargador de Stripe.js pone como `src` cadenas
  (`…/v3/fingerprinted/js/embedded-checkout-outer-*.js`, `…/trusted-types-checker-*.js`) y no crea política
  propia, así que las atiende la política `default` de la página. Un solo mecanismo: `frontend/main.ts` pasa
  `createShell({ trustedScriptOrigins: ['https://js.stripe.com'] })` y `default.createScriptURL` admite solo
  URL `https` de ese origen exacto (`@erplora/ui`, `shell/boot/trusted-types.boot.ts`); toda otra URL de script
  se rechaza. La `script-src` de cada página sigue decidiendo (la superficie de cuenta no nombra Stripe).
  Verificado con la CSP de producción en Chrome: Stripe.js inyecta sus trozos y el Embedded Checkout se crea y
  se monta sin ninguna violación.

## Facturas de ERPlora (L3-C)

El recibo de Stripe no es la factura legal (PLAN-SAAS §4, ADR-0478). La factura la **registra y numera el SaaS**
en la transacción del webhook y la **emite el hub de plataforma** de `hub-next` (su cadena VeriFactu, su QR y su
PDF). Aquí nunca se simula VeriFactu: sin respuesta del Hub la factura sigue «emitiéndose».

### Decisiones fiscales

- **Numera el SaaS**: contador propio por serie (`ERP-<año>-<5 cifras>`; las rectificativas, `ERPR-…`, serie
  propia, RD 1619/2012 art. 15.5), bloqueado en la transacción de la factura; la fecha de expedición se lee con el
  bloqueo ya tomado (un número posterior nunca lleva una fecha anterior) y el año nuevo vuelve a empezar en 1. El
  Hub recibe número y fecha. (PLAN-SAAS §4 decía que el Hub «devuelve número»: señalado, falta la ronda.)
- **Se factura al cobrar** (PLAN-SAAS §4): una renovación sin pagar se lista «No cobrada», sin número, y se
  numera la misma fila al pagarla; anulada o incobrable en Stripe, `void`, sin factura.
- **Las bajadas esperan al final del periodo**: un plan más barato, o de anual a mensual, no se cobra ahora (eso
  abonaría lo no usado del caro: una factura de Stripe en negativo). Stripe lo guarda como *subscription
  schedule*: la fase actual acaba con el periodo pagado y la siguiente cobra los items nuevos sin prorrateo; el
  negocio conserva lo pagado hasta entonces (`PlanChangeSchedule`, `scheduled_change` en la API). Las subidas se
  cobran al momento. Mantener el plan deshace la bajada; cancelar la sustituye (gana Gratis); comprar o cancelar
  módulos espera a deshacerla (409 `billing.plan_change_pending`).
- **Todo lo devuelto es una rectificativa** con importes negativos, la calificación y el destinatario de la
  original y su tipo VeriFactu (`rectification_type`: R1 devoluciones, duplicados y cambios de precio, art. 80.1 y
  80.2 LIVA; R4 lo demás, como un cobro fraudulento) y su motivo (`rectification_reason`, la nota o el motivo de
  Stripe): una nota de crédito, una devolución hecha sin ella (`charge.refunded`: el bruto devuelto, con el IVA
  sacado al tipo de la original, una vez por devolución) o una factura de Stripe en negativo (heredada o manual:
  rectifica la factura cuyo periodo abona).
- **VIES al facturar**: el NIF-IVA se juzga a fecha del cobro con el último veredicto de VIES hasta entonces,
  aunque tenga más de los 30 días que exige una venta (la prueba viaja con la factura). Sin ningún veredicto y con
  VIES caído, la factura espera (500, Stripe reintenta): nunca IVA español en una venta B2B intracomunitaria
  porque VIES no contestaba. Solo se juzga un NIF de otro estado miembro.
- **Nada se factura distinto de lo cobrado**: si las líneas no suman lo que Stripe cobró o devolvió, 500 y
  ERROR `fiscal.invoice.lines_do_not_add_up`, sin número gastado. Un pago que no se puede colocar en un negocio
  (`billing.unplaced_payment`), una rectificativa sin su factura todavía (`fiscal.credit.unknown_invoice`) o VIES
  caído sin prueba (`billing.invoice_waits_for_vies`): 500, Stripe reintenta; nunca un «unknown» silencioso. El
  primer cobro de un checkout duplicado se factura a su negocio.
- **Cobrar en live exige ruta de envío** (reglas de trabajo §15): `PLATFORM_INVOICING_ENABLED` y la salud del hub
  de plataforma (ver «Guardas de dinero»).

| Pieza | Qué hace |
|---|---|
| `models.py` | `Invoice` (factura o rectificativa; pago `open`/`paid`/`void`; estado fiscal `issuing`/`issued`/`accepted`/`accepted_with_errors`/`rejected`, el del Hub; el pagador copiado el día de la emisión; importes en céntimos, `net + tax = total`; pagada ⇔ numerada, en la BD; `stripe_source_id`, `rectification_type`, `rectification_reason` en las rectificativas), `InvoiceLine` (una por línea de Stripe, con su categoría, tipo, base y cuota sellados; `item_kind`/`item_slug` dicen qué plan o módulo cobra), `InvoiceCounter` (año y último número por serie) y `PlanChangeSchedule` (la bajada que espera) |
| `services.py` | `issue_number`, las operaciones internas `billing.invoice.record`, `billing.credit_note.record`, `billing.refund.record` y `billing.invoice.apply_fiscal_status`, `post_platform_invoice`, `refresh_platform_invoice`, `send_invoice_mail`, `reconcile_platform_invoices`, `invoicing_available` y `billing.invoice.pay` |
| `queries.py` | `billing.invoice.list`, `.get`, `.pdf`, `.csv`, `billing.subscription.list`, `billing.payment_method.get` |
| `live.py` | Facturas y Suscripciones son vivas; un evento de una factura llega al canal de su pagador y al del propietario de su negocio. La tarjeta no es viva (pregunta a Stripe) |
| `emails.py` | El aviso al pagador cuando el Hub la emite (texto plano en su idioma, con enlace a Facturación) |
| `management/commands/reconcile_platform_invoices.py` | `saas-cron`, cada 15 min: reintenta lo que el Hub debe y los correos que no salieron |

### Contrato con el hub de plataforma (lo implementa el carril Hub; firma HMAC v1 + v2 como todo `/internal`)

- `GET /internal/platform/invoices/health` — 200 `{"status": "ok"}` cuando el Hub emite facturas: abre el cobro
  en live (con `PLATFORM_INVOICING_ENABLED`). Cualquier otra respuesta lo cierra.
- `POST /internal/platform/invoices` — idempotente por `id`: repetirla devuelve lo que el Hub tiene. Cuerpo:
  `{id, kind: "invoice"|"credit_note", series, number, issued_on, stripe_invoice_id, stripe_source_id,
  rectification: null | {type: "R1"|"R2"|"R3"|"R4", reason}, currency, language, net_cents, tax_cents,
  total_cents, tax_treatment, tax_country, tax_rate: "21.00", vat_included_reconciled,
  vat_included_because_unverified, business: {id, name}, recipient: {name, tax_id, tax_id_type, tax_id_verified,
  vat_consultation_number, address, city, postal_code, country, email}, lines: [{position, description,
  item_kind, item_slug, quantity, proration, period_start, period_end, tax_category, tax_treatment, tax_rate,
  net_cents, tax_cents, total_cents}], rectifies: null | {id, number, issued_on}}`. Respuesta 200/201:
  `{status: "issuing"|"issued"|"accepted"|"accepted_with_errors"|"rejected", qr: "<contenido del QR>",
  error?: {code, message}}`. 4xx = negativa (se guarda su `code`, se reintenta y el comando falla); 5xx o sin
  respuesta = se reintenta.
- `GET /internal/platform/invoices/{id}` — la misma respuesta: el SaaS pregunta por las `issued` y `rejected`
  hasta que la AEAT acepta (una rechazada la corrige el Hub con un registro nuevo; su siguiente respuesta manda).
- `GET /internal/platform/invoices/{id}/pdf` — el PDF (`application/pdf`); 404 si no la tiene. El SaaS no lo
  guarda: lo pide al descargarlo (PLAN-SAAS §3.6 punto 7).

### Reintentos

`reconcile_platform_invoices` (lock `hashtext('erplora.saas.reconcile_platform_invoices')`): vuelve a mandar cada
«emitiéndose» cuya espera pasó (15 min tras el primer fallo, el doble cada vez, como mucho 6 h), pregunta por las
emitidas y rechazadas, cuenta como `stuck` las que llevan más de 1 h emitiéndose y envía los correos de las
emitidas que no salieron. Sale con error si queda algo `unreachable`, `refused`, `rejected`, `stuck`,
`mail_failed` o `errors`. En el admin (con `billing.change_invoice`), «Reenviar al hub de plataforma» y
«Reenviar el correo de la factura».

### Operaciones (permiso `billing.view` para leer, `billing.pay` para pagar)

Ve una factura la cuenta que la pagó (su pagador ese día) y el propietario actual del negocio; nadie más (404).

- `billing.invoice.list` — `GET /api/billing/invoices?hub_id=&status=paid|open|void&year=&search=&limit=&offset=`
  → `{rows, total, limit, offset}`; por fila: `number` (null sin pagar) y `reference` (el número de Stripe),
  `date`, `business {id, name}` (el nombre de la factura), importes en céntimos, `payment_status(_label)`,
  `fiscal_status(_label)`, `pay_blocked_reason` (`card_change_required` | `payer_required`), `actions`
  (`pay`, `pdf`, la fija primero), `can {pay, pdf}`, `rectification` (`null` en una factura; en una
  rectificativa, `{type: "R1"|"R2"|"R3"|"R4", reason}`) y `stripe_source_id` (`cn_…`/`re_…` de la rectificativa;
  vacío en una factura). Viva. Expuesta a las claves con `billing.read`.
- `billing.invoice.get` — `GET /api/billing/invoices/detail?id=` → la fila más líneas, destinatario, `rectifies` y QR.
  Viva (`billing/live.py`): la página de una factura pasa de «Emitiéndose» a su número y su QR sola.
- `billing.invoice.pdf` — `GET /api/billing/invoices/pdf?id=` → el fichero del Hub; 404
  `billing.invoice_not_issued` hasta que el Hub la emite; Hub caído, 503 `billing.platform_unavailable`.
- `billing.invoice.csv` — `GET /api/billing/invoices/csv?<filtros>` → «Descargar Excel» de todo lo filtrado:
  UTF-8 **con BOM** (sin él Excel rompe los acentos) y, en español, `;` y coma decimal (lo que espera Excel en
  ese idioma); en inglés, `,` y punto. Fechas ISO. Una celda de texto que empieza por `= + - @` lleva `'`
  delante (inyección de fórmulas). Decidido frente al SaaS antiguo, que no ponía BOM.
- `billing.invoice.pay` — `POST /api/billing/invoices/pay {id}` → `{url}` (la página de Stripe); solo su pagador
  (409 `billing.payer_required`); tarjeta rechazada sin cambiar, 409 `billing.card_change_required`; ya pagada,
  409 `billing.invoice_paid`; anulada, 409 `billing.invoice_void`.
- `billing.subscription.list` — `GET /api/billing/subscriptions` → una fila por negocio que Stripe cobra (del
  propietario o del pagador): plan y módulos a precio neto, `next_invoice {date, total_cents con IVA, currency}`
  (null si se cancela; `total_cents` null sin lugar del pagador), estado, `cancelling`, `ends_at`,
  `cancel_requested`, `unpaid_invoice_id`, `scheduled_change` (la bajada que espera), `actions` (`view_invoice`
  primero si hay una sin cobrar; si no, `change_plan` o `keep_plan`; `cancel_plan`; `view_invoices`) y `can`.
  Cambiar/cancelar/mantener: el propietario que paga. Viva. Filtros `?hub_id=` (uno ajeno da la lista vacía) y
  `?status=` (el de la suscripción); expuesta a las claves con `billing.read` (BILLING-F18, la API de
  suscripciones del SaaS antiguo). Un módulo terminado no sale.
- `billing.payment_method.get` — `GET /api/billing/payment-method?hub_id=` → por pagador de la cuenta, sus
  negocios, la tarjeta (`brand`, `last4`, `exp_month`, `exp_year`; la de la suscripción o la del cliente),
  `unavailable` si Stripe no contesta y el último cobro fallido. 10 min en caché; `customer.updated` la olvida.
- Cambiar la tarjeta: `billing.portal.open` (Customer Portal).

### Las páginas de Facturación (L3-C front)

`/billing/:tab` (`invoices` | `subscriptions` | `payment`; `/billing` abre Facturas conservando la consulta, que es
también la vuelta del Customer Portal) en `billing/frontend/` (maqueta `billing.html`, ronda 17 §2.6, §2.7 y §2.11).
No vende, así que está en todas las superficies: en las apps y con `?surface=account` se ven facturas y
suscripciones y se editan los datos fiscales; pagar, cambiar la tarjeta y cambiar, mantener o cancelar el plan
son solo web, y en su lugar se dice, sin enlace, cómo hacerlo desde el navegador.

- **Arriba, en las tres pestañas** (`BillingNotices` + `unpaid.ts`): las facturas no cobradas (`billing.invoice.list`
  con `status=open`, viva) con el estado de su negocio (`hubs.business.list`). En Facturas, un aviso por factura
  (`UnpaidInvoiceNotice`): importe, negocio, factura y fecha, hasta cuándo funciona (7 días) o que está suspendido;
  en la web «Pagar la factura» es el principal y, con `pay_blocked_reason = card_change_required`, «Cambiar tarjeta»
  (Customer Portal) pasa a principal y «Pagar» espera con el motivo (`aria-describedby`); con la tarjeta cambiada
  (`unpaid_reason = card_changed`) el aviso lo dice y «Pagar» vuelve. En las otras pestañas, una línea con enlace.
- **Pagar** (`pay.ts`, `PayInvoiceButton`): `billing.invoice.pay` → la página de Stripe, navegación de primer nivel.
  Un pago a la vez en toda la página (aviso y fila comparten el estado): «Pagando…» desde el clic hasta salir, sin
  doble cobro. La factura se recuerda en `sessionStorage` y, cuando sale de las no cobradas (aquí, en otra pestaña o
  al volver de Stripe), se pregunta `billing.invoice.get` y, pagada, «Factura pagada: … vuelve a estar al día».
- **Facturas** (`InvoicesTab`): `DataTable` de servidor (tarjetas hasta 1100 px), filtros negocio (también
  `?business=`; uno ajeno enseña todas y lo dice; uno en Gratis dice que no tiene), estado y año, guardados en la
  dirección; búsqueda por número; «Pagar» fija (solo web) y PDF si `can.pdf`; si no, «Emitiéndose». Una
  rectificativa dice su tipo y su motivo («Rectificativa R1 · <motivo>», o solo «Rectificativa R4» sin motivo; sin
  tipo, la etiqueta del servidor) y la factura que rectifica (de `billing.invoice.get`: la lista no lo trae), que
  la busca. Selección con «Descargar PDF (n)» (las que aún se emiten se dicen en un aviso) y «Descargar Excel» (el CSV
  de lo filtrado).
- **Una factura** (`/billing/invoices/:id`, `pages/InvoicePage.vue`, BILLING-F36): `billing.invoice.get` viva;
  número (o «no cobrada»), fecha, negocio, cobro, estado VeriFactu, líneas con periodo, «Prorrateado», base e IVA,
  totales y destinatario sellado. «Descargar PDF» con `can.pdf`, «Pagar» (solo web) si no se cobró, enlace a la
  factura que rectifica (`invoice-rectified-link`) y «Atrás» a Facturas. Se abre con «Ver la factura» (`view`) de
  cada fila de Facturas. Un error o un 404 se dicen igual: «No hemos podido cargar esta factura» con «Reintentar».
- **Admin de facturas** (`billing/admin.py`, `InvoiceAdmin`): campo «PDF» con «Descargar el PDF» de cualquier
  factura emitida (`<id>/pdf/`, `queries.platform_invoice_pdf`, con `view_invoice`); sin emitir, lo dice; Hub
  caído, vuelve a la factura con el motivo.
- **Descargas**: las hace el navegador con un enlace del mismo origen (`browser.ts`), con la cookie de sesión; no
  hay `fetch` propio (el SPA solo llega al servidor por el SDK, regla de eslint, y `api.call` lee JSON). El 404 de
  un PDF sin emitir no se ve: la fila solo ofrece el PDF con `can.pdf`.
- **Suscripciones** (`SubscriptionsTab`, `CancelPlanDialog`): una fila por negocio, tarjetas hasta 1280 px; plan y
  módulos a precio neto (nombres de `apps.app.list`), «(hasta el …)» en una línea, bajada programada
  (`scheduled_change`: «Cambia a … el …»), próxima factura con IVA y estado. Acciones del servidor: su primera fija
  («Ver la factura», «Mantener el plan» o «Cambiar plan», que nunca coinciden), «Ver facturas» y «Cancelar plan» en
  «⋮», con un diálogo que habla de ese negocio: fechas, módulos que se apagan, límites de Gratis frente a las
  personas que tiene (`hubs.business.get`) y la factura sin pagar que sigue pendiente.
- **Datos de pago** (`PaymentTab`, `PaymentMethodCard`, `BillingProfileCard`, `BillingProfileModal`): por pagador,
  la tarjeta (`billing.payment_method.get`; si Stripe no contesta, se dice) con su último cobro fallido y «Cambiar
  tarjeta» (solo web); y los datos de facturación (`hubs.billing_profile.get/update` por el primer negocio que paga),
  editables en un diálogo con el formulario de la Tienda y la comprobación en VIES al escribir (`billing.vat_check.run`).
- **Aviso para `@erplora/ui`**: la `DataTable` mide la columna de acciones por el `scrollWidth` de su caja, que no
  ve los botones que desbordan hacia el inicio; medida en un momento intermedio, la columna se quedaba estrecha y
  los botones pisaban el estado. Facturas y Suscripciones lo evitan con una regla `:deep` que no deja encoger la
  caja (la propia medición de la tabla corrige entonces la columna); `billing.spec.ts` lo vigila («actions over the
  previous column»). Hay que arreglarlo en la `DataTable` y quitar esas reglas.
- **e2e**: `tests/e2e/panel/billing.spec.ts` con `billing_seed.py` (cuatro negocios: facturas pagada y emitida,
  pagada emitiéndose, no cobrada con tarjeta rechazada y no cobrada con fallo blando; Gratis sin facturas).

### Pendiente (L3-C)

- **Carril Hub**: implementar las cuatro rutas `/internal/platform/…` de arriba (módulo `fiscal`, PLAN-HUB bloque
  6; `Hub.is_platform` no hace falta en el SaaS: la ruta no lleva negocio). Hasta entonces, en local real, las
  facturas se quedan «emitiéndose» y sin PDF, y una clave live no cobra.
- **aws-next**: programar `reconcile_platform_invoices` cada 15 min en `scheduler.tf` (`saas-cron`) y dar
  `PLATFORM_INVOICING_ENABLED` al servicio cuando el Hub tenga sus rutas.
- **PLAN-SAAS**: escribir como ronda las decisiones fiscales de arriba (número del SaaS, bajadas al final del
  periodo, VIES al facturar).
- Una rectificativa anulada en Stripe (`credit_note.voided`) no se trata: pediría otra rectificativa.
