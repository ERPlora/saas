# `fiscal_gateway/` — pasarela VeriFactu del SaaS

App de plataforma (`kind = "platform"`, PLAN §20) que presenta a la AEAT los sobres VeriFactu que el Hub ya ha
construido y validado (cadena, huella, XSD, QR). Sustituye al gateway en Rust (`erplora-old/verifactu-gateway`):
la pasarela vive en el SaaS y el Hub la llama por `/internal` (PLAN-SAAS §4; contrato 3 del bloque fiscal,
`docs/superpowers/plans/2026-10-15-bloque-fiscal-hub.md`). No tiene modelos ni operaciones: no guarda nada; solo
lee el negocio y su otorgamiento (`queries.py`, el único fichero que toca la BD).

| Fichero | Qué hace |
|---|---|
| `seal.py` | Abre un `.p12` (`load`) y elige el sello de ERPlora (`current`) |
| `aeat.py` | Puerta de la AEAT (`endpoint`), NIF del sobre (`nif_matches`) y presentación mTLS (`present`) |
| `schemas.py` | Cuerpos de las tres puertas |
| `queries.py` | Negocio que nombra `hub` (`hub_id_for`) y contribuyente de su otorgamiento aprobado (`approved_taxpayer`) |
| `internal.py` | Vistas `POST /internal/verifactu/submit\|query\|probe` |

Los flujos (prefijo `FISCAL`, también los de la autorización firmada que viven en `fiscal/`) están en
[`WORKBOOK.md`](WORKBOOK.md): el sello (FISCAL-F01), la presentación (F02), el cifrado de los documentos (F03), la
caducidad del sello (F04), los avisos de cada paso de la autorización (F05, `fiscal/emails.py`), el modelo del
Anexo I (F06, parcial) y lo descartado (F07, los apoderamientos ZP01).

## Contrato con el Hub

Firmado como todo `/internal` (`accounts/signing.py`: v1 o v2, ±300 s, secreto actual y anterior). Cuerpo:

```json
{"hub": "<slug|uuid>", "nif": "B12345674", "environment": "testing|production", "route": "erplora|own",
 "envelope": "<soapenv:Envelope…>", "certificate": {"p12_base64": "…", "password": "…"}}
```

`hub`: slug del hub (fase 1, el del host: `ctx.scope.key`) con el formato de slug de `live.slugs` (`HUB_SLUG_RE`),
o su UUID en minúsculas (con guiones). Tiene que ser un negocio que el SaaS conoce (no purgado); si no,
`404 hub_unknown`. Única excepción: el hub de plataforma (`PLATFORM_HUB_SLUG`) por `route = "erplora"`. `certificate` solo con `route = "own"`; `probe` no lleva `envelope`.

| Respuesta | Cuándo |
|---|---|
| `200 {"aeat_status", "aeat_body"}` | La AEAT contestó; su respuesta tal cual, diga lo que diga (la interpreta el Hub) |
| `404 hub_unknown` | `hub` no es un negocio que el SaaS conozca (o está purgado) ni el hub de plataforma por `erplora`; no sale nada hacia la AEAT |
| `409 nif_mismatch` | El sobre nombra a otro contribuyente; se decide **antes** de tocar la AEAT. Con `route = "erplora"`, también si el otorgamiento aprobado del negocio es de otro contribuyente (sin decir de cuál) o si el hub de plataforma pide un `nif` que no es el del titular del sello |
| `409 representation_not_approved` | `route = "erplora"` para un negocio sin otorgamiento aprobado (ninguno, en revisión, devuelto o retirado), declare el `nif` que declare, el de ERPlora incluido |
| `409 no_seal` | `route = "erplora"` sin sello utilizable (también si TLS rechaza el sello configurado) |
| `409 no_certificate` | `route = "own"` sin certificado |
| `409 certificate_invalid` | No abre con su contraseña, no permite autenticación de cliente (EKU), ha caducado o TLS lo rechaza (la clave no es la del certificado o es demasiado débil, p. ej. RSA de 1024); no sale nada hacia la AEAT |
| `409 environment_not_allowed` | `production` desde un despliegue que no es `prod` (`pre` solo presenta a pruebas) |
| `502 {"error": {"code": "aeat_unreachable", "sent"}}` | Sin respuesta de la AEAT; `sent = true` si la petición pudo llegar |
| `503 gateway_busy` | Semáforo lleno; el Hub reintenta |
| `401 unauthorized` | Sin firma, firma caducada (±300 s) o que no casa. Sin marca de tiempo, sin firma o con la marca fuera de la ventana (o de más de 20 dígitos) se decide por las cabeceras, **sin leer** el cuerpo |
| `405 method_not_allowed` | No es `POST` |
| `413 payload_too_large` | Cuerpo de más de 10 MiB |
| `422 invalid_payload` | No es JSON o no cumple el contrato; los campos fallidos, en `fields` |
| `probe` → `200 {"ready", "detail"}` | Si se podría presentar ahora y con qué certificado (`seal B…, expires 2027-…`); no toca la AEAT. Carga el certificado en TLS como una presentación: si `submit` respondería `404` o `409` (`hub_unknown`, `representation_not_approved`, `certificate_invalid`, `no_seal`…), `probe` da `ready: false` y el motivo en `detail` |

Los errores van en el sobre único `{"error": {"code", "message"}}`. El cuerpo se lee en la vista, con su propio
tope de 10 MiB, y no por `request.body`: un envío de 1000 registros supera el límite de formularios de Django
(2,5 MB).

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
  text/xml;charset=UTF-8`, `SOAPAction: ""`; 10 s para conectar y 60 s para leer. Conexión rechazada o sin
  conectar → `sent = false` (nada salió); tiempo de lectura agotado o conexión perdida → `sent = true`.

## Sello de ERPlora

Dos huecos en el entorno (Secrets Manager en AWS): `FISCAL_SEAL_CURRENT_P12_BASE64` / `_PASSWORD` y
`FISCAL_SEAL_NEXT_P12_BASE64` / `_PASSWORD` (vacío = hueco vacío). `seal.current()` usa `CURRENT` salvo que
falte, no abra, haya caducado o caduque en menos de 7 días; entonces `NEXT` si es utilizable; si no, `CURRENT`
mientras no caduque; sin ninguno, `no_seal`. La caducidad la vigila `manage.py report_seal_expiry`.

Con el sello de ERPlora se presenta en nombre del cliente gracias a su otorgamiento de representación (Anexo I
del Convenio 17), que el staff valida en el SaaS (`fiscal/`); con `route = "own"`, con el certificado del propio
cliente. Antes de tocar la AEAT, con `route = "erplora"`, la pasarela comprueba dos cosas:

1. **Otorgamiento aprobado**: el negocio (`hub`) tiene un `fiscal.RepresentationGrant` en estado `approved`. Uno
   en revisión, devuelto o retirado no basta, ni el aprobado de otro negocio → `409 representation_not_approved`.
2. **NIF del otorgamiento**: el `taxpayer_tax_id` de ese otorgamiento, normalizado (`billing.nif.normalise_nif`),
   es el `nif` de la llamada → si no, `409 nif_mismatch`. Ni la respuesta ni los logs dicen qué NIF tiene.

Única excepción: el **hub de plataforma** (las facturas de ERPlora), que el Hub nombra con
`hub = PLATFORM_HUB_SLUG` (entorno; por defecto `erplora`, slug reservado de `live.slugs` que ningún negocio
puede tener; con uno no reservado, `manage.py check` falla con `fiscal_gateway.E001` y el despliegue no arranca). No es un negocio del SaaS: no se le pide fila `Hub` ni otorgamiento, pero solo
presenta en nombre de ERPLORA CLOUD SL: `nif` tiene que ser el titular del sello; si no, `409 nif_mismatch`.
Cualquier otro hub que declare el NIF de ERPlora necesita su otorgamiento como los demás. Con `route = "own"` no
hay excepción ni comprobación de otorgamiento: el certificado es del cliente y el NIF del sobre ya tiene que ser
el suyo.

## Seguridad

- El certificado del cliente vive solo durante la llamada: no se guarda, no se registra en logs y no aparece en
  mensajes de error (`SecretStr`, `sensitive_variables`, errores con `from None`). Hay test con `caplog`.
- Los tests solo tocan la preproducción de la AEAT (`prewww*`) y siempre con `respx`: nunca una transmisión
  real. Los endpoints de producción se prueban solo como cadena.

## Por medir

- `VERIFACTU_GATEWAY_CONCURRENCY = 8` presentaciones a la vez por proceso: el gateway en Rust medía 12,7 MiB
  por envío; aquí el sobre se guarda entero dos veces (texto y bytes). Se fija tras medir en `pre`.
