# Workbook — WhatsApp (whatsapp)
Prefijo: WHATSAPP
Alcance MVP: fase 1 (la cuenta de WhatsApp Business de cada negocio en erplora.com: su número, los avisos de Meta, los envíos, el cupo del mes y las plantillas, al servicio de la bandeja del Hub)
Estado de la app: completa (2026-10-30)

> Manual de uso y especificación de la app `whatsapp` del SaaS (erplora.com). Cuenta qué hace erplora.com con el
> WhatsApp de cada negocio: guarda su número y el permiso que Meta le da, recibe los avisos de Meta y los entrega
> al Hub, envía en su nombre lo que el Hub pide, lleva la cuenta del cupo del mes y registra sus plantillas en
> Meta. Esta parte del manual no se publica en la tienda: es la referencia del equipo y de la QA. Lo que la
> persona ve (la bandeja, sus ajustes y las plantillas) lo pinta el Hub y está en el manual de la bandeja de
> WhatsApp del Hub.

## Para qué sirve y para quién

WhatsApp es la mitad de erplora.com de la **Bandeja de WhatsApp** del Hub. ERPlora tiene una sola app en Meta
para todos los negocios: el número de cada negocio se conecta a ella, y por eso lo que Meta cuenta (un mensaje de
un cliente, un mensaje entregado o leído, el veredicto sobre una plantilla) llega a erplora.com, que lo reparte al
Hub de cada negocio. Lo que el negocio envía también sale por erplora.com, que es quien tiene el permiso de Meta.

- El permiso de Meta de cada negocio y el PIN de su número se guardan cifrados y nunca se enseñan.
- Lo que escribe un cliente se guarda solo hasta que el Hub lo recoge y pasa el plazo (30 días); nada de lo que
  envía el negocio se guarda aquí, salvo la clave del envío.
- Cada plan trae un cupo de mensajes al mes; al llegar al tope, el envío se para hasta el mes siguiente o hasta
  mejorar el plan. Dos envíos a la vez nunca pasan los dos el tope.

Quién la usa:

- El **sistema**: el Hub de cada negocio la llama para conectar el número, enviar, borrar los datos de un cliente
  y registrar o borrar plantillas; Meta le manda sus avisos.
- El **propietario** y los **administradores** del negocio, desde los ajustes de la bandeja del Hub; reciben el
  correo «Vuelve a conectar WhatsApp» cuando el permiso de Meta no se puede renovar.
- Cualquier persona del negocio abre desde la bandeja las fotos, notas de voz y documentos de sus clientes.
- El **personal de ERPlora**, en el admin: ve los números, las plantillas y lo que espera al Hub, y puede
  desconectar un número, entregar ahora al Hub lo que espera y volver a leer las plantillas de Meta.

## Referencia adoptada

- **WhatsApp Business Platform (Cloud API) de Meta** como único canal, con el alta embebida (Embedded Signup) para
  que el negocio conecte su número en una ventana de Meta sin salir del Hub, incluida la coexistencia con la app
  WhatsApp Business del móvil (https://developers.facebook.com/docs/whatsapp/embedded-signup).
- **Twilio, WATI, Respond.io, Gupshup y Zoko** como proveedores que hacen de intermediario (una app de Meta para
  muchos negocios): reparten los avisos por número, guardan el permiso del negocio cifrado, reintentan la entrega
  a su cliente con espera creciente y cobran por mensaje dentro de un cupo del plan.
- **Odoo WhatsApp** y **Shopify Inbox**: las plantillas se escriben en el propio programa y se mandan a revisión
  de Meta desde él; el veredicto de Meta llega solo.

## Antes de empezar

- La app de Meta («ERPlora Inbox») se configura por entorno con su identificador, su secreto, el token de
  verificación del aviso y la configuración del alta embebida. Sin ellos, erplora.com dice que WhatsApp no está
  configurado y Meta no puede entregar sus avisos.
- La página de erplora.com a la que vuelve la ventana de Meta tiene que estar entre las direcciones de vuelta que
  admite la app de Meta, y ser segura (https) fuera de desarrollo; si no, WhatsApp tampoco está configurado.
- Los permisos de Meta se cifran con la clave del entorno; cambiarla deja de abrir los guardados, salvo que la
  anterior se deje como clave previa mientras se vuelve a conectar.
- No hay entorno de pruebas de Meta en desarrollo: en las pruebas, las respuestas de Meta salen de su
  documentación.

## Pantallas

### Vuelta de la ventana de Meta
La página de erplora.com a la que Meta lleva su ventana al terminar. Devuelve al Hub que la abrió lo que dio Meta y
se cierra sola, sin que nadie la vea. Si la abrió otra cosa, o lo que trae no es de un negocio, se queda abierta
con «Esta ventana ya se puede cerrar.», en el idioma del navegador.

### Correo «Vuelve a conectar WhatsApp»
Lo recibe el propietario del negocio, en su idioma, cuando Meta no deja renovar el permiso. Asunto «Hay que
actuar: vuelve a conectar WhatsApp (número)»; dice que el permiso está a punto de caducar, que hasta reconectar
los mensajes de los clientes no llegarán al Hub, y «Es un minuto: entra en tu Hub, ve a WhatsApp y vuelve a
conectar tu número», con el enlace al Hub.

### Admin: Números de WhatsApp
Admin de erplora.com, solo para el personal de ERPlora. Columnas: número, negocio, identificador del número en Meta,
cuenta de WhatsApp Business, activo, desde la app WhatsApp Business, permiso de Meta («Guardado: este número puede
enviar y recibir.», «Caducado: el negocio tiene que volver a conectar el número.» o «Falta: el negocio tiene que
volver a conectar el número.»), caducidad del permiso, hay que reconectar y fecha de conexión. Filtros por activo,
app WhatsApp Business y hay que reconectar; búsqueda por número, identificadores y negocio. Acciones «Desconectar el
número» y «Volver a leer las plantillas de Meta».

### Admin: Entregas de WhatsApp al Hub
Lo recibido de Meta para cada negocio: identificador del mensaje, tipo («Mensaje» o «Estado de entrega»), negocio,
recibido, recogido por el Hub, intentos, próximo intento y último error. Nunca lo que escribió el cliente ni su
número. Filtro por tipo y por «recogido por el Hub» vacío; acción «Entregar al Hub ahora».

### Admin: Plantillas, Envíos y Consumo mensual de WhatsApp
Solo para mirar: las plantillas de cada negocio con su estado y el motivo de Meta; las claves de los envíos con su
estado y su mes; y lo gastado cada mes por negocio.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | En el Hub, la bandeja; en el admin, la carga normal de una lista. |
| Vacío | En el admin, «0 Números de WhatsApp» y la lista vacía. |
| Error | Un correo que no sale se reintenta en la renovación siguiente; en el admin, cada acción dice qué hizo y qué no («Ahora no se ha podido leer Meta: las plantillas siguen como estaban.»). |
| Sin configurar | WhatsApp sin la app de Meta o sin su página de vuelta: el Hub no ofrece conectar y Meta no puede entregar sus avisos. |
| Sin permiso | El admin no se abre sin el papel; el grupo de soporte solo mira, sin acciones. Un adjunto de otro negocio dice que no está disponible. |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| WHATSAPP-F01 | Conectar el número de WhatsApp del negocio | hecho |
| WHATSAPP-F02 | Desconectar el número | hecho |
| WHATSAPP-F03 | Decir al Hub qué número tiene el negocio y si hay que reconectarlo | hecho |
| WHATSAPP-F04 | Guardar el número de cada negocio con su permiso de Meta cifrado | hecho |
| WHATSAPP-F05 | Llevar la cuenta de los mensajes del mes y parar al llegar al tope del plan | hecho |
| WHATSAPP-F06 | Enviar un WhatsApp en nombre del negocio | hecho |
| WHATSAPP-F07 | Recibir los avisos de Meta y entregarlos al Hub | hecho |
| WHATSAPP-F08 | Ver los números de WhatsApp en el admin | hecho |
| WHATSAPP-F09 | Mover un número al negocio que lo conecta | hecho |
| WHATSAPP-F10 | Hablar con Meta sin dejar ver el permiso del negocio | hecho |
| WHATSAPP-F11 | Dar al Hub lo que necesita para abrir la ventana de Meta | hecho |
| WHATSAPP-F12 | Renovar el permiso de Meta antes de que caduque y avisar si no se puede | hecho |
| WHATSAPP-F13 | Confirmar a Meta que la dirección de los avisos es nuestra | hecho |
| WHATSAPP-F14 | Olvidar los mensajes que el Hub ya recogió | hecho |
| WHATSAPP-F15 | Registrar en Meta una plantilla nueva o editada | hecho |
| WHATSAPP-F16 | Subir a Meta la muestra de la cabecera de una plantilla | hecho |
| WHATSAPP-F17 | Borrar una plantilla en Meta | hecho |
| WHATSAPP-F18 | Lo que puede hacer el personal de ERPlora | hecho |

### WHATSAPP-F01 Conectar el número de WhatsApp del negocio
<!-- origen: fi:saas/auth-services#conectar-numero-whatsapp-embedded-signup-oauth -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Bandeja de WhatsApp › Ajustes (en el Hub); Vuelta de la ventana de Meta
Pasos:
1. En los ajustes de la bandeja, pulsa «Conectar WhatsApp»: se abre la ventana de Meta, se entra con Facebook, se elige o se escribe el número y, si ya se usa la app WhatsApp Business del móvil, se escanea el código con el móvil.
2. Al terminar, la ventana pasa por erplora.com, que devuelve al Hub el código de un solo uso de Meta (o su motivo para no darlo) y se cierra sola.
3. El Hub pasa a erplora.com lo que Meta le dio; erplora.com consigue el permiso del negocio, comprueba que el número elegido está en esa cuenta, suscribe la app de ERPlora a la cuenta y registra el número (o, si viene de la app del móvil, pide a Meta los contactos y el historial sin registrarlo).
4. «Tu número» pasa a «Conectado» con el número y el nombre del negocio en WhatsApp.
Entra: lo que la ventana de Meta da al Hub: un código de un solo uso, la cuenta de WhatsApp Business, el número elegido y el portfolio.
Sale: el número activo del negocio con su permiso y su PIN cifrados; el Hub lo sabe por su foto de estado (`whatsapp.number.connected`).
Si falla: si Meta no da el código, el Hub recibe su motivo y no se conecta nada; el código solo vuelve al negocio que abrió la ventana: si la ventana llega con otro, o sin ninguno, no se devuelve nada y la ventana dice «Esta ventana ya se puede cerrar.». Si Meta rechaza un paso (el código caducó, el PIN no coincide, la suscripción no se acepta) no se guarda nada y se dice el motivo de Meta; si el número elegido no está en la cuenta, o la cuenta tiene varios y no se eligió ninguno, no se conecta otro: se dice que se elija; si Meta no contesta, se pide intentarlo de nuevo; sin la app de Meta configurada, WhatsApp no está disponible. Una demo no puede conectar ningún número. Si Meta no da el historial, el número queda conectado igual.
Implicados: bandeja de WhatsApp del Hub (ajustes)

### WHATSAPP-F02 Desconectar el número
<!-- origen: fi:saas/auth-services#desconectar-numero -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Bandeja de WhatsApp › Ajustes (en el Hub)
Pasos:
1. En los ajustes de la bandeja, pulsa «Desconectar» y confirma.
2. erplora.com deja de usar el número: olvida el permiso de Meta, quita la app de ERPlora de esa cuenta si ningún otro número conectado la usa y conserva el PIN para volver a registrarlo.
3. «Tu número» pasa a «Sin conectar» al momento, con «WhatsApp desconectado.»; las conversaciones del Hub no se tocan.
Entra: el negocio.
Sale: el número inactivo, sin permiso, con la fecha de desconexión; el Hub lo sabe por su foto de estado (`whatsapp.number.disconnected`).
Si falla: sin número conectado no cambia nada; si Meta no contesta al quitar la app, el número queda desconectado igual y lo que Meta siga contando de él se descarta.
Implicados: bandeja de WhatsApp del Hub (ajustes)

### WHATSAPP-F03 Decir al Hub qué número tiene el negocio y si hay que reconectarlo
<!-- origen: fi:saas/auth-services#listar-numeros-conectados -->
Estado: hecho
Actor: sistema
Pantalla: Bandeja de WhatsApp › Ajustes (en el Hub)
Pasos:
1. Cada vez que cambia algo del WhatsApp del negocio (el número, su permiso de Meta, el consumo del mes, una plantilla o el veredicto de Meta sobre ella), erplora.com sube la versión de la foto de estado del negocio y se la manda al Hub.
2. La foto dice si el número está «Conectado», «Sin conectar» o «Hay que reconectar», el número y el nombre en WhatsApp, el cupo y lo gastado este mes, y las plantillas con lo que dice Meta de cada una. «Hay que reconectar» sale en cuanto Meta rechaza el permiso del negocio: al renovarlo, al enviar un mensaje, al registrar o borrar una plantilla o al abrir un adjunto.
3. El Hub la aplica y los ajustes y la bandeja lo enseñan sin recargar.
Entra: el número activo del negocio, su plan, lo gastado este mes y sus plantillas.
Sale: la parte de WhatsApp de la foto de estado del negocio, con una versión que solo crece.
Si falla: si el Hub no está, la foto se reintenta con la conciliación de cada negocio; una foto más vieja que la guardada no se aplica.
Implicados: bandeja de WhatsApp del Hub, negocios (la foto de estado)

### WHATSAPP-F04 Guardar el número de cada negocio con su permiso de Meta cifrado
<!-- origen: fi:saas/auth-services#modelo-whatsappphonemapping-admin -->
Estado: hecho
Actor: sistema
Pantalla: Admin: Números de WhatsApp
Pasos:
1. Al conectar, erplora.com guarda el número del negocio con los identificadores de Meta, el nombre en WhatsApp, si viene de la app del móvil y cuándo caduca el permiso.
2. El permiso de Meta y el PIN se guardan cifrados con la clave del entorno; quien mira la base de datos solo ve texto cifrado.
3. Un negocio tiene un solo número activo; conectar otro desconecta el anterior.
Entra: lo que da la conexión.
Sale: el número del negocio, que usan el envío, la recepción y las plantillas.
Si falla: un permiso que ya no se puede descifrar (la clave cambió) se lee como que falta y el número se trata como «Sin conectar»; queda escrito como error para el equipo.
Implicados: ninguno

### WHATSAPP-F05 Llevar la cuenta de los mensajes del mes y parar al llegar al tope del plan
<!-- origen: fi:saas/auth-services#plan-y-uso-de-whatsapp -->
Estado: hecho
Actor: sistema
Pantalla: Bandeja de WhatsApp (en el Hub)
Pasos:
1. Cada envío que el Hub pide ocupa una plaza del cupo del mes del plan del negocio antes de salir hacia Meta.
2. Si Meta lo rechaza o no llega a salir, la plaza se libera; si salió, cuenta.
3. Al llegar al tope, el envío se para y el Hub dice que se llegó al tope del mes, hasta el mes siguiente o hasta mejorar el plan. El plan Gratis trae 30, Starter 150 y Standard 300; un plan sin WhatsApp no envía ninguno.
4. Si el Hub tenía lo gastado del mes atrasado y aún dejaba enviar, el envío parado en el tope lo pone al día al momento: la bandeja deja de dejar enviar, sin recargar. Otro envío parado con lo mismo gastado no lo vuelve a avisar.
Entra: el plan del negocio y lo gastado este mes.
Sale: lo gastado del mes, que el Hub enseña en sus ajustes (`whatsapp.message.recorded`).
Si falla: dos envíos a la vez con una sola plaza libre: sale uno y el otro se para; el mismo envío repetido (el Hub reintenta) no gasta otra plaza.
Implicados: negocios (el plan de cada negocio)

### WHATSAPP-F06 Enviar un WhatsApp en nombre del negocio
<!-- origen: fi:saas/auth-services#servicio-meta-graph-api -->
Estado: hecho
Actor: sistema
Pantalla: Bandeja de WhatsApp (en el Hub)
Pasos:
1. En la bandeja, alguien contesta a un cliente o le envía una plantilla aprobada; el Hub lo pasa a erplora.com con una clave propia del envío.
2. erplora.com reserva la plaza del cupo, lo envía a Meta con el permiso del negocio y devuelve el identificador del mensaje de WhatsApp.
3. Si la plantilla lleva en la cabecera una foto, un vídeo o un documento, el Hub manda el archivo con ella: erplora.com mira qué es por sus primeros bytes (los mismos tipos y pesos que al registrarla, F16), lo sube al número del negocio en Meta y envía la plantilla con él.
4. Lo que Meta diga después (entregado, leído, fallido) llega a la bandeja como su estado.
Entra: a quién, el texto o la plantilla con sus variables (y el archivo de su cabecera, si lo lleva), y la clave del envío.
Sale: el mensaje enviado por WhatsApp; la clave anotada para no enviarlo dos veces (`whatsapp.message.recorded`).
Si falla: fuera de las 24 horas desde el último mensaje del cliente, se dice que WhatsApp solo deja escribirle con una plantilla aprobada; un cliente que bloqueó al negocio, una plantilla no aprobada o un número sin conectar dicen su motivo y no gastan cupo; si el permiso de Meta caducó o el negocio lo retiró en Meta, no sale ni gasta cupo, se dice que hay que volver a conectar el número (no que está sin conectar) y el número queda «Hay que reconectar» en el Hub; si Meta no contesta, no se sabe si salió: el Hub reintenta con la misma clave y erplora.com nunca lo envía dos veces. Un archivo de la cabecera que no es del tipo o pesa de más dice la regla y no llega a Meta; si Meta rechaza el archivo o no contesta al subirlo, el mensaje no sale ni gasta cupo y la misma clave lo vuelve a intentar.
Implicados: bandeja de WhatsApp del Hub

### WHATSAPP-F07 Recibir los avisos de Meta y entregarlos al Hub
<!-- origen: fi:saas/auth-services#webhook-de-whatsapp-meta -->
Estado: hecho
Actor: sistema
Pantalla: Bandeja de WhatsApp (en el Hub)
Pasos:
1. Un cliente escribe al número del negocio (o el dueño contesta desde el móvil, o llega el historial al conectar): Meta lo cuenta a erplora.com, que comprueba que el aviso es de Meta y lo guarda para el negocio de ese número.
2. erplora.com lo entrega al Hub en el momento; si el Hub no está o no tiene la bandeja encendida, lo vuelve a intentar con una espera que crece hasta una hora, cada minuto mientras le quede algo. Si el Hub va lento, cada minuto entrega lo que cabe en ese minuto, sin repetir lo que aún está entregando.
3. Una foto, una nota de voz o un documento llegan como un enlace de erplora.com que solo abre una persona del negocio con su sesión; el archivo viene de Meta en ese momento y no se guarda.
4. El estado de un mensaje del negocio («Entregado», «Leído», «No entregado») llega a la bandeja: el de uno enviado desde el Hub, cuando erplora.com sabe cuál es; el de una respuesta del dueño desde el móvil, después de esa respuesta.
Entra: los avisos de Meta: mensajes, ecos del móvil, historial, estados de entrega y veredictos de plantillas.
Sale: el mensaje o el estado en la bandeja del Hub (`whatsapp.webhook.ingested`, `whatsapp.delivery.recorded`).
Si falla: un aviso sin la firma de Meta se rechaza y no se guarda; uno de un número que nadie tiene conectado se descarta; el estado de un mensaje que el Hub no tiene se espera diez minutos y se descarta; si el Hub dice que el mensaje no vale, no se reintenta y queda a la vista del personal; un adjunto de otro negocio, o que Meta ya no tiene, dice que no está disponible; si al abrir un adjunto el permiso de Meta caducó o el negocio lo retiró en Meta, el adjunto no se abre, se dice que hay que volver a conectar el número (no que está sin conectar) y el número queda «Hay que reconectar» en el Hub.
Implicados: bandeja de WhatsApp del Hub

### WHATSAPP-F08 Ver los números de WhatsApp en el admin
<!-- origen: fi:saas/django-admin#admin-whatsappphonemapping -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin: Números de WhatsApp
Pasos:
1. Abre «Números de WhatsApp» en el admin de erplora.com.
2. Ve cada número con su negocio, sus identificadores de Meta, si está activo, si viene de la app del móvil, si su permiso de Meta está guardado o caducado, o si falta, cuándo caduca y si hay que reconectarlo; filtra por «hay que reconectar» o busca por número o negocio.
3. Abre uno para verlo entero; nada se escribe a mano.
Entra: la cuenta del personal con su papel.
Sale: nada; solo se mira.
Si falla: sin el papel, el admin no se abre; el permiso de Meta y el PIN no salen nunca, ni en la ficha.
Implicados: ninguno

### WHATSAPP-F09 Mover un número al negocio que lo conecta
<!-- origen: fi:saas/support/auth-services#modelo-whatsappphonemapping -->
Estado: hecho
Actor: sistema
Pantalla: Bandeja de WhatsApp › Ajustes (en el Hub)
Pasos:
1. Un número tiene un solo dueño en toda la plataforma: si otro negocio lo conecta (por ejemplo, tras un cambio de dueño del local), pasa a ese negocio.
2. erplora.com avisa a los dos Hubs con su foto de estado: el nuevo lo ve «Conectado» y el anterior «Sin conectar».
3. Volver a conectar el mismo número en el mismo negocio solo renueva su permiso y cierra el aviso «Hay que reconectar».
Entra: la conexión del número desde el otro negocio.
Sale: el número en su negocio nuevo; queda escrito de dónde venía (`whatsapp.number.connected`).
Si falla: si la conexión falla, el número sigue donde estaba.
Implicados: bandeja de WhatsApp del Hub

### WHATSAPP-F10 Hablar con Meta sin dejar ver el permiso del negocio
<!-- origen: fi:saas/support/auth-services#service-meta-meta_api_get-meta_api_post -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada llamada a Meta lleva el permiso del negocio en la cabecera, nunca en la dirección, y no sigue redirecciones.
2. La respuesta se clasifica: Meta aceptó, Meta rechazó (con su código y su motivo para la persona), Meta pide esperar, o Meta no contestó (sin saber si llegó).
3. El permiso, el código de un solo uso y el secreto de la app no aparecen en ningún registro.
Entra: lo que cada flujo pide a Meta.
Sale: la respuesta de Meta, o el motivo por el que no la hay.
Si falla: un adjunto cuyo enlace no es de Meta o no va cifrado no se descarga.
Implicados: ninguno

### WHATSAPP-F11 Dar al Hub lo que necesita para abrir la ventana de Meta
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F01 -->
Estado: hecho
Actor: sistema
Pantalla: Bandeja de WhatsApp › Ajustes (en el Hub)
Pasos:
1. Al pintar «Tu número», el Hub pregunta a erplora.com.
2. erplora.com contesta si WhatsApp está configurado y, si lo está, el identificador de la app de Meta, el de la configuración del alta embebida, la versión de Meta que usa y su página a la que Meta devuelve el código; con esa misma página canjea después el código.
3. Sin la app configurada, o sin una página de vuelta válida, contesta que no está configurado, con los identificadores vacíos, y el Hub no enseña «Conectar WhatsApp».
Entra: el negocio.
Sale: los identificadores públicos de la app; el secreto y el token de verificación no salen nunca.
Si falla: un negocio que erplora.com no conoce, o una demo, no recibe nada.
Implicados: bandeja de WhatsApp del Hub (ajustes)

### WHATSAPP-F12 Renovar el permiso de Meta antes de que caduque y avisar si no se puede
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F05 -->
Estado: hecho
Actor: sistema
Pantalla: Correo «Vuelve a conectar WhatsApp»
Pasos:
1. Una vez al día, erplora.com mira los números conectados cuyo permiso caduca en 14 días o menos, de negocios que siguen activos.
2. Pide a Meta uno nuevo a cambio del actual; si lo consigue, apunta la nueva caducidad y cierra el aviso «Hay que reconectar».
3. Si Meta lo rechaza, o no contesta y quedan 3 días o menos, marca el número «Hay que reconectar» (el Hub lo enseña) y manda un correo, en su idioma, al propietario del negocio, uno por incidente.
Entra: los números conectados y sus permisos.
Sale: el permiso renovado o la marca «Hay que reconectar» con el correo (`whatsapp.number.reconnect_needed`).
Si falla: si Meta no contesta y queda margen, se reintenta al día siguiente; un correo que no sale se reintenta en la vuelta siguiente; un número que falla no para a los demás; sin ningún número que renovar, la tarea termina bien aunque falte la app de Meta; con números que renovar y sin la app de Meta configurada, termina con error para el equipo.
Implicados: negocios (el propietario), bandeja de WhatsApp del Hub

### WHATSAPP-F13 Confirmar a Meta que la dirección de los avisos es nuestra
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F06 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al dar de alta la dirección de los avisos en la app de Meta, Meta llama a erplora.com con el token de verificación y un reto.
2. Si el token coincide con el del entorno, erplora.com devuelve el reto y Meta da la dirección por buena.
3. Desde entonces, cada aviso de Meta llega firmado con el secreto de la app y erplora.com comprueba la firma antes de leerlo.
Entra: el token de verificación y el reto de Meta.
Sale: la dirección de los avisos confirmada en Meta.
Si falla: un token que no coincide se rechaza; sin token o sin secreto configurado, erplora.com dice que no está disponible y no acepta ningún aviso.
Implicados: ninguno

### WHATSAPP-F14 Olvidar los mensajes que el Hub ya recogió
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F11 -->
Estado: hecho
Actor: sistema
Pantalla: Admin: Entregas de WhatsApp al Hub
Pasos:
1. Una vez al día, erplora.com borra lo que el Hub recogió hace más de 30 días y los estados de entrega de más de 30 días.
2. Lo que el Hub nunca recogió en 30 días (un Hub apagado o sin la bandeja) también se borra, y queda escrito cuántos mensajes de qué negocio se perdieron.
3. Las claves de los envíos y de los registros de plantillas de más de 30 días también se borran.
Entra: lo que erplora.com guarda de cada negocio y sus fechas.
Sale: lo viejo borrado (`whatsapp.retention.purged`).
Si falla: el plazo se puede acortar a mano (de 1 a 30 días), nunca alargar; fuera de ese margen no se borra nada y la tarea termina con error.
Implicados: ninguno

### WHATSAPP-F15 Registrar en Meta una plantilla nueva o editada
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F17 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Bandeja de WhatsApp › Ajustes › Plantilla (en el Hub)
Pasos:
1. En el Hub, se escribe la plantilla (nombre, idioma, categoría, cabecera —de texto, o con una foto, un vídeo o un documento: F16—, texto con sus variables y un ejemplo de cada una, pie y botones) y se pulsa «Enviar a revisión de Meta» (al editarla, «Guardar y enviar a Meta»).
2. erplora.com comprueba las reglas de Meta antes de llamarla: nombre en minúsculas, cifras y guiones bajos, variables seguidas o con nombre, un ejemplo por variable, como mucho 10 botones con sus límites.
3. La registra en Meta (o, si Meta ya la tenía, edita la suya) y el Hub la enseña «En revisión»; el veredicto de Meta llega solo después.
Entra: la plantilla tal como se escribió y la clave del guardado.
Sale: la plantilla en Meta y su copia en erplora.com, que viaja al Hub en la foto de estado (`whatsapp.template.registered`).
Si falla: una regla rota dice cuál; Meta rechazándola da su motivo para la persona; si el permiso de Meta caducó o el negocio lo retiró en Meta, no se registra, se dice que hay que volver a conectar el número (no que está sin conectar) y el número queda «Hay que reconectar» en el Hub; si Meta no contesta o pide esperar, no se guarda nada y se puede reintentar; el mismo guardado repetido no se registra dos veces.
Implicados: bandeja de WhatsApp del Hub

### WHATSAPP-F16 Subir a Meta la muestra de la cabecera de una plantilla
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F18 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Bandeja de WhatsApp › Ajustes › Plantilla (en el Hub)
Pasos:
1. En el Hub, se elige para la cabecera de la plantilla una foto, un vídeo o un documento y se manda a revisión.
2. erplora.com mira qué es el archivo por sus primeros bytes, nunca por su nombre: una foto JPEG o PNG de hasta 5 MB,
   un vídeo MP4 de hasta 16 MB o un documento PDF de hasta 25 MB.
3. Lo sube a Meta como muestra con el permiso del número del negocio y registra la plantilla con ella (F15); en cada
   cambio de la plantilla la vuelve a subir, porque Meta la pide en cada revisión.
Entra: el archivo de la cabecera con su nombre, junto a la plantilla y la clave del guardado.
Sale: la muestra en Meta y la plantilla registrada con su cabecera; erplora.com no se queda con el archivo.
Si falla: un archivo que no es del tipo de la cabecera, o que pesa más de lo que admite, dice cuál es la regla y no
llega a Meta; si Meta no contesta, pide esperar o rechaza la muestra, la plantilla no se registra y el mismo guardado
se puede repetir (si el permiso de Meta caducó, se pide volver a conectar el número, como en F15); el mismo guardado
repetido no sube la muestra dos veces.
Implicados: bandeja de WhatsApp del Hub

### WHATSAPP-F17 Borrar una plantilla en Meta
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F19 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Bandeja de WhatsApp › Ajustes (en el Hub)
Pasos:
1. En el Hub, se borra una plantilla en un idioma.
2. erplora.com la borra en Meta en ese idioma (no las demás del mismo nombre) y la quita de su copia.
3. El Hub la da por borrada.
Entra: el nombre, el idioma y el identificador de Meta de la plantilla.
Sale: la plantilla fuera de Meta y de la copia de erplora.com (`whatsapp.template.forgotten`).
Si falla: si Meta ya no la tiene, cuenta como borrada; si el permiso de Meta caducó o el negocio lo retiró en Meta, sigue viva, se dice que hay que volver a conectar el número (no que está sin conectar) y el número queda «Hay que reconectar» en el Hub; si Meta la rechaza o no contesta, sigue viva y el Hub lo vuelve a pedir.
Implicados: bandeja de WhatsApp del Hub

### WHATSAPP-F18 Lo que puede hacer el personal de ERPlora
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F20 -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin: Números de WhatsApp, Admin: Entregas de WhatsApp al Hub
Pasos:
1. Una persona de ERPlora entra en el admin con la cuenta de erplora.com.
2. Ve, solo para leer y en su idioma, los números, las plantillas, lo que espera al Hub, las claves de los envíos y lo gastado cada mes; nunca el permiso, el PIN ni lo que escribió un cliente.
3. Si es superusuario, puede «Desconectar el número», «Volver a leer las plantillas de Meta» y «Entregar al Hub ahora»; cada acción dice qué hizo.
4. Las tareas diarias de renovar permisos y de olvidar lo viejo, y la de entregar lo que espera, también se pueden lanzar a mano.
Entra: la cuenta del personal con su papel.
Sale: lo que hacen sus acciones; el negocio de un número no se cambia ni se activa a mano.
Si falla: sin el papel, el admin no se abre; el grupo de soporte solo mira, sin acciones.
Implicados: ninguno

## Para quien lo mantiene

- Anatomía, datos, operaciones y tareas: `whatsapp/README.md`.
- **Contrato con el Hub**: las puertas 1–12 son las del WORKBOOK de `whatsapp_inbox` del Hub («Contrato con el SaaS»),
  que mandan y no se renombran. Las 10–12 nacieron en este porte (saas#63) y el Hub las llama y las recoge en su
  contrato desde hub#151; llevan la misma firma de todo `/internal` (`X-Erplora-Timestamp` + `X-Erplora-Signature`,
  HMAC-SHA256 de `f"{timestamp}.{cuerpo}"` con `INTERNAL_SHARED_SECRET`, ±300 s):
  - **10** `POST /internal/whatsapp/config` `{"hub"}` → 200 `{"configured", "app_id", "config_id", "graph_version",
    "redirect_uri"}` (WHATSAPP-F11); 404 `hub_unknown`. `redirect_uri` = `WHATSAPP_REDIRECT_URI` (por defecto
    `https://<PUBLIC_HOST>/whatsapp/return`; en desarrollo `http://localhost:8001/whatsapp/return`), absoluta, https
    fuera de `DEBUG` y sin consulta: si no lo es, `configured: false` y `whatsapp.I001` la nombra. La puerta 11 canjea
    el código con ese mismo valor (Meta rechaza otro: error 100/36008).
  - **11** `POST /internal/whatsapp/connect` `{"hub", "code", "event", "waba_id", "phone_number_id", "business_id"}`
    → 200 `{"connected": true, "phone_number", "display_name", "history_requested"}` (WHATSAPP-F01, F09); 409
    `whatsapp.meta_rejected | number_not_in_account | number_not_chosen`, 429 `whatsapp.meta_rate_limited`, 502
    `whatsapp.meta_no_token`, 503 `whatsapp.meta_unreachable | not_configured`, 404 `hub_unknown`, 422. Nada se
    guarda hasta que Meta aceptó todos los pasos.
  - **12** `POST /internal/whatsapp/disconnect` `{"hub"}` → 200 `{"disconnected": true|false}` (WHATSAPP-F02).
  El canal (puerta 3) no se usa desde el SaaS: la clave `whatsapp` de la foto (puerta 4) es la única fuente, con la
  versión de la foto y el reintento de `reconcile_hub_states`.
- **El permiso caducado** (FIX-SAAS-WHATSAPP-EXPIRED-TOKEN-SAYS-NOT-CONNECTED en la puerta 5;
  FIX-SAAS-WHATSAPP-TEMPLATE-DOORS-SAY-NOT-CONNECTED-ON-EXPIRED-PERMISSION en las puertas 8 y 9 y en los adjuntos):
  a los 409 de la puerta 5 (`whatsapp.cap_reached`, `not_connected`, `window_closed`, `template_not_approved`,
  `recipient_blocked` y `meta_rejected`) y de las puertas 8 y 9 (`whatsapp.meta_unreachable`, `meta_rate_limited`,
  `not_connected` y `template_invalid` en la 8 o `meta_rejected` en la 9) se suma `whatsapp.reconnect_needed`, que también
  contesta `GET /whatsapp/media/<id>`: Meta contestó 190 (el permiso caducó o el negocio lo retiró en Meta), el
  número queda «Hay que reconectar» y la foto lo lleva con una versión nueva (WHATSAPP-F06, F15, F17, F07, F03); la
  plantilla no se registra ni se borra.
  Los otros códigos de Meta de un número que no puede (10, 200, 131031, 133010) siguen siendo `not_connected` en las
  puertas 5, 8 y 9, sin marca. En los adjuntos el 190 cuenta igual al pedir el adjunto que al descargarlo; cualquier
  otro rechazo de Meta es un 404 `whatsapp.media_not_found` al pedirlo y un 502 `whatsapp.media_unavailable` al
  descargarlo, sin marca. El Hub lo entiende en la puerta 5 y en las plantillas
  (`whatsapp_inbox.reconnect_needed` con su propio texto, hub#245). Un adjunto lo abre el navegador de la persona
  (`<img>`, `<audio>` o un enlace), que no lee el código: cualquier 409 es para el Hub un adjunto que no carga, así
  que el código nuevo no cambia lo que pinta.
- **La muestra de la cabecera** (FIX-HUB-WHATSAPP-INBOX-TEMPLATE-HEADER-MEDIA-NOW-STORABLE, WHATSAPP-F16): la puerta 8
  lleva `header_format` (vacío o `TEXT`: cabecera de texto, como antes; `IMAGE`, `VIDEO` o `DOCUMENT`) y, con archivo,
  `header_sample` `{"name", "content_base64"}`. Su cuerpo pesa hasta `MAX_TEMPLATE_BODY_BYTES` (los 256 KB de las otras
  puertas más 25 MB en base64; por encima, 413 `payload_too_large` sin leerlo). `templates.check` lee el tipo por los
  primeros bytes (JPEG o PNG hasta 5 MB y MP4 hasta 16 MB, los de Meta; PDF hasta 25 MB, el tope del Hub para un
  archivo que guarda, `base.files.MAX_FILE_BYTES`, aunque Meta admite 100 MB) y lo que no casa es 409
  `whatsapp.template_invalid` antes de reclamar la clave. Con la clave reclamada, `meta.upload_sample` hace la
  *Resumable Upload API* de Meta: la sesión en `/<WHATSAPP_APP_ID>/uploads` (nombre, tamaño y tipo; `Bearer`) y los
  bytes en `/<upload:…>` (`OAuth`, `file_offset: 0`, hasta 60 s), sin seguir redirecciones; el id de la sesión se
  comprueba (empieza por `upload:` y no sale de su ruta) antes de mandarle el permiso. El componente `HEADER` va con
  `example.header_handle`, también al editar. Un rechazo o un silencio de Meta en la subida son los mismos 409 con
  nombre que al registrar, con la clave libre, y sin `WHATSAPP_APP_ID` es 503 `whatsapp.not_configured`, también
  con la clave libre. El Hub espera la puerta 8 con archivo hasta 90 s. El archivo no se guarda en erplora.com.
- **Puerta 5 con el archivo de la cabecera** (FIX-HUB-WHATSAPP-INBOX-TEMPLATE-HEADER-MEDIA-NOW-STORABLE, WHATSAPP-F06):
  `template` lleva `header_format` (`IMAGE`, `VIDEO` o `DOCUMENT`) y `header_sample` `{"name", "content_base64"}`
  cuando la cabecera es un archivo; el cuerpo pesa hasta `MAX_TEMPLATE_BODY_BYTES`, como la puerta 8.
  `templates.send_sample` lo comprueba como la puerta 8 (tipo por los primeros bytes, topes de Meta) y lo que no casa
  es 409 `whatsapp.template_invalid` antes de reclamar la clave. Con la clave reclamada, `meta.upload_media` lo sube
  al número (`POST /<PHONE_NUMBER_ID>/media`, multipart con `messaging_product` y su tipo; Meta lo guarda 30 días) y
  el mensaje lleva `{"type": "header", "parameters": [{"type": "image|video|document", "<tipo>": {"id"}}]}` (el
  documento, con `filename`). La subida no envía nada: su rechazo es el mismo 409 con nombre que el del envío y su
  silencio (o una respuesta sin `id`) es 503 `whatsapp.meta_unreachable`, los dos con la plaza y la clave libres. La
  misma clave ya enviada no sube ni envía otra vez. El archivo no se guarda en erplora.com.
- **Puerta 5 y el tope** (FIX-SAAS-WHATSAPP-CAP-REFUSAL-DOES-NOT-PUSH-USAGE, WHATSAPP-F05): el 409
  `whatsapp.cap_reached` no cambia para el Hub, pero ya no deshace la transacción: `whatsapp.message.claim` lo
  devuelve (`refused`, sin la clave: queda libre) y, si el consumo del mes no se había avisado con esa cifra
  (`Usage.cap_announced_usage`), sube la versión de la foto y la empuja tras el COMMIT, con `monthly_usage` al día
  (`reconcile_hub_states` la reintenta si el Hub no la toma). La misma cifra rechazada otra vez no sube nada: un
  empuje por cifra, no por envío rechazado.
- Vuelta de la ventana de Meta: `GET /whatsapp/return?code=…&state=<slug>.<32 hex>` (o `?error=…&error_description=…`;
  `whatsapp/signup_return.py`, WHATSAPP-F01), pública, sin sesión, sin caché y sin BD. Hace
  `window.opener.postMessage({"type": "erplora.whatsapp.signup", "state", "code" | "error", "error_description"},
  <origen del hub>)` y se cierra; el origen sale del `slug` del `state`, validado con `live.slugs` (ni reservados ni
  demos), y de `HUB_CALLBACK_TEMPLATE`, nunca `"*"`. Lleva `Cross-Origin-Opener-Policy: unsafe-none` solo en esa
  vista (el resto del SaaS, `same-origin` de Django, que corta la ventana de su `opener`; el Hub manda
  `same-origin-allow-popups`, hub#154) y el dato va como `json_script` leído por su único script, con el nonce de la
  CSP. El Hub abre la ventana sin el SDK de Facebook (su WORKBOOK `whatsapp_inbox`, «La ventana de Meta sin el SDK de
  Facebook»).
- Adjuntos: `GET /whatsapp/media/<id de la entrega>` (WHATSAPP-F07), con la sesión de erplora.com y miembro aceptado
  del negocio; lo que no es imagen, audio o vídeo se descarga con `Content-Disposition: attachment` y CSP `sandbox`.
  El Hub debe permitir el origen de erplora.com en `img-src` y `media-src` (su «Contrato con `base`»).
- Tareas programadas (ECS, `saas-cron`): `whatsapp_deliver` cada minuto (WHATSAPP-F07), `whatsapp_refresh_tokens`
  (WHATSAPP-F12) y `whatsapp_purge` (WHATSAPP-F14) una vez al día; las programa el repo de infraestructura
  (`aws`, `stacks/prod/scheduler.tf`), que también da los secretos `WHATSAPP_*` y `FERNET_KEY` (`secrets.tf` y
  `apps.tf`; los de `pre`, propios, en `pre_data.tf`).
- Los tests de cada flujo citan su clave del registro en el nombre del fichero de test o en su docstring:
  `WHATSAPP-Gnn` los de antes de `promote` y `WHATSAPP-Fnn` los posteriores, con el mismo número.
- Contradicción resuelta: «WhatsApp sale del SaaS y el Hub llama a Meta» lo derogan las rondas 2026-10-21 de
  `PLAN-SAAS.md` (§1.1, saas#63) y `PLAN-HUB.md` (§8, saas#63): WhatsApp se queda en el SaaS como única pasarela con
  Meta y el Hub habla con él por `/internal`. La ronda de cierre de la app (`PLAN-SAAS.md`, «cierre de `whatsapp`») recoge
  lo decidido al migrarla.

## Lo que NO hace, a propósito

- No tiene pantalla en el panel de erplora.com: la bandeja, sus ajustes y sus plantillas son del Hub.
- No guarda los archivos de los clientes ni el texto de lo que envía el negocio.
- No deja cambiar a mano el negocio de un número ni activarlo: solo la ventana de Meta conecta un número.
- No da de baja el número en Meta al desconectarlo: solo quita la app de ERPlora de su cuenta; el número sigue siendo
  del negocio en Meta.
- No guarda la muestra de la cabecera de una plantilla: la recibe del Hub en cada envío a revisión y solo la sube a Meta.
