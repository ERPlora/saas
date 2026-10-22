# Workbook — Negocios (hubs)
Prefijo: HUBS
Alcance MVP: fase 1 (los negocios de cada cuenta de erplora.com: crearlos, esperar a que estén listos, verlos en la lista y entrar en ellos)
Estado de la app: en construcción (partes 1 y 2 de 4: crear el negocio, los planes, esperar a que esté listo, la lista, la portada del panel, entrar y abrirlo en otro dispositivo; los ajustes, la dirección web, eliminar y recuperar, los suspendidos, el estado y el uso, y el personal en el admin)

> Manual de uso y especificación de la app `hubs` del SaaS (erplora.com). Cuenta cómo se crea un negocio, qué
> pasa mientras se prepara, cómo se ve la lista de negocios y cómo se entra en cada uno desde el navegador o desde
> la aplicación instalada, y cómo se cambian sus ajustes y su dirección web, cómo se elimina y se recupera, qué
> pasa con uno suspendido por impago y qué hace el personal de ERPlora con él. Esta parte del manual no se publica
> en la tienda: es la referencia del equipo y de la QA. Las personas de cada negocio (parte 3) y el plan, los
> derechos y lo que el negocio recibe de erplora.com (parte 4) se escriben a continuación.

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
- **El propietario** ve la lista de sus negocios, cambia su dirección web, lo elimina, recupera uno eliminado y
  cambia su plan; con los **administradores**, cambia su nombre, su idioma y su zona horaria.
- El **personal de ERPlora** mantiene los planes desde el admin y, desde ahí, vuelve a mandar a un negocio lo que
  no recibió.

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
- **Slack, Squarespace y Odoo**: el dueño cambia la dirección propia del espacio en sus ajustes; la antigua deja de
  servir (https://slack.com/help/articles/201719807).
- **Shopify, Square Online, Toast, Lightspeed, Odoo, Fresha y Vagaro**: el dominio propio se conecta a la web
  pública de la tienda, no al punto de venta, en planes de pago y con el certificado puesto solo
  (https://squareup.com/help/article/6916, https://support.toasttab.com/en/article/Toast-Online-Ordering-Pro-Domains,
  https://www.fresha.com/help-center/knowledge-base/online-presence/109902-manage-your-domains).

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

### Ajustes del negocio
La pestaña «Ajustes» de cada negocio. «General»: «Nombre del negocio», «País» (solo texto una vez listo),
«Zona horaria», «Idioma del negocio» y «Dirección web» con su botón de copiar y, para el propietario, «Cambiar
dirección»; «Guardar cambios» se activa al cambiar algo. Debajo, la «Zona de peligro» con «Eliminar negocio».

### Cambiar la dirección web
El diálogo de «Cambiar dirección»: «Nueva dirección», debajo «Tu negocio se abrirá en:» con la dirección que dará
y lo que pasa después; «Cambiar dirección» se activa cuando es distinta de la actual.

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
| HUBS-F15 | Cambiar el nombre, el idioma y la zona horaria del negocio | hecho |
| HUBS-F16 | Cambiar la dirección web del negocio | hecho |
| HUBS-F17 | Conectar un dominio propio a la web del negocio | parcial |
| HUBS-F18 | Eliminar un negocio | parcial |
| HUBS-F19 | Recuperar un negocio eliminado | hecho |
| HUBS-F20 | Avisar y dar de baja un negocio suspendido por impago | parcial |
| HUBS-F21 | Ver el estado y el uso de un negocio | parcial |
| HUBS-F22 | Recoger cada noche el uso de cada negocio | parcial |
| HUBS-F23 | Actuar el personal de ERPlora sobre un negocio desde el admin | hecho |

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
<!-- origen: old-saas:SAAS_DASHBOARD-F29 fi:saas/support/hubs#task-send_welcome_email_task fi:saas/support/hubs#signal-track_hub_status_change-purge_org_if_last_hub-send_welcome_email_on_activation-sync_hub_plan_to_stripe -->
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
<!-- origen: old-saas:SAAS_DASHBOARD-F30 gh:saas#2533 old-saas:SAAS_DASHBOARD-F74 -->
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

### HUBS-F15 Cambiar el nombre, el idioma y la zona horaria del negocio
<!-- origen: fi:saas/hubs#ajustes-del-terminal old-saas:SAAS_DASHBOARD-F09 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes del negocio
Pasos:
1. En la página del negocio abre «Ajustes»: «General» enseña el negocio tal como está.
2. Cambia el «Nombre del negocio», la «Zona horaria» o el «Idioma del negocio» (el «País» solo cambia mientras el negocio se prepara) y pulsa «Guardar cambios»: sale «Cambios guardados».
3. El negocio recibe el nombre nuevo para su pantalla y sus tiques, sin que nadie haga nada más.
Entra: el nombre, el idioma y la zona horaria; la sesión de la cuenta.
Sale: el negocio con lo cambiado, solo lo que cambió, y el negocio avisado tras guardar. Anota `hubs.business.updated`.
Si falla: un nombre vacío no se guarda y se dice en el campo; un país distinto en un negocio ya listo, «El país no cambia una vez listo el negocio: sus facturas son de un país.». Un gerente o un empleado no lo cambian, y un negocio eliminado tampoco. Sin conexión con el negocio, el cambio queda guardado y se le vuelve a mandar (HUBS-F08). La dirección postal y los datos de los tiques se cambian dentro del negocio.
Implicados: el negocio (recibe el nombre, el idioma y la zona horaria)

### HUBS-F16 Cambiar la dirección web del negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F10 -->
Estado: hecho
Actor: propietario
Pantalla: Ajustes del negocio › Cambiar la dirección web
Pasos:
1. En «Ajustes», junto a la «Dirección web», el propietario pulsa «Cambiar dirección».
2. Escribe la «Nueva dirección»; debajo, «Tu negocio se abrirá en:» con la dirección que dará, y el diálogo dice qué pasa: «Tus dispositivos y erplora.com te llevan a la nueva dirección.», «La dirección antigua deja de abrir el negocio: los enlaces y códigos QR con ella dejan de funcionar.» y «Nadie más puede quedarse con la dirección antigua mientras sea la última que tuviste.».
3. Pulsa «Cambiar dirección»: sale «El negocio se abre ahora en …» y la página enseña la nueva.
Entra: la nueva dirección; la sesión del propietario.
Sale: el negocio en su nueva dirección, que el negocio recibe en cuanto se guarda, y la entrada desde erplora.com y desde la aplicación instalada hacia ella; la antigua queda reservada para él. Anota `hubs.business.address_changed`.
Si falla: una dirección reservada, «Esta dirección está reservada. Elige otra.»; una que tiene otro negocio, «Esta dirección ya está ocupada. Elige otra.»; una con mayúsculas, espacios o guiones al principio o al final, el error en el campo. La misma dirección no cambia nada. Solo el propietario la cambia; un negocio eliminado no.
Implicados: el negocio (recibe su nueva dirección), accounts (la entrada a la nueva dirección)

### HUBS-F17 Conectar un dominio propio a la web del negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F11 old-saas:SAAS_DASHBOARD-F12 fi:saas/hubs#configuracion-de-dominios-subdominio-dominios-personalizados fi:saas/support/hubs#modelo-hubcustomdomain pc:cloud/dashboard/hubs-domains fi:saas/support/hubs#task-check_domain_validation old-saas:SAAS_DASHBOARD-F39 -->
Estado: parcial — no entra en la fase 1: el dominio propio se queda (como en las tiendas del mercado) solo para la web pública del negocio y en los planes que lo incluyen, y llega a la vez en sus tres piezas; hoy no hay ninguna: la comprobación del dominio en erplora.com, su certificado en la entrada de ERPlora y que el negocio sirva su web por ese dominio. Hasta entonces el panel no lo enseña.
Actor: propietario
Pantalla: Ajustes del negocio
Pasos:
1. En «Ajustes», el propietario de un negocio con un plan que incluye dominio propio escribe el suyo (por ejemplo, la web del negocio en su dominio) y erplora.com le enseña el registro que tiene que crear en su proveedor del dominio.
2. Cuando el registro apunta bien, erplora.com lo comprueba, pide el certificado y, puesto, el dominio queda activo: la web pública del negocio se abre por él.
3. Cada hora vuelve a mirarlo; si deja de apuntar bien tres veces seguidas, avisa al propietario y lo deja de servir hasta que vuelve.
4. Para quitarlo, lo quita de los ajustes y lo confirma.
Entra: el dominio del propietario y el registro de su proveedor.
Sale: la web pública del negocio en su dominio, con su certificado.
Si falla: un dominio que no apunta a ERPlora se queda sin activar y se dice qué registro falta; un plan que no lo incluye no lo ofrece. La aplicación y la entrada al negocio siguen en su dirección de erplora.com.
Implicados: website (la web pública del negocio), el negocio (sirve la web por su dominio)

### HUBS-F18 Eliminar un negocio
<!-- origen: fi:saas/hubs#borrado-cancelacion-del-terminal old-saas:SAAS_DASHBOARD-F22 old-saas:SAAS_DASHBOARD-F23 old-saas:SAAS_DASHBOARD-F24 -->
Estado: parcial — el correo de la baja todavía no lleva el enlace para descargar los datos del negocio: esa copia llega con la base de datos propia de cada negocio (fase 2); hasta entonces el correo y el panel dicen hasta cuándo se puede recuperar.
Actor: propietario, integración
Pantalla: Ajustes del negocio › Zona de peligro
Pasos:
1. En «Ajustes», en la «Zona de peligro», el propietario pulsa «Eliminar negocio»; el diálogo «Eliminar …» dice «Deja de funcionar ahora mismo para todos. Puedes recuperarlo durante 90 días; después se borra para siempre.» y «Su plan se cancela ahora: si lo recuperas, vuelve en Gratis.».
2. Escribe el nombre del negocio en «Escribe el nombre del negocio para confirmar» y pulsa «Eliminar negocio»: sale «Negocio eliminado: …. Puedes recuperarlo hasta el ….».
3. La página dice «Se eliminará para siempre el …» con «Recuperar negocio», y al propietario le llega el correo con esa fecha.
4. Una integración con la sesión de la cuenta hace lo mismo, con el nombre escrito; una clave de API no elimina.
Entra: el nombre escrito otra vez; la sesión del propietario.
Sale: el negocio eliminado, que deja de abrirse al momento para todos y se borra para siempre a los 90 días; su plan vuelve a Gratis y lo que se cobraba en Stripe se cancela en la pasada siguiente; el negocio recibe la baja tras guardar. Anota `hubs.business.deleted`.
Si falla: un nombre que no coincide no elimina nada (da igual en mayúsculas o con espacios alrededor); eliminarlo dos veces, «Este negocio se ha eliminado.». Solo el propietario lo elimina. Para dejar de pagar sin eliminarlo, se cancela el plan desde Facturación (BILLING-F13).
Implicados: billing (cancela lo que se cobraba), el negocio (deja de abrirse y lo guarda 90 días)

### HUBS-F19 Recuperar un negocio eliminado
<!-- origen: fi:saas/hubs#reactivar-terminal-inactivo -->
Estado: hecho
Actor: propietario
Pantalla: Negocios, Resumen del negocio
Pasos:
1. En **Negocios** (la fila dice hasta cuándo se puede recuperar) o en la página del negocio eliminado, el propietario pulsa «Recuperar negocio».
2. Sale «Negocio recuperado: …» y el negocio vuelve a abrirse como estaba, en el plan Gratis; para volver a un plan de pago, se cambia en la Tienda (BILLING-F08).
Entra: el negocio eliminado hace menos de 90 días; la sesión del propietario.
Sale: el negocio activo otra vez (o preparándose, si nunca llegó a estar listo), en Gratis, y el negocio avisado tras guardar. Anota `hubs.business.restored`.
Si falla: pasados los 90 días, «Este negocio se borró para siempre y no se puede recuperar.»; un negocio que no está eliminado, «Este negocio no está eliminado.». Si la cuenta ya tiene su negocio gratuito, no vuelve: primero el otro pasa a un plan de pago. Solo el propietario lo recupera.
Implicados: el negocio (lo vuelve a abrir)

### HUBS-F20 Avisar y dar de baja un negocio suspendido por impago
<!-- origen: old-saas:SAAS_DASHBOARD-F35 fi:saas/support/hubs#task-cleanup_inactive_hubs fi:saas/support/hubs#task-send_hub_suspended_email_task -->
Estado: parcial — la baja del día 180 es la de HUBS-F18 y tampoco lleva todavía el enlace para descargar los datos (llega con la base de datos propia de cada negocio, fase 2).
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un negocio cuyo plan no se pudo cobrar se suspende pasados sus días de gracia, y quien paga recibe el correo de la suspensión (BILLING-F16): desde ese momento corre su cuenta atrás.
2. Cada hora, erplora.com mira los negocios suspendidos. A los 30 días, el propietario recibe «… sigue suspendido» con la fecha en que se eliminará si no se paga y el camino para pagarla; a los 150, «Último aviso: … se eliminará el …». Cada aviso sale una sola vez.
3. A los 180 días, ya avisado por última vez, el negocio se elimina como lo elimina su propietario (HUBS-F18): 90 días más para recuperarlo, en Gratis, y el correo de la baja, que dice por qué.
4. Si entre tanto se paga la factura, el negocio vuelve a funcionar al momento y la cuenta atrás se olvida con sus avisos.
Entra: los negocios suspendidos por impago y la fecha en que se suspendieron.
Sale: los dos avisos al propietario y, al final, el negocio eliminado. Anota `hubs.business.deleted`.
Si falla: un aviso que no pudo salir se vuelve a mandar en la pasada siguiente, y sin él no se elimina nada; un negocio que falla no para a los demás y la pasada termina con error; un negocio suspendido sin fecha no se elimina nunca y se apunta para que lo mire una persona.
Implicados: billing (suspende, avisa de la suspensión y hace la pasada), el negocio (deja de abrirse)

### HUBS-F21 Ver el estado y el uso de un negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F26 -->
Estado: parcial — el negocio todavía no mide su uso cada noche (HUBS-F22), así que en un negocio real la tarjeta «Uso» dice «Sin datos todavía. Las cifras llegan cada noche, desde la primera tras crear el negocio.»; el estado, el plan y las plazas ya son los de verdad.
Actor: propietario, administrador
Pantalla: Resumen del negocio
Pasos:
1. En la página del negocio, la cabecera dice su estado («Activo», «Preparando», «Pago pendiente», «Suspendido» o eliminado) y el Resumen, su plan con los dispositivos y las personas frente a las plazas.
2. La tarjeta «Uso» («Cómo va tu negocio en ERPlora») enseña el «Almacenamiento» usado del espacio de su plan, con aviso al acercarse al tope, y las personas «Activos ayer» y de los «Últimos 30 días», con «Datos de ayer: se actualizan cada noche.».
Entra: el negocio y lo que midió la última noche.
Sale: nada se guarda; la página cambia sola cuando llega una noche nueva.
Si falla: sin ninguna noche medida, «Sin datos todavía. Las cifras llegan cada noche, desde la primera tras crear el negocio.»; con datos de un día anterior a ayer, «Datos del …: se actualizan cada noche.». Un gerente o un empleado no ven la página del negocio, solo «Abrir».
Implicados: el negocio (mide su uso)

### HUBS-F22 Recoger cada noche el uso de cada negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F57 -->
Estado: parcial — erplora.com ya lo pide cada noche, pero el servicio de los negocios todavía no sirve su medición; hasta que la sirva, la pasada termina con error y no se guarda nada.
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada noche, erplora.com pide al servicio de los negocios lo que midió de cada uno el día anterior: el espacio de sus ficheros, el de su base de datos y las personas que entraron ese día y en los últimos 30.
2. Guarda un día por negocio; si vuelve a recoger un día ya guardado, sustituye las cifras solo si cambiaron, y avisa a la página de ese negocio.
3. Un día que se perdió se recoge después, pidiéndolo por su fecha.
Entra: la medición de la noche, página a página.
Sale: el uso de cada negocio y día. Anota `hubs.business.usage_collected`.
Si falla: si el servicio no contesta o se niega, la pasada termina con error y avisa; una fila rota no para las demás; un negocio que erplora.com no vendió se apunta sin error. Dos pasadas a la vez no se pisan.
Implicados: el negocio (mide su uso)

### HUBS-F23 Actuar el personal de ERPlora sobre un negocio desde el admin
<!-- origen: fi:saas/django-admin#admin-hub fi:saas/hubs#administracion-de-hubs-django-admin old-saas:SAAS_DASHBOARD-F41 -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: admin › Negocios
Pasos:
1. El personal entra en el admin de erplora.com y busca el negocio por su dirección o su nombre; ve su ficha con sus miembros, su plan, quién paga, su uso y lo que el negocio aún no ha recibido.
2. Elige el negocio y una acción: «Enviar al Hub el estado más reciente», «Reintentar lo que el Hub tiene pendiente» o, en la ficha de los cierres de sesión, «Cerrar ya las sesiones en el Hub»; el admin dice cuántos quedaron al día y cuántos siguen pendientes.
3. Cada acción queda en el historial de ese negocio: quién la hizo, cuándo y cuál.
Entra: la cuenta del personal con su segundo factor.
Sale: lo que la acción manda al negocio y la línea del historial.
Si falla: el admin no crea, no cambia ni borra negocios, miembros ni planes de pago: eso solo lo hacen sus propias pantallas, así nadie del personal se hace propietario de un negocio ni lo borra sin su baja. El personal de soporte lo ve todo y no ejecuta acciones. Para los datos de dentro del negocio está el admin de los negocios (en el servicio de los negocios).
Implicados: el negocio (recibe lo que se le reenvía), accounts (la cuenta del personal)

## Para quien lo mantiene

- Anatomía, operaciones y decisiones: `hubs/README.md` (negocios, salto al Hub, foto y registro empujados al Hub,
  `reconcile_hub_states`, miembros, uso y demo).
- Partes del porte (MIGRATION-TASK APP-HUBS-1…4): este WORKBOOK nace en la parte 1 (F01–F14); la parte 2 añade
  F15–F23 (ajustes, dirección web y dominio propio, eliminar y recuperar, los suspendidos, estado y uso, admin del
  negocio); las partes 3 (personas) y 4 (plan, derechos, contrato con el Hub y taxonomía) añaden los suyos a
  continuación. La revisión flujo a flujo de los `hecho` la hace la parte 4.
- Equivalencia de claves del registro: G65 y G41 = F01; G66 = F02; G67, G09, G10 y G45 = F03; G68 = F04; G43,
  G04, G06, G21 y G44 = F05; G98 = F06; G91 = F07; G92 = F08; G69, G17, G18, G111 y G113 = F09; G14, G84 y
  G114 = F10; G70 = F11; G71 = F12; G72 y G12 = F13; G19 = F14. Parte 2: G08 y G73 = F15; G74 = F16; G75, G77,
  G13, G42, G112, G47 y G95 = F17; G11, G87, G88 y G89 = F18; G22 = F19; G94, G48 y G49 = F20; G90 = F21;
  G102 = F22; G02, G07 y G97 = F23; G46 y G51 = F07; G108 = F08. G93 y G85 (pausar y despertar el gratuito que
  nadie usa) se descartan: «Lo que NO hace».
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
- Dirección web (F16): `hubs.business.change_address` (solo el propietario; `can.change_address` en la página),
  validada como la valida el Hub (`live.slugs`, `_chosen_slug`); sube `registry_version` y `state_version`, debe
  `put` y empuja tras el COMMIT; `sync_access(hub, previous_slug=…)` mueve el espejo del salto. La antigua queda en
  `Hub.previous_slug` y `queries.slug_taken`/`free_slug` la cuentan como cogida para los demás (migración `0015`).
  El Hub acepta el cambio en su registro (`hub/base/tests/test_services_hub.py`,
  `test_registering_again_updates_it_without_another_ready`). Tests: `hubs/tests/test_change_address.py`,
  `hubs/frontend/components/AddressDialog.test.ts`.
- Suspendidos (F20): `Hub.suspended_at`, `suspension_warned_at` y `suspension_final_notice_at` (migración `0016`,
  que pone en marcha el reloj de los que ya estaban suspendidos el día del despliegue);
  `_apply_standing` fecha la suspensión y la olvida al pagar; `services.age_suspended()` (lo llama
  `billing.services.sweep_unpaid`, cada hora) corre por negocio `hubs.business.age_suspension` (solo el sistema):
  aviso a los 30 días, último a los 150 y baja a los 180 por `_delete_business`, el mismo camino que
  `hubs.business.delete`; un aviso solo se marca si su correo salió (`emails.send_suspension_notice`). Tests:
  `hubs/tests/test_suspended_lifecycle.py` y `hubs/tests/test_migrations.py`.
- Admin (F23): las acciones de plataforma llevan `@traced` (`hubs/admin.py`), que escribe en el historial del admin
  («Ejecutó «…»») cada fila sobre la que corrieron. Tests: `hubs/tests/test_admin.py::TestTheTrail`.
- Uso (F21, F22): el Hub aún no sirve `GET /internal/usage` (contrato en `hubs/README.md`); `collect_hub_usage`
  ya está programado (`hub-usage-daily`). Sin él, la pasada falla y la tarjeta dice «Sin datos todavía…».
- Dominio propio (F17): decisión de mercado de APP-HUBS-2, propuesta como ronda de PLAN-SAAS (ADR-0502): se mantiene
  solo para la web pública (`website`) y en planes con `includes_custom_domain`, y llega con sus tres piezas
  (erplora.com, borde de `aws` y el host en `base` del Hub); hasta entonces no hay modelo ni pantalla.
- Pruebas de la parte 2: e2e en `tests/e2e/panel/hubs-settings.spec.ts` (clave `HUBS-Gnn` en el título).
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
- No pausa, avisa ni borra un negocio gratuito porque nadie lo use, ni lo despierta al volver: sin un servidor por
  negocio no hay nada que dormir, y no hay borrado por inactividad hasta medir lo que cuesta uno ocioso.
- No conecta todavía un dominio propio (HUBS-F17): la web y la entrada de cada negocio están en su dirección de
  erplora.com.
- No entra sola en un negocio ya existente al abrir la Entrada, tampoco con uno solo: elige la persona.
