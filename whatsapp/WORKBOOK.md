# Workbook — WhatsApp (whatsapp)
Prefijo: WHATSAPP
Alcance MVP: fase 1 (la cuenta de WhatsApp Business de cada negocio en erplora.com: su número, los avisos de Meta, los envíos, el cupo del mes y las plantillas, al servicio de la bandeja del Hub)
Estado de la app: en uso (conectar y desconectar el número esperan a que el Hub lo pida)

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
- Los permisos de Meta se cifran con la clave del entorno; cambiarla deja de abrir los guardados, salvo que la
  anterior se deje como clave previa mientras se vuelve a conectar.
- No hay entorno de pruebas de Meta en desarrollo: en las pruebas, las respuestas de Meta salen de su
  documentación.

## Pantallas

### Correo «Vuelve a conectar WhatsApp»
Lo recibe el propietario del negocio, en su idioma, cuando Meta no deja renovar el permiso. Asunto «Hay que
actuar: vuelve a conectar WhatsApp (número)»; dice que el permiso está a punto de caducar, que hasta reconectar
los mensajes de los clientes no llegarán al Hub, y «Es un minuto: entra en tu Hub, ve a WhatsApp y vuelve a
conectar tu número», con el enlace al Hub.

### Admin: Números de WhatsApp
Admin de erplora.com, solo para el personal de ERPlora. Columnas: número, negocio, identificador del número en
Meta, cuenta de WhatsApp Business, activo, desde la app WhatsApp Business, permiso de Meta («Guardado», «Caducado»
o «Falta»), caducidad del permiso, hay que reconectar y fecha de conexión. Filtros por activo, app WhatsApp
Business y hay que reconectar; búsqueda por número, identificadores y negocio. Acciones «Desconectar el número» y
«Volver a leer las plantillas de Meta».

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
| Vacío | En el admin, «0 números de WhatsApp» y la lista vacía. |
| Error | Un correo que no sale se reintenta en la renovación siguiente; en el admin, cada acción dice qué hizo y qué no («Ahora no se ha podido leer Meta: las plantillas siguen como estaban»). |
| Sin configurar | WhatsApp sin la app de Meta: el Hub no ofrece conectar y Meta no puede entregar sus avisos. |
| Sin permiso | El admin no se abre sin el papel; el grupo de soporte solo mira, sin acciones. Un adjunto de otro negocio dice «no disponible». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| WHATSAPP-F01 | Conectar el número de WhatsApp del negocio | parcial |
| WHATSAPP-F02 | Desconectar el número | parcial |
| WHATSAPP-F03 | Decir al Hub qué número tiene el negocio y si hay que reconectarlo | hecho |
| WHATSAPP-F04 | Guardar el número de cada negocio con su permiso de Meta cifrado | hecho |
| WHATSAPP-F05 | Llevar la cuenta de los mensajes del mes y parar al llegar al tope del plan | hecho |
| WHATSAPP-F06 | Enviar un WhatsApp en nombre del negocio | hecho |
| WHATSAPP-F07 | Recibir los avisos de Meta y entregarlos al Hub | hecho |
| WHATSAPP-F08 | Ver los números de WhatsApp en el admin | hecho |
| WHATSAPP-F09 | Mover un número al negocio que lo conecta | hecho |
| WHATSAPP-F10 | Hablar con Meta sin dejar ver el permiso del negocio | hecho |
| WHATSAPP-F11 | Dar al Hub lo que necesita para abrir la ventana de Meta | parcial |
| WHATSAPP-F12 | Renovar el permiso de Meta antes de que caduque y avisar si no se puede | hecho |
| WHATSAPP-F13 | Confirmar a Meta que la dirección de los avisos es nuestra | hecho |
| WHATSAPP-F14 | Olvidar los mensajes que el Hub ya recogió | hecho |
| WHATSAPP-F15 | Registrar en Meta una plantilla nueva o editada | hecho |
| WHATSAPP-F16 | Subir a Meta la muestra de la cabecera de una plantilla | parcial |
| WHATSAPP-F17 | Borrar una plantilla en Meta | hecho |
| WHATSAPP-F18 | Lo que puede hacer el personal de ERPlora | hecho |

### WHATSAPP-F01 Conectar el número de WhatsApp del negocio
<!-- origen: fi:saas/auth-services#conectar-numero-whatsapp-embedded-signup-oauth -->
Estado: parcial — erplora.com ya conecta el número que le llega de la ventana de Meta, pero el Hub todavía no abre esa ventana: su botón lleva a erplora.com, que no tiene pantalla de WhatsApp
Actor: propietario, administrador
Pantalla: Bandeja de WhatsApp › Ajustes (en el Hub)
Pasos:
1. En los ajustes de la bandeja, pulsa «Conectar WhatsApp»: se abre la ventana de Meta, se entra con Facebook, se elige o se escribe el número y, si ya se usa la app WhatsApp Business del móvil, se escanea el código con el móvil.
2. Al cerrar la ventana, el Hub pasa a erplora.com lo que Meta le dio; erplora.com consigue el permiso del negocio, comprueba que el número elegido está en esa cuenta, suscribe la app de ERPlora a la cuenta y registra el número (o, si viene de la app del móvil, pide a Meta los contactos y el historial sin registrarlo).
3. «Tu número» pasa a «Conectado» con el número y el nombre del negocio en WhatsApp.
Entra: lo que la ventana de Meta da al Hub: un código de un solo uso, la cuenta de WhatsApp Business, el número elegido y el portfolio.
Sale: el número activo del negocio con su permiso y su PIN cifrados; el Hub lo sabe por su foto de estado (`whatsapp.number.connected`).
Si falla: si Meta rechaza un paso (el código caducó, el PIN no coincide, la suscripción no se acepta) no se guarda nada y se dice el motivo de Meta; si el número elegido no está en la cuenta, o la cuenta tiene varios y no se eligió ninguno, no se conecta otro: se dice que se elija; si Meta no contesta, «inténtalo de nuevo»; sin la app de Meta configurada, WhatsApp no está disponible. Una demo no puede conectar ningún número. Si Meta no da el historial, el número queda conectado igual.
Implicados: bandeja de WhatsApp del Hub (ajustes)

### WHATSAPP-F02 Desconectar el número
<!-- origen: fi:saas/auth-services#desconectar-numero -->
Estado: parcial — erplora.com ya desconecta (y el personal puede hacerlo desde el admin), pero el Hub todavía no lo pide desde sus ajustes
Actor: propietario, administrador
Pantalla: Bandeja de WhatsApp › Ajustes (en el Hub)
Pasos:
1. En los ajustes de la bandeja, pulsa «Desconectar» y confirma.
2. erplora.com deja de usar el número: olvida el permiso de Meta, quita la app de ERPlora de esa cuenta si ningún otro número conectado la usa y conserva el PIN para volver a registrarlo.
3. «Tu número» pasa a «Sin conectar»; las conversaciones del Hub no se tocan.
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
1. Cada vez que cambia algo del WhatsApp del negocio (el número, el consumo del mes, una plantilla o el veredicto de Meta sobre ella), erplora.com sube la versión de la foto de estado del negocio y se la manda al Hub.
2. La foto dice si el número está «Conectado», «Sin conectar» o «Hay que reconectar», el número y el nombre en WhatsApp, el cupo y lo gastado este mes, y las plantillas con lo que dice Meta de cada una.
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
Si falla: un permiso que ya no se puede descifrar (la clave cambió) se lee como que falta y el número se trata como «sin conectar»; queda escrito como error para el equipo.
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
3. Lo que Meta diga después (entregado, leído, fallido) llega a la bandeja como su estado.
Entra: a quién, el texto o la plantilla con sus variables, y la clave del envío.
Sale: el mensaje enviado por WhatsApp; la clave anotada para no enviarlo dos veces (`whatsapp.message.recorded`).
Si falla: fuera de las 24 horas desde el último mensaje del cliente, «solo se puede enviar una plantilla»; un cliente que bloqueó al negocio, una plantilla no aprobada o un número sin conectar dicen su motivo y no gastan cupo; si Meta no contesta, no se sabe si salió: el Hub reintenta con la misma clave y erplora.com nunca lo envía dos veces.
Implicados: bandeja de WhatsApp del Hub

### WHATSAPP-F07 Recibir los avisos de Meta y entregarlos al Hub
<!-- origen: fi:saas/auth-services#webhook-de-whatsapp-meta -->
Estado: hecho
Actor: sistema
Pantalla: Bandeja de WhatsApp (en el Hub)
Pasos:
1. Un cliente escribe al número del negocio (o el dueño contesta desde el móvil, o llega el historial al conectar): Meta lo cuenta a erplora.com, que comprueba que el aviso es de Meta y lo guarda para el negocio de ese número.
2. erplora.com lo entrega al Hub en el momento; si el Hub no está o no tiene la bandeja encendida, lo vuelve a intentar con una espera que crece hasta una hora, cada minuto mientras le quede algo.
3. Una foto, una nota de voz o un documento llegan como un enlace de erplora.com que solo abre una persona del negocio con su sesión; el archivo viene de Meta en ese momento y no se guarda.
4. El estado de un mensaje del negocio («Entregado», «Leído», «No entregado») llega a la bandeja: el de uno enviado desde el Hub, cuando erplora.com sabe cuál es; el de una respuesta del dueño desde el móvil, después de esa respuesta.
Entra: los avisos de Meta: mensajes, ecos del móvil, historial, estados de entrega y veredictos de plantillas.
Sale: el mensaje o el estado en la bandeja del Hub (`whatsapp.webhook.ingested`, `whatsapp.delivery.recorded`).
Si falla: un aviso sin la firma de Meta se rechaza y no se guarda; uno de un número que nadie tiene conectado se descarta; el estado de un mensaje que el Hub no tiene se espera diez minutos y se descarta; si el Hub dice que el mensaje no vale, no se reintenta y queda a la vista del personal; un adjunto de otro negocio, o que Meta ya no tiene, dice «no disponible».
Implicados: bandeja de WhatsApp del Hub

### WHATSAPP-F08 Ver los números de WhatsApp en el admin
<!-- origen: fi:saas/django-admin#admin-whatsappphonemapping -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin: Números de WhatsApp
Pasos:
1. Abre «Números de WhatsApp» en el admin de erplora.com.
2. Ve cada número con su negocio, sus identificadores de Meta, si está activo, si viene de la app del móvil, si su permiso está «Guardado», «Caducado» o «Falta», cuándo caduca y si hay que reconectarlo; filtra por «hay que reconectar» o busca por número o negocio.
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
Estado: parcial — erplora.com ya lo da, pero el Hub todavía no lo pide ni abre la ventana de Meta
Actor: sistema
Pantalla: Bandeja de WhatsApp › Ajustes (en el Hub)
Pasos:
1. Al pintar «Tu número», el Hub pregunta a erplora.com.
2. erplora.com contesta si WhatsApp está configurado y, si lo está, el identificador de la app de Meta, el de la configuración del alta embebida y la versión de Meta que usa.
3. Sin la app configurada contesta «no configurado» con los identificadores vacíos, y el Hub no enseña «Conectar WhatsApp».
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
Si falla: si Meta no contesta y queda margen, se reintenta al día siguiente; un correo que no sale se reintenta en la vuelta siguiente; un número que falla no para a los demás; sin la app de Meta configurada, la tarea termina con error para el equipo.
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
1. En el Hub, se escribe la plantilla (nombre, idioma, categoría, cabecera, texto con sus variables y un ejemplo de cada una, pie y botones) y se pulsa «Guardar».
2. erplora.com comprueba las reglas de Meta antes de llamarla: nombre en minúsculas, cifras y guiones bajos, variables seguidas o con nombre, un ejemplo por variable, como mucho 10 botones con sus límites.
3. La registra en Meta (o, si Meta ya la tenía, edita la suya) y el Hub la enseña «En revisión»; el veredicto de Meta llega solo después.
Entra: la plantilla tal como se escribió y la clave del guardado.
Sale: la plantilla en Meta y su copia en erplora.com, que viaja al Hub en la foto de estado (`whatsapp.template.registered`).
Si falla: una regla rota dice cuál; Meta rechazándola da su motivo para la persona; si Meta no contesta o pide esperar, no se guarda nada y se puede reintentar; el mismo guardado repetido no se registra dos veces.
Implicados: bandeja de WhatsApp del Hub

### WHATSAPP-F16 Subir a Meta la muestra de la cabecera de una plantilla
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F18 -->
Estado: parcial — el Hub no ofrece cabeceras con foto, vídeo o documento (se hacen en WhatsApp Manager), así que no hay muestra que subir; las plantillas con esa cabecera hechas en WhatsApp Manager sí se ven en el Hub
Actor: propietario, administrador
Pantalla: Bandeja de WhatsApp › Ajustes › Plantilla (en el Hub)
Pasos:
1. Una plantilla con cabecera de foto, vídeo o documento se crea en WhatsApp Manager de Meta.
2. erplora.com la trae con lo que dice Meta de ella y el Hub la enseña con su tipo de cabecera.
Entra: la plantilla tal como la tiene Meta.
Sale: su copia en erplora.com y en el Hub.
Si falla: si Meta no contesta, la lista se queda como estaba hasta la siguiente lectura.
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
Si falla: si Meta ya no la tiene, cuenta como borrada; si Meta la rechaza o no contesta, sigue viva y el Hub lo vuelve a pedir.
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
- **Contrato con el Hub**: las puertas 1–9 son las del WORKBOOK de `whatsapp_inbox` del Hub («Contrato con el SaaS»),
  que mandan y no se renombran. Este porte añade tres puertas, propuestas al Hub, con la misma firma de todo
  `/internal` (`X-Erplora-Timestamp` + `X-Erplora-Signature`, HMAC-SHA256 de `f"{timestamp}.{cuerpo}"` con
  `INTERNAL_SHARED_SECRET`, ±300 s):
  - **10** `POST /internal/whatsapp/config` `{"hub"}` → 200 `{"configured", "app_id", "config_id", "graph_version"}`
    (WHATSAPP-F11); 404 `hub_unknown`.
  - **11** `POST /internal/whatsapp/connect` `{"hub", "code", "event", "waba_id", "phone_number_id", "business_id"}`
    → 200 `{"connected": true, "phone_number", "display_name", "history_requested"}` (WHATSAPP-F01, F09); 409
    `whatsapp.meta_rejected | number_not_in_account | number_not_chosen`, 429 `whatsapp.meta_rate_limited`, 502
    `whatsapp.meta_no_token`, 503 `whatsapp.meta_unreachable | not_configured`, 404 `hub_unknown`, 422. Nada se
    guarda hasta que Meta aceptó todos los pasos.
  - **12** `POST /internal/whatsapp/disconnect` `{"hub"}` → 200 `{"disconnected": true|false}` (WHATSAPP-F02).
  El canal (puerta 3) no se usa desde el SaaS: la clave `whatsapp` de la foto (puerta 4) es la única fuente, con la
  versión de la foto y el reintento de `reconcile_hub_states`.
- Adjuntos: `GET /whatsapp/media/<id de la entrega>` (WHATSAPP-F07), con la sesión de erplora.com y miembro aceptado
  del negocio; lo que no es imagen, audio o vídeo se descarga con `Content-Disposition: attachment` y CSP `sandbox`.
  El Hub debe permitir el origen de erplora.com en `img-src` y `media-src` (su «Contrato con `base`»).
- Tareas programadas (ECS, `saas-cron`): `whatsapp_deliver` cada minuto (WHATSAPP-F07), `whatsapp_refresh_tokens`
  (WHATSAPP-F12) y `whatsapp_purge` (WHATSAPP-F14) una vez al día; programarlas, y los secretos `WHATSAPP_*` y
  `FERNET_KEY`, es del repo de infraestructura.
- Los tests de cada flujo citan su clave del registro (`WHATSAPP-Gnn`) en el nombre del fichero de test o en su
  docstring; `promote` en el registro la convierte en `WHATSAPP-Fnn` con el mismo número.
- Contradicción escrita, sin resolver: `PLAN-SAAS.md` y `PLAN-HUB.md` dicen que WhatsApp «sale del SaaS» y que el Hub
  llama a Meta directamente; el encargo del 2026-10-15 lo dejó en el SaaS, y esta app lo sigue. Falta la ronda.
- Contradicción escrita, sin resolver: el plan con `whatsapp_messages_per_month = 0` no envía ninguno (el SaaS
  rechaza con `whatsapp.cap_reached`), pero el Hub lee `monthly_limit = 0` como «Sin límite».
- El WORKBOOK del Hub (WHATSAPP_INBOX-F01) dice «se conecta en el panel de erplora.com», y `PLAN-SAAS.md` (bloque 12)
  dice que el panel no tiene pantalla de WhatsApp; este porte sigue al plan: la ventana de Meta la abre el Hub con
  las puertas 10 y 11.

## Lo que NO hace, a propósito

- No tiene pantalla en el panel de erplora.com: la bandeja, sus ajustes y sus plantillas son del Hub.
- No guarda los archivos de los clientes ni el texto de lo que envía el negocio.
- No deja cambiar a mano el negocio de un número ni activarlo: solo la ventana de Meta conecta un número.
- No da de baja el número en Meta al desconectarlo: solo quita la app de ERPlora de su cuenta; el número sigue siendo
  del negocio en Meta.
- No sube muestras de cabecera de plantillas: las plantillas con foto, vídeo o documento se hacen en WhatsApp Manager.
