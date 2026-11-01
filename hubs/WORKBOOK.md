# Workbook — Negocios (hubs)
Prefijo: HUBS
Alcance MVP: fase 1 (los negocios de cada cuenta de erplora.com: crearlos, esperar a que estén listos, verlos en la lista y entrar en ellos)
Estado de la app: completa (2026-11-01)

> Manual de uso y especificación de la app `hubs` del SaaS (erplora.com). Cuenta cómo se crea un negocio, qué
> pasa mientras se prepara, cómo se ve la lista de negocios y cómo se entra en cada uno desde el navegador o desde
> la aplicación instalada, y cómo se cambian sus ajustes y su dirección web, cómo se elimina y se recupera, qué
> pasa con uno suspendido por impago y qué hace el personal de ERPlora con él, y quién trabaja en cada negocio:
> cómo se invita a una persona, cómo acepta, cómo se le cambia el rol o se la quita y cómo se traspasa la propiedad,
> qué recibe cada negocio de erplora.com (su plan, sus topes, sus aplicaciones de pago y sus personas) y cómo mantiene
> el personal los sectores y tipos de negocio del alta. Esta parte del manual no se publica en la tienda: es la
> referencia del equipo y de la QA.

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
- El **propietario** y los **administradores** invitan a las personas del negocio, les cambian el rol y las quitan;
  solo el propietario da el rol de administrador y traspasa la propiedad. Un **encargado** o un **empleado** solo
  abre el negocio.
- El **personal de ERPlora** mantiene los planes, los sectores y los tipos de negocio desde el admin y, desde ahí,
  vuelve a mandar a un negocio lo que no recibió y consulta quién tiene acceso a cada negocio.
- El **sistema** manda a cada negocio, tras cada cambio y cada noche, su plan con sus topes, sus aplicaciones de pago,
  sus personas y su estado; el negocio trabaja con esa copia y no pregunta a erplora.com en cada venta.

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
- **Shopify y Stripe**: los derechos de una tienda viajan en un aviso tras cada cambio y la aplicación guarda su copia
  local; no pregunta en cada uso (https://shopify.dev/docs/apps/build/webhooks, https://docs.stripe.com/billing/entitlements).
- **Shopify, Square y Toast**: el propietario da acceso a su personal con un rol, y cada rol trae sus permisos; el
  acceso se cambia y se quita desde el mismo sitio, y quien trabaja solo con un PIN en la caja se gestiona dentro
  del punto de venta (https://help.shopify.com/en/manual/your-account/staff-accounts).

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
El formulario del alta: «Nombre del negocio», «País» (sugerido por el idioma del navegador), «Tipo de negocio
(opcional)» con «Todavía no lo sé» y, debajo del nombre, «Tu dirección será …». En la Entrada va en la tarjeta «Crea tu
negocio»; en **Negocios**, en el diálogo «Crear negocio», bajo «¿Cómo se llama tu negocio?».

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
La página que enseña la dirección de un negocio que aún se prepara: «Estamos preparando tu negocio» y «Tarda
unos segundos. Esta página se actualiza sola.».

### Ajustes del negocio
La pestaña «Ajustes» de cada negocio. «General»: «Nombre del negocio», «País» (solo texto una vez listo),
«Zona horaria», «Idioma del negocio» y «Dirección web» con su botón de copiar y, para el propietario, «Cambiar
dirección»; «Guardar cambios» se activa al cambiar algo. Debajo, la «Zona de peligro» con «Eliminar negocio».

### Cambiar la dirección web
El diálogo de «Cambiar dirección»: «Nueva dirección», debajo «Tu negocio se abrirá en:» con la dirección que dará
y lo que pasa después; «Cambiar dirección» se activa cuando es distinta de la actual.

### admin › Negocios › Planes
La ficha de cada plan para el personal, en su idioma: los textos en inglés y en español, el precio, qué incluye, sus
límites y sus precios de Stripe. Al guardar un cambio en lo que da el plan, el aviso «… negocios con este plan reciben
el cambio en los próximos 15 minutos.».

### admin › Negocios › Sectores y Tipos de negocio
Las dos listas de la taxonomía del alta para el personal, con buscador y filtros, y la ficha de cada una: el código,
el nombre y la descripción en inglés y en español, el icono, el color, el orden y si está activo; en un tipo de
negocio, además, su sector y su plantilla («Vertical»).

### Miembros
La pestaña «Miembros» de cada negocio, para el propietario y los administradores: la tabla «Equipo» con «Nombre»
(la fila propia marcada «Tú»), «Correo», «Rol», «Estado» y «Último acceso», el propietario primero; por fila, solo
lo que la persona puede hacer con ella («Cambiar rol», «Quitar», «Reenviar», «Cancelar invitación» y, en el menú
de la fila, «Transferir propiedad»). Debajo, las plazas del plan y «¿Qué puede hacer cada uno?»; encima, la
propiedad ofrecida que espera respuesta, con «Retirar la oferta». En el móvil son tarjetas.

### Invitar
El diálogo «Invitar a …»: «Correo», «Rol» y «Mensaje (opcional)», con «Enviamos un correo con el enlace. La
invitación dura 7 días.» y las plazas que quedan; «Enviar invitación» se activa con una dirección.

### Te han invitado
La tarjeta centrada de las invitaciones que esperan respuesta: «Alguien te ha dado acceso a su negocio. Acepta
para entrar.», una tarjeta por negocio con «Te invita … · …», «Aceptar y entrar» y «Rechazar», y al pie «El
propietario o un administrador del negocio pueden quitarte este acceso.». En **Negocios** y en la Entrada sale la
misma invitación encima de la lista.

### Transferir la propiedad
El diálogo «Transferir …»: a quién se ofrece, que tiene 7 días para aceptarla, que un plan de pago sigue hasta el
final del periodo ya pagado y después lo paga el nuevo propietario con su tarjeta, y el nombre del negocio escrito
para confirmar. Quien la recibe ve en **Negocios** «… te ofrece …»
con «Aceptar la propiedad» y «Rechazar».

### admin › Negocios › Miembros
La lista de accesos para el personal: negocio, persona, rol, cuándo se invitó, cuándo aceptó y su último acceso,
con buscador por negocio o por correo y filtro por rol; solo se consulta.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | La lista y la Entrada enseñan su esqueleto; «Crear mi negocio» se apaga mientras va la petición. |
| Vacío | Sin negocios, la lista y la Entrada son el formulario «Crea tu primer negocio» («Gratis y sin tarjeta: solo el nombre y el país.»). Una búsqueda sin resultados: «Nada coincide con la búsqueda» con «Mostrar todo». |
| Error | «No hemos podido cargar tus negocios» con «Reintentar»; un negocio que no se pudo preparar: «Sin preparar» y «No hemos podido prepararlo. Seguimos reintentándolo; si sigue fallando, avísanos.». |
| Preparando | La fila dice «Preparando» y «Lo estamos preparando. Se abre solo cuando esté listo.»; «Abrir» espera. |
| Sin conexión | «Reconectando… lo que ves puede tener unos segundos de retraso.» mientras vuelve la conexión en vivo. |
| Sin permiso | Un negocio de otra cuenta no existe para esa persona: no se lista ni se abre. Un encargado o un empleado que llega a la página de su negocio ve «No tienes permiso para gestionar este negocio». |

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
| HUBS-F17 | Conectar un dominio propio a la web del negocio | descartado |
| HUBS-F18 | Eliminar un negocio | hecho |
| HUBS-F19 | Recuperar un negocio eliminado | hecho |
| HUBS-F20 | Avisar y dar de baja un negocio suspendido por impago | hecho |
| HUBS-F21 | Ver el estado y el uso de un negocio | hecho |
| HUBS-F22 | Recoger cada noche el uso de cada negocio | hecho |
| HUBS-F23 | Actuar el personal de ERPlora sobre un negocio desde el admin | hecho |
| HUBS-F24 | Invitar a una persona a un negocio | hecho |
| HUBS-F25 | Aceptar o rechazar una invitación a un negocio | hecho |
| HUBS-F26 | Cambiar el rol de una persona en un negocio | hecho |
| HUBS-F27 | Quitar a una persona de un negocio | hecho |
| HUBS-F28 | Traspasar la propiedad de un negocio | hecho |
| HUBS-F29 | Ver las personas de un negocio | hecho |
| HUBS-F30 | Consultar los accesos de las personas en el admin | hecho |
| HUBS-F31 | Mandar a cada negocio su plan, sus aplicaciones y sus personas | hecho |
| HUBS-F32 | Aplicar los topes de personas y de dispositivos del plan | hecho |
| HUBS-F33 | Dar al negocio los mensajes del asistente de su plan | hecho |
| HUBS-F34 | Decir al negocio qué aplicaciones de pago puede usar y por qué | hecho |
| HUBS-F35 | Reconocer al servicio de los negocios cuando llama a erplora.com | hecho |
| HUBS-F36 | Mantener los sectores y los tipos de negocio en el admin | hecho |
| HUBS-F37 | Leer los sectores y los tipos de negocio | hecho |

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
1. Quien abre la dirección de un negocio que aún se prepara ve «Estamos preparando tu negocio» y «Tarda unos segundos. Esta página se actualiza sola.».
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
Estado: descartado — no entra en la fase 1: el dominio propio es solo de la web pública del negocio, en los planes que lo incluyen, y llega a la vez con sus tres piezas (la comprobación del dominio en erplora.com, su certificado en la entrada de ERPlora y que el negocio sirva su web por ese dominio); hasta entonces el panel no lo enseña (saas#195)
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
Estado: hecho
Actor: propietario, integración
Pantalla: Ajustes del negocio › Zona de peligro
Pasos:
1. En «Ajustes», en la «Zona de peligro», el propietario pulsa «Eliminar negocio»; el diálogo «Eliminar …» dice «Deja de funcionar ahora mismo para todos. Puedes recuperarlo durante 90 días; después se borra para siempre.» y «Su plan se cancela ahora: si lo recuperas, vuelve en Gratis.».
2. Escribe el nombre del negocio en «Nombre del negocio» y pulsa «Eliminar negocio»: sale «Negocio eliminado: …. Puedes recuperarlo hasta el ….».
3. La página dice «Se eliminará para siempre el …» con «Recuperar negocio» y, debajo, «Descargar los datos»: cada copia completa de sus datos con su fecha, «Al eliminarlo» y su tamaño, y «Descargar». Al propietario le llega el correo con esa fecha y «Descarga una copia completa de sus datos: …», que lleva a esa página; cuando la copia está lista, otro correo: «La copia de los datos de … está lista».
4. Una integración con la sesión de la cuenta hace lo mismo, con el nombre escrito; una clave de API no elimina.
Entra: el nombre escrito otra vez; la sesión del propietario.
Sale: el negocio eliminado, que deja de abrirse al momento para todos y se borra para siempre a los 90 días; su plan vuelve a Gratis y lo que se cobraba en Stripe se cancela en la pasada siguiente; el negocio recibe la baja tras guardar. Anota `hubs.business.deleted`.
Si falla: un nombre que no coincide no elimina nada (da igual en mayúsculas o con espacios alrededor); eliminarlo dos veces, «Este negocio se ha eliminado.». Solo el propietario lo elimina y descarga sus datos. Sin copia todavía, «La copia todavía no está lista. Te avisaremos por correo cuando lo esté.»; un negocio que nunca tuvo base de datos propia, «Este negocio no tiene copia de datos.», sin aviso, y su correo de la baja no lleva a la copia; una copia que ya no se guarda, «Esta copia de los datos ya no se conserva.»; si ahora no se puede bajar, «La copia no se puede descargar ahora mismo. Vuelve a intentarlo en un momento.». Para dejar de pagar sin eliminarlo, se cancela el plan desde Facturación (BILLING-F13).
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
Estado: hecho
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
Estado: hecho
Actor: propietario, administrador
Pantalla: Resumen del negocio
Pasos:
1. En la página del negocio, la cabecera dice su estado («Activo», «Preparando», «Pago pendiente», «Suspendido» o eliminado) y el Resumen, su plan con los dispositivos, las apps que puede tener activadas a la vez y las personas frente a las plazas.
2. La tarjeta «Uso» («Cómo va tu negocio en ERPlora») enseña el «Almacenamiento» usado del espacio de su plan, con aviso al acercarse al tope, y las personas «Activos ayer» y de los «Últimos 30 días», con «Datos de ayer: se actualizan cada noche.».
Entra: el negocio y lo que midió la última noche.
Sale: nada se guarda; la página cambia sola cuando llega una noche nueva.
Si falla: sin ninguna noche medida, «Sin datos todavía. Las cifras llegan cada noche, desde la primera tras crear el negocio.»; con datos de un día anterior a ayer, «Datos del …: se actualizan cada noche.». Un gerente o un empleado no ven la página del negocio, solo «Abrir».
Implicados: el negocio (mide su uso)

### HUBS-F22 Recoger cada noche el uso de cada negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F57 -->
Estado: hecho
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

### HUBS-F24 Invitar a una persona a un negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F13 fi:saas/orgs-users#invitar-miembro-a-la-organizacion fi:saas/orgs-users#invitar-usuario-formulario fi:saas/orgs-users#invitar-usuario-submit-a-hub-u-organizacion fi:saas/orgs-users#api-invitar-a-organizacion-o-a-hub-concreto-rest fi:saas/orgs-users#api-miembros-listar-invitar-rest -->
<!-- origen: fi:saas/support/orgs-users#service-invite_user_to_organization-invite_user_to_hub-invitations fi:saas/support/orgs-users#serializer-organizationmemberserializer-invitememberserializer-updatememberroleserializer-userserializer fi:saas/support/orgs-users#service-send_org_invitation_email-emails fi:saas/support/hubs#task-send_invitation_email_task gh:saas#2565 -->
Estado: hecho
Actor: propietario, administrador, integración
Pantalla: Miembros › Invitar
Pasos:
1. En la pestaña «Miembros» del negocio, «Invitar» abre «Invitar a …» con «Correo», «Rol» (Empleado de entrada; solo los roles por debajo del propio: el propietario da también Administrador) y «Mensaje (opcional)»; debajo, cuántas plazas del plan quedan.
2. Pulsa «Enviar invitación»: sale «Invitación enviada a …» y la persona aparece en la lista como invitación pendiente, con «Reenviar» y «Cancelar invitación».
3. La persona recibe un correo con quién la invita, a qué negocio, con qué rol, hasta cuándo vale y el enlace para aceptarla; si aún no tiene cuenta, también cómo entrar (con Google o poniendo su contraseña).
4. «Reenviar» manda el correo otra vez y le da 7 días más; «Cancelar invitación» la retira y su enlace ya no deja entrar a nadie. Una integración hace lo mismo con la sesión de la cuenta.
Entra: el correo, el rol, el mensaje y el negocio; la sesión de quien invita.
Sale: la invitación, que vale 7 días y ocupa una plaza del plan; la cuenta de esa dirección si no existía, sin contraseña. El negocio no recibe a la persona hasta que acepta. Anota `hubs.member.invited` (al reenviar, `hubs.member.invitation_resent`; al cancelar, `hubs.member.invitation_cancelled`).
Si falla: alguien que ya está en el negocio, «… ya está en este negocio.»; con una invitación que aún vale, «… ya tiene una invitación pendiente. Reenvíala.» (una caducada se renueva al invitar otra vez). Un rol igual o superior al propio, «No puedes dar un rol igual o superior al tuyo.». Sin plazas, el diálogo dice «El plan no tiene plazas libres: cambia de plan o quita a alguien para invitar a más personas.» y no manda nada. Una dirección del equipo de ERPlora, «Esta dirección es del equipo de ERPlora y no puede unirse a un negocio.». Una cuenta que nunca confirmó esa dirección se libera antes de invitarla: pierde su contraseña, su segundo factor, su Google y sus sesiones, y solo entra quien abre ese buzón. Un encargado o un empleado no invita; un negocio eliminado no admite invitaciones; un negocio ajeno no existe para quien invita. Si el correo no sale, la invitación queda igual.
Implicados: accounts (la cuenta de la persona invitada y, si nunca confirmó su dirección, su liberación), el negocio (recibe a la persona cuando acepta)

### HUBS-F25 Aceptar o rechazar una invitación a un negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F14 -->
Estado: hecho
Actor: administrador, encargado, empleado
Pantalla: Te han invitado, Negocios
Pasos:
1. La persona invitada entra en erplora.com con el correo de la invitación (o sigue su enlace): «Te han invitado» enseña una tarjeta por negocio con «Te invita … · …»; en **Negocios** y en la Entrada la misma invitación sale encima de la lista.
2. Pulsa «Aceptar y entrar»: entra en el negocio sin volver a escribir la contraseña, con el rol que dice la invitación, y el negocio ya sale en su lista.
3. O pulsa «Rechazar» y lo confirma en «Rechazar la invitación»: sale «Invitación rechazada» y quien la invitó tendría que invitarla otra vez.
Entra: las invitaciones de la cuenta que esperan respuesta y siguen dentro de sus 7 días.
Sale: al aceptar, la persona dentro del negocio y el negocio avisado con la lista de personas al día; al rechazar, la invitación borrada. Anota `hubs.invitation.accepted` o `hubs.invitation.declined`. El propietario y los administradores ven el cambio en «Miembros» al momento.
Si falla: una invitación caducada, «Esta invitación ha caducado. Pide a quien te invitó que te la vuelva a enviar.»; una ya respondida, retirada o ajena no se puede contestar («Esta invitación ya no vale»). Sin el correo confirmado, «Confirma tu correo electrónico antes de aceptar la invitación.». Una cuenta que pasó al equipo de ERPlora mientras la invitación esperaba no entra: «Esta dirección es del equipo de ERPlora y no puede unirse a un negocio.». Si el plan ya no tiene sitio, «Este negocio no tiene plazas libres en su plan. Pide a quien te invitó que libere una o que cambie de plan.». Aceptar dos veces no da nada más, y nunca toca los otros negocios de la persona.
Implicados: accounts (la sesión y el salto al negocio), el negocio (recibe a la persona)

### HUBS-F26 Cambiar el rol de una persona en un negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F15 fi:saas/orgs-users#cambiar-rol-de-un-miembro fi:saas/orgs-users#api-miembro-detalle-cambiar-rol-eliminar-rest fi:saas/support/orgs-users#service-user_can_access_hub-get_user_hub_role-funciones-modulo-nivel -->
Estado: hecho
Actor: propietario, administrador, integración
Pantalla: Miembros › Cambiar rol
Pasos:
1. En «Miembros», en la fila de la persona, «Cambiar rol» abre «Cambiar el rol de …» con los roles que se le pueden dar.
2. Elige el nuevo y pulsa «Cambiar rol»: sale «… ahora es …» y la fila enseña el rol nuevo.
3. El negocio recibe la lista de personas con el rol nuevo y cierra en ese momento la sesión de esa persona allí: lo siguiente que haga le pide volver a entrar, y vuelve con el rol nuevo.
Entra: la persona y el rol nuevo; la sesión de quien lo cambia, que tiene que tener más rango que la persona y que el rol que da.
Sale: el rol nuevo y el aviso al negocio, con el cierre de la sesión de esa persona allí; el de una invitación sin responder cambia sin avisar al negocio. Anota `hubs.member.role_changed`.
Si falla: el propio rol, «No puedes cambiar tu propia pertenencia.»; alguien de igual o más rango, «No puedes gestionar a un miembro con un rol igual o superior al tuyo.»; un rol igual o superior al propio, «No puedes dar un rol igual o superior al tuyo.». La propiedad no se da desde aquí (HUBS-F28). Un encargado o un empleado no cambia roles; una persona de un negocio ajeno no existe para quien lo pide.
Implicados: el negocio (BASE-F13: recibe el rol nuevo y cierra la sesión), accounts (la sesión)

### HUBS-F27 Quitar a una persona de un negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F16 old-saas:SAAS_AUTH-F22 fi:saas/orgs-users#eliminar-un-miembro fi:saas/orgs-users#quitar-acceso-de-un-usuario-a-un-hub gh:saas#2569 -->
Estado: hecho
Actor: propietario, administrador, integración
Pantalla: Miembros › Quitar
Pasos:
1. En «Miembros», en la fila de la persona, «Quitar» abre «Quitar a …» («… deja de tener acceso a … al momento. Su cuenta y sus otros negocios se quedan.»).
2. Pulsa «Quitar del negocio»: sale «… ya no está en el negocio» y la fila desaparece.
3. El negocio recibe la lista de personas sin ella y cierra en ese momento sus sesiones en ese negocio, solo en ese: si vuelve, erplora.com le dice «No tienes acceso a este hub».
Entra: la persona; la sesión de quien la quita, que tiene que tener más rango que ella.
Sale: la persona fuera de ese negocio (su cuenta y sus otros negocios siguen), una oferta de propiedad que tuviera pendiente retirada, el aviso al negocio y el cierre de sus sesiones allí, que se reintenta si el negocio no contesta. Anota `hubs.member.removed`.
Si falla: a uno mismo, «No puedes cambiar tu propia pertenencia.»; a alguien de igual o más rango (el propietario nunca), «No puedes gestionar a un miembro con un rol igual o superior al tuyo.». Una invitación sin responder se cancela, no se quita: «Esta persona aún no ha respondido: cancela la invitación.». A quien aún paga el negocio (el propietario anterior tras un traspaso) no se le quita: «… sigue pagando este negocio. Antes di quién paga a partir de ahora: tus datos de facturación se piden al pagar aquí un plan o un módulo.» o, si el plan sigue en su tarjeta, «El plan de este negocio aún se paga con la tarjeta de …: antes mantenlo con la tuya en Facturación.».
Implicados: el negocio (BASE-F13: recibe la lista sin ella y cierra sus sesiones), billing (quién paga el negocio)

### HUBS-F28 Traspasar la propiedad de un negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F17 -->
Estado: hecho
Actor: propietario
Pantalla: Miembros › Transferir la propiedad, Negocios, Facturación › Suscripciones
Pasos:
1. El propietario, en «Miembros», abre el menú de la fila de una persona que ya está en el negocio y elige «Transferir propiedad».
2. En «Transferir …» lee que tiene 7 días para aceptarla y que «Un plan de pago sigue hasta el final del periodo ya pagado; después lo paga el nuevo propietario con su tarjeta y la actual no se vuelve a cobrar.», escribe el nombre del negocio y pulsa «Ofrecer la propiedad»: sale «Oferta enviada a …: tiene 7 días para aceptarla» y, encima de la lista, «Propiedad ofrecida a …» con «Retirar la oferta».
3. La persona recibe un correo con el enlace a **Negocios**, donde ve «… te ofrece …» con «Aceptar la propiedad» y «Rechazar».
4. Al aceptar, sale «Ahora eres el propietario de …»: pasa a propietaria y el anterior queda como administrador; el anterior recibe un correo que le dice que su tarjeta ya no vuelve a pagar el plan.
5. Si el negocio tiene un plan de pago, el nuevo propietario lo ve en **Facturación › Suscripciones** con «Gratis desde el …» y «Se paga con la tarjeta de otra cuenta», y pulsa «Mantenerlo con mi tarjeta».
6. En «Mantén … con tu tarjeta» pone sus datos de facturación (los del anterior no son suyos), lee «Para … · hoy no se cobra nada: tu tarjeta lo paga desde el …» y añade su tarjeta en el pago seguro: sale «… mantiene …: tu tarjeta lo paga desde el …».
Entra: la persona elegida, que ya tiene que estar en el negocio; la sesión del propietario y, al responder, la de esa persona; para mantener el plan, los datos de facturación y la tarjeta del nuevo propietario.
Sale: la oferta, que vale 7 días; al aceptar, los dos roles cambiados a la vez (siempre un solo propietario), el negocio avisado y las sesiones de los dos cerradas allí. El plan de pago es del negocio y la tarjeta no: al aceptar deja de renovarse con la tarjeta del pagador anterior, que no se vuelve a cobrar, y el negocio lo conserva hasta el final del periodo ya pagado. Con «Mantenerlo con mi tarjeta», el plan y sus módulos pasan a la tarjeta del nuevo propietario desde ese día, sin cobrar nada hoy ni dos veces, y la suscripción anterior termina sin reembolso; si no lo hace, ese día el negocio vuelve a Gratis, como cualquier plan cancelado. El pago seguro que el propietario anterior dejó abierto se cierra al aceptar (ya no se puede pagar); si aun así se completa, no se aplica: se cancela, se le devuelve entero (con su rectificativa) y le llega «Te hemos devuelto el pago de …» (BILLING-F09). Anota `hubs.ownership.requested` y, al responder, `hubs.ownership.accepted`, `hubs.ownership.declined` o `hubs.ownership.cancelled`; al abrir el pago, `billing.checkout.started`; al devolver un pago de quien ya no es propietario, `billing.checkout.refunded`.
Si falla: a quien aún no está en el negocio, «Invita antes a esta persona al negocio: solo se puede traspasar a alguien que ya esté en él.»; a uno mismo, «Ya eres el propietario de este negocio.»; con otra oferta esperando, «Ya hay un traspaso de este negocio esperando respuesta.». Al responder: «Este traspaso ya se respondió.», «Este traspaso ha caducado. Pide al propietario que lo vuelva a enviar.», «Ya no estás en este negocio.» o «Este negocio ya cambió de manos: pide a su propietario actual que lo traspase.»; si el servicio de pagos no responde al aceptar un negocio con un plan de pago, no cambia de manos: «El servicio de pagos no ha respondido. No se ha cobrado nada; inténtalo en un momento.». Si no responde al cerrar el pago que dejó abierto el anterior, el traspaso queda hecho igual y el equipo lo ve en el registro (`billing.checkout_not_expired`); un pago de ese intento que llegue después se devuelve. Un negocio gratuito no se acepta si la persona ya tiene el suyo: «Ya tienes un negocio gratuito. Cambia su plan para crear otro.». Al mantener el plan: sin sus datos, el diálogo los pide primero («Indica primero quién paga este negocio: sus datos de facturación son de otra cuenta.»); con una factura sin pagar, «Este negocio tiene una factura sin pagar: págala antes de comprar o cambiar nada.»; si ya se paga con su tarjeta o está en Gratis, «El plan de este negocio ya se paga con tu tarjeta, o está en Gratis: no hay nada que mantener.». Solo el propietario ofrece, y solo el propietario mantiene el plan con su tarjeta; solo la persona elegida acepta o rechaza, y solo el propietario retira la oferta.
Implicados: billing (quién paga el negocio: el plan deja de renovarse en la tarjeta anterior y pasa a la del nuevo propietario), el negocio (BASE-F13: recibe los roles nuevos y cierra las sesiones de los dos)

### HUBS-F29 Ver las personas de un negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F18 old-saas:SAAS_DASHBOARD-F214 fi:saas/hubs#usuarios-del-terminal fi:saas/orgs-users#api-miembros-de-un-hub-concreto-rest fi:saas/orgs-users#listar-usuarios-global-por-organizaciones-gestionadas pc:cloud/dashboard/users-list fi:saas/support/orgs-users#serializer-hubaccessserializer -->
Estado: hecho
Actor: propietario, administrador, integración
Pantalla: Miembros
Pasos:
1. En la página del negocio, la pestaña «Miembros» enseña la tabla «Equipo»: el propietario primero y cada persona con su correo, su rol, su estado (dentro, invitación pendiente o caducada) y su último acceso; la fila propia lleva «Tú».
2. Cada fila ofrece solo lo que la persona puede hacer con ella (HUBS-F24 a HUBS-F28); en el móvil son tarjetas y, con muchas personas, se pasa de página.
3. Debajo dice cuántas plazas del plan se usan y «¿Qué puede hacer cada uno?»; la lista cambia sola cuando alguien acepta, cambia de rol o sale.
Entra: la sesión de la cuenta y el negocio.
Sale: nada guardado.
Si falla: «No hemos podido cargar los miembros» con «Reintentar». Un encargado o un empleado ve «No tienes permiso para gestionar este negocio»; un negocio ajeno no existe para quien lo pide. Una invitación sin responder no tiene fecha de alta.
Implicados: accounts (la sesión), billing (las plazas del plan)

### HUBS-F30 Consultar los accesos de las personas en el admin
<!-- origen: fi:saas/django-admin#admin-hubaccess fi:saas/support/orgs-users#modelo-hubaccess -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: admin › Negocios › Miembros
Pasos:
1. El personal entra en el admin de erplora.com y abre la lista de miembros; busca por el negocio o por el correo de la persona y filtra por rol.
2. Ve, por acceso, el negocio, la persona, su rol, cuándo se la invitó, cuándo aceptó y su último acceso; la ficha de cada negocio enseña también sus miembros.
Entra: la cuenta del personal con su segundo factor.
Sale: nada guardado.
Si falla: el admin no invita, no cambia ni quita a nadie: eso solo lo hacen el propietario y los administradores en «Miembros», así nadie del personal se da acceso a un negocio. El personal de soporte también lo consulta.
Implicados: accounts (la cuenta del personal)

### HUBS-F31 Mandar a cada negocio su plan, sus aplicaciones y sus personas
<!-- origen: old-saas:SAAS_DASHBOARD-F116 old-saas:SAAS_DASHBOARD-F40 old-saas:SAAS_DASHBOARD-F54 old-saas:SAAS_DASHBOARD-F53 fi:saas/hubs#entitlement-de-modulos-firmado-rs256 fi:saas/support/public-core-config#service-is_module_entitled-build_signed_entitlement-entitlement-py -->
Estado: hecho
Actor: sistema, personal de ERPlora
Pantalla: ninguna; para el personal, admin › Negocios › Planes
Pasos:
1. Cada vez que cambia algo que el negocio tiene que saber —su plan (al pagarlo, cambiarlo o terminarlo), una aplicación de pago comprada o cancelada, una persona que entra, cambia de rol o sale, su estado de cobro o su autorización de VeriFactu—, erplora.com lo guarda y, en cuanto queda guardado, manda al negocio su foto entera: el plan con sus topes (personas, dispositivos, los límites de su base de datos y los mensajes del asistente y de WhatsApp al mes), sus aplicaciones de pago, sus personas con su rol, su estado y su bloque de VeriFactu.
2. El negocio se queda siempre con la foto más nueva: una que llega tarde y es más vieja que la que ya tiene no cambia nada. Con ella trabaja sin preguntar a erplora.com en cada venta, así que sigue vendiendo aunque erplora.com no responda.
3. Si el personal cambia en el admin lo que da un plan (sus topes, su nivel de aplicaciones o sus mensajes al mes), al guardar ve «… negocios con este plan reciben el cambio en los próximos 15 minutos.» y cada negocio con ese plan lo recibe en la siguiente pasada; cambiar solo sus textos, su orden o su precio no manda nada.
4. Lo que un negocio no recibió se le vuelve a mandar cada 15 minutos (HUBS-F08) y, cada noche, todos los negocios reciben su foto otra vez.
Entra: el cambio guardado: el pago, las personas, la ficha del plan en el admin o la autorización de VeriFactu.
Sale: la foto del negocio, con un número de versión que solo crece. VeriFactu va en todos los planes, también en Gratis: con la autorización validada, el negocio presenta sus registros en el plan que tenga. Anota `hubs.subscription.changed` cuando cambian su plan o sus aplicaciones.
Si falla: si el negocio no responde o rechaza la foto, queda pendiente y se le reintenta (HUBS-F08); el rechazo se ve en su ficha del admin (HUBS-F23). Un negocio eliminado no recibe foto. Un cambio del admin que no llega en la pasada siguiente llega la noche siguiente.
Implicados: billing (el pago y el plan), fiscal (la autorización de VeriFactu), el negocio (guarda la foto y aplica su estado, sus personas, VeriFactu y WhatsApp; los topes y las aplicaciones, HUBS-F32 y HUBS-F34)

### HUBS-F32 Aplicar los topes de personas y de dispositivos del plan
<!-- origen: old-saas:SAAS_DASHBOARD-F58 old-saas:SAAS_DASHBOARD-F59 -->
Estado: hecho
Actor: sistema, propietario, administrador
Pantalla: Miembros › Invitar
Pasos:
1. Cada plan dice cuántas personas y cuántos dispositivos a la vez cubre en cada negocio: Gratis, 3 personas y 1 dispositivo; los planes de pago, sin tope.
2. Al invitar, erplora.com cuenta a las personas que ya están y las invitaciones que aún valen; sin plaza, el diálogo «Invitar a …» dice «El plan no tiene plazas libres: cambia de plan o quita a alguien para invitar a más personas.» y no manda nada (HUBS-F24). Cambiar el rol de quien ya está no gasta plaza.
3. El negocio recibe los dos topes en su foto (HUBS-F31) y aplica el de dispositivos: al entrar en uno más de los que cubre el plan, se cierra la sesión del que lleva más tiempo sin entrar (BASE-F57). Las personas, también las que entran con un PIN, son siempre las de «Miembros», así que el tope de personas lo aplica erplora.com al invitar; el negocio enseña en su personal cuántas plazas hay ocupadas (BASE-F77).
Entra: el plan del negocio, sus personas y sus invitaciones.
Sale: el rechazo de la invitación que no cabe y los dos topes en la foto; nada más se guarda.
Si falla: aceptar una invitación cuando el plan ya no tiene sitio se frena al aceptar (HUBS-F25). Bajar de plan no saca a nadie: frena las invitaciones nuevas hasta que vuelva a haber sitio.
Implicados: billing (el plan), el negocio (cierra la sesión de los dispositivos que sobran y enseña las plazas ocupadas)

### HUBS-F33 Dar al negocio los mensajes del asistente de su plan
<!-- origen: old-saas:SAAS_ASSISTANT-F12 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada plan incluye un número de mensajes del asistente al mes (Gratis 30, Starter 300, Standard 600; 0 es sin asistente); el personal lo cambia en la ficha del plan (HUBS-F05).
2. erplora.com lo manda al negocio en su foto (HUBS-F31), junto al de WhatsApp, y otra vez en cuanto cambian el plan o la cifra.
3. Cada mensaje cuenta para el mes del negocio: erplora.com lo cuenta en cada turno del asistente (ASSISTANT-F18) y le dice al negocio cuántos lleva, de cuántos y cuándo vuelven, para que avise al 80 %; al 100 % no deja preguntar más hasta el día 1 del mes siguiente (00:00 UTC); para tener más, se sube de plan.
Entra: el plan del negocio.
Sale: los mensajes al mes del plan, en la foto del negocio, y los gastados de cada mes (ASSISTANT-F18).
Si falla: un plan con 0 mensajes deja el asistente sin uso. No se venden paquetes de mensajes sueltos.
Implicados: assistant (el turno de cada mensaje y su cuenta, ASSISTANT-F18), el negocio (enseña lo que queda y avisa al 80 %)

### HUBS-F34 Decir al negocio qué aplicaciones de pago puede usar y por qué
<!-- origen: old-saas:SAAS_DASHBOARD-F62 old-saas:SAAS_PUBLIC-F20 fi:saas/hubs#estado-de-suscripcion-de-modulo-bouncer fi:saas/hubs#modulos-del-terminal -->
Estado: hecho
Actor: sistema, propietario
Pantalla: ninguna; las de cada negocio se ven en Tienda › Módulos (BILLING-F31)
Pasos:
1. Un negocio tiene una aplicación de pago por su plan (el nivel del plan la incluye) o porque la compró para ese negocio; las gratuitas no hacen falta en la lista: siempre se pueden usar.
2. erplora.com manda al negocio, en su foto (HUBS-F31), cada aplicación de pago que tiene, de dónde le viene (el plan o una compra) y hasta cuándo, si se canceló.
3. El negocio enciende las que tiene y en su página de aplicaciones dice de dónde le viene cada una («Incluida en tu plan», «Contratada»); una de pago sin derecho no se enciende, no hace nada de lo que se le pida y lleva a comprarla en erplora.com (BASE-F20, BASE-F27).
4. En **Tienda › Módulos**, con el negocio elegido, el propietario ve cada aplicación en ese negocio: «Incluido en tu plan» o «Ya lo tienes» (BILLING-F31).
Entra: el plan del negocio y sus compras.
Sale: las aplicaciones de pago del negocio en su foto; nada se guarda.
Si falla: una compra es de un solo negocio: nunca da la aplicación a otro, tampoco a otro de la misma cuenta. Una cancelada sigue hasta el final de lo pagado. Al bajar de plan se van las que daba el plan anterior; al subir, llegan las del nivel nuevo. Una aplicación de pago que el personal pone a la venta, o a la que cambia de nivel, llega a los negocios cuyo plan la incluye en la pasada siguiente (como mucho 15 minutos); el admin dice «… negocios cuyo plan lo incluye reciben el cambio en los próximos 15 minutos.».
Implicados: billing (las compras), apps (qué aplicación es de pago y su nivel), el negocio (enciende o frena cada aplicación)

### HUBS-F35 Reconocer al servicio de los negocios cuando llama a erplora.com
<!-- origen: old-saas:SAAS-F03 old-saas:SAAS_DASHBOARD-F50 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cuando el servicio de los negocios avisa o pide algo a erplora.com (que un negocio está listo, la entrada de una persona, la autorización de VeriFactu, una presentación a la Agencia Tributaria o un WhatsApp), firma la llamada con el secreto que comparten los dos y la hora.
2. erplora.com comprueba la firma y la hora (como mucho 5 minutos de diferencia) antes de leer nada; durante un cambio de secreto acepta también el anterior.
3. El negocio de la llamada es el que nombra su dirección, nunca una cabecera ni lo que diga el cuerpo; con la firma buena, contesta solo con lo de ese negocio.
Entra: la llamada firmada.
Sale: la respuesta de esa puerta; nada más.
Si falla: sin firma, con la firma de otro secreto o con una hora de hace más de 5 minutos, se rechaza sin hacer nada; la sesión de una persona, aunque sea del personal, no abre estas puertas. Un aviso que nombra a otro negocio que el de su dirección se rechaza. Estas puertas no se publican hacia internet.
Implicados: accounts (la firma y la entrada de cada persona), fiscal y fiscal_gateway (VeriFactu), whatsapp (los mensajes), el negocio (llama)

### HUBS-F36 Mantener los sectores y los tipos de negocio en el admin
<!-- origen: fi:saas/django-admin#admin-businesstype fi:saas/django-admin#admin-sector fi:saas/support/developer-commerce#command-seed_taxonomy fi:saas/support/public-core-config#command-seed_taxonomy fi:saas/support/developer-commerce#modelo-businesstype fi:saas/support/developer-commerce#modelo-sector fi:saas/support/public-core-config#modelo-sector-functionalunit-businesstype fi:saas/support/developer-commerce#task-translation-py-modeltranslation fi:saas/support/public-core-config#translation-py-catalog -->
Estado: hecho
Actor: personal de ERPlora, sistema
Pantalla: admin › Negocios › Sectores y Tipos de negocio
Pasos:
1. En cada despliegue, erplora.com crea los sectores y tipos de negocio que falten de su lista de partida (12 sectores y 70 tipos), sin tocar lo que el personal ya cambió.
2. El personal abre «Sectores» o «Tipos de negocio» en el admin, busca por código o nombre y filtra por «Activo» (los tipos, también por «Sector» y por «Vertical»); cambia el orden y si está activo desde la misma lista.
3. En la ficha escribe el nombre y la descripción en inglés y en español, el icono, el color, el orden y si está activo; en un tipo de negocio, además, su sector y su «Vertical», la plantilla con la que nace un negocio de ese tipo.
4. Guarda: el alta del negocio, las páginas de cada sector y quien los lea por la API los reciben en su idioma (HUBS-F37).
Entra: lo que escribe el personal.
Sale: el sector o el tipo de negocio, con cada texto en inglés y en español.
Si falla: un nombre o una descripción en español sin sus tildes o copiados del inglés no se guardan y el campo dice cómo corregirlos; dos tipos de negocio con el mismo nombre en un idioma tampoco; una plantilla que ninguna aplicación construye no se acepta. Una cuenta sin la marca de personal no entra en el admin.
Implicados: public (las páginas de cada sector), apps (las plantillas que construye cada aplicación), accounts (el alta del negocio)

### HUBS-F37 Leer los sectores y los tipos de negocio
<!-- origen: old-saas:SAAS_PUBLIC-F28 fi:saas/support/developer-commerce#serializer-sectorserializer-functionalunitserializer-businesstypeserializer-functionalunitdetailserializer-catalogmoduleserializer-categoryserializer-subcategoryserializer fi:saas/support/public-core-config#serializers-catalog-sector-functionalunit-businesstype-catalogmodule-category-subcategory -->
Estado: hecho
Actor: cualquiera, integración
Pantalla: ninguna; las usan Crear negocio y las páginas de cada sector
Pasos:
1. Cualquiera, sin entrar, pide la lista de sectores o la de tipos de negocio, todos o los de un sector.
2. erplora.com contesta con los activos, en el orden que puso el personal, cada uno con su código, su nombre y su descripción en el idioma de quien pide (el inglés si falta el español), su icono y su color; cada tipo de negocio, con su sector y su plantilla.
3. El formulario de Crear negocio llena con ella su «Tipo de negocio (opcional)» y la web pública, sus páginas de sectores.
Entra: el idioma de quien pide y, si quiere, un sector.
Sale: las dos listas; nada se guarda.
Si falla: un sector que no existe da una lista vacía; un sector o un tipo desactivado no sale en su lista. Una clave de API de la cuenta también las lee.
Implicados: public (las páginas de cada sector), accounts (el alta del negocio en la Entrada)

## Para quien lo mantiene

- Anatomía, operaciones y decisiones: `hubs/README.md` (negocios, salto al Hub, foto y registro empujados al Hub,
  `reconcile_hub_states`, miembros, uso y demo).
- Partes del porte (MIGRATION-TASK APP-HUBS-1…5): este WORKBOOK nace en la parte 1 (F01–F14); la parte 2 añade
  F15–F23 (ajustes, dirección web y dominio propio, eliminar y recuperar, los suspendidos, estado y uso, admin del
  negocio); la parte 3, F24–F30 (las personas de cada negocio); la parte 4, F31–F37 (plan, derechos, contrato con el
  Hub y taxonomía). La revisión flujo a flujo de los `hecho` la hace la parte 5. Completa el 2026-11-01 (CLOSE-HUBS):
  F18, F20, F21 y F22 llegaron con la tenencia S2b (hub#580, saas#168); F32 y F34 ya los aplicaba el Hub (APP-BASE-3,
  -4 y -5); F17 se descarta en esta versión (saas#195). Lo decidido durante la migración está en la ronda de PLAN-SAAS
  de ese día.
- Equivalencia de claves del registro: G65 y G41 = F01; G66 = F02; G67, G09, G10 y G45 = F03; G68 = F04; G43,
  G04, G06, G21 y G44 = F05; G98 = F06; G91 = F07; G92 = F08; G69, G17, G18, G111 y G113 = F09; G14, G84 y
  G114 = F10; G70 = F11; G71 = F12; G72 y G12 = F13; G19 = F14. Parte 2: G08 y G73 = F15; G74 = F16; G75, G77,
  G13, G42, G112, G47 y G95 = F17; G11, G87, G88 y G89 = F18; G22 = F19; G94, G48 y G49 = F20; G90 = F21;
  G102 = F22; G02, G07 y G97 = F23; G46 y G51 = F07; G108 = F08. G93 y G85 (pausar y despertar el gratuito que
  nadie usa) se descartan: «Lo que NO hace». Parte 3: G78, G31, G32, G33, G55, G25, G28, G54, G56 y G50 = F24;
  G79 = F25; G80, G29, G26 y G57 = F26; G81, G30, G35 y G64 = F27; G82 = F28; G83, G27, G115, G86, G34, G24 y
  G53 = F29; G03 y G52 = F30. G24 («Usuarios del Terminal») era la página del SaaS viejo con los accesos, la
  actividad y los activos de un negocio (la misma que G83), no los empleados con PIN, que viven en el negocio.
  Parte 4: G76, G96, G101, G100, G15 y G60 = F31; G103 y G104 = F32; G63 = F33; G107, G109, G16 y G20 = F34; G62 y
  G99 = F35; G01, G05, G36, G37, G38, G58, G40 y G61 = F36; G110, G39 y G59 = F37. G23, G105 y G106 (el Hub da de alta,
  comprueba o quita en el SaaS a las personas que añade) se descartan: «Lo que NO hace».
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
- El panel vive bajo `/dashboard/` (FIX-SAAS-PANEL-UNDER-DASHBOARD-PREFIX, como `apps/dashboard/` del viejo): Negocios
  en `/dashboard/businesses`, Tienda, Facturación, Cuenta y «Reportar un problema» igual, nombrados una vez en
  `base/navigation.py` (`PANEL`, menú, correos, vuelta de Stripe) y `accounts/frontend/paths.ts` (páginas; guardarraíl
  `paths.test.ts`). La Entrada (`/launch`, `/shell`), las invitaciones y las páginas de la entrada se quedan en la raíz.
  `/dashboard` y `/dashboard/` → `/dashboard/businesses`.
- Direcciones viejas (F03, F09, F10, F13): `hubs/redirects.py`, 301 directo (un salto) de `/dashboard/`,
  `/dashboard/hubs/`, `…/active/`, `…/inactive/`, `…/create/` (`/dashboard/businesses?create=1`) y `…/<id>/qr/` (el
  Resumen). El resto de `/dashboard/*` viejo es de sus apps. Las del panel en la raíz antes del prefijo (`/businesses`,
  `/account`, `/billing`, `/store`, `/report-a-problem` y sus hijas, a las que enlaza el Hub) son 301 de
  `config/urls.py` (`MovedToPanel`) a la misma página bajo `/dashboard/`, con su consulta (`config/tests/test_panel_prefix.py`).
- Quitar a quien aún paga (trampa saas#2587 y saas#2569; HUBS-F27): `hubs.member.remove`
  no saca del negocio a quien aún lo paga (`queries.still_pays`: es dueño de su pagador, o tras un traspaso el plan
  se sigue cobrando al cliente de Stripe de uno de sus pagadores). 409 `hubs.member_pays` con qué hacer: que el
  propietario ponga sus datos de pago (se piden al pagar un plan o un módulo) o, si el plan sigue en la tarjeta
  anterior, que lo mantenga con la suya en Facturación (`billing.plan.take_over`, HUBS-F28; hasta entonces
  `billing.payer_required`). Así nadie paga un negocio que ya no ve, y
  `accounts` retiene la cuenta de quien paga (`accounts.pays_businesses`, ACCOUNTS-F27). Tests:
  `hubs/tests/test_members.py::TestRemoveThePayer`.
- Planes (F05): `Plan` con columnas por idioma (`TranslatedFields`, `<campo>_en` y `<campo>_es`), sembrados por la
  migración `0013`; el admin (`hubs/admin.py`) es la única escritura. La lista pública es `hubs.plan.list`. La
  `0020` quita de las fichas de Pro, Enterprise y Max (descripción y características) lo que prometía
  infraestructura, sin tocar planes, precios ni límites (PLAN-SAAS §9). La `0021` quita de las características de
  Starter y Standard «todos sus locales» y «varios locales» (la multitienda va desde Pro y se cobra por ubicación,
  PLAN §32) y de Gratis y Starter los niveles de apps («All free apps included», «free and premium» → «All apps
  included»: todos los planes incluyen todas las apps), con la misma guarda: solo si la columna sigue con el texto de
  la `0013`, y reverse simétrico. `included_level` se queda en el modelo, sin uso en la web pública.
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
- Uso (F21, F22): el Hub sirve `GET /internal/usage` desde la tenencia S2b (hub#580; contrato en `hubs/README.md`):
  `db_bytes` es el tamaño de la BD propia de cada negocio. `collect_hub_usage` lo recoge cada noche (`hub-usage-daily`);
  sin ninguna noche medida, la tarjeta dice «Sin datos todavía…». La copia de los datos de F18 y F20 la hace el Hub al
  recibir la baja (hub#580) y el SaaS la enseña y la descarga con `GET /internal/hubs/{id}/dumps` (saas#168).
- Dominio propio (F17, `descartado` en esta versión, saas#195): decisión de mercado de APP-HUBS-2 (PLAN-SAAS §8, ronda
  2026-10-22; ADR-0502): se mantiene solo para la web pública (`website`) y en planes con `includes_custom_domain`, y
  llega con sus tres piezas (erplora.com, borde de `aws` y el host en `base` del Hub); hasta entonces no hay modelo ni
  pantalla.
- Pruebas de la parte 2: e2e en `tests/e2e/panel/hubs-settings.spec.ts` (clave `HUBS-Gnn` en el título).
- Personas (F24–F30): `hubs.member.{list,invite,change_role,remove,resend,cancel}`,
  `hubs.invitation.{list_mine,accept,decline}` y `hubs.ownership.{transfer,accept,decline,cancel}` (`api.py`, bajo
  `/api/hubs/members`, `/api/hubs/invitations` y `/api/hubs/ownership`). Cada fila de `hubs.member.list` trae sus
  `actions`, calculadas con las mismas reglas que las escrituras (`queries.member_actions`, `services._managed`).
  Quitar, cambiar el rol de alguien que ya respondió y aceptar un traspaso encolan `SessionRevocation`
  (`POST /internal/sessions/revoke`, `{user_id, hub_id}`), que el Hub sirve desde BASE-F13 (`base/internal.py`) y
  que se reintenta con espera creciente y en `reconcile_hub_states` si el negocio no contesta. Correos (`emails.py`,
  con la plantilla común `base.emails.branded_message`, texto y HTML en el idioma de quien recibe): `send_invitation`
  (enlaza a `/invitation` y, a una cuenta sin forma de entrar, a `/password/reset`), `send_ownership_offer` (enlaza a
  `/dashboard/businesses`, donde está la tarjeta de la oferta; el panel no tiene página `/ownership/<id>`; con un plan
  de pago dice hasta cuándo está pagado y enlaza a `/dashboard/billing/subscriptions`) y `send_ownership_accepted`
  (enlaza a `/dashboard/businesses/<id>` y, con un plan de pago, dice que la tarjeta del saliente ya no lo renueva). Tests:
  `hubs/tests/test_members.py`, `test_members_api.py`,
  `test_ownership.py`, `test_session_revocations.py`, `test_invite_unverified_account.py`, `test_emails.py`,
  `test_permission_matrix.py` y `test_admin.py`; e2e en `tests/e2e/panel/hubs-people.spec.ts` (clave `HUBS-Gnn` en el
  título), con `members.spec.ts` e `invitation.spec.ts`.
- Pruebas: cada test cita su clave en el nombre o el docstring; los e2e de esta parte están en
  `tests/e2e/panel/hubs-flows.spec.ts` (con la clave del registro, `HUBS-Gnn`, en el título).
- La foto (F31; PLAN-SAAS §2.2): `queries.hub_snapshot` (`PUT /internal/hubs/{id}/state`), con `plan` = los campos de
  `queries.SNAPSHOT_PLAN_FIELDS`; sube `state_version` y se empuja tras el COMMIT (`services.sync_hub`), la reintenta
  `reconcile_hub_states` y la repite `push_hub_snapshots` cada noche. Un cambio en el admin de uno de esos campos de un
  `Plan` (`PlanAdmin.save_model` → `services.owe_plan_rights`) reescribe los módulos de su nivel (`sync_plan_modules`) y
  sube la versión de cada negocio vivo con ese plan o con su prueba; la entrega la siguiente pasada (trampa de
  SAAS_DASHBOARD-F53/F54: el cambio del admin no llegaba al Hub). VeriFactu en todos los planes (PLAN §30, ronda
  2026-10-22b): el bloque `verifactu` lleva solo `representation`; `live_paid` se quitó de la foto cuando el Hub retiró
  esa condición (FIX-HUB-VERIFACTU-RETIRE-LIVE-PAID). Tests: `hubs/tests/test_hub_sync.py`, `test_plan_rights_reach_businesses.py`,
  `test_contract_hub.py`, `fiscal/tests/test_snapshot.py`; e2e `tests/e2e/panel/hubs-rights.spec.ts` («HUBS-G101»).
- Lo que el Hub aplica de la foto (F32 y F34; APP-BASE-3, -4 y -5 del Hub, hub#232, hub#229 y hub#244): `plan.max_devices`
  al entrar (`_end_other_devices`, BASE-F57), las plazas de `plan.max_users` en su personal (BASE-F77; las personas del
  Hub son las `members` de la foto, así que el tope lo aplica el SaaS al invitar) y el derecho de cada módulo `premium`
  (`base/entitlement.py`: 402 `app_entitlement_blocked`, fuera del menú y del relevo; su página de apps dice `plan`,
  `purchase` o la app que la trae, BASE-F14, F20 y F27). Los mensajes del asistente (F33) no los cuenta el Hub: los cuenta y los
  frena en cada turno la pasarela de `assistant` (ASSISTANT-F18, `assistant.message.claim`), con el cupo del plan
  (`Plan.assistant_messages_per_month`), y el Hub enseña las cifras de su puerta `usage` y del frame `usage`. El SaaS ya aplica `max_users` al invitar (`hubs/tests/test_seats.py`). Tests de la parte 4:
  `test_snapshot_rights.py` (una compra o el plan de otro negocio nunca llegan a este; bajar a Gratis no saca a nadie).
  Un `Module` nuevo, o con otro `tier`, en el admin de `apps` (`ModuleAdmin.save_model` → `services.owe_module_rights`)
  reescribe los módulos del plan de cada negocio vivo cuyo plan (o prueba) alcanza el nivel nuevo o el anterior, y sube
  su versión si cambian; lo entrega `reconcile_hub_states`. Tests: `test_plan_rights_reach_businesses.py` (HUBS-F34).
- Admin de Planes (pantalla de F05, vista en F31): nombres traducibles en los campos de `Plan` (migración `0018`, solo
  de estado), su `__str__` en el idioma activo («Starter · 29,99 €/mes») y el nivel y el soporte elegidos por sus
  nombres traducidos (`PlanForm`, sin cambiar los valores guardados). Tests: `test_admin.py` («plan … speaks Spanish»).
- Quién llama (F35): `/internal/*` se firma con HMAC (`accounts/signing.py`: v1 + v2, dos secretos vivos, 5 minutos). El
  guardarraíl `hubs/tests/test_internal_doors.py` recorre el resolver de URLs: toda puerta `internal/…` contesta 401 (o
  405) sin firma, con otra firma, con una hora vieja o con la sesión del personal; una puerta nueva sin la comprobación
  lo hace fallar.
- Taxonomía (F36, F37): `Sector` y `BusinessType` (columnas por idioma, sin modeltranslation), `seed_taxonomy` (en
  `saas-migrate` de cada despliegue; crea lo que falta, `--update` lo reescribe) y su admin, con los nombres de sus campos
  traducidos (migración `0017`, solo de estado). Lectura pública: `hubs.sector.list` y `hubs.business_type.list`
  (`/api/catalog/sectors`, `/api/catalog/business-types`). Sin unidades funcionales, categorías ni subcategorías
  (ronda 16, PLAN §21: la sección de una app la declara su `LiveAppConfig`). Tests: `test_api.py`,
  `test_seed_taxonomy.py`, `test_taxonomy_*.py` y `test_admin.py` («speak Spanish»); e2e `hubs-rights.spec.ts`
  («HUBS-G05 + HUBS-G01»).

## Lo que queda fuera

- **Conectar un dominio propio a la web del negocio** (HUBS-F17): fuera de la fase 1, llega con sus tres piezas
  (erplora.com, la entrada de ERPlora y el Hub) — saas#195.
- **Desde el Hub, «Mejorar plan» y «erplora.com» piden volver a entrar con la cuenta si el navegador no tenía la sesión
  abierta** (BASE-F11 del Hub, cruza esta app) — saas#190.

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
- No conecta todavía un dominio propio (HUBS-F17, saas#195): la web y la entrada de cada negocio están en su dirección
  de erplora.com.
- No entra sola en un negocio ya existente al abrir la Entrada, tampoco con uno solo: elige la persona.
- No tiene una página con las personas de todos los negocios: cada negocio enseña las suyas en «Miembros» (ronda 17:
  el panel es Negocios, Tienda, Facturación y Cuenta).
- No enseña la actividad reciente de las personas ni cuántas están conectadas: la actividad vive dentro del negocio.
- Nadie se sale solo de un negocio: lo quitan el propietario o un administrador, como en Square, Toast o Shopify.
- No da de alta a empleados que solo usen un PIN en la caja: toda persona entra en el negocio por «Miembros», con su
  cuenta, y su PIN o su placa se ponen dentro del negocio.
- No da de alta, no comprueba ni quita en erplora.com a las personas que se añaden o se quitan dentro del negocio:
  quién tiene cuenta y acceso se decide en «Miembros» (HUBS-F24 a HUBS-F28) y el negocio lo recibe en su foto
  (HUBS-F31); la entrada de cada persona la comprueba erplora.com al saltar al negocio.
- No firma un permiso para comprobarlo sin conexión: el negocio en la nube guarda su foto y no pregunta en cada venta;
  el permiso firmado de una aplicación que trabaje sin conexión llegará con el modo local.
- No enseña una página con las aplicaciones instaladas en cada negocio: las encendidas viven en el negocio y las de
  pago se ven en Tienda › Módulos (BILLING-F31).
- No clasifica las aplicaciones en unidades funcionales, categorías ni subcategorías: cada aplicación declara su
  sección y sus tipos de negocio (APPS-F06).
- La propiedad no se da cambiando el rol: solo con un traspaso que la otra persona acepta.
