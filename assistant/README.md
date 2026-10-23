# assistant — la pasarela de IA de erplora.com

App de plataforma del SaaS (`LiveAppConfig`, `kind = "platform"`), en la raíz junto a `base/`. Manual de uso y
flujos: [`WORKBOOK.md`](WORKBOOK.md) (y [`WORKBOOK.en.md`](WORKBOOK.en.md), la traducción de su parte de usuario con
su hash en la cabecera, el esquema de `translate_workbooks` del Hub). Parte 1 de 2 del porte (MIGRATION-TASK
APP-ASSISTANT-1): proveedores, claves, modelos, qué modelo contesta, probar un modelo, auditoría y comandos de claves.
El turno del Hub (`/internal/assistant/*`), el cupo por plan, los adjuntos y la voz (`/internal/speech/*`) son la
parte 2.

## Anatomía

| Fichero | Qué hace |
|---|---|
| `apps.py` | `AssistantConfig`: permiso único `assistant.manage`, de la plataforma y del personal; registra la auditoría. |
| `models.py` | `AIProvider` (una de las cuatro API, su dirección), `AIProviderCredential` (clave cifrada con su final), `AIModel` (precios, contexto, qué admite) y `AIRoutingPolicy` (una fila: el modelo que contesta y su reserva); `estimate_cost`. |
| `crypto.py`, `fields.py` | Fernet con `FERNET_KEY` (+ `FERNET_KEY_PREVIOUS` para leer en una rotación); la columna guarda el token. |
| `schemas.py` | Entradas y salidas; la clave viaja como `SecretStr`. |
| `queries.py` | Lecturas (`@operation`, `kind="query"`): la conexión de un proveedor, la política y la ruta de un turno. |
| `services.py` | Escrituras (`@operation`, `kind="command"`), cada una con el permiso del modelo de Django que la respalda (o solo la plataforma); `encrypted_columns` para la rotación. |
| `routing.py` | El turno a través de su ruta: prueba los modelos en orden y pasa a la reserva si el proveedor falla antes de contestar. |
| `providers/` | Clientes `httpx` de OpenAI, Anthropic, Gemini y DeepSeek (`base.py`, `factory.py`): eventos normalizados, sin SDK ni caché. |
| `auditlog.py` | Registro de auditoría (django-auditlog) de los cuatro modelos, sin la clave ni `updated_at`. |
| `events.py` | Nombres de los eventos del outbox (sin la clave ni lo que escribe una persona). |
| `admin.py`, `templates/admin/assistant/` | Admin de Django: proveedores con sus claves y modelos, «Elegir modelos del proveedor» (asíncrona), «Modelo que contesta» y «Probar un modelo» (ejecución asíncrona en directo). |
| `management/commands/` | `import_ai_keys_from_env` y `rotate_encryption_keys`. |

## Datos

| Dato | Dónde | Se borra |
|---|---|---|
| Proveedor: nombre, identificador, API, dirección, activado, notas | BD `saas`, `assistant_aiprovider` | A mano en el admin (con sus claves y modelos) |
| Clave de un proveedor: token Fernet, sus cuatro últimos caracteres, cuándo cambió, quién | BD `saas`, `assistant_aiprovidercredential` | A mano en el admin |
| Modelo de un proveedor: identificador, nombre, contexto, precios por millón de tokens, si está disponible | BD `saas`, `assistant_aimodel` | Al quitarlo de la elección del proveedor o a mano (nunca uno que use la política) |
| Qué modelo contesta y su reserva, quién lo cambió | BD `saas`, `assistant_airoutingpolicy` (una fila) | Nunca |
| Quién cambió cada cosa y cada prueba de un modelo (sin la clave ni el mensaje) | BD `saas`, `auditlog_logentry` | A los 90 días (`cleanup_old_logs`, ACCOUNTS-F37) |

No se guarda ninguna conversación: el turno pasa y se olvida (parte 2).

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

## Comandos y ajustes

- `import_ai_keys_from_env [--providers …] [--label …] [--force] [--dry-run]`: guarda cifradas `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` y `DEEPSEEK_API_KEY` (vacías por defecto); crea el proveedor si falta.
- `rotate_encryption_keys [--dry-run]`: vuelve a cifrar con `FERNET_KEY` toda columna de `ROTATED_FIELD_CLASSES` (la
  clave del proveedor y el token y el PIN de WhatsApp); termina con error si alguna no se abre.
- `ASSISTANT_TRY_RATELIMIT` (por defecto `10/m`): pruebas de un modelo por persona del personal.

## Pruebas

`uv run pytest -q assistant` (BD de prueba propia: `TEST_DB_NAME=test_saas_next_<tema>`). Ningún test llama a un
proveedor de verdad: los clientes hablan con `assistant/tests/fake_provider.py`, un servidor HTTP en `127.0.0.1`.
El e2e del admin, `tests/e2e/panel/assistant-admin.spec.ts` (datos de `tests/e2e/panel/assistant_seed.py`), arranca
ese mismo servidor en el puerto `E2E_SAAS_PORT + 8` (`uv run python -m assistant.tests.fake_provider --port …`).
