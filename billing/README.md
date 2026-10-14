# `billing` — lo que una cuenta paga a ERPlora y su IVA

App de plataforma del SaaS (`LiveAppConfig`, `kind = "platform"`), detrás de `hubs` en `INSTALLED_APPS`
(grafo `accounts ← hubs ← billing`, plan `docs/plans/2026-10-13-panel-saas-unificado.md` §2 punto 15 y §3).
Lote **L2-A**: el motor de IVA de la UE, portado de `ERPlora/saas` `apps/dashboard/fiscal/` (`origin/develop`,
`c5ca8cae8`) con sus tests. Stripe es L2-B; las facturas, L3-C.

## Qué hay

| Pieza | Qué hace |
|---|---|
| `models.py` | `TaxCategory` (qué se vende), `TaxRule` (tipo por país/región/categoría con vigencia; `is_subject=False` = no sujeta), `FiscalPolicy` (emisor, alta en el ROI, OSS y su umbral; una sola fila), `CompanyConfig` (identidad fiscal de ERPlora, la del solicitante de VIES; una sola fila) y `VatCheck` (bitácora de VIES: cada consulta es una fila nueva, nunca se edita) |
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
- **Umbral OSS**: `FiscalPolicy` guarda a mano lo vendido B2C transfronterizo en el SaaS antiguo (año en curso
  y anterior, en céntimos). Sin esos importes el total es «desconocido» en el admin.

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

## Fuera de L2-A

- **L2-B**: `hubs.billing_profile.update` llama a `validate_vat_for_profile` y valida el código postal con
  `vat.postal_code_is_valid` (el de `hubs` no lo valida aún); checkout con `sale_tax_rates` → `TaxRate` de
  Stripe; webhook con `resolve_vat`. **No se vende por este SaaS sin una suma OSS real que incluya el SaaS
  antiguo.** Sin portar: cliente de HMRC, `audit_tax_rules` y el umbral de factura completa.
- **L3-C**: `Invoice`. `queries.cross_border_b2c_cents` debe sumar sus facturas (el test
  `test_the_threshold_counts_the_invoices_the_day_they_exist` falla ese día a propósito) y las pruebas de la
  factura de `test_vies_contract` y `test_payer_vat_reaches_the_invoice` se portan entonces.
