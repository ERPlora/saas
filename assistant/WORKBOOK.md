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
ve sin poder cambiarla.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | La carga normal de una página del admin. |
| Vacío | «0 proveedores de IA» y la lista vacía; un proveedor sin clave dice «Sin clave»; sin modelos que puedan contestar, «Todavía no puede contestar ningún modelo: añade un proveedor con su clave y elige sus modelos.» |
| Error | En «Elegir modelos del proveedor», el motivo en rojo: «Este proveedor no tiene ninguna clave activa: añade una en su ficha y vuelve a intentarlo.», «El proveedor no ha dado sus modelos: …» o «El proveedor no tiene modelos de conversación en su lista.»; en las fichas, el error en rojo junto al campo: «Usa una dirección https: la clave del proveedor viaja a ella.», «Escribe la clave del proveedor.», «La clave de cifrado de las credenciales no está configurada: no se puede guardar ninguna clave de proveedor.». |
| Sin permiso | Sin los permisos de la pasarela, el admin contesta que no tiene permiso; quien solo puede mirar ve las fichas sin el campo «Clave». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| ASSISTANT-F01 | Dar de alta un proveedor de IA | hecho |
| ASSISTANT-F02 | Guardar la clave de un proveedor sin que se vea | hecho |
| ASSISTANT-F03 | Hablar con cada proveedor en su propia API | hecho |
| ASSISTANT-F04 | Elegir los modelos de un proveedor | hecho |
| ASSISTANT-F05 | Elegir qué modelo contesta | hecho |

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
- Clientes (`assistant/providers/`): `httpx` contra cada API (sin SDK ni LiteLLM), sin caché, uno por llamada;
  todos terminan con un solo `finish` y un fallo es un `error` con `retriable`, nunca una excepción. Se prueban contra
  `assistant/tests/fake_provider.py` (servidor HTTP en `127.0.0.1` que habla el formato de cada proveedor).
- Trampas del producto viejo cubiertas: saas#528 (clave en claro en la base de datos: `test_fields.py`), saas#2489
  (nombre de la app sin traducir en el admin: `test_apps.py`).

## Lo que NO hace, a propósito

- No enseña nunca una clave guardada, ni a un superusuario: se vuelve a escribir.
- No tiene pantalla en el panel de erplora.com ni en el Hub.
