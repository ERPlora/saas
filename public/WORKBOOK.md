# Workbook — Web pública (public)
Prefijo: PUBLIC
Alcance MVP: fase 1 (la web pública de erplora.com: lo que lee quien todavía no tiene cuenta y la puerta hacia el alta)
Estado de la app: hecha (la web, la ayuda, el contacto, las cookies, los textos legales, la tienda de apps, las descargas y la demo); lo que se crea dentro de una demo se borra con ella desde la fase 2 (PUBLIC-F34)

> Manual de uso y especificación de la app `public` del SaaS (erplora.com). Cuenta lo que ve una persona que llega a
> erplora.com sin cuenta: qué es ERPlora, cuánto cuesta, para qué negocios sirve, cómo protege los datos, en qué
> países cumple con la facturación, cómo se empieza y cómo se prueba una demo sin cuenta. Esta parte del manual no se
> publica en la tienda: es la referencia del equipo y de la QA.

## Para qué sirve y para quién

La web pública es el escaparate de ERPlora y la puerta del alta. Explica el producto con datos vivos (los planes y
sus precios salen de los mismos planes que se cobran; las apps, del catálogo publicado) y lleva a la pantalla de
entrar, donde también se crea la cuenta.

- Todo lo que promete lo hace hoy el producto: si algo no existe, la web no lo nombra.
- El precio que enseña es el que se cobra, sin IVA, con la nota de impuestos al lado.
- Se lee en inglés o en español; el idioma se elige solo (navegador) o desde el pie de cualquier página.

Quién la usa:

- **Cualquier visitante**, sin cuenta: lee, compara, cambia de idioma y empieza gratis.
- **Buscadores y asistentes**: leen el mapa del sitio, las reglas de rastreo, el resumen para asistentes y los datos
  estructurados de cada página.
- El **personal de ERPlora** mantiene los planes (y con ellos los precios de la web) desde el admin.

## Referencia adoptada

- **Shopify, Square y Lightspeed**: una portada con una sola llamada principal («Empieza gratis») que lleva al alta,
  planes con el precio mensual y el ahorro anual calculado, y la nota de impuestos junto al precio
  (https://www.shopify.com/pricing, https://squareup.com/us/en/pricing).
- **Stripe, Shopify y Square**: el selector de idioma en el pie de todas las páginas, con cada idioma escrito en su
  propia lengua (https://stripe.com, https://www.shopify.com).
- **Odoo y Microsoft Dynamics 365 Business Central**: la lista de países con lo que el producto cumple en cada uno,
  publicada con el producto y no editada a mano
  (https://www.odoo.com/documentation/19.0/applications/finance/fiscal_localizations.html,
  https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/compliance/apptest-countries-and-translations).
- **Lightspeed, Holded, fiskaly y Mollie**: la página de cumplimiento dice el sistema fiscal concreto de cada país y
  lo que queda fuera (VeriFactu frente a TicketBAI en España)
  (https://k-series-support.lightspeedhq.com/hc/en-us/articles/53394509875099-Understanding-Spanish-fiscal-compliance,
  https://www.holded.com/es/programa-contabilidad/cumplimiento-fiscal,
  https://www.fiskaly.com/fiscalisation,
  https://help.mollie.com/hc/en-us/articles/26810769614226-How-do-fiscalisation-regulations-work-with-Mollie-Point-of-Sale).
- **llmstxt.org y schema.org**: el resumen para asistentes y los datos estructurados de organización, aplicación y
  preguntas frecuentes (https://llmstxt.org, https://schema.org/SoftwareApplication).

- **AEPD, ICO y CNIL; GitHub**: las cookies técnicas no piden consentimiento, así que el aviso solo aparece cuando
  la web mide visitas o hace publicidad (https://www.aepd.es/guias/guia-cookies.pdf,
  https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guide-to-pecr/cookies-and-similar-technologies/,
  https://www.cnil.fr/fr/cookies-et-autres-traceurs/regles/cookies-solutions-pour-les-outils-de-mesure-daudience,
  https://github.blog/news-insights/company-news/no-cookie-for-you/).
- **Intercom, HubSpot y Zendesk**: el mensaje del formulario de contacto se responde a quien lo escribió, llega con
  el tema de la página de la que viene y lo escrito no se pierde si algo falla
  (https://www.hubspot.com/products/marketing/forms, https://www.zendesk.com/service/messaging/).
- **Shopify POS, Square POS; Safari View Controller y Custom Tabs**: dentro de una app, un texto legal se abre en un
  visor con solo el texto y una forma de volver, sin el resto de la web
  (https://developer.apple.com/documentation/safariservices/sfsafariviewcontroller,
  https://developer.chrome.com/docs/android/custom-tabs).
- **Shopify App Store y Odoo Apps**: la tienda por secciones con búsqueda, y la ficha de cada app con lo que
  necesita y su documentación (https://apps.shopify.com, https://apps.odoo.com).
- **Odoo y Dolibarr**: una demo de verdad, sin cuenta ni tarjeta, que se abre en el navegador, dura un tiempo
  limitado y se borra con todo lo que tenga dentro; quien quiere conservar su trabajo crea su propia cuenta
  (https://demo.odoo.com, https://www.dolibarr.org/onlinedemo).

## Antes de empezar

- La web se sirve desde erplora.com; en desarrollo, desde el puerto 8001 del SaaS.
- Los sectores salen de la taxonomía que se siembra en cada despliegue; sin ella, la lista de sectores dice que
  todavía se están configurando.
- La demo la crea el hub: sin el hub en marcha, la pantalla de la demo dice que no está disponible.

## Pantallas

### Portada
El titular «Un ERP. Infinitas configuraciones. Tuyo.» con «Empieza gratis», «Prueba la demo» y «Descargas»; debajo,
la franja «Hecho para pequeños negocios», lo que cuesta un conjunto típico de herramientas frente a ERPlora, la
plataforma, las apps, la app del mostrador, los planes, una comparativa, la llamada final y el contacto.

### Planes y precios
«Empieza gratis. Escala cuando lo necesites.» con una tarjeta por plan a la venta, la tabla de lo incluido en cada
plan, las comparativas con otros ERP y las preguntas frecuentes.

### Detalle de un plan
El nombre, la descripción, el precio mensual por hub con la nota de IVA, «Qué incluye», el botón para empezar y
«Otros planes».

### Sectores
«ERPlora para tu negocio.» con los tipos de negocio por sector y, al abrir uno, su página: la pregunta que
escribiría en un buscador, las apps con las que viene, las preguntas frecuentes y los enlaces a precios, apps,
producto y cumplimiento.

### Características, Seguridad y Actualizaciones
Tres páginas de producto: qué hace la plataforma, cómo protege los datos (con «Contactar con el Equipo de
Seguridad») y la política de actualizaciones (con «Leer la cláusula 7»).

### Cumplimiento
«Cumplimiento en la UE.»: tres cifras, los países «Listo para operar de verdad.» con su sistema fiscal y la
cuadrícula «Otros países de la UE.» con «Todavía sin conexión».

### Sobre nosotros, Colabora y las páginas «Muy pronto»
La misión de ERPlora, el programa de colaboradores con el año gratis valorado al precio de un año del plan, y
Blog, Empleos y Prensa, que solo anuncian lo que viene.

### Pie de página
Las columnas Producto, Empresa y Soporte, los enlaces legales y el selector de idioma «English · Español».

### Centro de ayuda y Soporte
«Centro de ayuda.» con una guía plegada por tema y su buscador; Soporte, con los tres caminos para pedir ayuda y qué
contar en el mensaje.

### Contacto
«Contáctanos» con el formulario, «Información de Contacto» (el correo de soporte y «Escríbenos») y «Tiempo de
respuesta»; el mismo formulario cierra la portada.

### Aviso de cookies y Preferencias de cookies
El aviso, solo cuando la web mide visitas, y «Preferencias de cookies» con una categoría por bloque y su interruptor.

### Textos legales y Declaración responsable
Aviso legal, Privacidad, Términos y la política de cookies, cada uno en su página; la declaración responsable en
vigor con su copia firmada y el archivo de versiones.

### Tienda de apps y Ficha de una app
Las apps por sección con la búsqueda y los filtros; la ficha con «Resumen», «Apps necesarias» y, si la tiene,
«Documentación».

### Descargas y La app de ERPlora
«Dos formas gratuitas de probar ERPlora.» con el hub en la nube y la app del mostrador por plataforma, y la página de
la app instalada.

### Demo
«Prueba ERPlora sin registrarte.» con una tarjeta que cambia según el momento: lo que trae la demo y «Prueba la
demo»; la demo en marcha, cuánto le queda y «Volver a mi demo»; o el motivo por el que ahora no se puede (apagada,
llena, demasiadas desde la conexión, no disponible, terminada) con lo que se puede hacer. Siempre hay un camino a
«Empieza gratis».

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | Las páginas llegan completas del servidor: no hay esqueleto ni espera. |
| Vacío | Sin planes a la venta, Planes y precios dice que no hay planes y no pinta tablas, y la portada omite el bloque de planes; sin apps publicadas, la portada omite los bloques de apps; sin sectores, «Todavía no hay tipos de negocio». |
| Error | Una dirección que no existe enseña «Página no encontrada» con el menú de la web; un fallo del servidor, «Algo ha fallado por nuestra parte», sin depender de la base de datos. La demo dice en su propia pantalla por qué no se puede dar ahora y qué hacer (PUBLIC-F29 a PUBLIC-F33). |
| Sin permiso | No aplica: todo es público. Las páginas privadas no aparecen en el mapa del sitio ni se dejan rastrear. |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| PUBLIC-F01 | Ver la portada | hecho |
| PUBLIC-F02 | Ver los planes y los precios | hecho |
| PUBLIC-F03 | Ver el detalle de un plan | hecho |
| PUBLIC-F04 | Que el precio pintado sea el que se cobra | hecho |
| PUBLIC-F05 | Ver los sectores y la página de un tipo de negocio | hecho |
| PUBLIC-F06 | Leer Características, Seguridad y Actualizaciones | hecho |
| PUBLIC-F07 | Leer solo lo que el producto hace | hecho |
| PUBLIC-F08 | Leer lo que la web dice de seguridad, datos y disponibilidad | hecho |
| PUBLIC-F09 | Ver el cumplimiento por país | hecho |
| PUBLIC-F10 | Conocer la empresa: Sobre nosotros y Colabora | hecho |
| PUBLIC-F11 | Empezar gratis desde cualquier página | hecho |
| PUBLIC-F12 | Llegar a una página «Muy pronto» o a una dirección retirada | hecho |
| PUBLIC-F13 | Cambiar de idioma | hecho |
| PUBLIC-F14 | Que buscadores y asistentes lean la web | hecho |
| PUBLIC-F15 | Leer la ayuda y el soporte | hecho |
| PUBLIC-F16 | Escribir al equipo desde el formulario de contacto | hecho |
| PUBLIC-F17 | Llegar al formulario desde otras páginas | hecho |
| PUBLIC-F18 | Ver los canales y el plazo de respuesta | hecho |
| PUBLIC-F19 | Decidir sobre las cookies | hecho |
| PUBLIC-F20 | Leer los textos legales | hecho |
| PUBLIC-F21 | Consultar la declaración responsable del sistema de facturación | hecho |
| PUBLIC-F22 | Recorrer la tienda de apps | hecho |
| PUBLIC-F23 | Ver la ficha de una app | hecho |
| PUBLIC-F24 | Conseguir la aplicación instalada | hecho |
| PUBLIC-F25 | Saber qué versión de la aplicación está publicada | hecho |
| PUBLIC-F26 | Abrir una página pública desde la aplicación instalada | hecho |
| PUBLIC-F27 | Llegar a la demo | hecho |
| PUBLIC-F28 | Crear la demo y entrar en ella | hecho |
| PUBLIC-F29 | Una demo que no se ha podido abrir | hecho |
| PUBLIC-F30 | La demo está apagada | hecho |
| PUBLIC-F31 | Todas las demos están ocupadas | hecho |
| PUBLIC-F32 | Límite de demos por conexión | hecho |
| PUBLIC-F33 | La demo terminó | hecho |
| PUBLIC-F34 | Retirar las demos que vencen | parcial |
| PUBLIC-F35 | De la demo a una cuenta de verdad | hecho |
| PUBLIC-F36 | Pedir una demo desde otra aplicación | descartado |
| PUBLIC-F37 | La demo no cuenta como un negocio | hecho |

### PUBLIC-F01 Ver la portada
<!-- origen: old-saas:SAAS_PUBLIC-F55 -->
Estado: hecho
Actor: visitante
Pantalla: Portada
Pasos:
1. La persona abre erplora.com y ve «Un ERP. Infinitas configuraciones. Tuyo.» con tres botones: «Empieza gratis», «Prueba la demo» y «Descargas».
2. Al bajar encuentra lo que pagaría por separado por facturación, inventario, clientes y venta (con el total sumado de esas filas) frente al plan más barato de ERPlora, la plataforma, las apps destacadas, la app del mostrador, el ecosistema, los planes, una comparativa, más apps, la llamada final y el formulario de contacto.
3. Las seis apps destacadas y las doce del bloque «a tu medida» son las primeras del catálogo publicado por sección y nombre; las tarjetas de plan son los planes a la venta, el gratuito primero.
Entra: el catálogo de apps publicado y los planes a la venta.
Sale: nada guardado; los datos estructurados de la organización y de la aplicación (PUBLIC-F14).
Si falla: sin apps publicadas se omiten los bloques de apps; sin planes a la venta, el bloque de planes. Las tarjetas dicen el precio sin IVA con su nota, nunca un total con IVA. Las cifras de la portada no se escriben a mano: el número de apps, los precios y el total de la tabla salen de los datos.
Implicados: hubs (los planes), apps (el catálogo), accounts (la entrada)

### PUBLIC-F02 Ver los planes y los precios
<!-- origen: old-saas:SAAS_PUBLIC-F56 fi:saas/public#pagina-publica-de-precios-planes -->
Estado: hecho
Actor: visitante
Pantalla: Planes y precios
Pasos:
1. La persona abre «Precios» y ve «Empieza gratis. Escala cuando lo necesites.» y una tarjeta por plan con el que se puede empezar (Gratis, Starter y Standard), con el precio mensual por hub, sus características y los mensajes al mes del asistente y de WhatsApp.
2. Si el plan tiene precio anual, la tarjeta dice el precio del año y los meses que ahorra («≈ 299,90 €/año · 2 meses gratis»), calculados de los dos precios; si todos los planes de pago ahorran lo mismo, la cabecera lo dice una vez («Paga el año y llévate 2 meses gratis.»).
3. Más abajo, la tabla de lo incluido en cada plan, las comparativas con otros ERP y las preguntas frecuentes; por encima de Standard no ofrece nada más.
Entra: los planes a la venta (los de mejora, como Pro, Enterprise y Max, no se pintan).
Sale: nada guardado; los datos estructurados de las preguntas frecuentes, salidos de la misma lista que el desplegable.
Si falla: sin planes a la venta, la página lo dice y no pinta tablas. Si el precio anual no ahorra ningún mes entero, la tarjeta dice solo el precio del año, sin «meses gratis». Un plan sin mensajes de asistente o de WhatsApp no los nombra.
Implicados: hubs (los planes), billing (el cobro, PUBLIC-F04)

### PUBLIC-F03 Ver el detalle de un plan
<!-- origen: old-saas:SAAS_PUBLIC-F57 fi:saas/public#detalle-publico-de-un-plan -->
Estado: hecho
Actor: visitante
Pantalla: Detalle de un plan
Pasos:
1. La persona llega a la página de un plan (por su dirección o desde «Otros planes» de otro plan).
2. Ve el nombre, la descripción, el precio mensual por hub con la nota de IVA y «Qué incluye».
3. Pulsa «Comenzar» y llega a la pantalla de entrar, donde también se crea la cuenta (PUBLIC-F11); «Otros planes» lleva a los demás planes a la venta.
Entra: el plan por su identificador.
Sale: nada guardado.
Si falla: un plan interno, retirado, de mejora o que no existe da «Página no encontrada». «Qué incluye» es la lista del plan sin los separadores heredados.
Implicados: hubs (los planes), accounts (la entrada)

### PUBLIC-F04 Que el precio pintado sea el que se cobra
<!-- origen: old-saas:SAAS_PUBLIC-F58 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. El precio de un plan (mensual y anual) vive en un solo sitio, sin IVA; la portada, Planes y precios, el detalle de un plan y Colabora lo leen de ahí.
2. El cobro de un plan usa ese mismo importe y el precio de Stripe pegado en el plan; el personal no puede guardar un precio de Stripe que cobre otra cantidad, en otra moneda o con el IVA incluido.
3. El IVA se calcula en el pago, a partir del NIF o NIF-IVA del comprador, y la web lo dice junto a cada precio.
Entra: el precio mensual y el anual de cada plan y sus precios de Stripe.
Sale: nada guardado.
Si falla: un precio de Stripe que no casa con el del plan se rechaza al guardarlo en el admin, con el motivo; si Stripe no contesta, no se da por bueno. Así la web no puede enseñar un precio y el pago cobrar otro.
Implicados: hubs (los planes), billing (el cobro y la comprobación de precios)

### PUBLIC-F05 Ver los sectores y la página de un tipo de negocio
<!-- origen: old-saas:SAAS_PUBLIC-F60 fi:saas/public#detalle-publico-de-una-industria fi:saas/public#listado-publico-de-industrias-tipos-de-negocio -->
Estado: hecho
Actor: visitante
Pantalla: Sectores
Pasos:
1. La persona abre «Industrias» y ve «ERPlora para tu negocio.» con los tipos de negocio, que puede filtrar por sector.
2. Abre uno y ve el titular con la pregunta que escribiría en un buscador («Software TPV y ERP para tu peluquería»), un arranque con el precio de entrada y cuántas apps hay, las apps con las que viene ese tipo de negocio y sus preguntas frecuentes.
3. Abajo tiene los enlaces a precios, a la tienda de apps, al producto y al cumplimiento, y «Empieza gratis» y «Explorar apps».
Entra: los sectores y tipos de negocio activos y las apps publicadas de su sector.
Sale: nada guardado; los datos estructurados de la aplicación y de las preguntas frecuentes.
Si falla: un tipo de negocio que no existe o está inactivo da «Página no encontrada»; un código retirado lleva para siempre al vigente. Sin apps para ese tipo de negocio no se pinta el bloque de apps. La página no nombra leyes de un país: el cumplimiento tiene su propia página (PUBLIC-F09).
Implicados: hubs (la taxonomía y los planes), apps (el catálogo)

### PUBLIC-F06 Leer Características, Seguridad y Actualizaciones
<!-- origen: old-saas:SAAS_PUBLIC-F61 fi:saas/public#paginas-de-producto-estaticas-features-security-updates -->
Estado: hecho
Actor: visitante
Pantalla: Características, Seguridad y Actualizaciones
Pasos:
1. En «Características» lee qué hace la plataforma: el punto de venta, el catálogo, el asistente y la app del mostrador.
2. En «Seguridad» lee cuatro bloques (acceso, datos, infraestructura y cumplimiento) y «Contactar con el Equipo de Seguridad» lo lleva al formulario de contacto.
3. En «Actualizaciones» lee por qué ERPlora actualiza sin preguntar, qué se compromete a cambio, cuándo avisa y cómo salir; «Leer la cláusula 7» abre los términos.
Entra: nada; el texto de las páginas.
Sale: nada guardado.
Si falla: las tres páginas dicen lo que la plataforma da, nunca con qué tecnología está hecha. Lo que prometen de seguridad lo vigila PUBLIC-F08.
Implicados: ninguno

### PUBLIC-F07 Leer solo lo que el producto hace
<!-- origen: old-saas:SAAS_PUBLIC-F76 -->
Estado: hecho
Actor: visitante
Pantalla: Portada, Planes y precios, Características, Colabora
Pasos:
1. La persona lee la portada, Planes y precios, las páginas de producto y Colabora para hacerse una idea de qué hace ERPlora.
2. Todo lo que se nombra existe hoy en las apps: punto de venta, facturación con VeriFactu, inventario, clientes, citas y reservas, personal y control horario, cocina y mesas.
3. La tabla de lo que se pagaría por separado solo lista funciones que las apps cubren y su total es la suma de sus filas.
Entra: nada; el texto de las páginas, contrastado con las apps del producto.
Sale: nada guardado.
Si falla: no se anuncia contabilidad, nóminas, tickets de soporte, TicketBAI, los modelos 303, 390 y 347, almacenes con lotes y caducidades ni conciliación bancaria, porque ninguna app los hace; la franja de sectores nombra los negocios que se sirven hoy (hostelería, comercio, peluquería y estética, servicios profesionales). Las comparativas con otros productos pueden nombrar lo que hacen ellos.
Implicados: ninguno

### PUBLIC-F08 Leer lo que la web dice de seguridad, datos y disponibilidad
<!-- origen: old-saas:SAAS_PUBLIC-F77 -->
Estado: hecho
Actor: visitante
Pantalla: Seguridad, Planes y precios, Portada, Sobre nosotros
Pasos:
1. La persona lee qué dicen Seguridad, las preguntas frecuentes de precios, la portada y Sobre nosotros sobre el acceso, los datos y la disponibilidad.
2. Lee lo que funciona hoy: sesiones de servidor en cookies seguras, código de un solo uso para entrar en el negocio, entrar con Google, contraseñas con hash y sal, cifrado en tránsito y en reposo, solo HTTPS con TLS 1.2 o 1.3, AWS en Irlanda con su cortafuegos web, copias continuas recuperables a cualquier momento de los últimos 14 días y alta disponibilidad.
3. A «¿Dónde se almacenan mis datos?» la respuesta es la Unión Europea, con la única excepción del asistente si su proveedor europeo no está disponible, y el enlace «Lee la política de privacidad».
Entra: nada; el texto de las páginas, contrastado con la infraestructura y la política de privacidad.
Sale: nada guardado.
Si falla: no se promete un acuerdo de disponibilidad con porcentaje, soporte 24/7, auditorías periódicas, informes de pruebas de intrusión, cifrado de extremo a extremo ni entrar con GitHub, y nunca «tus datos nunca salen de la UE», que contradiría la política de privacidad.
Implicados: ninguno

### PUBLIC-F09 Ver el cumplimiento por país
<!-- origen: old-saas:SAAS_PUBLIC-F62 fi:saas/public#pagina-publica-de-cumplimiento-por-pais -->
Estado: hecho
Actor: visitante
Pantalla: Cumplimiento
Pasos:
1. La persona abre «Cumplimiento» desde el pie de cualquier página (o desde la página de un tipo de negocio) y ve «Cumplimiento en la UE.» con tres cifras: los países de la UE donde puede vender, los conectados a su sistema fiscal y los que todavía no.
2. En «Listo para operar de verdad.» ve España, «Conectado», con VeriFactu: cada factura y cada tique se registra en una cadena inalterable, lleva su código QR y se envía a la AEAT; y lo que queda fuera: el País Vasco (TicketBAI) y Navarra tienen sus propios sistemas, a los que ERPlora todavía no se conecta. «Lee nuestra declaración responsable» abre la declaración.
3. En «Otros países de la UE.» ve el resto, cada uno con «Todavía sin conexión»: puede crear su negocio y vender, y debe consultar con su asesor qué exige su país antes de usar allí el TPV.
Entra: los países donde se puede crear un negocio y los sistemas fiscales a los que se conectan las apps.
Sale: nada guardado.
Si falla: un país solo sale como conectado cuando una app se conecta de verdad a su sistema; no se nombran normativas de otros países que nadie ha comprobado. España va primero y el resto por orden alfabético en el idioma de lectura.
Implicados: hubs (los países del alta), verifactu del negocio (la conexión con la AEAT)

### PUBLIC-F10 Conocer la empresa: Sobre nosotros y Colabora
<!-- origen: old-saas:SAAS_PUBLIC-F63 fi:saas/public#pagina-de-colaboracion-partners-con-cifras-dinamicas fi:saas/public#paginas-de-empresa-estaticas-about-careers-blog-press-developers fi:saas/public#redireccion-legacy-company -->
Estado: hecho
Actor: visitante
Pantalla: Sobre nosotros, Colabora
Pasos:
1. «Sobre Nosotros» cuenta la misión, cómo se guardan los datos de cada negocio y que todas las apps son de ERPlora.
2. «Colabora» explica el programa en cuatro pasos y ofrece un negocio completo gratis durante un año, valorado en lo que cuesta un año del plan de pago más barato (su precio anual), con los sectores y tipos de negocio que hay hoy; «Solicitar Ahora» lleva al contacto con el asunto del programa.
3. La dirección antigua de la empresa lleva para siempre a «Sobre Nosotros»; Blog, Empleos y Prensa son páginas «Muy pronto» (PUBLIC-F12).
Entra: los planes a la venta y la taxonomía (sectores y tipos de negocio activos).
Sale: nada guardado; la solicitud llega como mensaje del formulario de contacto.
Si falla: sin plan de pago a la venta, Colabora no inventa un valor; sin taxonomía, no dice cifras. No hay página de desarrolladores: no hay apps de terceros.
Implicados: hubs (los planes y la taxonomía)

### PUBLIC-F11 Empezar gratis desde cualquier página
<!-- origen: old-saas:SAAS_PUBLIC-F78 -->
Estado: hecho
Actor: visitante
Pantalla: Portada, Planes y precios, Detalle de un plan, Sectores, Características, Cumplimiento
Pasos:
1. La persona pulsa «Empieza gratis» (cabecera, portada, sectores, características) «Empezar» (tarjetas de plan de pago) o «Comenzar» (detalle de un plan) en cualquier página.
2. Llega a la pantalla de entrar de erplora.com, donde también se crea la cuenta.
3. Crea la cuenta y su negocio, que nace en el plan Gratis; el plan de pago se elige después, desde el panel.
Entra: nada: el botón no lleva parámetros.
Sale: nada en la web; la cuenta y el negocio los crea el alta.
Si falla: la tarjeta del plan gratuito dice «Empieza gratis» y la de un plan de pago «Empezar», porque todo negocio empieza en Gratis. Elegir un plan o un sector en la web no lo preselecciona en el alta.
Implicados: accounts (la entrada y el alta), hubs (el negocio en Gratis)

### PUBLIC-F12 Llegar a una página «Muy pronto» o a una dirección retirada
<!-- origen: old-saas:SAAS_PUBLIC-F79 -->
Estado: hecho
Actor: visitante
Pantalla: Muy pronto
Pasos:
1. Blog, Empleos y Prensa enseñan su titular y lo que vendrá; no se indexan y ningún menú las enlaza.
2. Una dirección antigua de la tienda (el marketplace, las soluciones o los módulos) lleva para siempre a la tienda de apps; la de la empresa, a «Sobre Nosotros».
3. La página de desarrolladores y la del puente local ya no existen: dan «Página no encontrada».
Entra: nada.
Sale: nada guardado.
Si falla: una dirección retirada nunca enseña la aplicación del panel en su lugar: o lleva a su sucesora o da «Página no encontrada».
Implicados: apps (la tienda)

### PUBLIC-F13 Cambiar de idioma
<!-- origen: old-saas:SAAS_PUBLIC-F68 -->
Estado: hecho
Actor: visitante
Pantalla: Pie de página
Pasos:
1. La web decide sola el idioma: el que eligió la persona antes, si no el de su navegador y, si ninguno vale, el inglés.
2. En el pie de cualquier página pulsa «Español» (o «English»); la misma página vuelve en ese idioma, con el idioma activo marcado.
3. El resto de páginas se leen en el idioma elegido mientras dure la elección (un año).
Entra: el idioma elegido y la página de vuelta.
Sale: la elección del idioma en el navegador; la preferencia de una cuenta no se toca (es del panel).
Si falla: un idioma que no está en la lista no cambia nada; una página de vuelta que no es de erplora.com se ignora y se vuelve a la portada.
Implicados: ninguno

### PUBLIC-F14 Que buscadores y asistentes lean la web
<!-- origen: old-saas:SAAS_PUBLIC-F75 fi:saas/support/public-core-config#modelos-translation-sitemaps-landing fi:saas/support/public-core-config#translation-py-sitemaps-py-usage-helper-i18n -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Las reglas de rastreo dan a cada buscador y asistente conocido su grupo, que deja fuera las partes privadas y deja entrar en la web pública; fuera de producción, no se deja rastrear nada.
2. El mapa del sitio lista las páginas públicas (también Cumplimiento y Colabora), cada tipo de negocio activo y la ficha de cada app publicada; el resumen para asistentes cuenta qué es ERPlora, enlaza las páginas que contestan lo que pregunta un comprador y lista las apps del catálogo vivo.
3. La portada, los precios, los sectores y cada app llevan sus datos estructurados, con el precio del plan de entrada y los sistemas en los que funciona: web, Windows, Linux y Android.
4. Cada día, en producción, se avisa a los buscadores que aceptan avisos (Bing, en el que se apoya la búsqueda de ChatGPT) de las páginas del mapa del sitio, para que las lean ese mismo día; fuera de producción no se avisa a ninguno.
Entra: el catálogo publicado, los planes a la venta, la taxonomía y la dirección de la petición; para el aviso diario, la dirección pública de la web.
Sale: nada guardado; el aviso diario a los buscadores.
Si falla: las páginas privadas nunca aparecen en el mapa ni en el resumen ni en el aviso, y llevan la marca de no indexar; las páginas «Muy pronto», la ayuda y el soporte tampoco se indexan. Si el buscador rechaza el aviso del día o no contesta, el envío acaba en error y salta la alarma del equipo de ERPlora; sin la clave de aviso configurada (lo normal en desarrollo) no se avisa a nadie y no es un error. Los textos de la web se traducen con los catálogos de idioma (inglés como fuente y su español).
Implicados: apps (el catálogo), hubs (los planes y la taxonomía)

### PUBLIC-F15 Leer la ayuda y el soporte
<!-- origen: old-saas:SAAS_DASHBOARD-F218 old-saas:SAAS_PUBLIC-F64 fi:saas/assistant-help#centro-de-ayuda-indice-de-guias fi:saas/assistant-help#guia-individual-markdown-html fi:saas/public#centro-de-ayuda-renderiza-guias-del-repo fi:saas/support/orgs-users#service-help_docs-list_docs-get_doc-all_sections-resolve_lang fi:saas/public#soporte-publico fi:saas/public#documentacion-publica-estatica -->
Estado: hecho
Actor: visitante
Pantalla: Centro de ayuda y Soporte
Pasos:
1. Desde el pie, «Centro de ayuda» abre «Centro de ayuda.» con una guía por tema (empezar, instalar, usuarios y permisos, ajustes y preguntas frecuentes), cada una plegada; al abrir una se lee entera.
2. El buscador de la página deja solo las guías que contienen lo escrito; si ninguna lo contiene, dice «No hemos encontrado ninguna guía».
3. «Soporte» ofrece tres caminos: «Buscar en el Centro de ayuda», «Contactar con soporte» (el formulario) y «Escribir al equipo» (el correo de soporte), y explica qué contar para que el equipo reproduzca el problema y qué no enviar nunca (contraseñas, PIN, códigos de recuperación).
4. La antigua página de documentación lleva para siempre al centro de ayuda; la documentación de cada app está en su ficha de la tienda.
Entra: las guías que se publican con la web, en inglés y en español.
Sale: nada guardado.
Si falla: una guía todavía sin traducir se lee en inglés, y un idioma sin guías también; nunca se enseña un documento que no sea una guía. La ayuda y el soporte no se indexan.
Implicados: ninguno

### PUBLIC-F16 Escribir al equipo desde el formulario de contacto
<!-- origen: old-saas:SAAS_PUBLIC-F65 -->
Estado: hecho
Actor: visitante
Pantalla: Contacto
Pasos:
1. En «Contáctanos» (o al final de la portada) la persona escribe nombre, apellidos, correo, el teléfono si quiere y lo que necesita, y pulsa «Ponte en contacto».
2. Antes de enviar, la página marca los campos obligatorios vacíos y un correo mal escrito, y se coloca en el primero.
3. Al enviarlo vuelve a la misma página con «¡Gracias! Recibimos tu mensaje y responderemos en un plazo de 4 horas laborables.»; el equipo lo recibe en el buzón de soporte y, al responderlo, la respuesta va a la persona.
Entra: lo escrito en el formulario.
Sale: un correo al buzón de soporte que se responde a la persona; la web no guarda el mensaje.
Si falla: un campo obligatorio vacío, un correo que no es válido, demasiados mensajes seguidos desde la misma red o un fallo al enviar el correo vuelven al formulario con su motivo («Introduce una dirección de correo electrónico válida.», «Demasiados mensajes desde tu red. Vuelve a intentarlo dentro de un rato.», «Lo sentimos, algo salió mal al enviar tu mensaje. Inténtalo de nuevo.») y con lo escrito en su sitio, una sola vez; no se envía nada.
Implicados: ninguno

### PUBLIC-F17 Llegar al formulario desde otras páginas
<!-- origen: old-saas:SAAS_PUBLIC-F66 -->
Estado: hecho
Actor: visitante
Pantalla: Contacto
Pasos:
1. «Contacto» del menú y del pie, «Contactar con soporte» de Soporte y los botones de contacto de Planes y precios y de Sectores abren el formulario.
2. Desde Colabora, «Únete al Programa» y «Solicitar Ahora» lo abren con el tema del programa de colaboradores; desde Seguridad, «Contactar con el Equipo de Seguridad» lo abre con el tema de seguridad.
3. El tema viaja con el mensaje: el equipo lo lee en el asunto del correo.
Entra: la página de la que se llega.
Sale: el tema en el asunto del correo al equipo.
Si falla: un tema que la web no conoce se ignora y el mensaje sale sin tema.
Implicados: ninguno

### PUBLIC-F18 Ver los canales y el plazo de respuesta
<!-- origen: old-saas:SAAS_PUBLIC-F67 -->
Estado: hecho
Actor: visitante
Pantalla: Contacto
Pasos:
1. En «Contáctanos», «Información de Contacto» enseña el correo de soporte y «Escríbenos» (WhatsApp); «Tiempo de respuesta» dice «En un plazo de 4 horas laborables».
2. El pie, Soporte, el bloque de contacto de la portada, las páginas de error y la pantalla de error de la entrada dan el mismo correo de soporte, y el formulario, el aviso de enviado y la portada («4 h») dan el mismo plazo.
Entra: nada.
Sale: nada guardado.
Si falla: ninguna página promete atención a todas horas ni otro plazo; el correo de soporte, el chat y el plazo se escriben en un solo sitio, así que no pueden contradecirse.
Implicados: ninguno

### PUBLIC-F19 Decidir sobre las cookies
<!-- origen: old-saas:SAAS-F10 old-saas:SAAS_PUBLIC-F69 old-saas:SAAS_PUBLIC-F70 fi:saas/support/orgs-users#command-init_cookie_groups -->
Estado: hecho
Actor: visitante
Pantalla: Aviso de cookies y Preferencias de cookies
Pasos:
1. Mientras la web no mida visitas, solo pone las cookies técnicas (la sesión, la protección de los formularios, el idioma, el tema y la elección de cookies) y no enseña ningún aviso: no hay nada que consentir.
2. Si se activa la medición de visitas, cada página enseña el aviso hasta que la persona elige «Aceptar todas», «Rechazar» o «Personalizar».
3. «Cookies» del pie abre «Preferencias de cookies»: las «Cookies esenciales», «Siempre activas», y cada categoría opcional («Cookies analíticas», «Cookies de marketing») con sus cookies y su interruptor; la elección dura un año.
4. Sin aceptar las analíticas no se carga ninguna medición, y en las pantallas de contraseñas y códigos no se carga nunca.
Entra: la elección de la persona.
Sale: la elección, guardada en el navegador; las cookies de una categoría rechazada se borran.
Si falla: las cookies esenciales nunca se borran (cerrarían la sesión); si la memoria rápida del servidor no contesta, la página sale igual y la limpieza se hace en la siguiente.
Implicados: accounts (las pantallas de entrada)

### PUBLIC-F20 Leer los textos legales
<!-- origen: old-saas:SAAS_PUBLIC-F71 fi:saas/public#paginas-legales-estaticas-privacy-terms-cookies-aviso-legal -->
Estado: hecho
Actor: visitante
Pantalla: Textos legales
Pasos:
1. En el pie, «Aviso legal», «Privacidad» y «Términos» abren cada texto en su página; la política de cookies se abre desde la privacidad.
2. La privacidad nombra a quién se confían los datos: Amazon Web Services en la región de Irlanda para el alojamiento y el correo, y el asistente en Fráncfort, sin entrenar con ellos.
3. Los términos dan los números que el producto cumple: los días del paquete de salida, los días que espera un negocio suspendido antes de borrarse y la prueba de los planes a la venta (ninguna si ninguno la tiene).
Entra: los planes a la venta (los términos).
Sale: nada guardado.
Si falla: ningún texto nombra un proveedor que ya no se usa ni otro alojamiento, y ningún enlace entre textos lleva a una página que no existe.
Implicados: hubs (los planes)

### PUBLIC-F21 Consultar la declaración responsable del sistema de facturación
<!-- origen: old-saas:SAAS_PUBLIC-F73 -->
Estado: hecho
Actor: visitante
Pantalla: Declaración responsable
Pasos:
1. «Declaración responsable» del pie (y la cláusula de actualizaciones de los términos) abre la versión en vigor, con su versión, su modalidad y si está firmada.
2. Si está firmada, ofrece abrir la copia firmada y descargarla, y explica que la firma solo se comprueba descargándola y abriéndola con un validador.
3. Abajo, el archivo de todas las versiones: la vigente marcada en vigor y las anteriores sustituidas; cada una se abre en su propia dirección.
Entra: las versiones de la declaración que se publican con la web.
Sale: nada guardado.
Si falla: una versión que no existe, o la copia de una versión todavía sin firmar, da «Página no encontrada»: nunca un archivo roto.
Implicados: ninguno

### PUBLIC-F22 Recorrer la tienda de apps
<!-- origen: old-saas:SAAS_PUBLIC-F29 fi:saas/public#marketplace-publico-de-modulos-listado-busqueda-filtro fi:saas/public#overview-publico-de-modulos-agrupados-por-unidad-funcional-modules -->
Estado: hecho
Actor: visitante
Pantalla: Tienda de apps
Pasos:
1. «Apps» del menú abre la tienda: las apps publicadas agrupadas por sección (ventas, catálogo, personas, restaurante, organización), cada una con su icono, su resumen y si es «Gratis» o «Incluida en los planes de pago».
2. «Buscar apps» busca en el nombre y el resumen; los filtros de sección (con cuántas apps tiene cada una) y de acceso (gratis o premium) se combinan con la búsqueda.
3. Las direcciones antiguas del marketplace, de las soluciones y de los módulos llevan para siempre a la tienda.
Entra: el catálogo publicado.
Sale: nada guardado.
Si falla: sin apps publicadas dice «Todavía no hay apps publicadas.» y no se indexa; si nada coincide, «Ninguna app coincide con tu búsqueda.», con la forma de quitar los filtros. Ninguna app tiene precio propio: las premium vienen con los planes de pago.
Implicados: apps (el catálogo)

### PUBLIC-F23 Ver la ficha de una app
<!-- origen: old-saas:SAAS_PUBLIC-F30 fi:saas/public#ficha-publica-de-un-modulo-detalle-ssr -->
Estado: hecho
Actor: visitante
Pantalla: Ficha de una app
Pasos:
1. Al pulsar una app se abre su ficha en «Resumen», con su descripción y, si necesita otras, «Apps necesarias», cada una enlazada a su ficha y con su acceso.
2. Si la app tiene documentación, la pestaña «Documentación» la enseña con sus diagramas; si solo existe en español, lo avisa con «Esta documentación solo está disponible en español.».
3. «Empieza gratis» lleva a la entrada; quien ya tiene cuenta va a su panel.
Entra: la app del catálogo y su documentación.
Sale: nada guardado.
Si falla: una app que no existe o no está publicada da «Página no encontrada»; una app sin documentación no tiene esa pestaña.
Implicados: apps (el catálogo), accounts (la entrada)

### PUBLIC-F24 Conseguir la aplicación instalada
<!-- origen: old-saas:SAAS_PUBLIC-F33 fi:saas/public#descarga-del-instalador-del-bridge-por-plataforma -->
Estado: hecho
Actor: visitante
Pantalla: Descargas y La app de ERPlora
Pasos:
1. «Descargas» del pie abre «Dos formas gratuitas de probar ERPlora.»: «Crea tu hub gratis en la nube», con los dispositivos y usuarios del plan Gratis, o «Instala la app de ERPlora» en el dispositivo del mostrador.
2. Cada botón de plataforma lleva a su tienda cuando su ficha está publicada (Microsoft Store, Google Play) y, si no, al último instalador (Windows y Linux); Android solo se instala desde Google Play.
3. La página de la app cuenta lo que hace en el mostrador y que primero hace falta un hub: «Antes que la app necesitas un hub.».
Entra: el plan Gratis a la venta y las fichas de las tiendas.
Sale: nada guardado.
Si falla: sin plan Gratis a la venta, la tarjeta no da ningún límite; una plataforma sin versión publicada (macOS) no se ofrece, y el puente local de antes ya no existe y da «Página no encontrada».
Implicados: hubs (el plan Gratis)

### PUBLIC-F25 Saber qué versión de la aplicación está publicada
<!-- origen: old-saas:SAAS_PUBLIC-F34 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada aplicación instalada pregunta a erplora.com qué versión está publicada.
2. La respuesta es la versión que dejó la última publicación junto a los instaladores.
Entra: la nota de versión que escribe cada publicación.
Sale: nada guardado.
Si falla: si esa nota no se puede leer o no trae una versión, la respuesta es que no se sabe, nunca un número inventado, y la aplicación lo trata como que no se pudo comprobar.
Implicados: ninguno

### PUBLIC-F26 Abrir una página pública desde la aplicación instalada
<!-- origen: old-saas:SAAS_PUBLIC-F74 -->
Estado: hecho
Actor: visitante
Pantalla: Textos legales
Pasos:
1. En la aplicación instalada (y en la cuenta que la aplicación abre en el navegador), la pantalla de entrada y la de comprobar el correo enlazan los términos y la privacidad.
2. Al pulsar uno, el texto se abre como en el visor de una aplicación: solo el texto y «Volver», sin el menú, el pie ni los botones de alta de la web.
3. Los textos que ese texto enlaza se abren igual mientras dure la sesión de la aplicación; «Volver» lleva a la pantalla de la aplicación que lo abrió, o a su inicio si el texto se abrió suelto.
Entra: desde qué parte de la aplicación se abre.
Sale: la marca de aplicación en la sesión de esa ventana.
Si falla: dentro de la aplicación no sale el aviso de cookies ni se carga ninguna medición, aunque se aceptaran en la web; una marca que la web no conoce se trata como la web.
Implicados: hubs (la entrada de la aplicación), accounts (comprobar el correo)

### PUBLIC-F27 Llegar a la demo
<!-- origen: old-saas:SAAS_PUBLIC-F80 -->
Estado: hecho
Actor: visitante
Pantalla: Demo
Pasos:
1. La persona pulsa «Prueba la demo» en la portada (arriba o en la llamada final) o en el menú de quien no ha entrado, o abre el enlace de la demo que le han pasado: la dirección de siempre y la corta abren la misma pantalla.
2. Ve «Prueba ERPlora sin registrarte.» y la tarjeta «Tu propio hub de demostración», con «Sin cuenta y sin tarjeta», «Un hub real en tu navegador, sin instalar nada» y «Termina solo a los 60 minutos».
3. Debajo están el botón «Prueba la demo» y «¿Quieres conservar lo que hagas? Empieza gratis: se tarda lo mismo.».
Entra: nada.
Sale: nada guardado: abrir la pantalla no crea ninguna demo, la abra una persona, un buscador o una recarga.
Si falla: si ese navegador ya tiene una demo en marcha, la pantalla no ofrece otra: dice «Tu demo está en marcha», cuánto le queda y «Volver a mi demo» (PUBLIC-F28).
Implicados: ninguno

### PUBLIC-F28 Crear la demo y entrar en ella
<!-- origen: old-saas:SAAS_PUBLIC-F81 old-saas:SAAS_PUBLIC-F82 old-saas:SAAS_PUBLIC-F83 -->
Estado: hecho
Actor: visitante, sistema
Pantalla: Demo
Pasos:
1. La persona pulsa «Prueba la demo».
2. Se crea un hub vacío para ese navegador, con una dirección propia al azar que empieza por «demo-», y dura 60 minutos desde ese momento. Está listo al instante: no hay espera.
3. La pantalla dice «Abriendo tu demo…» y el navegador entra solo en la demo, como el usuario «Demo», sin cuenta, contraseña ni PIN; sin JavaScript, el botón «Continuar» hace lo mismo.
4. Si vuelve a la pantalla de la demo mientras dura, ve «Tu demo está en marcha», «Termina en 12 minutos.» (lo que le quede) y «Volver a mi demo», que la devuelve a la misma demo.
5. Pulsar otra vez, recargar o abrir otra pestaña del mismo navegador devuelve la misma demo, y entrar después en su cuenta de erplora.com no la pierde.
Entra: el idioma del visitante, en el que se abre la demo.
Sale: un hub de demostración vacío con su usuario «Demo», y en ese navegador cuál es su demo y cuándo termina.
Si falla: solo entra el navegador que la pidió: el enlace de una demo abierto en otro navegador vuelve a la pantalla de la demo, que le ofrece una suya. Si la demo no se puede crear o abrir: PUBLIC-F29, PUBLIC-F31 y PUBLIC-F32.
Implicados: el Hub (su registro de hubs crea la demo y le abre la sesión)

### PUBLIC-F29 Una demo que no se ha podido abrir
<!-- origen: old-saas:SAAS_PUBLIC-F84 -->
Estado: hecho
Actor: visitante
Pantalla: Demo
Pasos:
1. Si el hub no contesta o rechaza la petición, la persona vuelve a la pantalla de la demo y ve «La demo no está disponible ahora mismo.» con «Volver a intentarlo».
2. Si la demo se creó pero la entrada no funcionó, ve «No hemos podido abrir tu demo. Vuelve a intentarlo.» y «Volver a mi demo», que la lleva a la misma demo mientras dure.
3. En los dos casos tiene también «Empieza gratis».
Entra: nada.
Sale: nada: un intento fallido no se queda como la demo de ese navegador, así que «Volver a intentarlo» la pide otra vez.
Si falla: el fallo queda en el registro del servicio; la persona solo ve el mensaje, nunca un error técnico.
Implicados: el Hub (su registro de hubs)

### PUBLIC-F30 La demo está apagada
<!-- origen: old-saas:SAAS_PUBLIC-F85 -->
Estado: hecho
Actor: visitante, sistema
Pantalla: Demo
Pasos:
1. Con la demo apagada, quien abre la pantalla de la demo ve «La demo está cerrada por ahora. Puedes empezar gratis: se tarda un minuto.».
2. Solo hay un botón, «Empieza gratis».
3. Apagarla cierra todas las puertas a la vez: pulsar el botón de una pantalla abierta antes o volver a entrar en una demo no crea ni abre nada y lleva a esta pantalla.
Entra: el interruptor de la demo, que el equipo pone en el despliegue.
Sale: nada.
Si falla: apagarla no desmonta nada: quien ya está dentro de su demo sigue hasta que termina.
Implicados: ninguno

### PUBLIC-F31 Todas las demos están ocupadas
<!-- origen: old-saas:SAAS_PUBLIC-F86 -->
Estado: hecho
Actor: visitante
Pantalla: Demo
Pasos:
1. Cuando ya hay en marcha tantas demos como admite la plataforma, la persona ve «La demo está llena ahora mismo. Vuelve a intentarlo en unos minutos.».
2. Tiene «Volver a intentarlo» y «¿Quieres conservar lo que hagas? Empieza gratis: se tarda lo mismo.».
Entra: cuántas demos hay en marcha.
Sale: nada: el intento no gasta ningún hueco.
Si falla: los huecos se liberan a medida que las demos terminan (PUBLIC-F34).
Implicados: el Hub (su registro de hubs cuenta las demos en marcha)

### PUBLIC-F32 Límite de demos por conexión
<!-- origen: old-saas:SAAS_PUBLIC-F87 -->
Estado: hecho
Actor: visitante, sistema
Pantalla: Demo
Pasos:
1. Cada demo nueva que se pide desde una misma conexión cuenta: como mucho 3 por hora, muy por debajo del total de la plataforma, para que nadie pueda dejar la demo llena para los demás.
2. Quien ya tiene una demo en marcha no gasta nada: pulsar otra vez, recargar u otra pestaña le devuelven la suya.
3. Pasado el límite, la persona ve «Demasiadas demos desde tu red. Vuelve a intentarlo dentro de un rato.» y solo «Empieza gratis», sin botón para reintentar.
Entra: la conexión desde la que se pide.
Sale: la cuenta de demos de esa conexión durante la hora.
Si falla: las demos que ya empezó siguen siendo suyas hasta que terminan.
Implicados: ninguno

### PUBLIC-F33 La demo terminó
<!-- origen: old-saas:SAAS_PUBLIC-F88 -->
Estado: hecho
Actor: visitante
Pantalla: Demo
Pasos:
1. Quien vuelve a la pantalla de la demo cuando la suya ya terminó ve una vez «Esta demo ha terminado. Empieza otra.».
2. Quien entra en la dirección de una demo terminada ve «La demo ha terminado» con «Crear otra demo», que le trae a esta misma pantalla.
3. La pantalla no arranca sola: «Empezar otra demo» pide una nueva (con la demo apagada no crea nada, PUBLIC-F30), y «Empieza gratis» lleva al alta.
Entra: cuándo termina la demo de ese navegador.
Sale: el navegador olvida su demo terminada: la siguiente visita ve la pantalla normal.
Si falla: una demo puede terminar antes de su hora (el equipo la retira); «Volver a mi demo» lo descubre y trae aquí.
Implicados: el Hub (la página de la demo terminada)

### PUBLIC-F34 Retirar las demos que vencen
<!-- origen: old-saas:SAAS_PUBLIC-F89 -->
Estado: parcial — lo que la persona creó dentro de la demo no se borra al retirarla: hasta la fase 2 las demos comparten los datos de las apps con las demás (ronda 2026-10-17, PLAN-SAAS §3.5 y PLAN-DB §6); la base de datos propia de cada demo, que se borra con ella, llega con la tenencia
Actor: sistema
Pantalla: ninguna
Pasos:
1. En cuanto pasa su hora, la dirección de la demo contesta «La demo ha terminado», aunque nadie la haya retirado todavía.
2. Cada minuto, el hub retira las demos vencidas: borra sus códigos de entrada, su usuario «Demo» y su acceso, y la marca como retirada; un fallo en una no detiene a las demás.
3. Pasados unos días, la dirección retirada deja de existir del todo.
Entra: las demos cuya hora ha pasado.
Sale: la demo retirada, sin usuario ni forma de entrar.
Si falla: si retirar una falla, se reintenta en la siguiente vuelta; mientras, su dirección ya dice que ha terminado.
Implicados: el Hub (su registro de hubs y su proceso de fondo)

### PUBLIC-F35 De la demo a una cuenta de verdad
<!-- origen: old-saas:SAAS_PUBLIC-F92 -->
Estado: hecho
Actor: visitante
Pantalla: Demo
Pasos:
1. En cualquier estado de la pantalla de la demo la persona tiene «Empieza gratis».
2. Llega a la misma entrada de erplora.com que el resto de botones «Empieza gratis» (PUBLIC-F11), donde se crea la cuenta y su negocio como cualquiera.
Entra: nada.
Sale: nada de la demo pasa a la cuenta: el negocio nace vacío, como avisa la pantalla: «El hub de demostración es tuyo durante 60 minutos; sin cuenta ni tarjeta. Todo lo que escribas desaparece cuando termina.».
Si falla: su demo sigue en marcha hasta que termina, aunque ya tenga cuenta.
Implicados: accounts (la entrada), hubs (el alta del negocio)

### PUBLIC-F36 Pedir una demo desde otra aplicación
<!-- origen: old-saas:SAAS_PUBLIC-F93 -->
Estado: descartado — la demo de ahora se crea y se abre en el mismo navegador que la pide, con un código de un solo uso atado a él, así que una puerta sin pantalla no podría abrirla; ninguna aplicación de ERPlora la llamaba, y la ronda 2026-10-17 (PLAN-SAAS §3.5) dejó la pantalla como única puerta
Actor: sistema
Pantalla: ninguna
Pasos:
1. Quien quiere una demo la pide desde la pantalla de la demo (PUBLIC-F28).
2. Los rechazos se ven en esa pantalla (PUBLIC-F29 a PUBLIC-F32).
Entra: nada.
Sale: nada.
Si falla: no aplica.
Implicados: ninguno

### PUBLIC-F37 La demo no cuenta como un negocio
<!-- origen: old-saas:SAAS_PUBLIC-F94 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Una demo no es un negocio de nadie: erplora.com no guarda ninguna, así que no aparece en la lista de negocios, ni en los planes, el cobro, las facturas o el uso.
2. Su principio de dirección, «demo-», está reservado: ningún cliente puede llamar así a su negocio, y un nombre como «Demo Bar» propone «demobar».
3. Una demo nunca se conecta a Hacienda de verdad.
Entra: nada.
Sale: nada.
Si falla: elegir a mano una dirección que empieza por «demo-» se rechaza con «Esta dirección está reservada. Elige otra.».
Implicados: hubs (la dirección del negocio), el Hub (VERIFACTU, la demo siempre a pruebas)

## Para quien lo mantiene

- Rutas y vistas: `public/urls.py` (`PUBLIC_PREFIXES`) y un módulo por área: `landing.py` (F01, F07, F11),
  `pricing.py` (F02–F04), `industries.py` (F05), `product.py` (F06, F08), `compliance.py` (F09), `company.py` (F10),
  `store.py` (redirecciones de F12), `language.py` (F13), `seo.py`, `sitemaps.py` y `structured_data.py` (F14).
  Plantillas en `public/templates/public/`, catálogo en `public/locale/es/`.
- Partes del porte (MIGRATION-TASK APP-PUBLIC-1…3): este WORKBOOK nace en la parte 1 (F01–F14); la parte 2 añade
  F15–F26 (ayuda, contacto, cookies, legales, tienda de apps, descargas) y la 3, F27–F37 (la demo), con la revisión
  flujo a flujo de los `hecho` de las tres.
- Demo (F27–F37; ronda 2026-10-17, PLAN-SAAS §3.5, plan `docs/plans/2026-10-17-demo-hubs-fase-1.md`): `demo.py`
  sirve `/demo/` (y la misma vista en `/try/`, canónica `/demo/`; GET, nunca crea), `/demo/start/` (POST con CSRF,
  `DEMO_SPAWN_RATELIMIT` por dirección solo si el navegador no tiene demo viva) y `/demo/enter/` (el salto con el
  `state` del Hub y `accounts/hub_login_form.html`). El SaaS no guarda filas de demo: solo `session["demo"]` y el token
  `session["demo_owner"]`, cuyo sha256 identifica al navegador ante el Hub (`hubs.hub_client.create_demo`,
  `create_demo_code`). `DEMO_ENABLED` lo miran las tres vistas. Lo demás es del Hub (`base/`): el registro
  `base.Hub` con `is_demo`, `POST /internal/demos` con `MAX_CONCURRENT_DEMOS` (503 `base.demo_full`), el 410 de una
  demo vencida con su enlace a `/demo/?state=expired`, `reap_demos` en el worker cada `REAPER_INTERVAL_SECONDS` y
  `purge_demo_data`, vacío a propósito en la fase 1 (F34 `parcial`). El prefijo `demo-` lo reserva
  `live.slugs` (`validate_hub_slug(allow_demo=…)`) y `hubs.queries.base_slug` lo normaliza (F37).
- Equivalencia de claves de la parte 3: G53 = F27; G54, G55 y G56 = F28; G57 = F29; G58 = F30; G59 = F31; G60 = F32;
  G61 = F33; G62 = F34; G63 = F35; G64 = F36; G65 = F37.
- Parte 2, por flujo: `help.py` y `resources.py` (F15; `/documentation/` es un 301 a `/help/`), `landing.py`
  (F16–F18: `contact_submit` con `reply_to`, el borrador `CONTACT_DRAFT_KEY` en la sesión y los temas
  `CONTACT_TOPICS`), `context_processors.py` (F18: `SUPPORT_EMAIL` de settings, `SUPPORT_WHATSAPP_URL` y
  `SUPPORT_REPLY_HOURS`), `partials/cookie_banner.html`, `partials/analytics.html`, `cookies.py` e
  `init_cookie_groups` (F19), `legal.py` (F20), `declaracion.py` (F21), `store.py` (F22, F23), `appdist.py` y
  `downloads.py` (F24, F25; la versión es `public.app.release`, que lee `downloads/app/latest/latest.json` del
  bucket que escribe la publicación de ERPlora/app). Los límites del plan Gratis de `/download/` son
  `pricing.free_plan` con el parcial `pricing/_plan_limits.html`, el mismo de la tabla de precios.
- Equivalencia de claves de la parte 2: G01, G02, G03, G21, G25, G38, G19 y G07 = F15; G39 = F16; G40 = F17;
  G41 = F18; G24, G43, G44 y G20 = F19; G45 y G17 = F20; G46 = F21; G26, G10 y G11 = F22; G27 y G08 = F23; G28 y
  G04 = F24; G29 = F25; G47 = F26.
- Modo aplicación (F26): la entrada de la SPA (`hubs/frontend/pages/LaunchPage.vue`, `VerifyEmailPage.vue`) enlaza
  los textos con `accounts/frontend/legal.ts` (`?surface=<superficie>` fuera de la web); `context_processors.app_surface`
  lo guarda en la sesión (`public.surface`; `?surface=web` lo quita) y `public_base.html` pinta `partials/app_bar.html`
  en lugar del menú, sin pie, aviso ni analítica; `frontend/public.ts` (`setupAppBack`) vuelve por el historial.
- Correo de soporte (F18): `SUPPORT_EMAIL` es la única fuente; las páginas de error lo leen con `{% support_email %}`
  (`public/templatetags/support.py`: la 500 se pinta sin contexto) y la SPA con el bloque JSON `support-email` de
  `base/spa.py` (`accounts/frontend/support.ts`).
- Equivalencia de claves del registro: G30 = F01; G31 y G14 = F02; G32 y G05 = F03; G33 = F04; G34, G06 y G09 = F05;
  G35 y G16 = F06; G49 = F07; G50 = F08; G36 y G13 = F09; G37, G12, G15 y G18 = F10; G51 = F11; G52 = F12; G42 = F13;
  G48, G22 y G23 = F14.
- Precios (F02–F04): los planes se leen con `hubs.plan.list`; el ahorro anual es `annual_months_free` (12 menos los
  meses que paga el precio anual, redondeado hacia abajo) y la cabecera usa `common_months_free`. El cobro es
  `billing.services.plan_sale` y la comprobación de los precios de Stripe al guardar un plan, `plan_price_problems`
  (BILLING-F28). Por encima de Standard la página no ofrece nada: la infraestructura dedicada por contacto (la
  constante `DEDICATED_FROM`, su banda, su fila y su pregunta) se retiró en la ronda 2026-10-24b (PLAN-SAAS §9).
- Promesas (F07, F08): la tabla de la portada es `landing.TYPICAL_STACK` (total sumado); las listas de frases
  prohibidas están en `public/tests/test_product.py` (`UNSHIPPED_CLAIMS`, `UNVERIFIED_SECURITY_CLAIMS`). El
  balanceador acepta TLS 1.2 y 1.3 (`ssl_policy` de ERPlora/aws).
- Cumplimiento (F09): `compliance.COUNTRY_NAMES` tiene que casar con `hubs.schemas.COUNTRIES` (lo exige un test);
  `FISCAL_SYSTEMS` dice qué sistema fiscal conecta cada país, hoy solo VeriFactu en España. Un país nuevo conectado
  se añade ahí con su app, en la misma entrega.
- Idioma (F13): el pie lleva un formulario por idioma que envía a `/set-language/`; Ionic mueve `aria-current` a la
  sombra del botón, así que el estilo del idioma activo va por `data-current`.
- Pruebas: cada test cita su flujo en el nombre o en el docstring; el e2e de esta parte es
  `tests/e2e/public-web.spec.ts` (claves `PUBLIC-Gnn` del registro en el título y capturas
  `APP-PUBLIC-1-<clave>-<ancho>.png` en `tests/e2e/.artifacts/`); el de la parte 2, `tests/e2e/public-web-2.spec.ts`
  (capturas `APP-PUBLIC-2-<clave>-<ancho>.png`; el servidor público del e2e escribe los correos en
  `.artifacts/public/mail*/`, nunca por SMTP); el de la parte 3, `tests/e2e/public-demo.spec.ts` (capturas
  `APP-PUBLIC-3-<clave>-<ancho>.png`), con `demo-door.spec.ts`. El recorrido entero de la demo contra un Hub de verdad
  es `tests/e2e/demo.spec.ts` del Hub, con este SaaS como su SaaS (README de `tests/e2e/` del Hub, «La demo»).

## Lo que NO hace, a propósito

- No tiene direcciones por idioma (`/es/`): una sola dirección por página y el idioma por la elección o el navegador.
- No lleva el plan ni el sector elegidos al alta: todo negocio nace en Gratis y el plan se cambia después.
- No tiene página de desarrolladores, marketplace de terceros ni puente local: todas las apps son de ERPlora.
- No cobra ni vende nada en la web pública: el pago está en el panel.
- No ofrece nada por encima de Standard: ni infraestructura dedicada ni planes por contacto (ronda 2026-10-24b,
  PLAN-SAAS §9).
- No nombra normativas fiscales de países a cuyo sistema no se conecta.
- No pide consentimiento de cookies mientras no mide visitas: las cookies técnicas no lo necesitan.
- No tiene una página de documentación aparte: la documentación es el centro de ayuda y la pestaña de cada app.
- No guarda los mensajes del formulario de contacto: los envía al buzón de soporte.
- La demo no arranca sola al abrir su pantalla: hay que pulsar «Prueba la demo», para que un buscador, una recarga o
  una vista previa del navegador no gasten huecos.
- No pasa nada de la demo a la cuenta que se crea después: el negocio nace vacío.
- No hay forma de pedir una demo sin su pantalla (PUBLIC-F36).
