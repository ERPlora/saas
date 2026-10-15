# `fiscal_gateway/` — pasarela VeriFactu del SaaS

App de plataforma (`kind = "platform"`, PLAN §20) que presenta a la AEAT los sobres VeriFactu que el Hub ya ha
construido y validado (cadena, huella, XSD, QR). Sustituye al gateway en Rust (`erplora-old/verifactu-gateway`):
la pasarela vive en el SaaS y el Hub la llama por `/internal` (PLAN-SAAS §4; contrato 3 del bloque fiscal,
`docs/superpowers/plans/2026-10-15-bloque-fiscal-hub.md`). No tiene modelos ni operaciones: no guarda nada.

| Fichero | Qué hace |
|---|---|
| `seal.py` | Abre un `.p12` (`load`) y elige el sello de ERPlora (`current`) |
| `aeat.py` | Puerta de la AEAT (`endpoint`), NIF del sobre (`nif_matches`) y presentación mTLS (`present`) |
| `schemas.py` | Cuerpos de las tres puertas |
| `internal.py` | Vistas `POST /internal/verifactu/submit\|query\|probe` |

## Contrato con el Hub

Firmado como todo `/internal` (`accounts/signing.py`: v1 o v2, ±300 s, secreto actual y anterior). Cuerpo:

```json
{"hub": "<uuid>", "nif": "B12345674", "environment": "testing|production", "route": "erplora|own",
 "envelope": "<soapenv:Envelope…>", "certificate": {"p12_base64": "…", "password": "…"}}
```

`certificate` solo con `route = "own"`; `probe` no lleva `envelope`.

| Respuesta | Cuándo |
|---|---|
| `200 {"aeat_status", "aeat_body"}` | La AEAT contestó; su respuesta tal cual, diga lo que diga (la interpreta el Hub) |
| `409 nif_mismatch` | El sobre nombra a otro contribuyente; se decide **antes** de tocar la AEAT |
| `409 no_seal` | `route = "erplora"` sin sello utilizable (también si TLS rechaza el sello configurado) |
| `409 no_certificate` | `route = "own"` sin certificado |
| `409 certificate_invalid` | No abre con su contraseña, no permite autenticación de cliente (EKU), ha caducado o TLS lo rechaza (la clave no es la del certificado o es demasiado débil, p. ej. RSA de 1024); no sale nada hacia la AEAT |
| `409 environment_not_allowed` | `production` desde un despliegue que no es `prod` (`pre` solo presenta a pruebas) |
| `502 {"error": {"code": "aeat_unreachable", "sent"}}` | Sin respuesta de la AEAT; `sent = true` si la petición pudo llegar |
| `503 gateway_busy` | Semáforo lleno; el Hub reintenta |
| `401 unauthorized` | Sin firma, firma caducada (±300 s) o que no casa |
| `405 method_not_allowed` | No es `POST` |
| `413 payload_too_large` | Cuerpo de más de 10 MiB |
| `422 invalid_payload` | No es JSON o no cumple el contrato; los campos fallidos, en `fields` |
| `probe` → `200 {"ready", "detail"}` | Si se podría presentar ahora y con qué certificado (`seal B…, expires 2027-…`); no toca la AEAT. Carga el certificado en TLS como una presentación: si `submit` respondería `409` (`certificate_invalid`, `no_seal`…), `probe` da `ready: false` y el motivo en `detail` |

Los errores van en el sobre único `{"error": {"code", "message"}}`. El cuerpo se lee en la vista, con su propio
tope de 10 MiB (`MAX_BODY_BYTES`), y no por `request.body`: un envío de 1000 registros (el máximo de la AEAT por
envío) ronda los 3 MB y supera el límite de formularios de Django (2,5 MB); el tope deja margen para eso y el
certificado.

## A quién presenta y con qué

- **NIF del sobre**: cuentan la `Cabecera/ObligadoEmision/NIF` y todo `IDEmisorFactura` e
  `IDEmisorFacturaAnulada` del espacio `SuministroInformacion` (no el destinatario, el sistema informático ni el
  representante). Todos deben ser el `nif` declarado; un sobre que no nombra a nadie, mal formado o con
  `DOCTYPE` no coincide con nadie.
- **Certificado**: titular por `organizationIdentifier` y, si no, `serialNumber`, sin el prefijo ETSI
  (`VATES-`, `IDCES-`). Tipo: `seal` solo con el QcType eIDAS eSeal; `representative` (entidad + DNI/NIE),
  `personal` (solo persona) o `unknown`. Un EKU declarado sin `clientAuth` se rechaza.
- **Puerta**: `seal` → `prewww10.aeat.es` (pruebas) / `www10.agenciatributaria.gob.es` (producción); cualquier
  otro → `prewww1.aeat.es` / `www1.agenciatributaria.gob.es`; ruta `/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP`.
- **Presentación**: mTLS con `httpx` (raíces de `certifi`); certificado y clave en dos ficheros `0600` de un
  directorio temporal privado que se borra en cuanto TLS los ha leído, pase lo que pase. `Content-Type:
  text/xml;charset=UTF-8`, `SOAPAction: ""`; 5 s para conectar y 30 s para leer (los del contrato, WORKBOOK del Hub,
  «Contrato con el SaaS»). Nada del entorno desvía la presentación (`trust_env=False`: ni `HTTPS_PROXY` ni
  `SSL_CERT_FILE`) y una redirección es una respuesta, nunca se sigue. Conexión rechazada o sin
  conectar → `sent = false` (nada salió); tiempo de lectura agotado o conexión perdida → `sent = true`.

## Sello de ERPlora

Dos huecos en el entorno (Secrets Manager en AWS): `FISCAL_SEAL_CURRENT_P12_BASE64` / `_PASSWORD` y
`FISCAL_SEAL_NEXT_P12_BASE64` / `_PASSWORD` (vacío = hueco vacío). `seal.current()` usa `CURRENT` salvo que
falte, no abra, haya caducado o caduque en menos de 7 días; entonces `NEXT` si es utilizable; si no, `CURRENT`
mientras no caduque; sin ninguno, `no_seal`. La caducidad la vigila `manage.py report_seal_expiry`.

Con el sello de ERPlora se presenta en nombre del cliente gracias a su otorgamiento de representación (Anexo I
del Convenio 17), que el staff valida en el SaaS; con `route = "own"`, con el certificado del propio cliente.

## Seguridad

- El certificado del cliente vive solo durante la llamada: no se guarda, no se registra en logs y no aparece en
  mensajes de error (`SecretStr`, `sensitive_variables`, errores con `from None`). Hay test con `caplog`.
- Los tests solo tocan la preproducción de la AEAT (`prewww*`) y siempre con `respx`: nunca una transmisión
  real. Los endpoints de producción se prueban solo como cadena.

## Por medir

- `VERIFACTU_GATEWAY_CONCURRENCY = 8` presentaciones a la vez por proceso: el gateway en Rust medía 12,7 MiB
  por envío; aquí el sobre se guarda entero dos veces (texto y bytes). Se fija tras medir en `pre`.

## Concurrencia bajo ASGI

Las vistas son síncronas a propósito. Bajo daphne, el `ASGIHandler` de Django abre un `ThreadSensitiveContext`
por petición, así que cada petición corre su código síncrono en su propio hilo: ocho presentaciones esperan a la
AEAT a la vez y una lenta no frena a las demás. `tests/test_concurrency.py` lo comprueba por la `application`
real de `config.asgi` (no con el `AsyncClient` de Django, que no abre ese contexto y lo serializaría todo): 8
presentaciones retenidas a la vez en la AEAT simulada, la novena `503 gateway_busy`, y `/healthz` contesta
mientras una presentación espera.
