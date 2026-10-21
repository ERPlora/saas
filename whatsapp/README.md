# `whatsapp` — la mitad de erplora.com de la bandeja de WhatsApp del Hub

App de plataforma del SaaS (`LiveAppConfig`, `kind = "platform"`, siempre activa), en la raíz junto a `billing/` y
`fiscal_gateway/`. Es la cuenta de WhatsApp Business de cada negocio ante Meta: su número y su permiso (Embedded
Signup), el webhook de Meta, la entrega al Hub con reintento, los envíos con el cupo del plan, las plantillas y los
adjuntos. **Sin pantallas en el panel** (PLAN-SAAS, bloque 12): la bandeja y sus ajustes son del Hub
(`hub/apps/whatsapp_inbox/`); por eso no hay `frontend/` ni `UI-REQUESTS.md`. Manual y flujos: `WORKBOOK.md`
(`WHATSAPP-Fnn`). Porte de `ERPlora/saas` `apps/whatsapp_inbox/` (`origin/develop`) y del inventario
`fi:saas/auth-services` (MIGRATION-TASK APP-WHATSAPP, con FIX-SAAS-WHATSAPP-GATEWAY-DOORS).

## El contrato manda

Las puertas 1–9 son las del `WORKBOOK.md` de `whatsapp_inbox` del Hub, «Contrato con el SaaS», y **no se
renombran** (el Hub ya está en producción con ellas). Firma de todo `/internal`, en los dos sentidos:
`X-Erplora-Timestamp` + `X-Erplora-Signature` = HMAC-SHA256 de `f"{timestamp}.{cuerpo}"` con
`INTERNAL_SHARED_SECRET` (±300 s; `accounts.signing`, v1 o v2, secreto actual o el previo).

| Puerta | Sentido | Qué | Aquí |
|---|---|---|---|
| 1 `POST /internal/whatsapp/inbound` | SaaS → Hub | un mensaje, eco o historial | `hub_client.post_inbound`, desde `gateway.deliver` |
| 2 `POST /internal/whatsapp/status` | SaaS → Hub | un estado con su `client_message_id` | `hub_client.post_status` |
| 3 `PUT /internal/whatsapp/channel` | SaaS → Hub | el canal | **no se usa**: va en la foto (puerta 4) |
| 4 clave `whatsapp` de `PUT /internal/hubs/{id}/state` | SaaS → Hub | el canal con la versión de la foto | `queries.channel_block` en `hubs.queries.hub_snapshot`; `services.announce_channel` sube la versión y empuja tras el COMMIT |
| 5 `POST /internal/whatsapp/send` + `Idempotency-Key` | Hub → SaaS | enviar | `internal.send` → `gateway.send` |
| 6 `POST /internal/whatsapp/erase` | Hub → SaaS | olvidar un número de cliente | `gateway.erase` |
| 7 | — | envío de estados (obligación de la 2) | el webhook los aparca y `deliver` los empuja |
| 8 `POST /internal/whatsapp/templates` + `Idempotency-Key` | Hub → SaaS | registrar una plantilla | `gateway.submit_template` |
| 9 `POST /internal/whatsapp/templates/delete` | Hub → SaaS | borrar una plantilla en un idioma | `gateway.delete_template` |
| 10 `POST /internal/whatsapp/config` | Hub → SaaS | **propuesta**: lo público para abrir la ventana de Meta | `gateway.config` |
| 11 `POST /internal/whatsapp/connect` | Hub → SaaS | **propuesta**: conectar el número que dio la ventana | `gateway.connect` |
| 12 `POST /internal/whatsapp/disconnect` | Hub → SaaS | **propuesta**: desconectar | `gateway.disconnect` |

Respuestas y códigos de cada puerta: el docstring de `internal.py` (comunes: 401 `unauthorized`, 405, 413, 422
`invalid_payload` con `fields`, 404 `hub_unknown`, también para una demo) y el de cada función de `gateway.py`.
Las puertas 10–12 están escritas en el `WORKBOOK.md`, «Para quien lo mantiene»; el Hub aún no las llama.

## Qué hay

| Pieza | Qué hace |
|---|---|
| `models.py` | `PhoneNumber` (número de un negocio, permiso y PIN cifrados; uno activo por negocio, un dueño por número), `Template` (espejo de las plantillas de Meta), `TemplateSubmission` (clave de cada registro de la puerta 8), `Send` (clave de cada envío de la puerta 5), `Usage` (contador del mes, UTC), `Delivery` (lo que espera al Hub: mensaje o estado) |
| `crypto.py` + `fields.py` | Fernet (`FERNET_KEY` + `FERNET_KEY_PREVIOUS`, `MultiFernet`) y el campo cifrado: lo que no se descifra se lee vacío y queda en el registro como error |
| `meta.py` | Cliente de la API Graph (httpx, 5 s/15 s, 30 s al enviar): token en cabecera, sin redirecciones, `MetaRefused` (código, subcódigo, `error_user_msg`) y `MetaUnreachable(sent)`; adjuntos solo de hosts de Meta por https; `exchange_code`, `exchange_token`, `token_expiry` |
| `parse.py` | Lectura pura del aviso de Meta: mensajes, ecos, historial y su continuación, estados, veredictos de plantillas |
| `webhooks.py` | `GET/POST /webhooks/whatsapp/`: verificación (`hub.verify_token`) y firma `X-Hub-Signature-256`; 503 sin configurar, 403, 413, 400 |
| `hub_client.py` | Las puertas 1 y 2, firmadas |
| `internal.py` | Las puertas 5, 6, 8, 9 y 10–12 (`_door`: firma, tamaño, esquema, `Idempotency-Key`) |
| `gateway.py` | Los pasos de cada puerta alrededor de las operaciones: nunca una transacción esperando a Meta o al Hub. Sin ORM |
| `templates.py` | Las reglas de Meta de una plantilla antes de llamarla (`check`), sus componentes y la lectura de la lista de Meta (`from_meta`) |
| `media.py` | `GET /whatsapp/media/<id de la entrega>`: el adjunto de un cliente con la sesión de erplora.com y miembro aceptado del negocio, en streaming desde Meta, sin caché; lo que no es imagen, audio o vídeo se descarga con CSP `sandbox` |
| `emails.py` | «Vuelve a conectar WhatsApp», en el idioma del propietario |
| `admin.py` | Números, plantillas, entregas, envíos y consumo: solo lectura; acciones de superusuario (desconectar, volver a leer las plantillas, entregar ahora). `support` solo mira (`0002`) |
| `checks.py` | `whatsapp.E001` (`FERNET_KEY` no es una clave Fernet) y `whatsapp.I001` (WhatsApp apagado, informativo) |

## Operaciones (`@operation`, permiso `whatsapp.manage`, contexto de plataforma)

- Comandos (`services.py`): `whatsapp.webhook.ingest`, `whatsapp.delivery.claim|record|due_now`,
  `whatsapp.message.claim|record|erase`, `whatsapp.template.claim|record|forget|sync`,
  `whatsapp.number.connect|disconnect|reconnect_needed|renewal|alerted`, `whatsapp.retention.purge`.
- Consultas (`queries.py`): `whatsapp.template.account`, `whatsapp.number.renewal_due`,
  `whatsapp.number.connecting`, `whatsapp.media.locate`; y las funciones `known_hub` y `channel_block` (la foto).
- Eventos (`events.py`, outbox en la misma transacción): `whatsapp.webhook.ingested`, `whatsapp.delivery.recorded`,
  `whatsapp.message.recorded|erased`, `whatsapp.template.registered|forgotten|synced`,
  `whatsapp.number.reconnect_needed|connected|disconnected`, `whatsapp.retention.purged`. Sin `live.py`: no hay
  consultas vivas (no hay pantalla).

## Datos

- **Cupo**: `Plan.whatsapp_messages_per_month` (`hubs/0012`: Gratis 30, Starter 150, Standard 300; 0 = ninguno).
  Reserva atómica al aceptar (`UPDATE … WHERE used < limit`); `Idempotency-Key` repetida = la misma respuesta, sin
  segundo envío ni segundo consumo; Meta 2xx sin id = enviado para siempre (saas#2653).
- **Retención** (`whatsapp_purge`): entregado > 30 días, estados > 30 días, no recogido > 30 días (con aviso en el
  registro por negocio, saas#1930) y claves de envíos y registros > 30 días (saas#2662).
- Nada de lo que envía el negocio se guarda, salvo la clave; los adjuntos nunca.

## Tareas (ECS, `saas-cron`)

- `manage.py whatsapp_deliver`: cada minuto, lo que espera al Hub, por lotes de 50 (hasta 20 lotes).
- `manage.py whatsapp_refresh_tokens`: cada día, renueva los permisos a 14 días de caducar (bajo un lock de nombre),
  marca «Hay que reconectar» y avisa al propietario; sale con error sin la app de Meta o si un número revienta.
- `manage.py whatsapp_purge [--days N]`: cada día; N de 1 a 30.

Programarlas y dar los secretos (`WHATSAPP_APP_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`,
`WHATSAPP_CONFIG_ID`, `FERNET_KEY`, `FERNET_KEY_PREVIOUS`) es del repo de infraestructura.

## Ajustes

`WHATSAPP_APP_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_CONFIG_ID`, `WHATSAPP_GRAPH_VERSION`
(`v25.0`), `WHATSAPP_WEBHOOK_MAX_BYTES`, `WHATSAPP_MEDIA_BASE_URL` (el origen de erplora.com: el Hub solo acepta ese),
`FERNET_KEY` (en desarrollo, una fija; en producción nace vacía y el check la exige) y `FERNET_KEY_PREVIOUS`.

## Tests

`TEST_DB_NAME=test_saas_next_<tema> uv run pytest -q whatsapp`. Meta se sustituye solo en la frontera HTTP (`respx`,
con cuerpos de su documentación y de los tests viejos); el Hub, con su doble HTTP real de `hubs.tests.hub_double`, que
comprueba la firma. Cada test cita su clave del registro (`WHATSAPP-Gnn`) en el docstring del fichero.
