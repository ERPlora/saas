# Workbook — Asistente de IA (assistant)
Prefijo: ASSISTANT
Alcance MVP: fase 1 (la pasarela de IA de erplora.com: los proveedores que paga ERPlora, sus claves cifradas, sus modelos y qué modelo contesta; el turno del asistente de cada negocio con sus herramientas y sus adjuntos, el cupo de mensajes de su plan, las huellas de su índice, el dictado y la lectura en voz alta, las denuncias de una respuesta y lo que gasta cada negocio; el asistente del panel de erplora.com para cada cuenta, con las herramientas del panel, su dictado y su propio cupo)
Estado de la app: completa (2026-11-03)

> Manual de uso y especificación de la app `assistant` del SaaS (erplora.com). Cuenta lo que hace el personal de
> ERPlora para que el asistente de IA conteste (dar de alta un proveedor de modelos y su clave, elegir sus modelos,
> decidir qué modelo contesta y probarlo antes, ver lo que gasta cada negocio) y lo que hace erplora.com cada vez que
> el asistente de un negocio le pide algo: contestar un turno, leer sus adjuntos, contar sus mensajes, buscar en la
> documentación de ERPlora, transcribir un dictado o leer una respuesta en voz alta. También contesta al asistente del
> propio panel de erplora.com, el de cada cuenta: sus negocios, lo que paga a ERPlora y su cuenta. No se publica en la
> tienda: es la referencia del equipo y de la QA. Ningún cliente ve las pantallas del admin; la cuenta ve el chat del
> panel (ASSISTANT-F25), y el asistente que usa el negocio vive en el Hub.

## Para qué sirve y para quién

El Hub nunca habla con el proveedor de un modelo de IA: habla con erplora.com, que guarda la clave del proveedor,
decide qué modelo contesta y lo llama. Así la clave no sale nunca de erplora.com y el gasto de IA se controla en un
solo sitio.

- La clave de cada proveedor se guarda cifrada; se escribe una vez y nunca se vuelve a enseñar: solo sus cuatro
  últimos caracteres, para reconocerla.
- Hay un modelo que contesta y, si falla su proveedor, uno de reserva.
- Antes de poner un modelo a contestar se puede probar desde el admin, con lo que tarda, lo que consume y lo que
  cuesta.
- Cada mensaje que una persona escribe al asistente gasta uno del cupo mensual del plan de su negocio (una demo tiene
  10 en toda su vida); el resto (las herramientas, los adjuntos, las huellas, la voz) no gasta mensajes, pero se mide.
- erplora.com usa la conversación para llamar al modelo y la olvida: no la guarda en ningún sitio.

Quién la usa:

- El **personal de ERPlora**, en el admin de erplora.com, con los permisos de la pasarela de IA. El grupo de
  soporte no los tiene: las claves son gasto de ERPlora.
- El **asistente del Hub** de cada negocio (y el de cada demo): manda a erplora.com cada turno, sus adjuntos, las
  preguntas de cómo se hace algo en ERPlora (ASSISTANT-F28) y los dictados, y enseña
  a la persona lo que le queda del cupo.
- El **personal de ERPlora**, en «Registros de uso del asistente», ve lo que gasta cada negocio y lo que cuesta.
- La **persona con cuenta** en erplora.com, en el panel: abre el asistente con el botón «Asistente» de la barra y le
  pregunta o le dicta (ASSISTANT-F21) sobre sus negocios, lo que paga y su cuenta (ASSISTANT-F25), con 30 mensajes al
  mes (ASSISTANT-F26).

## Referencia adoptada

- **Pasarelas de IA** (OpenRouter, Portkey, Cloudflare AI Gateway, Vercel AI Gateway, el router de LiteLLM): un
  modelo principal y otro de reserva si el proveedor falla; las claves de los proveedores en la pasarela, nunca en
  el cliente.
- **Las consolas de los proveedores** (OpenAI, Anthropic, Google AI Studio, DeepSeek): la clave se enseña una vez
  al crearla y después solo su final; la lista de modelos sale de la API del propio proveedor
  (https://platform.openai.com/docs/models, https://docs.anthropic.com/en/docs/about-claude/models).
- **El producto viejo de ERPlora** (`apps/assistant` del SaaS): proveedores con su clave y sus modelos en una sola
  ficha, la política de qué modelo contesta y el probador con coste y latencia; el turno del Hub por la pasarela, con
  el cupo por negocio, los adjuntos, las huellas y la voz.
- **Asistentes con cupo** (ChatGPT, Claude, Gemini, Copilot de Microsoft 365, Shopify Magic): un número de mensajes
  por periodo según el plan, que vuelve al empezar el siguiente; al agotarse se avisa y se propone subir de plan; un
  mensaje que falla antes de contestar no se cobra. Las herramientas que no son del negocio las ejecuta el servidor,
  nunca el dispositivo; la voz es dictado a texto y lectura en voz alta del mismo
  proveedor (https://platform.openai.com/docs/guides/speech-to-text, https://platform.openai.com/docs/guides/text-to-speech).
- **Avisos de cupo por correo** (ASSISTANT-F29): un correo al acercarse al límite y otro al llegar, también en los productos
  que ya lo enseñan en pantalla. GitHub, al 90 % y al 100 % de lo incluido en el plan
  (https://docs.github.com/en/billing/concepts/budgets-and-alerts); HubSpot, al 75 % y al 100 % de su límite mensual
  de IA (https://knowledge.hubspot.com/records/understand-communication-analysis-limit-notifications); Tern, al 75, 90
  y 100 % de su cupo de IA por persona (https://help.tern.travel/en/articles/15303956-ai-usage-limits); Eraser
  (https://docs.eraser.io/docs/usage-based-pricing) y Outfunnel
  (https://support.outfunnel.com/en/articles/3245437-what-happens-if-i-exceed-my-monthly-active-contacts-plan-limit),
  al 80 % y al 100 %; Vercel, «Usage increased» y «Usage limit reached» (https://vercel.com/docs/notifications); Userflow,
  al 90 % y al parar por el límite (https://help.userflow.com/docs/managing-the-ai-assistant-usage-notifications). La
  excepción es Odoo, con una sola alerta de umbral y destinatarios configurables
  (https://www.odoo.com/documentation/master/applications/essentials/in_app_purchase.html). Apagarlos: el mercado está
  partido (GitHub y Vercel lo dejan; en Userflow no hay nada que configurar); aquí no se apagan por simples, son dos
  correos al mes como mucho.
- **Cambiar de plan, en su pantalla y no en el chat** (ASSISTANT-F25): los asistentes de los productos de gestión
  trabajan con los datos del negocio y ninguno cuenta entre lo que hace cambiar la suscripción. Square AI no toca la
  cuenta (https://squareup.com/help/gb/en/article/8516-use-ask-ai-to-get-insights-about-your-business); Shopify Sidekick
  (https://help.shopify.com/en/manual/shopify-admin/productivity-tools/sidekick), Toast IQ
  (https://support.toasttab.com/en/article/Toast-IQ-Overview) y Lightspeed AI
  (https://www.lightspeedhq.com/news/lightspeed-ai-expands-from-insights-to-action-with-new-agentic-capabilities-for-retail/)
  piden aprobar cada cambio, y el plan no sale en sus manuales. El plan se cambia en su pantalla, que enseña antes lo
  que se cobra: Shopify (https://help.shopify.com/en/manual/your-account/manage-orgs-and-stores/manage-pricing-plan/change-plan),
  Microsoft 365 (https://learn.microsoft.com/microsoft-365/commerce/subscriptions/upgrade-to-different-plan), QuickBooks
  (https://quickbooks.intuit.com/learn-support/en-us/help-articles/downgrade-your-quickbooks-online-plan/00/290898) y
  WooCommerce Subscriptions (https://woocommerce.com/document/subscriptions/switching-guide/).

## Antes de empezar

- erplora.com necesita su clave de cifrado de credenciales en el entorno; sin ella no se puede guardar ninguna
  clave de proveedor y la ficha lo dice al guardar.
- Cada proveedor necesita una clave activa que se pueda leer para que sus modelos contesten o se puedan probar.
- Los precios por millón de palabras-unidad (tokens) de cada modelo los escribe el personal: las API de los
  proveedores no los dan. Sin precio, la prueba dice el consumo y un coste de cero.
- Las huellas del índice y el dictado los hace el proveedor de servicios (OpenAI): tiene que estar dado de alta,
  activado y con su clave.
- La lectura en voz alta la hace el proveedor de voz (Azure AI Speech): tiene que estar dado de alta, activado y con su
  clave; su dirección es la de su región (Suecia Central si no se escribe otra). Sin él, el Hub y el panel leen con la
  voz del dispositivo.
- El cupo de mensajes de cada plan («Mensajes del asistente de IA al mes») se escribe en el admin de «Planes».

## Pantallas

### Admin: Proveedores de IA
Lista de los proveedores con su API, si está activado y el estado de su clave: «…» y los cuatro últimos caracteres,
«Sin clave» o «Ilegible: vuelve a escribir la clave». La ficha de cada proveedor tiene sus claves dentro: etiqueta,
el campo «Clave» (se escribe una vez, nunca se enseña; vacío deja la que había), si está activa, cuándo se cambió y
quién; y sus modelos, con su precio de entrada y de salida, su contexto y si están disponibles. Arriba, «Elegir
modelos del proveedor».

### Admin: Elegir modelos del proveedor
La lista de modelos de conversación que da la API del proveedor, con una casilla «Se queda» (marcada en los que ya
tiene), su nombre y su contexto, y los botones «Guardar la elección» y «Volver al proveedor».

### Admin: Modelos de IA
Todos los modelos de todos los proveedores, con su precio, su contexto y si están disponibles, para corregirlos.

### Admin: Modelo que contesta
Una sola página (su lista la abre): «Modelo que contesta» y «Modelo de reserva», cada uno con los modelos que pueden
contestar (disponibles y de un proveedor activado), quién hizo el último cambio y «Guardar». Quien solo puede mirar la
ve sin poder cambiarla. Arriba, «Probar un modelo» (solo para quien puede cambiarla).

### Admin: Probar un modelo
«Modelo» (los que pueden contestar), «Mensaje», «Herramientas» (opcional, una lista como la del ejemplo) y «Enviar». Debajo,
«Respuesta»: el modelo que contesta, el texto según llega, las herramientas que pide y una tabla con «Tokens de
entrada», «Tokens de salida», «Tiempo» y «Coste» (en dólares).

### Admin: Registros de uso del asistente
Una fila por negocio y mes (una demo, una sola en toda su vida; una cuenta, una por mes con el asistente del panel)
con «Negocio, demo o cuenta» (de una cuenta, su correo), «Mes», «Mensajes», «Tokens de entrada», «Tokens de salida»,
«Tokens de huellas», «Dictados», «Caracteres leídos en voz alta» y «Coste (USD)». Arriba, el buscador (por nombre o
dirección del negocio, por la dirección de la demo o por el correo de la cuenta) y los meses; a la derecha, el filtro
«Por tipo» («Negocios», «Demos» o «Cuentas») y el del mes. Cada fila se abre para verla entera, sin poder cambiarla.

### Panel: Asistente
En todas las pantallas del panel de erplora.com con la sesión abierta, al final de la barra de arriba, el botón
«Asistente» (las chispas), marcado mientras el panel está abierto. El panel se abre a la derecha: desde 768 px de ancho
se acopla junto a la pantalla, que se estrecha y sigue funcionando; en el móvil la cubre sobre un velo. Arriba,
«Asistente», «Voz» (la elección de la voz que lee las respuestas: las dos de su idioma, Ximena y Tristan o Ava y
Andrew, y «Voz del dispositivo»; la primera, si no se elige otra), «Nueva conversación» (cuando ya hay una) y ×
(«Cerrar»); en medio, la conversación: sin ella, «Pregúntame
por tus negocios, tus facturas o tu cuenta.» y tres atajos («¿Qué negocios tengo?», «¿Cuánto pago al mes?» y «¿Cómo
creo un negocio?»); con ella, las burbujas de la persona y las respuestas, con «Ir a …» para las pantallas del panel
que nombran, lo hecho bajo cada cambio («Hecho: …», «No se hizo, cancelado: …»), «Leer en voz alta» (con la voz
elegida; si la de erplora.com no está disponible, con la del propio dispositivo) y «Denunciar un problema». Abajo, el aviso de cuántos mensajes quedan (desde el 80 % del mes), el clip de
adjuntar, el micrófono «Dictar por voz» («Detener la grabación» mientras graba; gira mientras transcribe) y la caja
«Escribe un mensaje…» con «Enviar» («Parar» mientras contesta). Un cambio que pide el modelo abre
encima la tarjeta «¿Ejecutar esta acción?» con «Cancelar» y «Ejecutar»; crear, borrar o cambiar la dirección de un
negocio, ofrecerlo a otro o cancelar su plan piden además escribir «CONFIRMAR».

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | La carga normal de una página del admin; al probar un modelo, «Enviando…» y el botón «Enviar» apagado hasta que acaba («Hecho.»). En el asistente del panel, la burbuja de «El asistente está escribiendo» hasta la primera palabra y «Parar» en lugar de «Enviar». |
| Vacío | «0 proveedores de IA» y la lista vacía; en «Registros de uso del asistente», «0 registros de uso del asistente» hasta el primer mensaje de un negocio; un proveedor sin clave dice «Sin clave»; sin modelos que puedan contestar, «Todavía no puede contestar ningún modelo: añade un proveedor con su clave y elige sus modelos.» En el asistente del panel, «Pregúntame por tus negocios, tus facturas o tu cuenta.» con sus tres atajos. |
| Error | En «Elegir modelos del proveedor», el motivo en rojo: «Este proveedor no tiene ninguna clave activa: añade una en su ficha y vuelve a intentarlo.», «El proveedor no ha dado sus modelos: …» o «El proveedor no tiene modelos de conversación en su lista.»; en las fichas, el error en rojo junto al campo: «Usa una dirección https: la clave del proveedor viaja a ella.», «Escribe la clave del proveedor.», «La clave de cifrado de las credenciales no está configurada: no se puede guardar ninguna clave de proveedor.»; al probar un modelo, en rojo: «El modelo no ha contestado: …», «Demasiadas pruebas en un minuto: espera un momento y vuelve a intentarlo.» o «No se ha podido enviar la prueba: revisa la conexión y vuelve a intentarlo.». En el asistente del panel, bajo la pregunta: «El asistente no está disponible ahora mismo. Vuelve a intentarlo en unos minutos.» con «Reintentar»; con el mes gastado, «Has usado todos los mensajes del asistente de este mes (30 de 30). Se renuevan el 1 de …» y «Cada negocio tiene su propio asistente, con sus propios mensajes: abre el negocio para seguir preguntando allí.», sin «Mejorar plan»; sin conexión, en el pie, «Sin conexión: puedes escribir y enviar cuando vuelva.»; bajo la caja, lo que impide un dictado: «El acceso al micrófono está denegado. Permítelo en tu navegador para dictar.», «No se ha oído nada. Inténtalo de nuevo más cerca del micrófono.», «La grabación es demasiado larga: dicta un mensaje más corto.» o «No se ha podido transcribir el audio. Inténtalo de nuevo.» |
| Sin permiso | Sin los permisos de la pasarela, el admin contesta que no tiene permiso; quien solo puede mirar ve las fichas sin el campo «Clave». «Registros de uso del asistente» no se pueden cambiar ni borrar, ni siquiera un superusuario. Sin sesión, el panel lleva a entrar y no hay botón «Asistente»; una sesión que termina a media conversación dice «Tu sesión ha terminado. Vuelve a entrar para seguir hablando.» con «Volver a entrar». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| ASSISTANT-F01 | Dar de alta un proveedor de IA | hecho |
| ASSISTANT-F02 | Guardar la clave de un proveedor sin que se vea | hecho |
| ASSISTANT-F03 | Hablar con cada proveedor en su propia API | hecho |
| ASSISTANT-F04 | Elegir los modelos de un proveedor | hecho |
| ASSISTANT-F05 | Elegir qué modelo contesta | hecho |
| ASSISTANT-F06 | Elegir proveedor y modelo de cada turno | hecho |
| ASSISTANT-F07 | Probar un modelo antes de ponerlo a contestar | hecho |
| ASSISTANT-F08 | Ver quién cambió la configuración de la IA | hecho |
| ASSISTANT-F09 | Cargar las claves de los proveedores desde el entorno | hecho |
| ASSISTANT-F10 | Cambiar la clave de cifrado sin perder ninguna credencial | hecho |
| ASSISTANT-F11 | Reconocer quién llama y de qué negocio es | hecho |
| ASSISTANT-F12 | Contestar un turno del asistente en directo | hecho |
| ASSISTANT-F13 | Contestar el mismo turno de una vez | hecho |
| ASSISTANT-F14 | Usar las herramientas de erplora.com y las del negocio | descartado |
| ASSISTANT-F15 | Rechazar un turno con su motivo | hecho |
| ASSISTANT-F16 | Frenar a un negocio que pide demasiado | hecho |
| ASSISTANT-F17 | No guardar la conversación | hecho |
| ASSISTANT-F18 | Contar los mensajes del plan de cada negocio | hecho |
| ASSISTANT-F19 | Leer los adjuntos de una pregunta | hecho |
| ASSISTANT-F20 | Calcular la huella de unos textos para el índice del negocio | hecho |
| ASSISTANT-F21 | Transcribir un dictado de voz | hecho |
| ASSISTANT-F22 | Leer una respuesta en voz alta | hecho |
| ASSISTANT-F23 | Recibir la denuncia de una respuesta del asistente | hecho |
| ASSISTANT-F24 | Ver lo que ha gastado un negocio del asistente | hecho |
| ASSISTANT-F25 | Contestar al asistente del panel de una cuenta | hecho |
| ASSISTANT-F26 | Contar los mensajes de una cuenta con el asistente del panel | hecho |
| ASSISTANT-F27 | Buscar en la documentación desde el panel | hecho |
| ASSISTANT-F28 | Buscar en la documentación desde el Hub | hecho |
| ASSISTANT-F29 | Avisar por correo a una cuenta de que se le acaban los mensajes del asistente del panel | hecho |

### ASSISTANT-F01 Dar de alta un proveedor de IA
<!-- origen: fi:saas/support/auth-services#modelo-aiprovider fi:saas/django-admin#admin-aiprovider old-saas:SAAS_ASSISTANT-F22 -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin: Proveedores de IA
Pasos:
1. En «Proveedores de IA», pulsa «Añadir proveedor de IA».
2. Escribe su nombre y un identificador corto (por ejemplo «openai»), elige la API que habla (OpenAI, Anthropic, Google Gemini o DeepSeek; un proveedor compatible con la de OpenAI es «OpenAI» con su dirección) y, si no es la del propio proveedor, su dirección.
3. Lo deja activado o apagado y guarda.
Entra: nombre, identificador, API, dirección, activado, notas.
Sale: el proveedor en la lista, listo para su clave y sus modelos.
Si falla: una dirección que no es https se rechaza con «Usa una dirección https: la clave del proveedor viaja a ella.» (solo se admite sin https una dirección de la propia máquina); un identificador repetido se rechaza; sin permiso, el admin no deja entrar.
Implicados: ninguno

### ASSISTANT-F02 Guardar la clave de un proveedor sin que se vea
<!-- origen: fi:saas/support/auth-services#modelo-aiprovidercredential fi:saas/django-admin#admin-aiprovidercredential -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin: Proveedores de IA
Pasos:
1. En la ficha del proveedor, añade una clave: etiqueta (por defecto «default»), la clave en el campo «Clave» y si está activa.
2. Guarda: la clave queda cifrada y la ficha y la lista solo enseñan «…» y sus cuatro últimos caracteres.
3. Para cambiarla, escribe la nueva en «Clave» y guarda: queda la fecha del cambio y quién la hizo. Dejar «Clave» vacía guarda lo demás sin tocar la clave.
4. Para quitarla, marca «Eliminar» en su fila y guarda.
Entra: etiqueta, clave, activa.
Sale: la clave cifrada con su final a la vista (`assistant.credential.saved`, con si se cambió la clave; al quitarla, `assistant.credential.deleted`). Ni la ficha, ni la lista, ni los avisos, ni el registro llevan nunca la clave.
Si falla: una clave nueva sin clave se rechaza con «Escribe la clave del proveedor.»; una etiqueta repetida en el mismo proveedor se rechaza; sin la clave de cifrado de erplora.com, «La clave de cifrado de las credenciales no está configurada: no se puede guardar ninguna clave de proveedor.» y no se guarda nada; una clave que ya no se puede leer sale como «Ilegible: vuelve a escribir la clave» y guardar la ficha sin escribir otra no la toca; quien solo puede mirar no ve el campo «Clave»; sin permiso, el admin no deja entrar.
Implicados: ninguno

### ASSISTANT-F03 Hablar con cada proveedor en su propia API
<!-- origen: fi:saas/support/auth-services#service-providers-base-provider-toolspec-turnrequest-providerevent fi:saas/support/auth-services#service-providers-factory-get_provider fi:saas/support/auth-services#service-providers-anthropic_provider-anthropicprovider fi:saas/support/auth-services#service-providers-openai_provider-openaiprovider fi:saas/support/auth-services#service-providers-gemini_provider-geminiprovider fi:saas/support/auth-services#service-providers-deepseek_provider-deepseekprovider -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cuando hay que llamar a un modelo (un turno del asistente, una prueba del admin o la lista de modelos de un proveedor), erplora.com prepara la llamada en la forma que pide la API del proveedor: OpenAI (y los compatibles con ella), Anthropic, Google Gemini o DeepSeek, con la clave del proveedor y su dirección.
2. Manda la conversación con sus instrucciones, sus imágenes, las herramientas que se ofrecen (una sola por respuesta) y el máximo de salida, y recibe la respuesta en directo, trozo a trozo.
3. Traduce lo que contesta cada proveedor a lo mismo para todos: el texto según llega, cada herramienta que el modelo pide con sus datos completos, el consumo de entrada y de salida y cómo terminó (normal, porque pidió una herramienta, por largo o por el filtro de contenido).
4. Para la lista de modelos, pide al proveedor sus modelos de conversación, página a página, y deja fuera los que no conversan (voz, imágenes, huellas de texto).
Entra: la API, la dirección y la clave del proveedor; el modelo, la conversación, las instrucciones y las herramientas.
Sale: el texto, las herramientas pedidas, el consumo y el final del turno, iguales sea cual sea el proveedor; o la lista de modelos de conversación.
Si falla: si el proveedor rechaza la clave o la petición, el turno termina con su motivo y se marca como un fallo que no se arregla repitiendo; si no contesta, tarda demasiado, va saturado o limita el ritmo, termina con un fallo que otro intento puede arreglar (para pasar al modelo de reserva); el motivo nunca lleva la clave. Si erplora.com no puede cargar sus certificados de confianza (`SSL_CERT_FILE` nombra un fichero que no está o que no tiene ninguno), la llamada no llega a salir: termina con un fallo que no se arregla repitiendo, y su motivo y el registro del servidor nombran la variable y el fichero. Un proveedor sin clave o con una API desconocida no se llama.
Implicados: ASSISTANT-F04, ASSISTANT-F06, ASSISTANT-F07

### ASSISTANT-F04 Elegir los modelos de un proveedor
<!-- origen: fi:saas/support/auth-services#modelo-aimodel fi:saas/django-admin#admin-aimodel -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin: Proveedores de IA, Admin: Elegir modelos del proveedor, Admin: Modelos de IA
Pasos:
1. En la ficha del proveedor, pulsa «Elegir modelos del proveedor»: erplora.com pregunta a la API del proveedor, con su clave, qué modelos de conversación tiene.
2. Marca los que se quedan (ya salen marcados los que tiene) y pulsa «Guardar la elección».
3. Vuelve a la ficha con el resumen, por ejemplo «Local: 1 nuevos, 0 se quedan, 1 quitados, 0 en uso por el modelo que contesta.»: los marcados quedan disponibles y los no marcados se quitan, salvo los que usa el modelo que contesta, que se quedan.
4. En la ficha o en «Modelos de IA», escribe el precio de entrada y de salida de cada modelo (dólares por millón de tokens), corrige su nombre o su contexto, o lo apaga.
Entra: el proveedor con una clave activa; la elección de modelos; los precios.
Sale: los modelos del proveedor, exactamente los elegidos más los que están en uso (`assistant.model.selected`, con cuántos se crearon, se quedaron, se quitaron y se protegieron).
Si falla: sin clave activa que se pueda leer, «Este proveedor no tiene ninguna clave activa: añade una en su ficha y vuelve a intentarlo.» y no se pregunta nada al proveedor; si el proveedor rechaza la clave o no contesta, «El proveedor no ha dado sus modelos:» con su motivo; si no tiene modelos de conversación, «El proveedor no tiene modelos de conversación en su lista.»; sin permiso para ver proveedores y para añadir y quitar modelos, el admin no deja entrar; un modelo en uso por el modelo que contesta no se puede borrar.
Implicados: ASSISTANT-F03, ASSISTANT-F05

### ASSISTANT-F05 Elegir qué modelo contesta
<!-- origen: fi:saas/support/auth-services#modelo-airoutingpolicy fi:saas/django-admin#admin-airoutingpolicy-singleton-tester fi:saas/auth-services#routing-ai-configuracion-de-proveedores-modelos-admin old-saas:SAAS_ASSISTANT-F23 -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin: Modelo que contesta
Pasos:
1. Abre «Modelo que contesta» (desde la portada del asistente o su lista, que lleva directamente a la página).
2. Elige el «Modelo que contesta» y, si quiere, un «Modelo de reserva» distinto, entre los modelos disponibles de los proveedores activados.
3. Pulsa «Guardar»: «Se ha guardado el modelo que contesta.»; el turno siguiente del asistente ya usa esta elección y queda quién la cambió.
Entra: el modelo que contesta y el de reserva.
Sale: la elección de toda la plataforma (`assistant.policy.updated`, con los dos modelos).
Si falla: un modelo apagado, de un proveedor apagado o que ya no existe se rechaza con «Este modelo no puede contestar: está apagado, su proveedor está apagado o no existe.»; la reserva igual al primero, con «El modelo de reserva tiene que ser otro modelo.»; una reserva sin modelo que contesta, con «Elige el modelo que contesta antes que su reserva.»; si el modelo elegido se apaga después, la página avisa «El modelo que contesta está apagado o lo está su proveedor: elige otro.»; quien solo puede mirar no ve «Guardar» y, si lo intenta, no se guarda; sin permiso, el admin no deja entrar. Nadie añade ni borra esta elección, y un modelo en uso no se puede borrar.
Implicados: ASSISTANT-F04, ASSISTANT-F06

### ASSISTANT-F06 Elegir proveedor y modelo de cada turno
<!-- origen: old-saas:SAAS_ASSISTANT-F05 fi:saas/support/auth-services#signals-provider-cache-invalidation -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada turno del asistente lee de nuevo qué modelo contesta y cuál es su reserva, con la clave activa más reciente de cada proveedor que se puede abrir; así, una clave cambiada o otra elección valen ya en el turno siguiente, sin reiniciar nada.
2. Se salta el modelo apagado, el de un proveedor apagado y el de un proveedor sin clave usable; el turno empieza por el primero que queda y dice qué modelo contesta.
3. Si su proveedor falla antes de contestar nada (caído, saturado, limitando el ritmo o rechazando la clave), el turno pasa al modelo de reserva y avisa del cambio con su motivo; si ya había empezado a contestar, el turno termina con el fallo, porque la persona ya ha visto el principio de la respuesta.
4. Al probar un modelo desde el admin, el turno va solo a ese modelo, sin reserva.
Entra: el modelo que contesta y su reserva (o el modelo que se prueba) y las claves de sus proveedores.
Sale: el modelo que contesta el turno y, si su proveedor falla antes de contestar, el aviso del paso al modelo de reserva.
Si falla: sin modelo que contesta, «Todavía no contesta ningún modelo: elige uno en la página “Modelo que contesta”.»; si ninguno de los elegidos se puede usar, «Ningún modelo puede contestar: los proveedores de los modelos elegidos no tienen ninguna clave activa.»; un modelo que se prueba apagado, o de un proveedor apagado, «Este modelo está apagado o lo está su proveedor: enciéndelos para usarlo.»; si fallan todos, el turno termina con el motivo del último; el personal solo prueba un modelo con permiso para cambiar el modelo que contesta.
Implicados: ASSISTANT-F03, ASSISTANT-F05, ASSISTANT-F07

### ASSISTANT-F07 Probar un modelo antes de ponerlo a contestar
<!-- origen: old-saas:SAAS_ASSISTANT-F24 -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin: Probar un modelo
Pasos:
1. En «Modelo que contesta», pulsa «Probar un modelo».
2. Elige el «Modelo», escribe el «Mensaje» y, si quiere ver cómo pide herramientas, escribe en «Herramientas» una lista de herramientas con su nombre, como en el ejemplo.
3. Pulsa «Enviar»: sale «Enviando…», el modelo que contesta y su respuesta según llega, con las herramientas que pide.
4. Al acabar, «Hecho.» y la tabla con «Tokens de entrada», «Tokens de salida», «Tiempo» y «Coste» (con los precios del modelo).
Entra: el modelo, el mensaje y las herramientas.
Sale: la respuesta del modelo con su consumo, su tiempo y su coste; la prueba queda en el registro de auditoría con quién la hizo, cuánto medía el mensaje y cuántas herramientas llevaba, nunca el mensaje (`assistant.model.tried`). No toca ningún negocio, cupo ni conversación.
Si falla: sin modelo de la lista, «Elige de la lista el modelo que quieres probar.»; sin mensaje, «Escribe el mensaje que quieres enviar.»; unas herramientas mal escritas, «Las herramientas no están bien escritas: escribe una lista de herramientas como la del ejemplo, cada una con su nombre.»; un modelo apagado o de un proveedor apagado, «Este modelo está apagado o lo está su proveedor: enciéndelos para usarlo.»; un proveedor sin clave usable, «Ningún modelo puede contestar: los proveedores de los modelos elegidos no tienen ninguna clave activa.»; si el proveedor falla, «El modelo no ha contestado: …» con su motivo, nunca la clave; más de 10 pruebas en un minuto, «Demasiadas pruebas en un minuto: espera un momento y vuelve a intentarlo.»; sin red, «No se ha podido enviar la prueba: revisa la conexión y vuelve a intentarlo.». Solo prueba quien puede cambiar el modelo que contesta (cada prueba gasta la clave de ERPlora); sin ese permiso, el admin no deja entrar.
Implicados: ASSISTANT-F05, ASSISTANT-F06

### ASSISTANT-F08 Ver quién cambió la configuración de la IA
<!-- origen: fi:saas/support/auth-services#modelo-aiconfigauditlog fi:saas/django-admin#admin-aiconfigauditlog -->
Estado: hecho
Actor: superusuario de ERPlora (o alguien del equipo con permiso para ver el registro)
Pantalla: el admin de erplora.com › «Registro de auditoría»
Pasos:
1. Cada alta, cambio o baja de un proveedor de IA, de una clave de proveedor (también apagarla o cambiarla por otra), de un modelo (sus precios, si está disponible) y del modelo que contesta queda anotado: qué cambió, de qué valor a cuál, cuándo, quién lo hizo y desde qué dirección.
2. Cada prueba de un modelo queda anotada como una consulta de ese modelo, con quién la hizo, cuánto medía el mensaje y cuántas herramientas llevaba.
3. Abre «Registro de auditoría» en el admin, filtra por tipo de recurso o busca, y abre una entrada para ver sus cambios.
Entra: los cambios de la configuración de la IA, hechos desde el admin o por los comandos de erplora.com.
Sale: una entrada por cambio en el mismo registro de auditoría que las cuentas, los cobros y la documentación fiscal.
Si falla: nunca se anota una clave de proveedor, ni en claro ni cifrada: su cambio se ve en sus cuatro últimos caracteres y en cuándo se cambió; tampoco el mensaje de una prueba. Nadie puede crear, cambiar ni borrar una entrada a mano, y alguien del equipo sin el permiso no puede abrir el registro.
Implicados: ACCOUNTS-F36, ASSISTANT-F02, ASSISTANT-F07

### ASSISTANT-F09 Cargar las claves de los proveedores desde el entorno
<!-- origen: fi:saas/auth-services#comando-importar-claves-ai-desde-el-entorno fi:saas/support/auth-services#command-import_ai_keys_from_env -->
Estado: hecho
Actor: personal de ERPlora, en la línea de órdenes de erplora.com
Pantalla: ninguna
Pasos:
1. Con las claves de OpenAI, Anthropic, Google Gemini, DeepSeek y Azure AI Speech en el entorno de erplora.com, ejecuta la carga de las claves del entorno.
2. Cada clave se guarda cifrada en su proveedor con la etiqueta por defecto (u otra que se elija); si falta el proveedor, se da de alta con su nombre y su API.
3. Si el proveedor ya tenía una clave con esa etiqueta, se deja como está, salvo que se pida reemplazarla: entonces se cambia, se enciende y queda cuándo se cambió.
4. Se puede elegir qué proveedores cargar y ensayar la carga sin guardar nada.
Entra: las claves del entorno, los proveedores elegidos, la etiqueta y si se reemplazan las que ya hay.
Sale: las claves cifradas en sus proveedores (`assistant.credential.saved`) y, por cada una, si se creó, se cambió, se dejó o se saltó, con sus cuatro últimos caracteres.
Si falla: una variable vacía se salta; un proveedor desconocido detiene la carga antes de guardar nada; sin la clave de cifrado de las credenciales no se guarda ninguna. Nunca escribe una clave entera en pantalla, y el cambio queda en el registro de auditoría.
Implicados: ASSISTANT-F01, ASSISTANT-F02, ASSISTANT-F08

### ASSISTANT-F10 Cambiar la clave de cifrado sin perder ninguna credencial
<!-- origen: fi:saas/auth-services#comando-rotacion-de-claves-de-cifrado-gdpr fi:saas/support/public-core-config#command-rotate_encryption_keys -->
Estado: hecho
Actor: personal de ERPlora, en la línea de órdenes de erplora.com
Pantalla: ninguna
Pasos:
1. Pone la clave de cifrado nueva como la actual y deja la anterior como la previa (que solo lee), y despliega erplora.com.
2. Ensaya el cambio: dice cuántos valores se volverían a cifrar en cada sitio, sin escribir nada.
3. Ejecuta el cambio: cada valor guardado con la clave de las credenciales (las claves de los proveedores de IA y los tokens y PIN de WhatsApp) se vuelve a cifrar con la clave nueva; los que ya lo están se dejan como están.
4. Si acaba sin errores, quita la clave previa: todas las credenciales se siguen leyendo.
Entra: la clave nueva y la anterior.
Sale: todas las credenciales cifradas con la clave nueva (`assistant.encryption.rotated`, con cuántas se cambiaron, cuántas ya estaban y cuántas no se pudieron leer).
Si falla: un valor que no abre ninguna de las dos claves no se escribe nunca: se nombra su fila y el cambio termina con error, para que no se quite la clave previa mientras algo la necesite (se recupera la clave que lo cifró o se vuelve a escribir el valor, y se repite). Sin la clave de cifrado no cambia nada. Nunca enseña un valor ni su cifrado, y ninguna fecha de las filas se mueve.
Implicados: ASSISTANT-F02, ASSISTANT-F09

### ASSISTANT-F11 Reconocer quién llama y de qué negocio es
<!-- origen: old-saas:SAAS_ASSISTANT-F01 -->
Estado: hecho
Actor: el asistente del Hub de un negocio (o de una demo)
Pantalla: ninguna
Pasos:
1. Cada vez que el asistente de un negocio pide algo a erplora.com (un turno, el cupo que le queda, unas huellas, un dictado, una lectura en voz alta o una denuncia), la petición va firmada con el secreto que comparten el Hub y erplora.com, con su hora, y dice de qué negocio es: su dirección, su identificador o, si es una demo, la dirección de la demo.
2. erplora.com comprueba la firma y que no tiene más de cinco minutos antes de leer nada más.
3. Busca el negocio: tiene que existir y estar funcionando (activo, o con un pago pendiente en sus días de gracia); una demo se reconoce por su dirección.
4. Con el negocio reconocido, la petición sigue: el freno de tasa, el cupo y lo que haya pedido se aplican a ese negocio y a ningún otro.
Entra: la firma y su hora, el negocio (o la demo) y lo que pide.
Sale: el negocio o la demo para el que se contesta; ningún negocio ve ni gasta el cupo de otro.
Si falla: sin firma, con una firma mala, caducada o de otro secreto, se rechaza como no autorizada; un negocio que no existe o ya se borró, como desconocido; uno que se está preparando, suspendido o borrándose, como inactivo; una petición que no es la que espera cada puerta se rechaza diciendo qué campos fallan; otra cosa que no sea un envío se rechaza; un cuerpo que pasa del tamaño de su puerta se rechaza sin guardarlo. Nada de eso gasta mensajes ni freno.
Implicados: ASSISTANT-F16, ASSISTANT-F18

### ASSISTANT-F12 Contestar un turno del asistente en directo
<!-- origen: old-saas:SAAS_ASSISTANT-F02 fi:saas/auth-services#proxy-de-chat-sse-streaming fi:saas/support/auth-services#service-orchestrator-run_turn -->
Estado: hecho
Actor: el asistente del Hub de un negocio
Pantalla: ninguna
Pasos:
1. La persona escribe al asistente del Hub; el Hub manda a erplora.com la conversación entera (es suya: vive en el navegador de la persona), sus instrucciones y las herramientas que ofrece el negocio.
2. erplora.com prepara la conversación: sus instrucciones son las únicas del sistema, se quedan los últimos 100 mensajes, se quita la respuesta de una herramienta que nadie pidió y los adjuntos se convierten en lo que el modelo puede leer.
3. Toma un mensaje del cupo del negocio y manda el turno al modelo que contesta (o a su reserva, si su proveedor falla antes de contestar nada).
4. Devuelve la respuesta en directo, trozo a trozo, y cada herramienta del negocio que el modelo pide; al final, la respuesta entera con su consumo, lo que le queda al negocio del cupo y el cierre.
5. Si el modelo pidió herramientas del negocio, el turno acaba ahí con un pase de continuación: el Hub las ejecuta y vuelve a mandar la conversación con sus resultados y ese pase, y esa vuelta no gasta otro mensaje.
Entra: el negocio, la conversación, las instrucciones, las herramientas del negocio y, si contesta a unas herramientas, su pase de continuación.
Sale: el texto según llega, las herramientas que el negocio tiene que ejecutar, el consumo del turno y el cupo que queda (`assistant.message.claimed`; lo gastado, `assistant.usage.recorded`).
Si falla: lo que se sabe antes de llamar al modelo es un rechazo y no gasta ningún mensaje (ver ASSISTANT-F15); si el proveedor falla después de empezar, el turno acaba con un aviso de fallo que dice si vale la pena repetir; si el turno no llegó a contestar nada, su mensaje se devuelve al cupo, también si el Hub corta la conexión a medias. Un pase de continuación usado, caducado (15 minutos), de otro negocio o de otras herramientas no vale: esa vuelta gasta un mensaje.
Implicados: ASSISTANT-F06, ASSISTANT-F13, ASSISTANT-F14, ASSISTANT-F15, ASSISTANT-F17, ASSISTANT-F18, ASSISTANT-F19

### ASSISTANT-F13 Contestar el mismo turno de una vez
<!-- origen: old-saas:SAAS_ASSISTANT-F03 fi:saas/auth-services#proxy-de-chat-json-no-streamed -->
Estado: hecho
Actor: el asistente del Hub de un negocio
Pantalla: ninguna
Pasos:
1. Cuando el Hub no necesita ver la respuesta según llega (una tarea del propio Hub, un mensaje que no se pinta), manda el mismo turno que en ASSISTANT-F12 a la puerta que contesta de una vez. Así llega el paso «Pedírselo al asistente» de una automatización del negocio, sin nadie delante: es un turno más, sin nada que lo distinga del chat.
2. erplora.com hace lo mismo que en directo: prepara la conversación, toma el mensaje del cupo, llama al modelo (o a su reserva) y ejecuta sus propias herramientas.
3. Devuelve de una vez la respuesta entera, las herramientas que el negocio tiene que ejecutar con su pase de continuación, el consumo y el cupo que queda.
Entra: lo mismo que el turno en directo.
Sale: la respuesta entera con su consumo, su pase de continuación y el cupo que queda (`assistant.message.claimed`; lo gastado, `assistant.usage.recorded`).
Si falla: los rechazos antes del modelo, iguales que en directo; si el proveedor falla, un error de pasarela con su motivo, si vale la pena repetir y el cupo que queda, y el mensaje vuelve al cupo si no se contestó nada. El paso de una automatización gasta lo mismo que el chat: su primer turno, un mensaje; los turnos que contestan a todas sus herramientas (también a las que no se hicieron) con su pase de continuación, ninguno; si contestan pasados los 15 minutos del pase (un cambio que esperó el sí de una persona), uno.
Implicados: ASSISTANT-F12, ASSISTANT-F15, ASSISTANT-F18 y, en el Hub, FLOW-F39

### ASSISTANT-F14 Usar las herramientas de erplora.com y las del negocio
<!-- origen: old-saas:SAAS_ASSISTANT-F06 -->
Estado: descartado — la búsqueda en la web y el tipo de cambio entre monedas del producto anterior llegan con la etapa ERP (saas#202); las herramientas del negocio y la fecha y la hora de erplora.com sí funcionan
Actor: el asistente del Hub de un negocio
Pantalla: ninguna
Pasos:
1. En cada turno, el modelo puede usar las herramientas del negocio (las que manda el Hub: buscar un cliente, crear una cita…) y la de erplora.com: la fecha, la hora y el día de la semana de hoy.
2. Si el modelo pide una herramienta de erplora.com, erplora.com la ejecuta y le devuelve el resultado sin que el Hub vea nada.
3. Si pide una del negocio, el turno se la pasa al Hub para que la ejecute (ver ASSISTANT-F12).
4. El modelo se vuelve a llamar como mucho cinco veces en un turno; en la última ya no se le ofrecen las herramientas de erplora.com y tiene que contestar.
Entra: las herramientas del negocio y las preguntas del modelo.
Sale: el resultado de cada herramienta de erplora.com para el modelo; su consumo se suma al del turno y no gasta otro mensaje.
Si falla: una herramienta de erplora.com que falla da al modelo el motivo para que conteste con él, nunca un turno fallido; una herramienta del negocio con el nombre de una de erplora.com la ejecuta erplora.com; la búsqueda en la web y el tipo de cambio no se ofrecen, aunque el entorno de erplora.com tenga la clave de un buscador.
Implicados: ASSISTANT-F12, ASSISTANT-F13

### ASSISTANT-F15 Rechazar un turno con su motivo
<!-- origen: old-saas:SAAS_ASSISTANT-F07 -->
Estado: hecho
Actor: el asistente del Hub de un negocio
Pantalla: ninguna
Pasos:
1. Antes de llamar al modelo, erplora.com comprueba el turno: su forma, su tamaño, que haya un modelo que pueda contestar y que al negocio le quede cupo.
2. Si algo no cuadra, rechaza el turno sin llamar al modelo y sin gastar ningún mensaje, con un código que el Hub traduce a su texto y si vale la pena repetir.
3. Si el cupo está agotado, el rechazo dice cuántos mensajes se han usado de cuántos, cuándo vuelven y que hay que subir de plan para tener más.
Entra: el turno.
Sale: un rechazo con su código: cupo agotado, sin modelo que conteste, proveedor sin configurar, conversación o adjunto demasiado grandes, o forma que no es la esperada.
Si falla: un fallo que no se esperaba se devuelve como un error interno que vale la pena repetir, sin detalles; nunca sale la clave del proveedor ni sus palabras.
Implicados: ASSISTANT-F12, ASSISTANT-F13, ASSISTANT-F18, ASSISTANT-F19

### ASSISTANT-F16 Frenar a un negocio que pide demasiado
<!-- origen: old-saas:SAAS_ASSISTANT-F08 -->
Estado: hecho
Actor: el asistente del Hub de un negocio
Pantalla: ninguna
Pasos:
1. Cada puerta del asistente tiene un máximo de peticiones por hora para cada negocio (y para cada demo): 600 turnos y consultas de cupo, 600 lotes de huellas, 120 dictados, 120 lecturas en voz alta y 60 denuncias.
2. Solo cuenta una petición con la firma buena y de un negocio que funciona: una petición falsa no gasta el freno de nadie.
3. Pasado el máximo, se rechaza la petición y se dice cuántos segundos faltan para poder volver a pedir.
Entra: las peticiones de cada negocio.
Sale: la petición atendida o frenada; el freno de un negocio no frena a otro.
Si falla: un negocio frenado espera lo que se le dice y vuelve a intentarlo; los máximos se cambian en el entorno de erplora.com sin tocar el código.
Implicados: ASSISTANT-F11

### ASSISTANT-F17 No guardar la conversación
<!-- origen: old-saas:SAAS_ASSISTANT-F09 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. La conversación de cada turno llega con la petición, se usa para llamar al modelo y se olvida al terminar.
2. erplora.com solo apunta lo que se gastó: los mensajes, los tokens y el coste del negocio en el mes.
3. Si el proveedor falla, el registro de erplora.com solo apunta el estado de la respuesta del proveedor, nunca sus palabras (pueden citar la conversación).
Entra: la conversación del turno.
Sale: la respuesta para el Hub y lo gastado; ni la base de datos, ni los registros, ni el registro de auditoría guardan una palabra de la conversación, de sus adjuntos, de sus dictados ni de lo leído en voz alta.
Si falla: si algo de la conversación llegara a un registro, un test lo detecta antes de salir.
Implicados: ASSISTANT-F12, ASSISTANT-F19, ASSISTANT-F21, ASSISTANT-F22, ASSISTANT-F23

### ASSISTANT-F18 Contar los mensajes del plan de cada negocio
<!-- origen: old-saas:SAAS_ASSISTANT-F11 old-saas:SAAS_ASSISTANT-F10 fi:saas/auth-services#config-del-asistente-tier-routing-cuota fi:saas/support/auth-services#modelo-assistantusage -->
Estado: hecho
Actor: el asistente del Hub de un negocio
Pantalla: ninguna
Pasos:
1. El cupo de un negocio es el del plan que tiene ahora («Mensajes del asistente de IA al mes»); 0 es ninguno, nunca ilimitado. Una demo tiene 10 mensajes en toda su vida.
2. Cada mensaje que la persona escribe gasta uno al empezar el turno, antes de llamar al modelo; si dos turnos llegan a la vez con un solo mensaje libre, solo pasa uno.
3. Si el turno no llega a contestar nada (el proveedor falla, el Hub corta), el mensaje se devuelve al mes en que se tomó.
4. Cada turno suma sus tokens y su coste al mes del negocio; las herramientas, las huellas, los dictados y la voz se miden pero no gastan mensajes.
5. El Hub pregunta cuánto le queda (cuántos se han usado, de cuántos y cuándo vuelven) y lo enseña; el cierre de cada turno trae las mismas cifras. El cupo vuelve el día 1 de cada mes a las 00:00 UTC; el de una demo no vuelve.
Entra: el negocio (o la demo) y su plan.
Sale: el mensaje tomado o devuelto y lo gastado en el mes (`assistant.message.claimed`, `assistant.message.released`, `assistant.usage.recorded`).
Si falla: sin mensajes libres, el turno se rechaza con el cupo agotado y la propuesta de subir de plan (ver ASSISTANT-F15); no hay paquetes de mensajes sueltos: más mensajes es subir de plan.
Implicados: ASSISTANT-F12, ASSISTANT-F15, ASSISTANT-F24, HUBS-F05

### ASSISTANT-F19 Leer los adjuntos de una pregunta
<!-- origen: old-saas:SAAS_ASSISTANT-F18 -->
Estado: hecho
Actor: el asistente del Hub de un negocio
Pantalla: ninguna
Pasos:
1. La persona adjunta a su pregunta imágenes o documentos; el Hub los manda dentro del turno.
2. Una imagen (PNG, JPEG, WebP o GIF) va tal cual al modelo si ve imágenes; si no las ve, el modelo recibe una nota en su lugar.
3. Un documento (PDF, Word, Excel, texto, CSV, Markdown o un fichero .json) se convierte en su texto (una hoja de cálculo, hoja por hoja) y el modelo lo lee con su nombre.
4. Todo se hace en memoria: no se descarga nada de ninguna dirección ni se escribe nada en disco.
Entra: las imágenes y los documentos de la pregunta.
Sale: lo que el modelo puede leer de cada adjunto, o una nota si no se puede leer.
Si falla: un adjunto de más de unos 9 MB o más de 20 adjuntos en una conversación rechazan el turno como demasiado grande, sin cortar nada y sin gastar mensaje; un documento roto, protegido, de un tipo que no se lee o que al abrirse crecería demasiado es una nota para el modelo, nunca un turno fallido; una imagen o un documento dados por una dirección no se descargan; el nombre del fichero no llega a ningún registro.
Implicados: ASSISTANT-F12, ASSISTANT-F15, ASSISTANT-F17

### ASSISTANT-F20 Calcular la huella de unos textos para el índice del negocio
<!-- origen: old-saas:SAAS_ASSISTANT-F17 fi:saas/auth-services#proxy-de-embeddings-rag-local-del-hub fi:saas/support/auth-services#service-embeddings -->
Estado: hecho
Actor: el asistente del Hub de un negocio
Pantalla: ninguna
Pasos:
1. Un Hub que guarde un índice propio con la huella de cada texto manda a erplora.com los textos de los que necesita la huella, de 1 a 256 a la vez. El Hub de hoy no guarda ninguno: busca en la documentación de ERPlora a través de erplora.com (ver ASSISTANT-F28).
2. erplora.com pide las huellas al proveedor de servicios, siempre con el mismo modelo de huellas, y las devuelve en el orden de los textos.
3. Los tokens y su coste se suman al mes del negocio.
Entra: el negocio y los textos.
Sale: una huella por texto, en su orden, con el nombre del modelo que las calculó (`assistant.usage.recorded`).
Si falla: sin proveedor de servicios configurado (o sin su clave), se rechaza diciendo que el proveedor no está configurado; si el proveedor rechaza la petición o no contesta, un error de pasarela que dice si vale la pena repetir; un texto vacío o más de 256 se rechazan; no gasta mensajes del cupo.
Implicados: ASSISTANT-F11, ASSISTANT-F16, ASSISTANT-F24

### ASSISTANT-F21 Transcribir un dictado de voz
<!-- origen: old-saas:SAAS_ASSISTANT-F19 fi:saas/auth-services#transcripcion-de-voz-speech-to-text fi:saas/hubs#transcripcion-de-voz-del-hub -->
Estado: hecho
Actor: el asistente del Hub de un negocio; la persona con cuenta en erplora.com, en el asistente del panel
Pantalla: Panel: Asistente
Pasos:
1. La persona dicta su pregunta en el Hub o en el asistente del panel de erplora.com: pulsa «Dictar por voz», el navegador le pide el micrófono si aún no lo tiene, habla y pulsa «Detener la grabación». El Hub manda a erplora.com el audio, su tipo (WebM, Ogg, WAV, MP4, MP3 o FLAC) y, si lo sabe, el idioma; el panel manda lo mismo con la sesión de la cuenta, sin firma.
2. erplora.com lo pasa al proveedor de servicios desde la memoria, sin escribirlo en disco, y devuelve el texto y el idioma. El texto cae en la caja, detrás de lo que hubiera escrito, para que la persona lo lea y lo envíe: un dictado nunca se envía solo.
3. El dictado se cuenta en el mes del negocio o, en el panel, en el de la cuenta; no gasta mensajes (el mensaje lo gasta el turno que se envía con ese texto).
Entra: el negocio o, en el panel, la cuenta de la sesión; el audio, su tipo y su idioma.
Sale: el texto dictado y su idioma (`assistant.usage.recorded`).
Si falla: un audio de más de 2 MB se rechaza como demasiado grande; vacío, mal codificado o de otro tipo, se rechaza diciendo qué falla; sin proveedor de servicios configurado, que no está configurado; si el proveedor falla, un error de pasarela que dice si vale la pena repetir. Ni el audio ni el texto quedan guardados ni en un registro. En el panel, sin sesión no hay botón y la petición se rechaza; cada cuenta tiene el mismo máximo de 120 dictados por hora que un negocio; y lo que impide un dictado se dice bajo la caja, que se queda como estaba: un micrófono denegado, dónde permitirlo, sin grabar nada; una grabación en la que no se oye nada, que se intente más cerca; demasiado larga, que se dicte algo más corto; y cualquier rechazo del servidor (el máximo por hora y el proveedor incluidos), que no se ha podido transcribir y se intente de nuevo.
Implicados: ASSISTANT-F11, ASSISTANT-F16, ASSISTANT-F17, ASSISTANT-F24, ASSISTANT-F25, ASSISTANT-F26

### ASSISTANT-F22 Leer una respuesta en voz alta
<!-- origen: old-saas:SAAS_ASSISTANT-F20 -->
Estado: hecho
Actor: el asistente del Hub de un negocio
Pantalla: ninguna
Pasos:
1. Un Hub que quiera leer una respuesta con la voz de erplora.com le manda el texto, su idioma (español o inglés) y, si quiere, la voz: Ximena o Tristan en español, Ava o Andrew en inglés; sin voz, la de mujer del idioma (Ximena o Ava). El asistente del panel de erplora.com la pide para la cuenta con la voz elegida en su cabecera; el Hub de hoy no la pide y lee con la voz del propio dispositivo.
2. erplora.com pide el audio a Azure AI Speech, con sus voces de alta definición (como mucho los primeros 4.096 caracteres), y lo devuelve en MP3.
3. Los caracteres leídos se cuentan en el mes del negocio (o de la cuenta); no gasta mensajes.
Entra: el negocio, el texto, el idioma y la voz.
Sale: el audio de la respuesta (`assistant.usage.recorded`).
Si falla: un texto vacío, un idioma sin voces o una voz que no está en el catálogo se rechazan; sin el proveedor de voz configurado, que la lectura en voz alta no está disponible (y el Hub o el panel leen con la voz del dispositivo); si Azure falla, un error de pasarela que dice si vale la pena repetir. El texto no queda guardado ni en un registro.
Implicados: ASSISTANT-F11, ASSISTANT-F16, ASSISTANT-F17, ASSISTANT-F24

### ASSISTANT-F23 Recibir la denuncia de una respuesta del asistente
<!-- origen: old-saas:SAAS_ASSISTANT-F21 -->
Estado: hecho
Actor: el asistente del Hub de un negocio
Pantalla: ninguna
Pasos:
1. La persona marca una respuesta del asistente como incorrecta, dañina, que no hace lo que se pidió u otra cosa, y añade, si quiere, un comentario.
2. El Hub manda a erplora.com la denuncia con la pregunta y la respuesta.
3. erplora.com la manda por correo al buzón de soporte de ERPlora con el negocio, el motivo, el comentario, la pregunta y la respuesta (cada texto, como mucho 4.000 caracteres), y no guarda nada.
4. Si la misma respuesta del mismo negocio se denuncia otra vez en 24 horas (un doble toque, un reintento), no se manda otro correo.
Entra: el negocio, la respuesta denunciada, el motivo, el comentario y la pregunta.
Sale: el correo en el buzón de soporte, o el aviso de que ya se había mandado (`assistant.report.sent`).
Si falla: si el correo no puede salir, se dice que no se ha podido enviar y que se vuelva a intentar en un momento, y se puede volver a enviar; un motivo que no es uno de los cuatro se rechaza; un negocio que deja de trabajar (eliminado o suspendido) mientras llega su denuncia no manda nada y recibe la misma respuesta que en cualquier otra llamada (ASSISTANT-F11).
Implicados: ASSISTANT-F11, ASSISTANT-F16, ASSISTANT-F17

### ASSISTANT-F24 Ver lo que ha gastado un negocio del asistente
<!-- origen: old-saas:SAAS_ASSISTANT-F15 fi:saas/django-admin#admin-assistantusage fi:saas/auth-services#tiers-suscripcion-uso-del-asistente-modelos-admin -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin: Registros de uso del asistente
Pasos:
1. En el admin de erplora.com, abre «Registros de uso del asistente».
2. Busca el negocio por su nombre o su dirección (la demo por su dirección, la cuenta por su correo), o filtra «Por tipo» («Negocios», «Demos» o «Cuentas») y por mes.
3. Lee su fila del mes: «Mensajes» del cupo, «Tokens de entrada», «Tokens de salida», «Tokens de huellas», «Dictados», «Caracteres leídos en voz alta» y «Coste (USD)» (con los precios del modelo que contestó cada turno).
4. Abre la fila para verla entera, con cuándo se creó y cuándo se cambió.
Entra: el negocio, la demo o la cuenta y el mes.
Sale: lo gastado por el negocio (o la cuenta) en el mes, sin poder cambiarlo.
Si falla: nadie puede añadir, cambiar ni borrar una fila, ni siquiera un superusuario (borrar la del mes devolvía al negocio todo su cupo); alguien del equipo sin el permiso para verlo no entra.
Implicados: ASSISTANT-F18, ASSISTANT-F20, ASSISTANT-F21, ASSISTANT-F22, ASSISTANT-F26

### ASSISTANT-F25 Contestar al asistente del panel de una cuenta
<!-- origen: old-saas:SAAS_DASHBOARD-F220 old-saas:SAAS_DASHBOARD-F221 -->
Estado: hecho
Actor: la persona con cuenta en erplora.com
Pantalla: Panel: Asistente
Pasos:
1. La persona, con su sesión abierta en el panel de erplora.com, pulsa «Asistente» al final de la barra y se abre el panel del asistente: junto a la pantalla desde 768 px, encima en el móvil. Sin conversación, ve «Pregúntame por tus negocios, tus facturas o tu cuenta.» con tres atajos.
2. Escribe al asistente, le dicta (ver ASSISTANT-F21) o pulsa un atajo («¿Qué negocios tengo?», «¿Cuánto pago al mes?», «¿Cómo creo un negocio?»); hasta la primera palabra de la respuesta ve la burbuja de «El asistente está escribiendo».
3. erplora.com le ofrece al modelo las herramientas del panel que esa cuenta puede usar (sus negocios y su gente, los planes, sus facturas y suscripciones, su cuenta, el catálogo de apps), primero las de lo que ha preguntado, y siempre la lista de sus negocios.
4. Una consulta que el modelo pide se ejecuta sola, como la propia persona: nunca ve un negocio que no es suyo.
5. Un cambio que el modelo pide se para en la tarjeta «¿Ejecutar esta acción?», que dice qué va a hacer, dónde (la pantalla del panel: «Negocios», «Facturación», «Cuenta» o «Tienda») y con qué datos, nombrando el negocio por su nombre y el país por el suyo en su idioma («País: España»); solo se hace si la persona pulsa «Ejecutar», y «Cancelar» no cambia nada. Crear, borrar o cambiar la dirección de un negocio, ofrecerlo a otro o cancelar su plan piden además escribir «CONFIRMAR». Al cancelar el plan, la tarjeta enseña antes lo que dice el diálogo «Cancelar el plan» de Facturación (BILLING-F13): el plan en que sigue y hasta qué día está pagado (el día del negocio), que después pasa a Gratis, qué módulos se desactivan ese día, cuántas personas y dispositivos caben en Gratis frente a las personas que tiene ahora y, si la hay, la factura sin pagar, que sigue pendiente. Cambiar de plan no se hace desde el chat, sino en la Tienda (BILLING-F11), que enseña antes lo que se cobra: el asistente dice que se hace allí y la enlaza.
6. Con lo que han devuelto las herramientas, el modelo contesta en directo, trozo a trozo, en el idioma de la persona. La tarjeta es la única pregunta de un cambio: el modelo no pregunta en su texto si lo hace ni escribe un resumen para que se apruebe, y solo pide un dato que el cambio necesita, que ninguna herramienta da y que la persona no ha dicho. Enlaza la pantalla del panel donde se hace lo que no puede hacer él («Ir a Negocios»…); para lo que pasa dentro de un negocio (ventas, productos, la gente de la caja) dice que se abra el negocio y se pregunte a su asistente. Bajo la respuesta queda lo que se hizo de cada cambio («Hecho: Crear negocio en Negocios», «No se hizo, cancelado: …»). Si la respuesta da por hecho un cambio que no se hizo (tras «Cancelar», «Creado Café Triana» o «Ya debería verse más oscura»), debajo sale además «El asistente ha dicho que hizo un cambio, pero no se ejecutó ninguna acción. No se ha modificado nada.»; decir que no se hizo, o cuándo se creó algo, no lo saca. En la cuenta que se abre desde la app, donde no se vende ni se cobra, a lo que pregunte de planes, precios, módulos, códigos promocionales, pagos o la tarjeta contesta, sin enlace, «Para cambiar de plan o añadir módulos, entra en erplora.com desde el navegador.» (con una factura sin pagar, «Para pagarla, entra en erplora.com desde el navegador.»), aunque la documentación lo explique; consultar facturas y suscripciones y editar los datos fiscales sí se hace ahí.
7. Desde el 80 % de los mensajes del mes, el pie del panel dice cuántos quedan y cuándo vuelven (ver ASSISTANT-F26). El panel se cierra con ×, Escape, el velo o el mismo botón; el dispositivo recuerda si se dejó abierto, y la conversación se olvida al cerrar la sesión.
Entra: la conversación (vive en el navegador de la persona), las herramientas que el modelo pidió y la respuesta de la persona a su tarjeta.
Sale: lo que se ha hecho y su resultado, la tarjeta del cambio que espera, el texto según llega, el cupo que queda y el cierre; lo que hace cada herramienta deja su propio rastro (`hubs.business.created`…), nunca la conversación.
Si falla: sin sesión, el panel lleva a entrar y no hay botón «Asistente», y una sesión que termina a media conversación pide volver a entrar; con el cupo del mes gastado, el primer aviso es el cupo agotado, con cuántos se han usado y cuándo vuelven, y que cada negocio tiene su propio asistente, sin «Mejorar plan» (ver ASSISTANT-F26); con demasiados turnos seguidos, avisa de que hay que esperar un momento; sin un modelo que conteste, de que el asistente no puede contestar ahora, con «Reintentar»; sin conexión, el pie lo dice. Una herramienta que la cuenta no tiene, o que no es del chat (descargar un fichero, crear una clave de API, abrir el pago, entrar en un negocio), no se ejecuta nunca. Sin la palabra escrita o con un «no», el cambio no se hace y el modelo lo dice, sin mandar a confirmar una tarjeta que ya se cerró; ese «no» vale hasta que la persona vuelva a escribir: si el modelo pide otra vez el mismo cambio, no sale otra tarjeta ni otro «No se hizo». Unos datos que el cambio no acepta (un país que no es de los que sirve ERPlora, un valor fuera de su lista) o un cambio que no se puede hacer (cancelar el plan de un negocio en Gratis, o el de uno que paga otra cuenta) no llegan a la tarjeta: vuelven al modelo, que los corrige en la misma pregunta, y la persona confirma una sola vez. Un negocio nuevo que no se puede crear (la cuenta ya tiene su negocio gratuito, es del personal de ERPlora o no hay plan Gratis) tampoco llega a la tarjeta: el modelo dice por qué y, si es el negocio gratuito, que se cambie el plan del que ya tiene (HUBS-F01). Donde no se vende (la cuenta abierta desde la aplicación instalada), no se ofrecen la Tienda ni sus cambios de plan. Pasadas seis rondas de herramientas en una misma pregunta, se para.
Implicados: ASSISTANT-F12, ASSISTANT-F14, ASSISTANT-F15, ASSISTANT-F16, ASSISTANT-F17, ASSISTANT-F21, ASSISTANT-F23, ASSISTANT-F26, ASSISTANT-F29, HUBS-F01, HUBS-F09, BILLING-F11, BILLING-F13

### ASSISTANT-F26 Contar los mensajes de una cuenta con el asistente del panel
<!-- origen: nuevo (PLAN-SAAS §23: un cupo fijo por cuenta, como los asistentes de cuenta de Shopify, Square, Stripe, GitHub y Vercel, que van con la cuenta y no con el plan de cada tienda) -->
Estado: hecho
Actor: la persona con cuenta en erplora.com
Pantalla: ninguna
Pasos:
1. Cada cuenta tiene 30 mensajes al mes con el asistente del panel, tenga los negocios que tenga y en el plan que estén; el cupo de cada negocio es aparte, el de su plan en su Hub (ver ASSISTANT-F18).
2. Cada mensaje que la persona escribe gasta uno al empezar el turno, antes de llamar al modelo; la vuelta con los resultados de las herramientas que el modelo pidió no gasta otro, ni un dictado, que solo se mide (ver ASSISTANT-F21).
3. Si el turno no llega a contestar nada (el proveedor falla, la persona corta), el mensaje se devuelve al mes en que se tomó.
4. El panel pregunta cuánto le queda (cuántos se han usado, de cuántos y cuándo vuelven); el cierre de cada turno trae las mismas cifras. El cupo vuelve el día 1 de cada mes a las 00:00 UTC.
Entra: la cuenta de la sesión.
Sale: el mensaje tomado o devuelto y lo gastado en el mes de la cuenta (`assistant.message.claimed`, `assistant.message.released`, `assistant.usage.recorded`, con la cuenta).
Si falla: sin mensajes libres, el turno se rechaza con el cupo agotado y la fecha en que vuelven; no hay plan que subir ni paquetes sueltos. Una cuenta nunca gasta los mensajes de sus negocios, ni un negocio los de su cuenta; al borrar la cuenta se borran sus filas.
Implicados: ASSISTANT-F18, ASSISTANT-F21, ASSISTANT-F24, ASSISTANT-F25, ASSISTANT-F29

### ASSISTANT-F27 Buscar en la documentación desde el panel
<!-- origen: old-saas:SAAS_DASHBOARD-F220 old:saas/apps/dashboard/assistant/knowledge.py old:saas/apps/dashboard/assistant/tools.py#search_cloud_docs -->
Estado: hecho
Actor: la persona con cuenta en erplora.com
Pantalla: ninguna
Pasos:
1. La persona pregunta al asistente del panel cómo se hace algo en ERPlora o qué incluye un plan («¿Cómo invito a alguien a mi negocio?», «¿Qué incluye el plan Starter?»).
2. El asistente tiene siempre a mano la búsqueda en la documentación, junto a la lista de negocios de la cuenta, y la usa para las preguntas de cómo se hace.
3. erplora.com busca en la ayuda pública de erplora.com, en la documentación de cada app del Hub que está en la tienda, en la parte de usuario de los manuales del panel (la cuenta, los negocios, la facturación, la tienda y la web) y en los planes en venta con sus precios y lo que incluye cada uno. En la cuenta que se abre desde la app no busca en los planes ni en los manuales de la facturación, la tienda y la web.
4. Devuelve hasta 8 fragmentos (12 como mucho, aunque el modelo pida más), los más cercanos a la pregunta, en el idioma de la persona; si en su idioma hay menos de tres que de verdad respondan, se suman los de inglés. Cada fragmento dice de dónde sale y bajo qué títulos.
5. El modelo contesta con lo que dicen esos fragmentos y cita de dónde salen; un precio o lo que incluye un plan sale siempre de los planes en venta, nunca de memoria.
6. La documentación se pone al día sola cada día a las 06:50 UTC: un cambio en la ayuda, en un manual, en la documentación de una app o en un plan llega al asistente con la siguiente pasada, y el equipo de ERPlora puede lanzarla a mano si quiere adelantarla.
Entra: la pregunta (hasta 500 caracteres) y cuántos fragmentos quiere el modelo.
Sale: los fragmentos con su fuente, de dónde salen, sus títulos, su texto, su idioma y lo cerca que están de la pregunta; de la pregunta solo queda su huella en la caché durante un día (la misma pregunta otra vez no se calcula de nuevo).
Si falla: sin el proveedor de las huellas configurado, o si falla, la búsqueda contesta que ahora no se puede buscar en la documentación y el modelo se lo dice a la persona; una cuenta sin permiso para preguntar al asistente no busca; mientras la documentación no se ha indexado, no encuentra nada y el modelo dice que no lo sabe en lugar de inventarlo.
Implicados: ASSISTANT-F20, ASSISTANT-F25, APPS-F02, HUBS-F05, PUBLIC-F15

### ASSISTANT-F28 Buscar en la documentación desde el Hub
<!-- origen: old-saas:SAAS_ASSISTANT-F17 fi:saas/auth-services#proxy-de-embeddings-rag-local-del-hub -->
Estado: hecho
Actor: el asistente del Hub de un negocio
Pantalla: ninguna
Pasos:
1. Una persona del negocio pregunta al asistente del Hub cómo se hace algo en ERPlora, qué significa una opción o qué incluye un plan («¿Cómo abro la caja?», «¿Qué incluye el plan Starter?»).
2. El Hub no guarda la documentación: manda a erplora.com la pregunta, el negocio (o la demo) y el idioma de la persona.
3. erplora.com calcula la huella de la pregunta y busca en la misma documentación que el asistente del panel (ver ASSISTANT-F27): la ayuda pública de erplora.com, la documentación de cada app del Hub, la parte de usuario de los manuales del panel y los planes en venta con sus precios.
4. Devuelve hasta 8 fragmentos (12 como mucho, aunque se pidan más), los más cercanos a la pregunta, en el idioma de la persona; si en su idioma hay menos de tres que de verdad respondan, se suman los de inglés. Cada fragmento dice de dónde sale y bajo qué títulos.
5. El asistente del Hub contesta solo con lo que dicen esos fragmentos y cita de dónde salen; si no hay ninguno, dice que la documentación no lo cubre en lugar de inventarlo.
Entra: el negocio o la demo, la pregunta (hasta 500 caracteres), el idioma (inglés o español) y cuántos fragmentos quiere.
Sale: los fragmentos con su fuente, de dónde salen, sus títulos, su texto, su idioma y lo cerca que están de la pregunta; de la pregunta solo queda su huella en la caché durante un día (la misma pregunta otra vez no se calcula de nuevo). No gasta mensajes del cupo.
Si falla: sin el proveedor de las huellas configurado, contesta que ahora no se puede buscar en la documentación porque el proveedor no está configurado; si el proveedor falla, que se vuelva a intentar en un momento; con demasiadas búsquedas seguidas del mismo negocio, que espere un momento; una llamada sin firmar, de un negocio que erplora.com no conoce o de uno que no está activo se rechaza como en cualquier puerta del Hub; mientras la documentación no se ha indexado, no encuentra nada y el asistente dice que la documentación no lo cubre.
Implicados: ASSISTANT-F11, ASSISTANT-F16, ASSISTANT-F27

### ASSISTANT-F29 Avisar por correo a una cuenta de que se le acaban los mensajes del asistente del panel
<!-- origen: nuevo (PLAN-SAAS §23 y §29; gh:saas#204; avisan al acercarse al tope y otra vez al llegar: ver «Referencia adoptada») -->
Estado: hecho
Actor: la persona con cuenta en erplora.com
Pantalla: ninguna
Pasos:
1. Al gastar el mensaje que la deja en el 80 % del mes, el 24 de 30, el mismo punto desde el que lo dice el pie del panel (ASSISTANT-F25), erplora.com le manda un correo a la dirección de su cuenta y en su idioma: «Te quedan 6 de 30 mensajes con el asistente este mes.», cuándo vuelven («Se renuevan el 1 de diciembre.») y un enlace al panel.
2. Al gastar el último, el 30 de 30, le manda otro: «Has usado los 30 mensajes con el asistente de este mes.», cuándo vuelven, «Cada negocio tiene su propio asistente, con sus propios mensajes: abre el negocio para seguir preguntando allí.» y el enlace al panel. Ninguno ofrece subir de plan ni comprar mensajes, porque no existen (ASSISTANT-F26).
3. Cada correo sale una sola vez por cuenta y mes, aunque dos turnos a la vez lleguen al mismo punto. Un mensaje devuelto (ASSISTANT-F26, paso 3) no anula el aviso ya mandado ni hace que se repita al volver a llegar. Con el cupo del mes siguiente pueden volver a salir.
Entra: el mensaje tomado de la cuenta (ASSISTANT-F26), y el correo y el idioma de la persona.
Sale: el correo, y la marca de que ya salió en el mes de la cuenta (`assistant.usage.warned`, con la cuenta y las cifras).
Si falla: un correo que no sale no frena el turno: queda en el registro y se vuelve a intentar con el siguiente mensaje que la persona escriba ese mes, con las cifras de ese momento, también si ya no le queda ninguno; con el cupo gastado solo sale el de «Has usado», nunca el de «Te quedan». El cupo de un negocio (ASSISTANT-F18) y el de una demo no mandan este correo. No se puede apagar en Preferencias: son dos correos al mes como mucho y sin publicidad (ver ACCOUNTS-F23).
Implicados: ASSISTANT-F25, ASSISTANT-F26, ACCOUNTS-F23

## Para quien lo mantiene

- Anatomía, datos y operaciones: `assistant/README.md`.
- La clave se cifra con Fernet y `FERNET_KEY` (`assistant/crypto.py`, `assistant/fields.py`); durante una rotación
  `FERNET_KEY_PREVIOUS` aún la lee. Una clave que ninguna de las dos abre se lee vacía y se registra como
  `assistant.crypto.undecryptable`, sin el token.
- Escrituras por `assistant.credential.save|delete` (`services.py`), con el permiso del modelo de Django que las
  respalda (`add|change|delete_aiprovidercredential`); el admin las llama como el miembro del personal que pulsa.
- «Elegir modelos del proveedor» es una vista asíncrona del admin (`AIProviderAdmin.models_view`): la llamada al
  proveedor no ocupa el hilo que usan las demás peticiones; lee la conexión con `assistant.provider.connection`
  (`view_aiprovider`) y guarda con `assistant.model.select` (`add_aimodel` y `delete_aimodel`).
- La política es una sola fila (`AIRoutingPolicy.solo`), leída con `assistant.policy.show` (`view_airoutingpolicy`)
  y cambiada con `assistant.policy.update` (`change_airoutingpolicy`). Sin el paso doble del producto viejo
  (razonamiento y ejecución con dos modelos, apagado en producción): un modelo y su reserva, como las pasarelas del
  mercado.
- El turno: `assistant.route.resolve` (`queries.py`; la plataforma con `platform_context`, el personal con
  `change_airoutingpolicy` y un modelo) da los modelos en orden con su clave, leídos en cada turno (sin caché ni
  señales que la limpien: lo que el producto viejo hacía con ASSISTANT-G39); `assistant.routing.stream` los prueba
  en orden y solo pasa a la reserva si el fallo llega antes del primer texto o herramienta (eventos `model` y
  `fallback`).
- Auditoría: `assistant/auditlog.py` registra proveedores, claves, modelos y política con `accounts.auditlog.audit`
  (sin `api_key` ni `updated_at`); sin el `AIConfigAuditLog` propio del producto viejo: un solo registro para todo
  erplora.com (PLAN-SAAS §1.1). La prueba de un modelo es una entrada `ACCESS` del modelo, escrita por
  `assistant.model.try`.
- `import_ai_keys_from_env` (`--providers`, `--label`, `--force`, `--dry-run`) lee `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY` y `AZURE_SPEECH_KEY` de `config/settings.py` y guarda con
  `assistant.credential.import` (solo la plataforma); el proveedor que falta se da de alta con el identificador de su
  API (`azure-speech` para `azure_speech`, `models.provider_slug`). El turno y la voz nunca leen esas variables: solo
  la base de datos.
- `rotate_encryption_keys [--dry-run]` corre `assistant.encryption.rotate` (solo la plataforma) sobre toda columna de
  `ROTATED_FIELD_CLASSES` (`services.encrypted_columns`, derivada de los modelos: hoy la clave del proveedor y el
  token y el PIN de WhatsApp): rota cada token tal cual (`crypto.rotate`, por `UPDATE` sin pasar por `save`) y nunca
  escribe uno ilegible. Un test falla si aparece un campo cifrado que la rotación no conoce (#1016 del producto
  viejo). Los documentos fiscales usan su propia clave (`FISCAL_DOCUMENTS_KEY`) y no entran aquí.
- Clientes (`assistant/providers/`): `httpx` contra cada API (sin SDK ni LiteLLM), sin caché, uno por llamada;
  todos terminan con un solo `finish` y un fallo es un `error` con `retriable`, nunca una excepción. Se prueban contra
  `assistant/tests/fake_provider.py` (servidor HTTP en `127.0.0.1` que habla el formato de cada proveedor).
- Trampas del producto viejo cubiertas: saas#528 (clave en claro en la base de datos: `test_fields.py`), saas#2489
  (nombre de la app sin traducir en el admin: `test_apps.py`).

- El turno pide su ruta con `assistant.route.resolve` como la plataforma (`services.platform_context()`) y la
  recorre con `assistant.routing.stream`; el coste sale de `models.estimate_cost` con los precios del modelo que
  contestó. `seed_ai_providers` del producto viejo no se porta (sembraba dos proveedores apagados de API que no
  hablamos): los proveedores los da el admin o `import_ai_keys_from_env`.

### Las puertas del Hub (`assistant/internal.py`, ASSISTANT-F11…F23, F28)

Todas `POST`, firmadas como todo `/internal` (`accounts.signing`: v1 sobre el cuerpo o v2 sobre método, ruta y
cuerpo; ±`INTERNAL_SIGNATURE_MAX_AGE_SECONDS`; el secreto actual o el previo), sin CSRF, asíncronas (un turno que
espera a su modelo no ocupa un hilo). Cada cuerpo nombra el negocio en `hub`: su `slug`, su id (la grafía del UUID) o
la dirección `demo-…` de una demo (`assistant.caller.resolve`). Antes de su respuesta, cada puerta contesta, por
orden: 405 `method_not_allowed`, 413 `payload_too_large` (por `Content-Length` antes de leer, o por lo leído), 401
`unauthorized`, 422 `invalid_payload` (con `fields`), 404 `hub_unknown`, 403 `hub_inactive` (solo `ACTIVE` y
`PAST_DUE` pasan) y 429 `rate_limited` (con `Retry-After`; el freno se gasta solo tras la firma y el negocio,
saas#2531). Un rechazo es `{"error": {"code", "message", …}}`; el `message` es inglés y orientativo: el Hub enseña su
propio texto por `code`.

| Puerta | Cuerpo | Respuesta | Freno (ajuste) |
|---|---|---|---|
| `/internal/assistant/chat/stream` | `hub`, `messages` (1–1000), `instructions`, `tools` (≤256, formato de OpenAI), `continuation` | `text/event-stream` (abajo) | `ASSISTANT_TURN_RATELIMIT` 600/h |
| `/internal/assistant/chat` | igual | `{output, usage, continuation, quota}`; fallo del proveedor: 502 con `code`, `retriable` y `quota` | el mismo |
| `/internal/assistant/usage` | `hub` | `{used, limit, resets_at, demo}` (`resets_at` UTC; `null` en una demo) | el mismo |
| `/internal/assistant/embeddings` | `hub`, `texts` (1–256, ninguno vacío) | `{embeddings, model}` en el orden de `texts`; ningún Hub la llama hoy (no guarda índice) | `ASSISTANT_EMBED_RATELIMIT` 600/h |
| `/internal/assistant/docs/search` | `hub`, `query` (1–500, no en blanco), `language` (`en` \| `es`), `limit` (≥1, recortado a 12; 8 por defecto) | `{results: [{source, path, heading, text, score, lang}]}` (vacío con el índice vacío); 409 `assistant.provider_not_configured`, 503 `assistant.provider_unavailable` | `ASSISTANT_DOCS_RATELIMIT` 600/h |
| `/internal/speech/transcribe` | `hub`, `audio` (base64, ≤2 MB), `mime_type`, `language` | `{text, language}` | `ASSISTANT_TRANSCRIBE_RATELIMIT` 120/h |
| `/internal/speech/synthesize` | `hub`, `text`, `language` (`es` \| `en`), `voice` (opcional, un id de `media.VOICES`) | `audio/mpeg` de Azure AI Speech (≤4096 caracteres leídos); 422 con una voz o un idioma fuera del catálogo; 503 `assistant.speech_unavailable` sin el proveedor de voz con clave; 502 si Azure falla | `ASSISTANT_SYNTHESIZE_RATELIMIT` 120/h |
| `/internal/assistant/report` | `hub`, `message_id`, `reason` (`incorrect`, `harmful`, `instructions`, `other`), `comment`, `question`, `answer` | 202 `{sent, duplicate}`; 503 `assistant.report_not_sent` | `ASSISTANT_REPORT_RATELIMIT` 60/h |

- **Frames del turno en directo** (`data: <json>`): `text_delta {text}`, `function_call {name, call_id, arguments}`
  (una herramienta del Hub), `response {output, usage, continuation}` (si no falló), `error {code, message,
  retriable}` (fallo del proveedor tras empezar), `usage {used, limit, resets_at, demo}` y `[DONE]`. Lo que se
  decide antes del modelo es un estado HTTP sin stream: 413/422, 503 `assistant.no_model` o
  `assistant.provider_not_configured` y 429 `assistant.quota_exceeded` (`upgrade_required`, `used`, `limit`,
  `resets_at`, `demo`).
- **Continuación**: con herramientas del Hub, el turno acaba con `continuation` (firmado con `CONTINUATION_SALT`,
  15 min, un solo uso por la caché, atado al negocio y a los `call_id`). El Hub vuelve a mandar la conversación con
  los resultados y ese token: no toma mensaje. Sin token (o caducado, usado, de otro negocio o de otras llamadas),
  la vuelta cuenta: arregla el «último mensaje del mes» del producto viejo, que dejaba seguir gratis.
- **El cupo lo cuenta erplora.com** (`assistant.message.claim`: un `UPDATE … WHERE messages < limit`;
  `assistant.message.release` si el turno no contestó nada, al mes en que se tomó; `assistant.usage.record` para
  tokens, huellas, dictados, caracteres y coste), en `AssistantUsage` (una fila por negocio y mes; una demo, una en
  su vida, y las de más de un día se olvidan al nacer otra). El límite es `Plan.assistant_messages_per_month` del
  plan efectivo (`hubs.queries.effective_plan`); una demo, `ASSISTANT_DEMO_MESSAGES` (10). El Hub no cuenta: enseña
  lo que dicen `usage` y el frame `usage` (aviso al 80 % y bloqueo al 100 % con esas cifras).
- **Herramientas de erplora.com** (`assistant/server_tools.py`): `current_datetime`; como mucho `MAX_ROUNDS` (5)
  llamadas al modelo por turno. Ganan a una herramienta del Hub con el mismo nombre. La búsqueda web (Tavily) y el
  tipo de cambio (Frankfurter) del producto viejo no se portan en la etapa TPV (PLAN §30, ronda 2026-10-22b): ni
  herramienta, ni regla de citar en las instrucciones, ni ajuste; F14 queda `parcial` hasta la etapa ERP.
- **Adjuntos** (`assistant/attachments.py`): `image_url` con `data:` de imagen, `input_file` con `filename`,
  `mime_type` y `data`; `MAX_ATTACHMENT_BYTES` (12 MB de base64) por adjunto, `MAX_ATTACHMENTS` (20) por
  conversación, `MAX_EXTRACTED_CHARS` por documento, zip comprobado antes de abrirlo; nada a disco (un test lo vigila
  con un audit hook de Python, `test_attachments.py`). Tampoco el cuerpo de la petición: Django lo pasaría a un
  temporal en disco por encima de `FILE_UPLOAD_MAX_MEMORY_SIZE` (2,5 MB) antes de la vista; `config/asgi.py`
  (`BodiesInMemory`) guarda en memoria el de `/internal/assistant/*` y `/internal/speech/*` hasta `TURN_BODY_BYTES` y
  descarta lo que pase (la puerta contesta 413), `test_body_in_memory.py`.
- **La documentación** (`docs_search`, ASSISTANT-F28): calcula la huella de la pregunta con
  `queries.prepare_questions` (fuera de toda transacción, en la caché un día) y corre la misma operación que el panel,
  `assistant.docs.search`, como la plataforma (`platform_context()`) en el `language` del cuerpo: una sola búsqueda
  para los dos asistentes y un solo índice (`DocChunk`). No toma mensaje ni apunta tokens (una pregunta son unas
  decenas). En el Hub es la herramienta `base__docs__search` (`base.docs.search`, ERPlora/hub).
- **Huellas y voz** (`assistant/media.py`): el proveedor de servicios es el `AIProvider` de slug
  `ASSISTANT_SERVICE_PROVIDER` («openai»), de API OpenAI, activado y con clave (`assistant.service.connection`);
  modelos fijos `text-embedding-3-small` y `whisper-1`. La lectura en voz alta va al proveedor de voz, el `AIProvider`
  de slug `ASSISTANT_SPEECH_PROVIDER` («azure-speech»), de API `azure_speech`, activado y con clave
  (`assistant.speech.connection`; sin él, 503 `assistant.speech_unavailable`): su `base_url` es el endpoint de su
  región (`DEFAULT_BASE_URLS`: Suecia Central) y su clave va en `Ocp-Apim-Subscription-Key`. SSML con el texto
  escapado, voces DragonHD de `media.VOICES` (el mismo catálogo e ids que `@erplora/ui`), mp3
  `audio-24khz-48kbitrate-mono-mp3`, 20 s de tope; sus fallos son `MediaFailed`, como los de OpenAI. Un proveedor de
  `SPEECH_KINDS` no contesta turnos: sus modelos no se ofrecen, no se eligen ni se enrutan (`choosable_models`,
  `can_answer`), y su ficha del admin no tiene «Elegir modelos del proveedor» ni lista de modelos
  (`AIProvider.reads_aloud`).
- **Privacidad**: ni la conversación, ni los adjuntos, ni el audio, ni el texto leído van a la BD, a un log o al
  auditlog; del fallo de un proveedor el log solo lleva el estado (`test_privacy.py`). Ninguna variable `key`,
  `token` ni `api_key` en una llamada al logger (`test_guardrails.py`).
- **Ajustes nuevos** (`config/settings.py`, con valor seguro por defecto): `ASSISTANT_*_RATELIMIT`,
  `ASSISTANT_DEMO_MESSAGES` y `ASSISTANT_SERVICE_PROVIDER`.
- **Tests** (todos contra `assistant/tests/fake_provider.py`, nunca un proveedor real): `test_internal_caller.py`
  (F11), `test_turn.py` (F12, F13, F15), `test_server_tools.py` (F14), `test_ratelimit.py` (F16),
  `test_privacy.py` (F17), `test_quota.py` (F18), `test_attachments.py` (F19), `test_embeddings.py` (F20),
  `test_speech.py` (F21, F22), `test_report.py` (F23), `test_admin_usage.py` (F24) y `test_internal_docs.py` (F28); `assistant/tests/doors.py`
  firma como el Hub, lee los frames y cuelga a medias (`hang_up`). e2e de las puertas y del admin:
  `tests/e2e/panel/assistant-gateway.spec.ts`. El dictado del panel: `base/tests/test_assistant_transcribe.py` y
  `tests/e2e/panel/assistant-dictation.spec.ts` (`-denied`: el micrófono que el navegador deniega).
- Trampas del producto viejo cubiertas: saas#2531 (el freno se gastaba antes de comprobar la firma:
  `test_internal_caller.py`, `test_speech.py`), saas#2445 (el nombre del fichero en el log: `test_attachments.py`),
  saas#2599 (la demo sin tope: `test_quota.py`).

### El asistente del panel (`base/assistant.py`, ASSISTANT-F25, F26)

- **Rutas** (`base/api.py`, con sesión; las mismas que el Hub): `POST /api/assistant/turn` (`base.assistant.turn`,
  `text/event-stream`; cuerpo hasta `TURN_BODY_BYTES` con `base/request_body.py` y en memoria por
  `config.asgi.IN_MEMORY_PATHS`), `GET /api/assistant/usage` (`base.assistant.usage`) y `POST /api/assistant/report`
  (`base.assistant.report`: el freno `ASSISTANT_REPORT_RATELIMIT` de la puerta `report` del Hub, por cuenta, 429
  `rate_limited` sin correo; 503 `base.assistant_report_not_sent`) y `POST /api/assistant/transcribe`
  (`base.assistant.transcribe`; cuerpo hasta `TRANSCRIBE_BODY_BYTES`, también en memoria) y `POST /api/assistant/speak`
  (`base.assistant.speak`, `audio/mpeg`). Permiso `assistant.ask` del rol `account` en las cinco (sin él, 403).
- **Herramientas**: toda operación del SaaS declara `ai=` (`live.E017`): `AI(description=…, risk=…)` o `INTERNAL` con
  su motivo en un comentario. `catalog(ctx)` = las `AI` que la cuenta puede usar, en todas las apps (son de
  plataforma); en la superficie de la cuenta (`base.surface`) sin las de la pantalla Tienda (`navigation.WEB_ONLY`).
  `relevant` con `ALWAYS = ("hubs.business.list", "assistant.docs.search")` y las palabras de las pantallas del menú. La tarjeta
  (`PanelWords`) nombra el negocio por `hubs.business.list` de la cuenta y la pantalla del panel; sus datos salen por
  `AssistantFieldOut` con todas las marcas de `live.assistant.field` (`titled`, `signed`, `named`, `money`), así que una
  lista que el servidor dijo elemento a elemento llega con `named` y la tarjeta de `@erplora/ui` dice sus elementos (hoy
  ninguna escritura del panel manda una lista; guarda: `TestTheCardOfAList`, saas#181). `billing.plan.change`
  es `INTERNAL` a propósito (saas#211): cobra en el acto, así que se hace en la Tienda (BILLING-F11), cuyo diálogo pide
  al servidor el `proration_date` reciente y enseña antes lo que se cobra. El modelo dice en qué pantalla se hace y la
  enlaza (`instructions`); guarda: `test_the_account_gets_the_saas_tools_and_none_of_what_is_internal`.
- **La pasarela en proceso**: `turn_frames` → `assistant.turn.spend` (cubo `turn` por `user:<id>`) → `turn.start`
  (cupo) → `turn.frames` → `settle`; un `turn.Refused` es el primer marco `error` (`assistant.quota_exceeded` con
  `used/limit/resets_at/demo`, `assistant.rate_limited` + `retry_after`, `assistant.too_large`,
  `assistant.unavailable`), como `_refusal` del Hub. Las puertas del Hub (`internal.py`) usan las mismas piezas.
- **El dictado** (F21): la operación (`database=False`) es la puerta: sesión, permiso, cubo `transcribe` por `user:<id>`
  (`ASSISTANT_TRANSCRIBE_RATELIMIT`, 429 `rate_limited`) e idioma (el pedido o el de la cuenta). La ruta espera después
  al proveedor, sin transacción abierta, con `assistant.internal.dictation`, la misma pieza que la puerta `transcribe`
  del Hub, y lo anota en la fila del mes de la cuenta (`transcriptions`), sin tocar sus mensajes. `dictation_refusal` da
  los códigos de la operación del Hub: 413 `base.assistant_audio_too_long`, 422, 503
  `assistant.provider_not_configured` y 503 `base.assistant_transcribe_failed`, que no nombra al proveedor.
- **La lectura en voz alta** (F22): como el dictado, la operación (`database=False`) es la puerta: sesión, permiso, cubo
  `synthesize` por `user:<id>` (`ASSISTANT_SYNTHESIZE_RATELIMIT`, 429 `rate_limited`) e idioma (el pedido o el de la
  cuenta; inglés si el suyo no tiene voces); el texto, el idioma y la voz los valida `assistant.schemas.SpeechIn` antes
  de gastar el cubo. La ruta espera después a Azure con `assistant.internal.speech`, la misma pieza que la puerta
  `synthesize` del Hub, y anota los caracteres en la fila del mes de la cuenta (`speech_characters`). `speech_refusal`
  da 503 `assistant.speech_unavailable` sin el proveedor de voz con clave y 503 `base.assistant_speech_failed`, que no nombra al
  proveedor. El frontend del panel la pide con `speak` de `assistant/frontend/options.ts` (`fetchFile` del SDK con
  POST, sesión y CSRF: el mp3 o el `ApiError` del sobre, y entonces lee el dispositivo); la CSP del panel deja
  reproducir su `blob:` (`media-src`). e2e: `tests/e2e/panel/assistant-voice.spec.ts`.
- **Cupo por cuenta**: `Caller(user_id=…)`, una fila `AssistantUsage(user, month)` (check «negocio, demo o cuenta»,
  única por cuenta y mes; migración `0003_account_usage`, que al volver atrás borra las filas de cuentas),
  `ASSISTANT_ACCOUNT_MESSAGES` (30).
- **El aviso por correo de los mensajes** (ASSISTANT-F29, saas#204): `assistant/emails.py` (`send_messages_near` y
  `send_messages_spent`, con `branded_message`; un correo que no sale se registra como `assistant.mail.not_sent` y
  devuelve `False`, nunca lanza). Las marcas son dos columnas nulas de la fila de la cuenta, `near_warned_at` y
  `spent_warned_at` (migración `0006_account_quota_mails`, que al volver atrás solo las quita). `message_claim`, solo
  con `data.user_id` y también cuando `claimed` es falso (para que el reintento alcance al último), llama a
  `_warn_the_account`: `_warning_due` da `spent` con el cupo gastado y `near` desde `NEAR_FROM` (4/5, el `NOTE_FROM` de
  `usageNote` de `@erplora/ui`), coge la marca con `UPDATE … WHERE <marca> IS NULL` (dos turnos a la vez: uno la
  coge), escribe `assistant.usage.warned` en la misma transacción y manda el correo con
  `transaction.on_commit(partial(_mail_the_warning, …), robust=True)`, que suelta su propia marca si no sale. El e2e
  fija `ASSISTANT_ACCOUNT_MESSAGES=2`: ahí solo sale el del 100 %, a la carpeta de correos del e2e, y
  `assistant-panel.spec.ts` comprueba que sale una sola vez y en el idioma de la cuenta.
- **El chat** (`assistant/frontend/`): el del Hub, de `@erplora/ui/components` (`AssistantPanel`, `AssistantButton`,
  `AssistantEmpty`), configurado en `options.ts` (`SAAS_ASSISTANT`: turno en `/api/assistant/turn`, sin `?surface=`,
  que el servidor lee de la sesión; cupo, denuncia y dictado por `base.assistant.usage|report|transcribe`; `canUse` =
  `assistant.ask`; nadie sube de plan). `frontend/main.ts` lo monta con `chrome: { topbar: AssistantTopbar, background:
  AssistantBackground }`, bajo demanda, y lo olvida al cerrar sesión. Sus palabras van en el catálogo de la entrada
  (`saas.assistant.*` de `frontend/locale`, porque `assistant` es el espacio del chat compartido): el verbo de cada
  escritura `AI` (`card.operations`, una por escritura: `base/tests/test_assistant_panel_words.py`), el de cada acción
  (`card.actions`), las cuatro pantallas, el vacío y sus atajos; la frase bajo el cupo agotado, donde nadie sube de
  plan, es `spentNoteKey: 'saas.assistant.errors.quotaSpentAccount'` de `SAAS_ASSISTANT` (opción del paquete, ui#49),
  y las palabras del chat (`assistant.*`) van tal cual.
- **Tests**: `base/tests/test_assistant_turn.py`, `base/tests/test_api_assistant.py`,
  `assistant/tests/test_account_quota.py`, `test_emails.py` (ASSISTANT-F29, también por la ruta del panel y con dos
  turnos a la vez), `test_admin_usage.py` (la cuenta en el admin) y `test_privacy.py` (la ruta
  del panel no guarda la conversación); Vitest de `assistant/frontend/` y `frontend/main.test.ts`; e2e
  `tests/e2e/panel/assistant-panel.spec.ts` (proveedor `tests/e2e/assistant-provider.ts`, siembra
  `assistant_seed.py panel`, `ASSISTANT_ACCOUNT_MESSAGES=2` en `panel/project.ts`).
- **QA**: capa 1, `base/tests/test_assistant_asks.py` (cada frase de `asks` llega a su herramienta, sin modelo ni red);
  capa 2, con el modelo de verdad (`QA_REAL_PROVIDER=1`) y frases que no están en `asks`:
  `tests/e2e/panel/assistant-probes.spec.ts` (sondas en `tests/e2e/qa/probes/`) y la batería
  `tests/e2e/panel/assistant-battery.spec.ts`. Receta en `tests/e2e/README.md`, «Sondas del asistente (capa 2)»; el
  catálogo que leen sale de `manage.py export_assistant_catalog`.

### La documentación del asistente del panel (`assistant/knowledge.py`, ASSISTANT-F27)

- **Índice**: `assistant.DocChunk` en la BD de control (`id` UUIDv7, `source` `help` | `app_doc` | `workbook` |
  `plans`, `path`, `lang`, `heading`, `text`, `content_hash` único, `embedding` `vector(1536)`, `indexed_at`), con
  búsqueda exacta, sin índice aproximado: la migración `0005_drop_doc_chunk_hnsw` quitó el `HnswIndex`, porque filtraba
  el idioma después de sus 40 filas más cercanas y perdía fragmentos, también con todas las filas vivas (run 41600831045;
  `TestTheIndexLosesNothing`). Unos 3000 fragmentos se leen en 5 ms. La extensión `vector` (pgvector) no es de confianza en
  Aurora (solo `rds_superuser`): la crea antes, como usuario maestro, el arranque de plataforma del Hub
  (`bootstrap_databases`) en `saas` y `pre_saas`; la migración `0004_doc_chunks`
  (`CREATE EXTENSION IF NOT EXISTS vector`) la encuentra antes de mirar permisos, así que solo la crea en local y en
  CI (imagen `pgvector/pgvector`, `.github/workflows/test.yml`); al volver atrás borra la tabla y su índice y deja la
  extensión (en Aurora es del usuario maestro: `saas_migrator` no podría borrarla). `django.contrib.postgres` instalado por el índice.
- **Fragmentos** (`knowledge.chunk_markdown`): corte por `##` y `###` (las preguntas de la FAQ son `###`), títulos
  en ruta («Preguntas frecuentes > Acceso > ¿Por qué…?»), ventana de 220 palabras con solape de 50, comentarios HTML
  fuera; la huella se calcula sobre títulos + texto, hasta 6000 caracteres. `content_hash` = sha256 de fuente, ruta,
  idioma, títulos y texto (`models.content_hash`): el mismo texto en otro sitio es otro fragmento.
- **Fuentes** (`knowledge.SOURCES`): `docs/<lang>/help/*.md`; `apps.doc.list` (el markdown de cada app que la tienda
  lista, por idioma; lo escribe el Hub con cada versión); la parte de usuario de `accounts|hubs|billing|apps|public`
  `/WORKBOOK.md` (hasta «## Para quien lo mantiene»; sin ese título falla, `WorkbookWithoutCut`) y `WORKBOOK.en.md`;
  y `plans`, un documento por idioma desde `hubs.plan.list` (precio al mes y al año sin IVA, personas, dispositivos,
  apps a la vez, mensajes del asistente y de WhatsApp, si es solo de mejora y lo que incluye).
- **`index_docs [--full] [--dry-run]`**: por fuente, `assistant.docs.list` (los hashes que ya tiene), embebe solo los
  nuevos (`--full`: todos) en lotes de 64 con `media.embed` y el proveedor de servicios
  (`ASSISTANT_SERVICE_PROVIDER`), y escribe cada lote con `assistant.docs.index` (una transacción por lote; el último
  lleva `keep`, lo que la fuente guarda, y borra lo demás: una pasada que falla a medias deja un documento cambiado
  con sus fragmentos viejos, buscable). Lote a lote porque escribir una fuente de una vez llegó a
  688 MB en local con las 26 apps del Hub (saas-cron tiene 512 MB); así, 266 MB. Una línea por fuente en el log y en
  pantalla: `assistant.index_docs source=… chunks=… embedded=… deleted=… tokens=… cost_usd=…`; sin fila de
  `AssistantUsage` (gasto de la plataforma). Sin proveedor sale con código 2 sin escribir nada; si el proveedor falla
  sale con error, lo ya escrito se queda y no se borra nada (la siguiente pasada hace el resto). Advisory lock
  `hashtext('erplora.saas.index_docs')` (`hubs.services.run_exclusively`). Evento `assistant.docs.indexed` por lote.
  Medido en local (2026-10-31): 68 fragmentos de ayuda, 2162 de las apps del Hub, 685 de los WORKBOOK y 14 de planes;
  un indexado completo ≈ 680 000 tokens ≈ 0,014 $; una pasada sin cambios, 0 llamadas.
- **Programación**: `index-docs-daily` de `platform_schedule_specs` en ERPlora/aws (aws#28, mergeada el 2026-10-31),
  diario a las 06:50 UTC en `saas-cron`; encendida en producción desde el `apply` del 2026-11-01 y con la primera pasada
  el 2026-11-02. Para adelantarla, se lanza a mano como tarea suelta de `saas-cron` (`saas/README.md`, «Operación»).
- **Donde no se vende** (PLAN-SAAS §3.6 punto 6, `base.surface.sells_nothing`): `base.assistant.nothing_sold_here` abre
  las instrucciones del turno con la regla y las dos frases de las pantallas (en el catálogo de Django, y un test las
  compara con `hubs` y `billing` de `frontend/locale`); el catálogo no ofrece lo de la tienda, tampoco `hubs.plan.list`;
  y `assistant.docs.search` no lee `queries.SELLING_WORKBOOKS` ni los planes. La redacción la pone el modelo: se mide con
  las sondas `*-app-*` de `tests/e2e/qa/probes/` (capa 2). Va la primera y dice «tu respuesta entera es esta frase» porque
  medido con el modelo de verdad, detrás de las demás reglas o como consejo, a veces mandaba a Facturación.
- **`assistant.docs.search`** (`queries.py`, `kind="query"`, `assistant.ask`, herramienta `assistant__docs__search`):
  nunca llama al proveedor. La huella de la pregunta la calcula antes `queries.prepare_questions`, fuera de toda
  transacción (la ruta del turno, `base.assistant.prepare`, para cada búsqueda que pidió el modelo; una llamada para
  todas, tope de espera de 10 s, nunca falla), y la guarda en la caché de Django un día por el sha256 de la pregunta
  normalizada (espacios y mayúsculas fuera): ninguna conexión espera al proveedor dentro de una transacción. Sin la
  huella en la caché, 409 si no hay proveedor y 503 si no se pudo calcular. Orden por `CosineDistance` en el idioma de la persona (`es` para cualquier español, si no `en`); con menos
  de 3 a distancia < 0,55 se suman los de `en`; `limit` 8 por defecto, recortado a 12. En `base/assistant.py` está en `ALWAYS` (una
  pregunta de «cómo se hace» no comparte palabras con la herramienta y sin eso quedaba fuera de las 40) y su recibo no
  nombra una pantalla del panel sino la ayuda.
- **Tests**: `assistant/tests/test_knowledge.py`, `test_index_docs.py` (con la migración de ida y vuelta y sin índice
  aproximado) y `test_docs_search.py` (también por el turno del panel); `apps/tests/test_queries.py` (`apps.doc.list`).

## Lo que queda fuera

- **Buscar en la web y el tipo de cambio entre monedas** (ASSISTANT-F14): llegan con la etapa ERP — saas#202.

## Lo que NO hace, a propósito

- No enseña nunca una clave guardada, ni a un superusuario: se vuelve a escribir.
- No tiene pantalla en el Hub: el chat de cada negocio es la app del Hub. En el panel de erplora.com su única pantalla
  es el chat de la cuenta (ASSISTANT-F25), el mismo componente que el del Hub.
- No guarda aparte una copia de la clave de cifrado (el producto viejo la copiaba a un almacén externo): la guarda el
  gestor de secretos de la nube, con sus versiones y su plazo de recuperación, y una credencial perdida se vuelve a
  escribir.
- No guarda la conversación, ni un historial de chats: la conversación es del navegador de la persona, en el Hub o
  en el panel.
- No habla por WebSocket: el turno en directo va por HTTP (sin channels), y el de una vez, en una respuesta.
- No tiene «niveles» del asistente con su cupo, su precio y su modelo (el producto viejo, con su siembra y su admin):
  el cupo es el del plan, que se edita en «Planes», y el modelo que contesta es uno para todos, con su reserva.
- No vende paquetes de mensajes sueltos: más mensajes es subir de plan.
- No usa dos modelos por turno (uno que razona y otro que ejecuta): el producto viejo lo tenía apagado.
- No cambia de plan desde el chat: cobra en el acto, y lo que se cobra se ve y se confirma en la Tienda (BILLING-F11);
  el asistente lo dice y enlaza la Tienda (saas#211).
- No busca en la web ni da tipos de cambio: llegan con la etapa ERP (PLAN §30, saas#202).
