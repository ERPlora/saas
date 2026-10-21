# Workbook — Negocios (hubs)
Prefijo: HUBS
Alcance MVP: fase 1 (los negocios de cada cuenta de erplora.com: crearlos, esperar a que estén listos, verlos en la lista y entrar en ellos)
Estado de la app: en construcción (parte 1 de 4: crear el negocio, los planes, esperar a que esté listo, la lista, la portada del panel, entrar y abrirlo en otro dispositivo)

> Manual de uso y especificación de la app `hubs` del SaaS (erplora.com). Cuenta cómo se crea un negocio, qué
> pasa mientras se prepara, cómo se ve la lista de negocios y cómo se entra en cada uno desde el navegador o desde
> la aplicación instalada. Esta parte del manual no se publica en la tienda: es la referencia del equipo y de la
> QA. Los ajustes, la dirección web, la baja y la purga (parte 2), las personas de cada negocio (parte 3) y el
> plan, los derechos y lo que el negocio recibe de erplora.com (parte 4) se escriben a continuación.

## Para qué sirve y para quién

Un negocio es el sitio donde se trabaja: su caja, su agenda y sus datos, con su propia dirección web
(`<nombre>.erplora.com`). Una cuenta de erplora.com crea sus negocios, los ve en una lista y entra en ellos sin
volver a escribir la contraseña. Todo negocio nace en el plan Gratis, sin tarjeta; el plan se cambia después.

- Cada cuenta tiene un negocio gratuito; para crear otro, el primero pasa antes a un plan de pago.
- Un negocio recién creado tarda unos segundos en estar listo: mientras tanto se ve «Preparando» y, si la persona
  lo acaba de crear, entra sola en cuanto está listo.
- La aplicación instalada (Windows y Android) empieza en la misma pantalla de entrada que erplora.com y, al abrir
  un negocio, se queda unida a él para usar la impresora, el cajón y el resto del hardware.

Quién la usa:

- **Cualquier persona con cuenta** crea su negocio y entra en los negocios de los que es miembro.
- **El propietario** ve la lista de sus negocios, recupera uno eliminado y cambia su plan.
- El **personal de ERPlora** mantiene los planes desde el admin.

## Referencia adoptada

- **Shopify y Square**: crear la tienda pide solo el nombre y el país, con la dirección propuesta mientras se
  escribe; la tienda nace en un plan de prueba o gratuito y el plan se elige después
  (https://help.shopify.com/en/manual/intro-to-shopify/initial-setup/sign-up).
- **Vercel y Netlify**: una lista de proyectos con su estado («Building», «Ready», «Error») que cambia sola, y la
  pantalla de espera que entra sola en cuanto está listo (https://vercel.com/docs/deployments).
- **Odoo y Toast**: un solo inicio de sesión para varios negocios, con el último usado arriba y la elección de
  dónde trabajar (https://www.odoo.com/documentation/18.0/applications/general/users.html).
- **Stripe**: los planes y sus precios los mantiene el personal en un panel propio, con el nombre y la descripción
  en cada idioma de venta (https://docs.stripe.com/products-prices/manage-prices).

## Antes de empezar

- Se entra en erplora.com. En desarrollo, el panel está en el puerto 8001 y cada correo queda en la carpeta de
  correo local en vez de enviarse.
- Para que un negocio pase de «Preparando» a «Activo», el servicio de los negocios tiene que estar en marcha: es
  quien avisa de que está listo.

## Pantallas

### Entrada (erplora.com y la aplicación instalada)
La tarjeta centrada de erplora.com, la misma que abre la aplicación instalada al arrancar. Sin sesión, el
formulario de entrar o crear la cuenta. Con sesión y sin negocios, «Crea tu negocio» con el formulario del alta;
con un negocio, «Hola, …» con «Abrir …» e «Ir al panel»; con varios, «¿Dónde trabajas hoy?» con el último abierto
arriba. Una invitación pendiente sale encima.

### Crear negocio
El formulario del alta: «¿Cómo se llama tu negocio?», «Nombre del negocio», «País» (sugerido por el idioma del
navegador), «Tipo de negocio (opcional)» con «Todavía no lo sé» y, debajo del nombre, «Tu dirección será …». En la
Entrada va en la tarjeta; en **Negocios**, en el diálogo «Crear negocio».

### Preparando
La barra en marcha y tres pasos: «Negocio creado», «Preparando tu negocio» (o «Instalando los módulos de …») y
«Se abre solo al terminar» en la Entrada o «Listo para abrir» en el diálogo.

### Negocios
La portada del panel: la lista de los negocios de la cuenta con «Negocio», «Dirección web», «Estado», «Plan»,
«Rol» y «Último uso», el buscador, «Crear negocio» y, por fila, «Abrir», «Gestionar» y «Recuperar». En el móvil
son tarjetas. Encima, las invitaciones, las ofertas de propiedad y las facturas sin pagar.

### Resumen del negocio
La página de cada negocio abre en su Resumen: el plan (con «Mejorar plan» o «Cambiar plan»), el uso y la tarjeta
«En tus dispositivos» con la dirección web del negocio, «Copiar dirección» y las aplicaciones para Windows y
Android.

### Tu negocio se está preparando
La página que enseña la dirección de un negocio que aún se prepara: «Tu negocio se está preparando» y «Tarda
unos segundos. Esta página se actualiza sola.».

### admin › Negocios › Planes
La ficha de cada plan para el personal: los textos en inglés y en español, el precio, qué incluye, sus límites y
sus precios de Stripe.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | La lista y la Entrada enseñan su esqueleto; «Crear mi negocio» se apaga mientras va la petición. |
| Vacío | Sin negocios, la lista y la Entrada son el formulario «Crea tu primer negocio» («Gratis y sin tarjeta: solo el nombre y el país.»). Una búsqueda sin resultados: «Nada coincide con la búsqueda» con «Mostrar todo». |
| Error | «No hemos podido cargar tus negocios» con «Reintentar»; un negocio que no se pudo preparar: «Sin preparar» y «No hemos podido prepararlo. Seguimos reintentándolo; si sigue fallando, avísanos.». |
| Preparando | La fila dice «Preparando» y «Lo estamos preparando. Se abre solo cuando esté listo.»; «Abrir» espera. |
| Sin conexión | «Reconectando… lo que ves puede tener unos segundos de retraso.» mientras vuelve la conexión en vivo. |
| Sin permiso | Un negocio de otra cuenta no existe para esa persona: no se lista ni se abre. |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| HUBS-F01 | Crear el negocio gratuito con una sola pregunta | hecho |
| HUBS-F02 | Crear el negocio gratuito desde la aplicación instalada | hecho |
| HUBS-F03 | Contratar un negocio de pago | hecho |
| HUBS-F04 | Esperar a que el negocio esté listo y entrar solo | hecho |
| HUBS-F05 | Mantener los planes en el admin | hecho |
| HUBS-F06 | Ver «tu negocio se está preparando» | hecho |
| HUBS-F07 | Dar el negocio por listo | hecho |
| HUBS-F08 | Reintentar lo que el negocio no recibió | hecho |
| HUBS-F09 | Ver la lista de negocios | hecho |
| HUBS-F10 | Ver la portada del panel | hecho |
| HUBS-F11 | Entrar en un negocio desde erplora.com | hecho |
| HUBS-F12 | Elegir el negocio en la aplicación instalada | hecho |
| HUBS-F13 | Abrir el negocio en otro dispositivo | hecho |
| HUBS-F14 | Ver los negocios por la API | hecho |

### HUBS-F01 Crear el negocio gratuito con una sola pregunta
<!-- origen: old-saas:SAAS_DASHBOARD-F01 fi:saas/support/hubs#modelo-hub -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Entrada › Crear negocio
Pasos:
1. Tras crear la cuenta y entrar sin ningún negocio, la Entrada enseña «Crea tu negocio» («Gratis y sin tarjeta: solo el nombre y el país.»).
2. Escribe el «Nombre del negocio»; debajo aparece «Tu dirección será …» con la dirección que propone el nombre. El «País» viene sugerido por el idioma del navegador y el «Tipo de negocio (opcional)» admite «Todavía no lo sé».
3. Pulsa «Crear mi negocio»: sale «Negocio creado: …» y la tarjeta pasa a **Preparando** (HUBS-F04).
Entra: el nombre, el país (uno de los 27 de la Unión Europea en los que vende ERPlora) y, si la persona lo sabe, el tipo de negocio; la sesión de la cuenta.
Sale: el negocio en el plan Gratis (sin tarjeta y sin prueba), con la persona como propietaria, su dirección sacada del nombre (si está cogida se numera, `bar-manolo-2`; una palabra reservada se completa sola) y quién paga, con el país del negocio. El servicio de los negocios recibe el alta en cuanto se guarda y, con el tipo de negocio, los módulos de su sector. Anota `hubs.business.created`.
Si falla: sin nombre, «Escribe el nombre de tu negocio.» y no se manda nada; un país fuera de la lista, el error en el campo. Si la cuenta ya tiene su negocio gratuito, no crea otro: el diálogo dice «Ya tienes un negocio gratuito» y ofrece «Cambiar el plan de …». Sin el plan Gratis disponible, «Ahora mismo no se pueden crear negocios. Inténtalo dentro de unos minutos.». Una cuenta del personal de ERPlora no crea negocios. Dos pulsaciones seguidas crean uno solo.
Implicados: accounts (la cuenta y la Entrada), el negocio (recibe su alta)

### HUBS-F02 Crear el negocio gratuito desde la aplicación instalada
<!-- origen: old-saas:SAAS_DASHBOARD-F02 -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Entrada (en la aplicación instalada) › Crear negocio
Pasos:
1. La aplicación recién instalada arranca en la Entrada de erplora.com; sin sesión, la persona entra o crea su cuenta ahí mismo.
2. Sin ningún negocio, la Entrada enseña «Crea tu negocio» con el mismo formulario de HUBS-F01 (nombre, país y tipo opcional, con la dirección propuesta mientras escribe).
3. Pulsa «Crear mi negocio»: la tarjeta pasa a **Preparando** y, cuando el negocio está listo, la aplicación entra sola en él y se queda unida a ese negocio (HUBS-F12).
Entra: lo mismo que HUBS-F01.
Sale: lo mismo que HUBS-F01, con el país y el tipo de negocio que la persona elige (la aplicación vieja no los preguntaba).
Si falla: los mismos avisos que HUBS-F01. Dentro de la aplicación no se vende nada: para cambiar de plan dice «Para cambiar de plan o añadir módulos, entra en erplora.com desde el navegador.».
Implicados: accounts (la Entrada), la aplicación instalada (arranca en la Entrada y se une al negocio)

### HUBS-F03 Contratar un negocio de pago
<!-- origen: old-saas:SAAS_DASHBOARD-F03 fi:saas/hubs#alta-de-terminal-crear-hub-checkout-stripe fi:saas/hubs#alta-de-terminal-por-api-checkout fi:saas/support/hubs#service-lifecycle-create_hub -->
Estado: hecho
Actor: propietario, integración
Pantalla: Negocios › Crear negocio, Resumen del negocio, Tienda
Pasos:
1. En **Negocios**, «Crear negocio» abre el diálogo con el formulario de HUBS-F01; el negocio nace en Gratis.
2. En el Resumen del negocio, la tarjeta del plan ofrece «Mejorar plan», que abre la Tienda con ese negocio elegido.
3. Elige el plan y el periodo y paga con el pago seguro de Stripe (BILLING-F07 y BILLING-F08); el negocio sigue funcionando todo el tiempo y cambia de plan en cuanto Stripe lo confirma.
4. Una integración hace lo mismo con la sesión de la cuenta: crea el negocio y después empieza su pago.
Entra: lo mismo que HUBS-F01 y, para pagar, el plan, el periodo, los datos de facturación y la tarjeta.
Sale: el negocio creado como en HUBS-F01 y, al pagar, su suscripción de pago (`hubs.subscription.changed`), con el plan nuevo enviado al negocio.
Si falla: los mismos avisos que HUBS-F01 al crear y los de BILLING-F08 al pagar; si la persona cierra el pago, no se cobra nada y el negocio sigue en Gratis, funcionando. La segunda empresa de una cuenta se crea después de pasar la primera a un plan de pago.
Implicados: billing (el pago y el plan), el negocio (recibe su plan)

### HUBS-F04 Esperar a que el negocio esté listo y entrar solo
<!-- origen: old-saas:SAAS_DASHBOARD-F04 -->
Estado: hecho
Actor: propietario
Pantalla: Preparando
Pasos:
1. Tras «Crear mi negocio», la Entrada enseña «Preparando …» («Suele tardar unos segundos.») con la barra y los tres pasos; en **Negocios**, el diálogo enseña lo mismo y la fila dice «Preparando».
2. La pantalla se actualiza sola: no hace falta recargar ni quedarse («Ir al panel mientras tanto»).
3. Cuando el negocio está listo, la Entrada lleva a la persona dentro del negocio sin volver a pedir la contraseña; el diálogo de **Negocios** dice «Tu negocio está listo» con «Abrir negocio».
4. Al propietario le llega además el correo «… ya está listo» con el enlace para abrirlo y el de su página en el panel.
Entra: el aviso de que el negocio está listo (HUBS-F07).
Sale: la entrada en el negocio con un pase de un solo uso, que nunca viaja en la dirección; el correo «ya está listo», una sola vez.
Si falla: si el negocio no se pudo preparar, la pantalla dice «No se ha podido preparar» y «Hemos guardado …, pero no se ha podido preparar. Seguimos reintentándolo; si sigue fallando, avísanos.», y entra sola si el reintento (HUBS-F08) lo arregla. Con varios negocios no entra sola en ninguno: la persona elige.
Implicados: accounts (el salto al negocio), el negocio (avisa de que está listo)

### HUBS-F05 Mantener los planes en el admin
<!-- origen: fi:saas/support/hubs#modelo-plan-alias-hubplan fi:saas/django-admin#admin-plan fi:saas/hubs#admin-django-plan-hub-plans-con-traduccion fi:saas/hubs#plans-rest-crud-admin-only fi:saas/support/hubs#otro-plantranslationoptions-translation-py -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: admin › Negocios › Planes
Pasos:
1. El personal abre la lista de planes, busca por identificador o nombre y filtra por «activo», «solo como mejora» o «interno».
2. En la ficha de un plan escribe su nombre, su descripción, las líneas de su tarjeta y su distintivo en inglés y en español, su precio mensual y anual, qué incluye (nivel de módulos, soporte, dominio propio, negocios, dispositivos y personas), los límites de su base de datos, los mensajes del asistente y de WhatsApp al mes y sus precios de Stripe.
3. Guarda: el cliente ve los textos en su idioma (el inglés cuando falta el español) en la Tienda y en la web de precios.
Entra: lo que escribe el personal.
Sale: el plan, con cada texto en inglés y en español. Gratis se ofrece al darse de alta y sin prueba; Pro, Enterprise y Max solo como mejora; un plan interno nunca se ofrece a los clientes.
Si falla: un precio que Stripe rechaza no se guarda y el plan se queda como estaba; sin Stripe, se guarda y avisa de que no se ha comprobado. Una cuenta sin la marca de personal no entra en el admin.
Implicados: billing (los precios en Stripe, BILLING-F28), public (la web de precios)

### HUBS-F06 Ver «tu negocio se está preparando»
<!-- origen: old-saas:SAAS_DASHBOARD-F44 -->
Estado: hecho
Actor: cualquiera
Pantalla: Tu negocio se está preparando
Pasos:
1. Quien abre la dirección de un negocio que aún se prepara ve «Tu negocio se está preparando» y «Tarda unos segundos. Esta página se actualiza sola.».
2. La página vuelve a mirar cada pocos segundos y, en cuanto el negocio está listo, enseña el negocio (o su entrada, sin sesión).
Entra: la dirección del negocio.
Sale: nada; la página no cambia el negocio.
Si falla: una dirección que no es de ningún negocio dice que no existe; la de un negocio eliminado dice que ya no está, con el camino de vuelta a erplora.com.
Implicados: el negocio (sirve la página)

### HUBS-F07 Dar el negocio por listo
<!-- origen: old-saas:SAAS_DASHBOARD-F29 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cuando el negocio termina de prepararse, avisa a erplora.com con una llamada firmada.
2. erplora.com lo pasa de «Preparando» a «Activo», apunta la hora y las pantallas de su propietario cambian solas.
3. Al propietario le llega el correo «… ya está listo», una sola vez.
Entra: el aviso firmado del negocio.
Sale: el negocio activo y la hora en que quedó listo; `hubs.business.ready`; el correo, tras guardar.
Si falla: un aviso sin firma válida, de otro negocio o de un negocio desconocido se rechaza y no cambia nada. Un negocio que se eliminó o se suspendió mientras tanto se queda como estaba y no se anuncia. Si el aviso no llega, la siguiente pasada de HUBS-F08 pregunta al negocio por un alta que lleva más de 2 minutos sin él.
Implicados: el negocio (manda el aviso)

### HUBS-F08 Reintentar lo que el negocio no recibió
<!-- origen: old-saas:SAAS_DASHBOARD-F30 gh:saas#2533 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada 15 minutos, erplora.com busca lo que el servicio de los negocios aún no ha recibido: un alta, una baja, una recuperación o el estado más reciente de un negocio.
2. Se lo vuelve a mandar y, a un alta que lleva más de 2 minutos sin el aviso de «listo», le pregunta cómo va: si ya está listo, la da por lista; si el servicio no la conoce, la manda otra vez.
3. Apunta en el registro cuánto entregó, cuánto quedó pendiente y cuánto rechazó el negocio.
Entra: los negocios con algo pendiente.
Sale: lo entregado, marcado como entregado; lo que falla queda pendiente para la siguiente pasada.
Si falla: un negocio que falla no para la pasada; la pasada termina con error si algo quedó pendiente, sin conexión o rechazado, y ese error salta como alarma. Dos pasadas a la vez no se pisan: la segunda sale sin hacer nada.
Implicados: el negocio (recibe lo pendiente)

### HUBS-F09 Ver la lista de negocios
<!-- origen: old-saas:SAAS_DASHBOARD-F05 fi:saas/hubs#listado-de-terminales-activos fi:saas/hubs#listado-de-terminales-inactivos pc:cloud/dashboard/hubs-active pc:cloud/dashboard/hubs-inactive -->
Estado: hecho
Actor: propietario, administrador, encargado, empleado
Pantalla: Negocios
Pasos:
1. En el menú, «Negocios» abre la lista de los negocios de la cuenta, el último abierto primero; las direcciones viejas del panel de negocios llevan aquí.
2. Cada fila enseña el negocio (enlace a su página), su dirección web, su «Estado» («Activo», «Preparando», «Pago pendiente», «Suspendido», «En eliminación»), con el porqué y la fecha cuando importa («Eliminado. Puedes recuperarlo hasta el …»), su «Plan», el «Rol» de la persona y su «Último uso».
3. Busca por nombre o dirección web y abre la acción de la fila: «Abrir», «Gestionar» (propietario y administradores) o «Recuperar» (el propietario, un negocio eliminado dentro de sus 90 días).
4. La lista cambia sola cuando un negocio pasa a estar listo, cambia de plan o de personas, sin recargar.
Entra: los negocios de los que la persona es miembro con la invitación aceptada.
Sale: nada; la lista se mantiene al día sola.
Si falla: sin negocios, «Crea tu primer negocio» con el formulario del alta; una búsqueda sin resultados, «Nada coincide con la búsqueda» con «Mostrar todo»; sin conexión, el error con «Reintentar», nunca una lista vacía. Un negocio purgado ya no sale.
Implicados: billing (el plan y las facturas sin pagar de cada fila)

### HUBS-F10 Ver la portada del panel
<!-- origen: old-saas:SAAS_DASHBOARD-F200 fi:saas/hubs#dashboard-de-hubs-resumen pc:cloud/dashboard/overview -->
Estado: hecho
Actor: propietario, administrador, encargado, empleado
Pantalla: Negocios
Pasos:
1. Desde la Entrada, «Ir al panel» abre **Negocios**, la portada del panel, con el menú «Negocios», «Tienda», «Facturación» y «Cuenta».
2. Arriba ve lo que espera respuesta (invitaciones, ofertas de propiedad, facturas sin pagar) y debajo todos sus negocios con su plan, su estado y su último uso (HUBS-F09).
3. Sin negocios, la portada es «Crea tu primer negocio»; la dirección vieja de la vista general lleva aquí.
Entra: los negocios de la cuenta.
Sale: nada.
Si falla: los estados de la lista de negocios (HUBS-F09).
Implicados: billing (Facturación), accounts (Cuenta)

### HUBS-F11 Entrar en un negocio desde erplora.com
<!-- origen: old-saas:SAAS_DASHBOARD-F06 -->
Estado: hecho
Actor: propietario, administrador, encargado, empleado
Pantalla: Entrada, Negocios
Pasos:
1. En la Entrada (con uno o varios negocios) o en **Negocios**, la persona pulsa «Abrir» en su negocio («Abriendo …»).
2. El navegador va a la dirección del negocio, que pide a erplora.com el pase de entrada con la sesión ya abierta, sin volver a pedir la contraseña.
3. Entra en el negocio ya identificada; erplora.com recuerda ese negocio como el último abierto y la Entrada lo pone arriba la próxima vez.
4. Desde una invitación, «Aceptar y entrar» acepta y entra igual.
Entra: la persona miembro del negocio y su sesión.
Sale: la entrada en el negocio con un pase de un solo uso que nunca viaja en la dirección; el negocio como último abierto (`hubs.business.opened`).
Si falla: un negocio que se prepara, suspendido o eliminado no se abre y la fila dice por qué; uno con un pago pendiente sigue abriendo. Un negocio de otra cuenta o una invitación sin aceptar no se abren. A una cuenta con el segundo paso de entrada, erplora.com se lo pide antes de dar el pase.
Implicados: accounts (el pase de entrada), el negocio (abre su sesión)

### HUBS-F12 Elegir el negocio en la aplicación instalada
<!-- origen: old-saas:SAAS_DASHBOARD-F07 -->
Estado: hecho
Actor: propietario, administrador, encargado, empleado
Pantalla: Entrada (en la aplicación instalada)
Pasos:
1. La aplicación sin negocio recordado (o tras «Cambiar de negocio») abre la Entrada: con un negocio, «Abrir …»; con varios, «¿Dónde trabajas hoy?» con el último abierto arriba y el estado de cada uno.
2. La persona pulsa «Abrir» en el negocio en el que quiere trabajar.
3. La aplicación va al negocio, entra sin pedir otra vez la contraseña y se queda unida a él: desde ese momento la impresora, el cajón y el resto del hardware responden solo a ese negocio.
4. La próxima vez la aplicación arranca directamente en el negocio recordado.
Entra: los negocios de los que la persona es miembro.
Sale: lo mismo que HUBS-F11, y la aplicación unida a ese negocio; nunca a una dirección que no sea de un negocio de ERPlora.
Si falla: un negocio de otra cuenta no se encuentra; uno que no abre ahora (se prepara, suspendido, eliminado) vuelve a la Entrada, que dice por qué. Sin sesión, la Entrada pide entrar y vuelve después al negocio. La Entrada nunca entra sola en un negocio ya existente: siempre elige la persona.
Implicados: accounts (el pase de entrada), la aplicación instalada (se une al negocio), el negocio

### HUBS-F13 Abrir el negocio en otro dispositivo
<!-- origen: old-saas:SAAS_DASHBOARD-F08 fi:saas/hubs#codigo-qr-del-terminal-bridge -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Resumen del negocio › En tus dispositivos
Pasos:
1. En la página del negocio, el Resumen enseña la tarjeta «En tus dispositivos» («Entra desde cualquier sitio»).
2. La persona copia la «Dirección web del negocio» con «Copiar dirección» y la abre en el navegador de la caja, la tableta o el móvil, o descarga la «App para Windows» o la «App para Android».
3. En el otro dispositivo entra con su cuenta como siempre (HUBS-F11).
Entra: la dirección web del negocio.
Sale: nada; la tarjeta solo comparte la dirección.
Si falla: si el navegador no deja copiar, «No se ha podido copiar la dirección. Selecciónala y cópiala a mano.». Dentro de la aplicación no salen las descargas: la tarjeta habla de los otros dispositivos.
Implicados: public (las descargas de las aplicaciones)

### HUBS-F14 Ver los negocios por la API
<!-- origen: fi:saas/hubs#listado-detalle-de-hubs-por-api-user-jwt -->
Estado: hecho
Actor: propietario, integración
Pantalla: ninguna
Pasos:
1. Con la sesión de su cuenta, o con una clave de API de lectura de Negocios de esa cuenta, una integración pide la lista de los negocios, con el mismo orden, búsqueda y páginas que la pantalla.
2. Pide la ficha de uno de ellos, con su estado, su plan, sus personas y lo que puede hacer.
Entra: la sesión o la clave de API de la cuenta.
Sale: los mismos datos que enseña el panel; nada se guarda.
Si falla: sin sesión ni clave, la petición se rechaza; una clave sin permiso de lectura de Negocios también; un negocio de otra cuenta no se encuentra. Las claves solo leen: crear o cambiar un negocio pide la sesión.
Implicados: accounts (las claves de API)

## Para quien lo mantiene

- Anatomía, operaciones y decisiones: `hubs/README.md` (negocios, salto al Hub, foto y registro empujados al Hub,
  `reconcile_hub_states`, miembros, uso y demo).
- Partes del porte (MIGRATION-TASK APP-HUBS-1…4): este WORKBOOK nace en la parte 1 con estos flujos; las partes 2
  (ajustes, dirección web y dominios, baja, purga, estado y uso, admin del negocio), 3 (personas) y 4 (plan,
  derechos, contrato con el Hub y taxonomía) añaden los suyos a continuación. La revisión flujo a flujo de los
  `hecho` la hace la parte 4.
- Equivalencia de claves del registro: G65 y G41 = F01; G66 = F02; G67, G09, G10 y G45 = F03; G68 = F04; G43,
  G04, G06, G21 y G44 = F05; G98 = F06; G91 = F07; G92 = F08; G69, G17, G18, G111 y G113 = F09; G14, G84 y
  G114 = F10; G70 = F11; G71 = F12; G72 y G12 = F13; G19 = F14.
- Alta (F01–F03): `hubs.business.create` (una transacción: `BillingProfile`, `Hub`, `HubMember` propietario y
  `Subscription` Gratis) y el empuje tras el COMMIT (`services.sync_hub`). El pago es de `billing`
  (`billing.checkout.start`). El país sugerido sale de `navigator.languages` (`regions.suggestedCountry`, con
  `Intl.Locale.maximize`): la primera región que ERPlora vende; si no, España.
- Listo (F04, F07): `POST /internal/hubs/{id}/ready` (`hubs/internal.py`) → `hubs.business.mark_ready`; el correo
  `emails.send_ready` sale tras el COMMIT y solo cuando esa llamada pasa el negocio de `preparing` a `active`.
- F06 lo sirve el Hub (`base/middleware.py`, plantilla `base/hub_preparing.html`, 503 con `Retry-After`; tests
  en `base/tests/test_middleware.py` del Hub).
- Aplicación instalada (F02, F12; PLAN-SAAS bloque 3, PLAN-HUB ronda 18): `ERPlora/app` arranca en `/shell/` y
  nunca lo cambia, y solo se une a un hub cuando una navegación con `?shell=1` sale de una página del SaaS
  (`hub_link.rs`). `/shell` es un alias del lanzador (`frontend/routes.ts`); «Abrir» dentro de la app
  (superficies `desktop` y `mobile`, no `account`) pide `hubs.business.open` con `shell: true`, y
  `/shell/open/<id>/` (`hubs/shell.py`) hace lo mismo para un enlace: 302 al inicio del salto del Hub con
  `&shell=1`; sin sesión, `/shell/?next=…`; un negocio ajeno, 404; uno que no abre, vuelta a `/shell/`.
- Direcciones viejas (F03, F09, F10, F13): `hubs/redirects.py`, 301 de `/dashboard/`, `/dashboard/hubs/`,
  `…/active/`, `…/inactive/`, `…/create/` (`/businesses?create=1`) y `…/<id>/qr/` (el Resumen). El resto de
  `/dashboard/*` es de sus apps.
- Quitar a quien aún paga (trampa saas#2587; el flujo de miembros lo escribe la parte 3, personas): `hubs.member.remove`
  no saca del negocio a quien aún lo paga (`queries.still_pays`: es dueño de su pagador, o tras un traspaso el plan
  se sigue cobrando al cliente de Stripe de uno de sus pagadores). 409 `hubs.member_pays` con qué hacer: que el
  propietario ponga sus datos de pago (se piden al pagar un plan o un módulo) o, si el plan sigue en la tarjeta
  anterior, que soporte lo pase a su nombre (`billing.payer_required`). Así nadie paga un negocio que ya no ve, y
  `accounts` retiene la cuenta de quien paga (`accounts.pays_businesses`, ACCOUNTS-F27). Tests:
  `hubs/tests/test_members.py::TestRemoveThePayer`.
- Planes (F05): `Plan` con columnas por idioma (`TranslatedFields`, `<campo>_en` y `<campo>_es`), sembrados por la
  migración `0013`; el admin (`hubs/admin.py`) es la única escritura. La lista pública es `hubs.plan.list`.
- Pruebas: cada test cita su clave en el nombre o el docstring; los e2e de esta parte están en
  `tests/e2e/panel/hubs-flows.spec.ts` (con la clave del registro, `HUBS-Gnn`, en el título).

## Lo que NO hace, a propósito

- No tiene una «Vista general» con cifras ni actividad: la portada del panel es Negocios (ronda 17).
- No separa los negocios en pestañas de activos e inactivos ni filtra por estado o plan: una sola lista con
  buscador, y los eliminados en ella con «Recuperar» mientras se pueden recuperar.
- No cobra al crear: todo negocio nace en Gratis y el plan de pago se elige después en la Tienda.
- No enseña un código QR: la tarjeta «En tus dispositivos» comparte la dirección y las aplicaciones.
- No tiene una API para escribir planes: el personal los mantiene en el admin.
- No pausa ni reinicia negocios, ni enseña su CPU, su memoria o sus conexiones: un solo servicio sirve a todos.
- No entra sola en un negocio ya existente al abrir la Entrada, tampoco con uno solo: elige la persona.
