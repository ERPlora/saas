# Workbook — Asistente de IA (assistant)
Prefijo: ASSISTANT
Alcance MVP: fase 1 (la pasarela de IA de erplora.com: los proveedores que paga ERPlora, sus claves cifradas, sus modelos, qué modelo contesta y la prueba de un modelo antes de que conteste; el turno del Hub y la voz llegan con la parte 2 del porte)
Estado de la app: en construcción

> Manual de uso y especificación de la app `assistant` del SaaS (erplora.com). Cuenta lo que hace el personal de
> ERPlora para que el asistente de IA conteste: dar de alta un proveedor de modelos y su clave, elegir sus modelos,
> decidir qué modelo contesta y probar un modelo antes. No se publica en la tienda: es la referencia del equipo y
> de la QA. Ningún cliente ve estas pantallas; el asistente que usa el negocio vive en el Hub.

## Para qué sirve y para quién

El Hub nunca habla con el proveedor de un modelo de IA: habla con erplora.com, que guarda la clave del proveedor,
decide qué modelo contesta y lo llama. Así la clave no sale nunca de erplora.com y el gasto de IA se controla en un
solo sitio.

- La clave de cada proveedor se guarda cifrada; se escribe una vez y nunca se vuelve a enseñar: solo sus cuatro
  últimos caracteres, para reconocerla.
- Hay un modelo que contesta y, si falla su proveedor, uno de reserva.
- Antes de poner un modelo a contestar se puede probar desde el admin, con lo que tarda, lo que consume y lo que
  cuesta.

Quién la usa:

- El **personal de ERPlora**, en el admin de erplora.com, con los permisos de la pasarela de IA. El grupo de
  soporte no los tiene: las claves son gasto de ERPlora.
- El **sistema**: el turno del asistente del Hub elige con esta configuración el modelo que contesta.

## Referencia adoptada

- **Pasarelas de IA** (OpenRouter, Portkey, Cloudflare AI Gateway, Vercel AI Gateway, el router de LiteLLM): un
  modelo principal y otro de reserva si el proveedor falla; las claves de los proveedores en la pasarela, nunca en
  el cliente.
- **Las consolas de los proveedores** (OpenAI, Anthropic, Google AI Studio, DeepSeek): la clave se enseña una vez
  al crearla y después solo su final; la lista de modelos sale de la API del propio proveedor
  (https://platform.openai.com/docs/models, https://docs.anthropic.com/en/docs/about-claude/models).
- **El producto viejo de ERPlora** (`apps/assistant` del SaaS): proveedores con su clave y sus modelos en una sola
  ficha, la política de qué modelo contesta y el probador con coste y latencia.

## Antes de empezar

- erplora.com necesita su clave de cifrado de credenciales en el entorno; sin ella no se puede guardar ninguna
  clave de proveedor y la ficha lo dice al guardar.
- Cada proveedor necesita una clave activa que se pueda leer para que sus modelos contesten o se puedan probar.
- Los precios por millón de palabras-unidad (tokens) de cada modelo los escribe el personal: las API de los
  proveedores no los dan. Sin precio, la prueba dice el consumo y un coste de cero.

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

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | La carga normal de una página del admin; al probar un modelo, «Enviando…» y el botón «Enviar» apagado hasta que acaba («Hecho.»). |
| Vacío | «0 proveedores de IA» y la lista vacía; un proveedor sin clave dice «Sin clave»; sin modelos que puedan contestar, «Todavía no puede contestar ningún modelo: añade un proveedor con su clave y elige sus modelos.» |
| Error | En «Elegir modelos del proveedor», el motivo en rojo: «Este proveedor no tiene ninguna clave activa: añade una en su ficha y vuelve a intentarlo.», «El proveedor no ha dado sus modelos: …» o «El proveedor no tiene modelos de conversación en su lista.»; en las fichas, el error en rojo junto al campo: «Usa una dirección https: la clave del proveedor viaja a ella.», «Escribe la clave del proveedor.», «La clave de cifrado de las credenciales no está configurada: no se puede guardar ninguna clave de proveedor.»; al probar un modelo, en rojo: «El modelo no ha contestado: …», «Demasiadas pruebas en un minuto: espera un momento y vuelve a intentarlo.» o «No se ha podido enviar la prueba: revisa la conexión y vuelve a intentarlo.». |
| Sin permiso | Sin los permisos de la pasarela, el admin contesta que no tiene permiso; quien solo puede mirar ve las fichas sin el campo «Clave». |

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

### ASSISTANT-F01 Dar de alta un proveedor de IA
<!-- origen: fi:saas/support/auth-services#modelo-aiprovider, fi:saas/django-admin#admin-aiprovider, old-saas:SAAS_ASSISTANT-F22 -->
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
<!-- origen: fi:saas/support/auth-services#modelo-aiprovidercredential, fi:saas/django-admin#admin-aiprovidercredential -->
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
<!-- origen: fi:saas/support/auth-services#service-providers-base-provider-toolspec-turnrequest-providerevent, fi:saas/support/auth-services#service-providers-factory-get_provider, fi:saas/support/auth-services#service-providers-anthropic_provider-anthropicprovider, fi:saas/support/auth-services#service-providers-openai_provider-openaiprovider, fi:saas/support/auth-services#service-providers-gemini_provider-geminiprovider, fi:saas/support/auth-services#service-providers-deepseek_provider-deepseekprovider -->
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
Si falla: si el proveedor rechaza la clave o la petición, el turno termina con su motivo y se marca como un fallo que no se arregla repitiendo; si no contesta, tarda demasiado, va saturado o limita el ritmo, termina con un fallo que otro intento puede arreglar (para pasar al modelo de reserva); el motivo nunca lleva la clave. Un proveedor sin clave o con una API desconocida no se llama.
Implicados: ASSISTANT-F04, ASSISTANT-F06, ASSISTANT-F07

### ASSISTANT-F04 Elegir los modelos de un proveedor
<!-- origen: fi:saas/support/auth-services#modelo-aimodel, fi:saas/django-admin#admin-aimodel -->
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
<!-- origen: fi:saas/support/auth-services#modelo-airoutingpolicy, fi:saas/django-admin#admin-airoutingpolicy-singleton-tester, fi:saas/auth-services#routing-ai-configuracion-de-proveedores-modelos-admin, old-saas:SAAS_ASSISTANT-F23 -->
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
<!-- origen: old-saas:SAAS_ASSISTANT-F05, fi:saas/support/auth-services#signals-provider-cache-invalidation -->
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
- Clientes (`assistant/providers/`): `httpx` contra cada API (sin SDK ni LiteLLM), sin caché, uno por llamada;
  todos terminan con un solo `finish` y un fallo es un `error` con `retriable`, nunca una excepción. Se prueban contra
  `assistant/tests/fake_provider.py` (servidor HTTP en `127.0.0.1` que habla el formato de cada proveedor).
- Trampas del producto viejo cubiertas: saas#528 (clave en claro en la base de datos: `test_fields.py`), saas#2489
  (nombre de la app sin traducir en el admin: `test_apps.py`).

## Lo que NO hace, a propósito

- No enseña nunca una clave guardada, ni a un superusuario: se vuelve a escribir.
- No tiene pantalla en el panel de erplora.com ni en el Hub.
