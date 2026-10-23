# assistant — la pasarela de IA de erplora.com

App de plataforma del SaaS (`LiveAppConfig`, `kind = "platform"`), en la raíz junto a `base/`. Manual de uso y
flujos: [`WORKBOOK.md`](WORKBOOK.md) (y [`WORKBOOK.en.md`](WORKBOOK.en.md)).

## Anatomía

| Fichero | Qué hace |
|---|---|
| `apps.py` | `AssistantConfig`: permiso único `assistant.manage`, de la plataforma y del personal. |
| `models.py` | `AIProvider` (una de las cuatro API, su dirección) y `AIProviderCredential` (clave cifrada con su final). |
| `crypto.py`, `fields.py` | Fernet con `FERNET_KEY` (+ `FERNET_KEY_PREVIOUS` para leer en una rotación); la columna guarda el token. |
| `schemas.py` | Entradas y salidas; la clave viaja como `SecretStr`. |
| `services.py` | Escrituras (`@operation`, `kind="command"`), cada una con el permiso del modelo de Django que la respalda. |
| `events.py` | Nombres de los eventos del outbox (sin la clave ni lo que escribe una persona). |
| `admin.py` | Admin de Django: proveedores con sus claves dentro. |

## Datos

| Dato | Dónde | Se borra |
|---|---|---|
| Proveedor: nombre, identificador, API, dirección, activado, notas | BD `saas`, `assistant_aiprovider` | A mano en el admin (con sus claves) |
| Clave de un proveedor: token Fernet, sus cuatro últimos caracteres, quién y cuándo | BD `saas`, `assistant_aiprovidercredential` | A mano en el admin |

## Operaciones

| Operación | Permiso que comprueba | Evento |
|---|---|---|
| `assistant.credential.save` | `add_aiprovidercredential` (nueva) o `change_aiprovidercredential` (cambio) | `assistant.credential.saved` |
| `assistant.credential.delete` | `delete_aiprovidercredential` | `assistant.credential.deleted` |

## Pruebas

`uv run pytest -q assistant` (BD de prueba propia: `TEST_DB_NAME=test_saas_next_<tema>`). Ningún test llama a un
proveedor de verdad: los clientes hablan con `assistant/tests/fake_provider.py`, un servidor HTTP en `127.0.0.1`.
