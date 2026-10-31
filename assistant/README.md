# assistant — la pasarela de IA de erplora.com

App de plataforma del SaaS (`LiveAppConfig`, `kind = "platform"`), en la raíz junto a `base/`. Manual de uso y
flujos: [`WORKBOOK.md`](WORKBOOK.md) (y [`WORKBOOK.en.md`](WORKBOOK.en.md), la traducción de su parte de usuario con
su hash en la cabecera, el esquema de `translate_workbooks` del Hub). Portada en dos partes: la 1 (MIGRATION-TASK
APP-ASSISTANT-1) con los proveedores, las claves, los modelos, qué modelo contesta, la prueba de un modelo, la
auditoría y los comandos de claves; la 2 (APP-ASSISTANT-2) con las puertas del Hub (`/internal/assistant/*` y
`/internal/speech/*`): el turno, sus herramientas y sus adjuntos, el cupo por plan y el uso, las huellas del índice,
la voz y las denuncias. El contrato de esas puertas, en «Para quien lo mantiene» del WORKBOOK. Desde la ronda
2026-10-30e (PLAN-SAAS §23, plan `docs/plans/2026-10-30-asistente-saas.md`) la pasarela contesta también, en
proceso, al asistente del propio panel (`base/assistant.py`, `POST /api/assistant/turn`), con un cupo por cuenta y
su propia documentación para buscar (`assistant.docs.search` sobre pgvector, ASSISTANT-F27).

## Anatomía

| Fichero | Qué hace |
|---|---|
| `apps.py` | `AssistantConfig`: `assistant.manage`, de la plataforma y del personal, y `assistant.ask`, de toda cuenta (el asistente del panel); registra la auditoría. |
| `models.py` | `AIProvider` (una de las cuatro API, su dirección), `AIProviderCredential` (clave cifrada con su final), `AIModel` (precios, contexto, qué admite), `AIRoutingPolicy` (una fila: el modelo que contesta y su reserva), `AssistantUsage` (lo gastado por negocio y mes; una demo, una fila en su vida; una cuenta, una por mes) y `DocChunk` (un fragmento de la documentación con su huella, `vector(1536)` con índice HNSW por coseno); `estimate_cost`, `content_hash`. |
| `crypto.py`, `fields.py` | Fernet con `FERNET_KEY` (+ `FERNET_KEY_PREVIOUS` para leer en una rotación); la columna guarda el token. |
| `schemas.py` | Entradas y salidas; la clave viaja como `SecretStr`. |
| `queries.py` | Lecturas (`@operation`, `kind="query"`): la conexión de un proveedor, la política, la ruta de un turno, quién llama, el cupo que queda y el proveedor de servicios. |
| `services.py` | Escrituras (`@operation`, `kind="command"`), cada una con el permiso del modelo de Django que la respalda (o solo la plataforma); `encrypted_columns` para la rotación. |
| `routing.py` | El turno a través de su ruta: prueba los modelos en orden y pasa a la reserva si el proveedor falla antes de contestar. |
| `internal.py` | Las puertas del Hub, vistas asíncronas firmadas (`door`: método, tamaño, firma, contrato, quién llama y freno por negocio): el turno en directo y de una vez, el cupo, las huellas, el dictado, la lectura en voz alta y la denuncia. |
| `turn.py` | El turno: prepara la conversación, ofrece las herramientas, emite los frames, el token de continuación de un solo uso y lo gastado (`Outcome`); y el turno tal como lo sirve una puerta, sea la del Hub o la del panel (`start`, `frames`/`stream`, `settle`, `spend`, `Refused`). |
| `server_tools.py` | Las herramientas que ejecuta erplora.com: la fecha y la hora (la búsqueda web y el tipo de cambio esperan a la etapa ERP, PLAN §30). |
| `attachments.py` | Los adjuntos: imágenes al modelo que ve, PDF/Word/Excel/texto a texto en memoria, con topes y el zip comprobado. El cuerpo de las puertas lo guarda en memoria el servidor (`config/asgi.py`, `BodiesInMemory`), nunca en el temporal en disco de Django. |
| `media.py` | Huellas (`text-embedding-3-small`), dictado (`whisper-1`) y lectura en voz alta (`tts-1`) por la API de OpenAI del proveedor de servicios. |
| `knowledge.py` | La documentación del asistente del panel (ASSISTANT-F27): `chunk_markdown` (corte por `##`/`###`, ventana de 220 palabras con solape de 50) y sus cuatro fuentes (ayuda pública, documentación de las apps del Hub por `apps.doc.list`, parte de usuario de los WORKBOOK del panel y los planes en venta por `hubs.plan.list`); sin ORM. |
| `providers/` | Clientes `httpx` de OpenAI, Anthropic, Gemini y DeepSeek (`base.py`, `factory.py`): eventos normalizados, sin SDK ni caché; cada cliente toma el contexto TLS de `base.tls` (`trusted_context`): si el servidor no puede cargar sus certificados (`SSL_CERT_FILE`), el fallo es definitivo y nombra la variable y el fichero. |
| `auditlog.py` | Registro de auditoría (django-auditlog) de los cuatro modelos, sin la clave ni `updated_at`. |
| `events.py` | Nombres de los eventos del outbox (sin la clave ni lo que escribe una persona). |
| `admin.py`, `templates/admin/assistant/` | Admin de Django: proveedores con sus claves y modelos, «Elegir modelos del proveedor» (asíncrona), «Modelo que contesta», «Probar un modelo» (ejecución asíncrona en directo) y «Registros de uso del asistente» (solo lectura). |
| `management/commands/` | `import_ai_keys_from_env`, `rotate_encryption_keys` e `index_docs`. |

## Datos

| Dato | Dónde | Se borra |
|---|---|---|
| Proveedor: nombre, identificador, API, dirección, activado, notas | BD `saas`, `assistant_aiprovider` | A mano en el admin (con sus claves y modelos) |
| Clave de un proveedor: token Fernet, sus cuatro últimos caracteres, cuándo cambió, quién | BD `saas`, `assistant_aiprovidercredential` | A mano en el admin |
| Modelo de un proveedor: identificador, nombre, contexto, precios por millón de tokens, si está disponible | BD `saas`, `assistant_aimodel` | Al quitarlo de la elección del proveedor o a mano (nunca uno que use la política) |
| Qué modelo contesta y su reserva, quién lo cambió | BD `saas`, `assistant_airoutingpolicy` (una fila) | Nunca |
| Quién cambió cada cosa y cada prueba de un modelo (sin la clave ni el mensaje) | BD `saas`, `auditlog_logentry` | A los 90 días (`cleanup_old_logs`, ACCOUNTS-F37) |
| Lo gastado por un negocio en un mes: mensajes del cupo, tokens del turno y de las huellas, dictados, caracteres leídos y coste (USD) | BD `saas`, `assistant_assistantusage` (una fila por negocio y mes) | Con el negocio (al purgarlo); nunca a mano |
| Lo gastado por una demo en toda su vida | BD `saas`, `assistant_assistantusage` (una fila por dirección `demo-…`) | Al nacer otra demo, las de más de un día |
| Un token de continuación ya usado y una denuncia ya enviada (solo su clave) | Caché de Django | A los 15 minutos y a las 24 horas |
| Fragmentos de la documentación del panel: fuente, ruta, idioma, títulos, texto, hash y huella | BD `saas`, `assistant_docchunk` | Al dejar de existir en su fuente (el siguiente `index_docs`) |
| La huella de una pregunta a la documentación (sin la pregunta: la clave es su sha256) | Caché de Django | A las 24 horas |

No se guarda ninguna conversación, adjunto, audio ni texto leído: el turno pasa y se olvida (ASSISTANT-F17).

## Operaciones

| Operación | Permiso que comprueba | Evento |
|---|---|---|
| `assistant.provider.connection` | `view_aiprovider` | — |
| `assistant.policy.show` | `view_airoutingpolicy` | — |
| `assistant.route.resolve` | la plataforma; el personal, `change_airoutingpolicy` (un modelo) | — |
| `assistant.credential.save` | `add_aiprovidercredential` (nueva) o `change_aiprovidercredential` (cambio) | `assistant.credential.saved` |
| `assistant.credential.delete` | `delete_aiprovidercredential` | `assistant.credential.deleted` |
| `assistant.credential.import` | solo la plataforma | `assistant.credential.saved` |
| `assistant.model.select` | `add_aimodel` y `delete_aimodel` | `assistant.model.selected` |
| `assistant.policy.update` | `change_airoutingpolicy` | `assistant.policy.updated` |
| `assistant.model.try` | `change_airoutingpolicy` | `assistant.model.tried` |
| `assistant.encryption.rotate` | solo la plataforma | `assistant.encryption.rotated` |
| `assistant.caller.resolve` | solo la plataforma | — |
| `assistant.usage.show` | la plataforma; el personal, `view_assistantusage` | — |
| `assistant.service.connection` | solo la plataforma | — |
| `assistant.message.claim` | solo la plataforma | `assistant.message.claimed` |
| `assistant.message.release` | solo la plataforma | `assistant.message.released` |
| `assistant.usage.record` | solo la plataforma | `assistant.usage.recorded` |
| `assistant.report.send` | solo la plataforma | `assistant.report.sent` |
| `assistant.docs.list` | solo la plataforma | — |
| `assistant.docs.index` | solo la plataforma | `assistant.docs.indexed` |
| `assistant.docs.search` | `assistant.ask` (toda cuenta) | — |

Todas llevan `ai=INTERNAL` (son la pasarela, no herramientas del asistente) salvo `assistant.docs.search`, que es
`AI(...)`: la herramienta `assistant__docs__search` del asistente del panel (`live.E017`, PLAN §30).

## Comandos y ajustes

- `import_ai_keys_from_env [--providers …] [--label …] [--force] [--dry-run]`: guarda cifradas `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` y `DEEPSEEK_API_KEY` (vacías por defecto); crea el proveedor si falta.
- `rotate_encryption_keys [--dry-run]`: vuelve a cifrar con `FERNET_KEY` toda columna de `ROTATED_FIELD_CLASSES` (la
  clave del proveedor y el token y el PIN de WhatsApp); termina con error si alguna no se abre.
- `index_docs [--full] [--dry-run]`: indexa la documentación del asistente del panel (ASSISTANT-F27); solo embebe lo
  que cambió, en lotes de 64, con el proveedor de servicios; una línea por fuente con lo que costó; código 2 sin
  proveedor. Diario a las 06:50 UTC en `saas-cron` y una vez a mano tras el primer despliegue (`saas/README.md`,
  «Operación»).
- `ASSISTANT_TRY_RATELIMIT` (por defecto `10/m`): pruebas de un modelo por persona del personal.
- Freno por negocio de las puertas del Hub: `ASSISTANT_TURN_RATELIMIT` (`600/h`, turnos y cupo),
  `ASSISTANT_EMBED_RATELIMIT` (`600/h`), `ASSISTANT_TRANSCRIBE_RATELIMIT` (`120/h`),
  `ASSISTANT_SYNTHESIZE_RATELIMIT` (`120/h`) y `ASSISTANT_REPORT_RATELIMIT` (`60/h`), con la caché de Django.
- `ASSISTANT_DEMO_MESSAGES` (`10`): los mensajes de una demo en toda su vida.
- `ASSISTANT_ACCOUNT_MESSAGES` (`30`): los mensajes al mes de cada cuenta con el asistente del panel de erplora.com,
  fijos, aparte del cupo del plan de cada uno de sus negocios. El freno de turnos del panel es el mismo
  `ASSISTANT_TURN_RATELIMIT`, por cuenta.
- `ASSISTANT_SERVICE_PROVIDER` (`openai`): el identificador del proveedor (de API OpenAI) que calcula las huellas
  (las del índice del Hub y las de la documentación del panel, `index_docs` y `assistant.docs.search`) y la voz.
- Postgres con la extensión `vector` (pgvector, imagen `pgvector/pgvector`; en Aurora, extensión de confianza): la
  crea la migración `assistant/0004_doc_chunks`.
- `INTERNAL_SHARED_SECRET` (y `INTERNAL_SHARED_SECRET_PREVIOUS`): el secreto con que firma el Hub, el de todo
  `/internal`.
- `FERNET_KEY` (y `FERNET_KEY_PREVIOUS` durante una rotación), para quien despliega: sin ella, el admin lo dice al
  guardar una clave y no guarda ninguna (503 `assistant.encryption_not_configured` en las operaciones).

## Pruebas

`uv run pytest -q assistant` (BD de prueba propia: `TEST_DB_NAME=test_saas_next_<tema>`). Ningún test llama a un
proveedor de verdad: los clientes hablan con `assistant/tests/fake_provider.py`, un servidor HTTP en `127.0.0.1`.
El e2e del admin, `tests/e2e/panel/assistant-admin.spec.ts` (datos de `tests/e2e/panel/assistant_seed.py`), arranca
ese mismo servidor en el puerto `E2E_SAAS_PORT + 7` (`aiProviderPort` de `tests/e2e/stack.ts`; el `+ 8` es el doble de reCAPTCHA) (`uv run python -m assistant.tests.fake_provider --port …`). El e2e
de las puertas del Hub y de «Registros de uso del asistente», `tests/e2e/panel/assistant-gateway.spec.ts`, llama firmado como el
Hub contra el mismo servidor falso.
