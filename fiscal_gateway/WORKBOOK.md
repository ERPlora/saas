# Workbook — Pasarela fiscal (fiscal_gateway)
Prefijo: FISCAL
Alcance MVP: fase 1 (presentar a la AEAT los registros VeriFactu de los negocios y de ERPlora, con el sello de ERPlora o con el certificado del negocio, y la revisión de la autorización firmada que permite usar el sello)
Estado de la app: hecha

> Manual de uso y especificación de la pasarela fiscal de erplora.com y de lo que la rodea en el SaaS: el sello
> de ERPlora, la presentación a la AEAT, los documentos de la autorización firmada (Anexo I) y los avisos de su
> revisión. No tiene pantallas propias: la usan el Hub de cada negocio (app VeriFactu) y el personal de ERPlora
> desde el admin. Este manual no se publica en la tienda: es la referencia del equipo y de la QA.

## Para qué sirve y para quién

La pasarela fiscal es la puerta por la que **todos** los registros VeriFactu llegan a la AEAT. El Hub de cada
negocio construye, encadena y valida sus registros; la pasarela solo los presenta y devuelve la respuesta de la
AEAT tal cual, sin guardar nada. Hay dos vías:

- **Con el sello de ERPlora**: ERPlora presenta en nombre del negocio gracias a la autorización que el negocio
  firma (el Anexo I del Convenio 17, «otorgamiento de la representación directa») y que una persona de ERPlora
  revisa. Sin una autorización aprobada, el sello no se usa para ese negocio.
- **Con el certificado del propio negocio**: el certificado vive en la base de datos de su Hub y solo pasa por la
  pasarela durante cada envío; ERPlora no lo guarda.

Quién la usa:

- El **Hub de cada negocio** (app VeriFactu) envía, consulta y prueba la conexión.
- El **negocio de plataforma** de ERPlora presenta las facturas que ERPlora emite a sus clientes.
- El **personal de ERPlora** cambia el sello cuando caduca, recibe el aviso de cada autorización que espera
  revisión y decide en el admin.
- El **propietario y los administradores** del negocio reciben un correo en cada paso de su autorización.

## Referencia adoptada

- **El colaborador social de la AEAT** (Convenio 17 y su Anexo I): el software presenta en nombre de su cliente
  con su propio sello, después de recibir y guardar la autorización firmada, como hacen los programas de
  facturación y las gestorías adheridas.
- **La verificación de identidad de Stripe y Square**: la persona sube sus documentos, una persona del equipo los
  revisa, y cada paso (recibido, aprobado, devuelto con su motivo) llega por correo; el equipo recibe aviso de lo
  que espera, sin documentos en el correo.
- **La rotación de certificados de los proveedores de nube**: dos huecos (el actual y el siguiente), cambio
  automático antes de la caducidad y alarma con margen.

## Antes de empezar

- En desarrollo y en el entorno de pruebas, la pasarela solo presenta en el entorno de pruebas de la AEAT; el
  entorno real solo se alcanza desde el despliegue de producción.
- El sello de ERPlora no se sube en ninguna pantalla: lo pone el equipo en los secretos del despliegue.
- Sin una dirección propia para la mesa de revisión, sus avisos van al buzón de soporte.

## Pantallas

### Admin › Autorizaciones firmadas › Revisar

La cola de autorizaciones con su negocio, versión, estado y fecha; cada una se abre en «Revisar la autorización
firmada», con sus documentos y los botones «Aprobar», «Devolver al cliente» y «Retirar la aprobación». Es la
pantalla a la que lleva el aviso a la mesa de revisión.

### Correos

No es una pantalla: los avisos de cada paso de la autorización llegan por correo a la mesa de revisión y al
negocio, cada uno en su idioma.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | El admin carga la cola como cualquier lista del admin. |
| Vacío | La cola sin autorizaciones dice que no hay ninguna. |
| Error | Un paso que no se puede dar (aprobar una que ya no espera, devolver sin motivo) lo explica arriba de la página y no cambia nada. |
| Sin permiso | Quien no es del equipo con permiso de revisar no ve la cola ni puede decidir. |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| FISCAL-F01 | Cambiar el sello de ERPlora con el que se presenta | hecho |
| FISCAL-F02 | Presentar a la AEAT los registros de un negocio | hecho |
| FISCAL-F03 | Guardar cifrados los documentos de la autorización | hecho |
| FISCAL-F04 | Avisar al equipo antes de que caduque el sello | hecho |
| FISCAL-F05 | Avisar a la mesa de revisión y al negocio de cada paso de la autorización | hecho |
| FISCAL-F06 | Poner el sello y la firma de ERPlora en el modelo de la autorización | parcial |
| FISCAL-F07 | Vigilar los apoderamientos (ZP01) de los clientes | descartado |

### FISCAL-F01 Cambiar el sello de ERPlora con el que se presenta
<!-- origen: fi:saas/django-admin#admin-verifactuconfig-singleton-vistas-operador fi:saas/support/billing-fiscal#modelo-verifactuconfig fi:saas/support/billing-fiscal#serializer-form-verifactuconfigform-load_pkcs12 -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: ninguna
Pasos:
1. Una persona del equipo pone el sello nuevo de ERPlora, con su contraseña, en el hueco «siguiente» de los secretos del despliegue; el hueco «actual» guarda el que está en uso.
2. Al arrancar, la pasarela abre cada hueco con su contraseña y comprueba que es un certificado con su clave que permite conectarse a la AEAT; uno que no abre, que no la permite o que ha caducado no se usa, y el registro dice qué hueco falló, nunca su contenido.
3. La pasarela presenta con el «actual» hasta 7 días antes de que caduque; desde entonces, con el «siguiente» si es válido. Sin «siguiente», sigue con el «actual» mientras no caduque.
4. Con el cambio hecho, la persona pasa el sello nuevo al hueco «actual» y deja el «siguiente» vacío para la próxima vez.
Entra: el sello de ERPlora y su contraseña, en los secretos del despliegue.
Sale: el sello con el que se presenta cada envío por la vía de ERPlora; la prueba de conexión del Hub dice con cuál y hasta cuándo vale.
Si falla: sin ningún sello utilizable, cada envío por la vía de ERPlora se rechaza antes de tocar la AEAT porque no hay sello y el Hub lo guarda para reintentarlo; nunca se presenta con un sello caducado.
Implicados: el Hub (VERIFACTU-F10 prueba la conexión y ve el sello), FISCAL-F04 (avisa antes de la caducidad)

### FISCAL-F02 Presentar a la AEAT los registros de un negocio
<!-- origen: fi:saas/support/billing-fiscal#service-aeatclient -->
Estado: hecho
Actor: sistema (el Hub del negocio)
Pantalla: ninguna
Pasos:
1. El Hub envía a la pasarela el sobre ya firmado y validado, con el negocio, su NIF, el entorno (pruebas o producción) y la vía: el sello de ERPlora o el certificado del propio negocio, que viaja solo en ese envío.
2. Antes de tocar la AEAT, la pasarela comprueba que el negocio existe, que el sobre solo nombra a ese contribuyente, que el entorno de producción solo se pide desde el despliegue de producción y, por la vía de ERPlora, que el negocio tiene su autorización aprobada y que es del mismo NIF.
3. Presenta el sobre a la puerta de la AEAT que toca (la de sellos de entidad o la del titular) con una conexión segura con el certificado, y devuelve la respuesta de la AEAT tal cual.
4. Con la misma puerta, el Hub consulta lo que la AEAT ya tiene, o prueba si podría presentar ahora y con qué certificado, sin enviar nada.
Entra: el sobre del Hub, el negocio, el NIF, el entorno, la vía y, por la vía propia, el certificado del negocio con su contraseña.
Sale: la respuesta de la AEAT tal cual (la interpreta el Hub); en la prueba de conexión, si está lista y con qué certificado.
Si falla: cada rechazo dice por qué y sale antes de tocar la AEAT: negocio desconocido, NIF que no casa, autorización no aprobada, sin sello, sin certificado, certificado no válido o caducado, o producción desde un despliegue que no lo es. Sin respuesta de la AEAT, el Hub sabe si el envío pudo llegar o no para no repetirlo a ciegas; con demasiados envíos a la vez, le pide que lo reintente. El certificado del negocio nunca se guarda ni aparece en un registro o en un error.
Implicados: el Hub (VERIFACTU-F15 envía, VERIFACTU-F27 consulta, VERIFACTU-F10 prueba la conexión), FISCAL-F01 (el sello), FISCAL-F05 (la autorización aprobada)

### FISCAL-F03 Guardar cifrados los documentos de la autorización
<!-- origen: fi:saas/support/billing-fiscal#service-fields-encryptedcharfield-encrypt_bytes-decrypt_bytes -->
Estado: hecho
Actor: sistema
Pantalla: Admin › Autorizaciones firmadas › Revisar
Pasos:
1. Cuando el Hub manda la autorización firmada de un negocio, el modelo firmado, la copia del documento de identidad y, si los hay, la muestra de firma y la prueba de representación se cifran antes de guardarse.
2. Solo la página «Revisar la autorización firmada» los descifra, para la persona del equipo que decide; ni la cola, ni el panel del negocio, ni los avisos ni lo que se manda al Hub llevan un documento.
3. La clave de cifrado es propia y obligatoria en producción: sin ella el despliegue no arranca, y nunca se toma la clave general de la aplicación en su lugar.
Entra: los documentos que sube el negocio desde su Hub.
Sale: los documentos guardados cifrados; la base de datos y sus copias nunca los tienen en claro.
Si falla: una clave que no sirve para cifrar se dice al arrancar y el despliegue se para; un documento guardado con otra clave no se abre y la página de revisión lo dice en lugar de enseñarlo.
Implicados: FISCAL-F05 (la revisión), el Hub (VERIFACTU-F05 sube la autorización)

### FISCAL-F04 Avisar al equipo antes de que caduque el sello
<!-- origen: fi:saas/support/billing-fiscal#task-check_certificate_expiry -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada día, una tarea programada abre los dos huecos del sello y publica cuántos días le quedan al que caduca antes (negativo si ya caducó).
2. Con menos de 30 días, salta la alarma del equipo, que pone el sello nuevo en el hueco «siguiente» (FISCAL-F01).
Entra: los dos huecos del sello.
Sale: los días que le quedan al sello, en las métricas de la plataforma, y la alarma con menos de 30.
Si falla: un hueco que no abre hace fallar la tarea, que también avisa al equipo, sin decir nunca lo que guarda; con los dos huecos vacíos no publica nada. Los certificados propios de los negocios viven en su Hub, que avisa de su caducidad.
Implicados: FISCAL-F01

### FISCAL-F05 Avisar a la mesa de revisión y al negocio de cada paso de la autorización
<!-- origen: old-saas:SAAS_DASHBOARD-F159 gh:saas#2051 -->
Estado: hecho
Actor: sistema
Pantalla: Admin › Autorizaciones firmadas › Revisar
Pasos:
1. Cuando un negocio envía su autorización firmada desde su Hub, la mesa de revisión recibe un correo con el negocio, la versión y el enlace a «Revisar la autorización firmada», sin documentos, NIF ni nombres de personas.
2. A la vez, el propietario y los administradores del negocio reciben, en su idioma, que ERPlora la ha recibido y que tendrán respuesta por correo.
3. Cuando una persona del equipo pulsa «Aprobar», les llega que la autorización ya está en vigor y que ERPlora ya puede enviar a Hacienda sus facturas con su sello.
4. Si pulsa «Devolver al cliente» o «Retirar la aprobación», les llega con el motivo que escribió y que la vuelvan a enviar desde la app VeriFactu del negocio.
Entra: cada paso de la autorización: enviada, aprobada, devuelta o retirada.
Sale: un correo a la mesa de revisión por cada autorización que espera y uno a cada propietario o administrador por cada paso; en el panel, el estado al momento (`fiscal.representation.changed`).
Si falla: los correos salen cuando el paso ya está guardado, nunca antes; un correo que no sale queda en el registro con la autorización y no deshace el paso, y la autorización sigue en la cola del admin. Una versión que otra más nueva sustituyó no avisa a nadie: avisa la nueva. Estos avisos llegan aunque la persona haya apagado los avisos del negocio, porque deciden si ERPlora puede enviar sus facturas.
Implicados: el Hub (VERIFACTU-F05 y VERIFACTU-F06 envían la autorización), FISCAL-F03 (los documentos)

### FISCAL-F06 Poner el sello y la firma de ERPlora en el modelo de la autorización
<!-- origen: old-saas:SAAS_DASHBOARD-F160 -->
Estado: parcial — el modelo que descarga el negocio es el oficial de la AEAT en blanco: aún no lleva el nombre, el NIF ni el sello y la firma de ERPlora como representante, que el equipo añade a mano
Actor: personal de ERPlora
Pantalla: ninguna
Pasos:
1. El negocio descarga desde la app VeriFactu de su Hub el modelo oficial del Anexo I para firmarlo.
2. El modelo llega en blanco, también en la casilla del representante, y ERPlora lo firma como representante cuando la AEAT se lo pide.
Entra: el modelo oficial del Anexo I.
Sale: el modelo en blanco que firma el negocio.
Si falla: si el modelo no se puede servir, el Hub dice que no lo ha podido descargar y el negocio lo vuelve a pedir.
Implicados: el Hub (VERIFACTU-F05 descarga el modelo), FISCAL-F05

### FISCAL-F07 Vigilar los apoderamientos (ZP01) de los clientes
<!-- origen: old-saas:SAAS_DASHBOARD-F162 -->
Estado: descartado — ERPlora presenta por la colaboración social del Convenio 17 con la autorización firmada del Anexo I, que revisa y retira el equipo (FISCAL-F05), no por apoderamientos ante la AEAT; no hay registro de apoderamientos que vigilar
Actor: sistema
Pantalla: ninguna
Pasos:
1. La autorización de cada negocio se revisa, se aprueba, se devuelve o se retira en el admin, y el Hub la ve en cada cambio.
2. No hay un registro aparte de apoderamientos ni una consulta diaria a la AEAT.
Entra: nada.
Sale: nada.
Si falla: no aplica.
Implicados: FISCAL-F05

## Para quien lo mantiene

- Anatomía: `fiscal_gateway/README.md` (la pasarela: `seal.py`, `aeat.py`, `internal.py`, `queries.py`, el contrato
  con el Hub y la tabla de respuestas) y la app `fiscal/` del SaaS (la autorización firmada: modelos, servicios,
  `crypto.py`, `emails.py`, admin). La pasarela es una app de plataforma sin modelos ni operaciones; los flujos
  FISCAL-F03, FISCAL-F05 y FISCAL-F06 viven en `fiscal/`.
- Este WORKBOOK nace en la tarea de migración APP-FISCAL_GATEWAY con las filas FISCAL-G01 a FISCAL-G09 del registro:
  G01, G02 y G03 (la configuración singleton de VerifactuConfig, su modelo y su formulario con `load_pkcs12`) son
  FISCAL-F01, sin pantalla ni modelo, porque el sello va en los secretos del despliegue (dos huecos,
  `FISCAL_SEAL_{CURRENT,NEXT}_{P12_BASE64,PASSWORD}`) y el entorno lo fija el despliegue (como VERIFACTU-G19); G04
  (`AEATClient`) es FISCAL-F02 (`aeat.py` + `internal.py`); G05 (`EncryptedCharField`) es FISCAL-F03
  (`fiscal/crypto.py`, Fernet con `FISCAL_DOCUMENTS_KEY`, saas#1057); G06 (`check_certificate_expiry`) es
  FISCAL-F04 (`manage.py report_seal_expiry`, programada a diario en `saas-cron` con la alarma `seal_expiry` de
  `aws`); G07 es FISCAL-F05 (`fiscal/emails.py`, `FISCAL_REVIEW_EMAIL`); G08 es FISCAL-F06; G09 es FISCAL-F07.
- FISCAL-F06 queda parcial: el viejo generaba el Anexo I con WeasyPrint, prerrellenado con los datos del cliente y de
  ERPlora y con el PNG del sello y la firma del representante (subido en el admin a un bucket privado). El nuevo sirve
  el PDF oficial estático (`GET /internal/representation/model`). Falta decidir dónde vive la imagen del sello con la
  firma (el repo es público, un secreto de AWS no pasa de 64 KB y aún no hay bucket privado de documentos fiscales) y
  superponer nombre, NIF y sello en el PDF oficial.
- Fiscal: los tests solo tocan la preproducción de la AEAT, y siempre con el transporte simulado (`respx`); nunca una
  transmisión real ni un certificado real (los `.p12` de los tests se generan en `tests/conftest.py`).
- Los tests de cada flujo citan su clave en el nombre o en el docstring (`fiscal/tests/test_emails.py` para
  FISCAL-F05).

## Lo que NO hace, a propósito

- No tiene pantalla para el sello de ERPlora ni guarda el sello en la base de datos: va en los secretos del
  despliegue, y el entorno (pruebas o producción) lo fija el despliegue, no un ajuste.
- No guarda nada de lo que presenta: ni sobres, ni respuestas, ni el certificado del negocio; la cola fiscal y las
  respuestas viven en el Hub de cada negocio.
- No interpreta la respuesta de la AEAT: la devuelve tal cual y la interpreta el Hub.
- No manda documentos por correo ni los adjunta al aviso de la mesa de revisión: solo el enlace a la revisión.
- No vigila apoderamientos ante la AEAT (procedimiento ZP01): la vía de ERPlora es la colaboración social.
