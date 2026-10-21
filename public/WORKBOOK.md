# Workbook — Web pública (public)
Prefijo: PUBLIC
Alcance MVP: fase 1 (la web pública de erplora.com: lo que lee quien todavía no tiene cuenta y la puerta hacia el alta)
Estado de la app: en construcción (partes 1 y 2 de 3: la portada, los planes y precios, los sectores, el producto y la seguridad, el cumplimiento por país, la empresa, adónde lleva cada «Empieza gratis», las páginas «Muy pronto», el idioma y los buscadores; la ayuda y el soporte, el contacto, las cookies, los textos legales y la declaración responsable, la tienda de apps y las descargas)

> Manual de uso y especificación de la app `public` del SaaS (erplora.com). Cuenta lo que ve una persona que llega a
> erplora.com sin cuenta: qué es ERPlora, cuánto cuesta, para qué negocios sirve, cómo protege los datos, en qué
> países cumple con la facturación y cómo se empieza. Esta parte del manual no se publica en la tienda: es la
> referencia del equipo y de la QA. La demo (parte 3) se escribe a continuación.

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
- **Shopify App Store y Odoo Apps**: la tienda por secciones con búsqueda, y la ficha de cada app con lo que
  necesita y su documentación (https://apps.shopify.com, https://apps.odoo.com).

## Antes de empezar

- La web se sirve desde erplora.com; en desarrollo, desde el puerto 8001 del SaaS.
- Los sectores salen de la taxonomía que se siembra en cada despliegue; sin ella, la lista de sectores dice que
  todavía se están configurando.

## Pantallas

### Portada
El titular «Un ERP. Infinitas configuraciones. Tuyo.» con «Empieza gratis», «Prueba la demo» y «Descargas»; debajo,
la franja «Hecho para pequeños negocios», lo que cuesta un conjunto típico de herramientas frente a ERPlora, la
plataforma, las apps, la app del mostrador, los planes, una comparativa, la llamada final y el contacto.

### Planes y precios
«Empieza gratis. Escala cuando lo necesites.» con una tarjeta por plan a la venta, la oferta de infraestructura
dedicada, la tabla de lo incluido en cada plan, las comparativas con otros ERP y las preguntas frecuentes.

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

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | Las páginas llegan completas del servidor: no hay esqueleto ni espera. |
| Vacío | Sin planes a la venta, Planes y precios dice que no hay planes y no pinta tablas, y la portada omite el bloque de planes; sin apps publicadas, la portada omite los bloques de apps; sin sectores, «Todavía no hay tipos de negocio». |
| Error | Una dirección que no existe enseña «Página no encontrada» con el menú de la web; un fallo del servidor, «Algo ha fallado por nuestra parte», sin depender de la base de datos. |
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
| PUBLIC-F26 | Abrir una página pública desde la aplicación instalada | parcial |

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
3. Más arriba ofrece la infraestructura dedicada, por contacto; más abajo, la tabla de lo incluido en cada plan, las comparativas con otros ERP y las preguntas frecuentes.
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
3. La tabla «lo que pagarías por separado» solo lista funciones que las apps cubren y su total es la suma de sus filas.
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
3. A «¿Dónde se guardan mis datos?» la respuesta es la Unión Europea, con la única excepción del asistente si su proveedor europeo no está disponible, y el enlace «Lee la política de privacidad».
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
1. «Sobre nosotros» cuenta la misión, cómo se guardan los datos de cada negocio y que todas las apps son de ERPlora.
2. «Colabora» explica el programa en cuatro pasos y ofrece un negocio completo gratis durante un año, valorado en lo que cuesta un año del plan de pago más barato (su precio anual), con los sectores y tipos de negocio que hay hoy; «Solicitar Ahora» lleva al contacto con el asunto del programa.
3. La dirección antigua de la empresa lleva para siempre a «Sobre nosotros»; Blog, Empleos y Prensa son páginas «Muy pronto» (PUBLIC-F12).
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
2. Una dirección antigua de la tienda (el marketplace, las soluciones o los módulos) lleva para siempre a la tienda de apps; la de la empresa, a «Sobre nosotros».
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
Entra: el catálogo publicado, los planes a la venta, la taxonomía y la dirección de la petición.
Sale: nada guardado.
Si falla: las páginas privadas nunca aparecen en el mapa ni en el resumen y llevan la marca de no indexar; las páginas «Muy pronto», la ayuda y el soporte tampoco se indexan. Los textos de la web se traducen con los catálogos de idioma (inglés como fuente y su español).
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
Si falla: un campo obligatorio vacío, un correo que no es válido, demasiados mensajes seguidos desde la misma red o un fallo al enviar el correo vuelven al formulario con su motivo («Introduce un correo válido.», «Demasiados mensajes desde tu red. Vuelve a intentarlo dentro de un rato.», «Lo sentimos, algo salió mal al enviar tu mensaje. Inténtalo de nuevo.») y con lo escrito en su sitio, una sola vez; no se envía nada.
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
2. El pie, Soporte y el formulario dan el mismo correo de soporte, y el formulario, el aviso de enviado y la portada («4 h») dan el mismo plazo.
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
Estado: parcial — dentro de la aplicación instalada, un texto legal abierto desde la entrada se ve como en el navegador (menú, pie y «Empieza gratis») y no tiene botón para volver: la aplicación no se da a conocer a la web pública
Actor: visitante
Pantalla: Textos legales
Pasos:
1. En la aplicación instalada, la pantalla de entrada enlaza los términos y la privacidad.
2. Al pulsar uno, el texto legal se abre en la misma ventana.
Entra: nada.
Sale: nada guardado.
Si falla: mientras la web no mida visitas, no se pone ninguna cookie opcional ni sale el aviso de cookies.
Implicados: hubs (la entrada de la aplicación)

## Para quien lo mantiene

- Rutas y vistas: `public/urls.py` (`PUBLIC_PREFIXES`) y un módulo por área: `landing.py` (F01, F07, F11),
  `pricing.py` (F02–F04), `industries.py` (F05), `product.py` (F06, F08), `compliance.py` (F09), `company.py` (F10),
  `store.py` (redirecciones de F12), `language.py` (F13), `seo.py`, `sitemaps.py` y `structured_data.py` (F14).
  Plantillas en `public/templates/public/`, catálogo en `public/locale/es/`.
- Partes del porte (MIGRATION-TASK APP-PUBLIC-1…3): este WORKBOOK nace en la parte 1 (F01–F14); la parte 2 añade
  F15–F26 (ayuda, contacto, cookies, legales, tienda de apps, descargas) y la 3 (la demo) los suyos a continuación;
  la revisión flujo a flujo de los `hecho` la hace la parte 3.
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
- Equivalencia de claves del registro: G30 = F01; G31 y G14 = F02; G32 y G05 = F03; G33 = F04; G34, G06 y G09 = F05;
  G35 y G16 = F06; G49 = F07; G50 = F08; G36 y G13 = F09; G37, G12, G15 y G18 = F10; G51 = F11; G52 = F12; G42 = F13;
  G48, G22 y G23 = F14.
- Precios (F02–F04): los planes se leen con `hubs.plan.list`; el ahorro anual es `annual_months_free` (12 menos los
  meses que paga el precio anual, redondeado hacia abajo) y la cabecera usa `common_months_free`. El cobro es
  `billing.services.plan_sale` y la comprobación de los precios de Stripe al guardar un plan, `plan_price_problems`
  (BILLING-F28). La infraestructura dedicada es la constante `DEDICATED_FROM`.
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
  `.artifacts/public/mail*/`, nunca por SMTP).

## Lo que NO hace, a propósito

- No tiene direcciones por idioma (`/es/`): una sola dirección por página y el idioma por la elección o el navegador.
- No lleva el plan ni el sector elegidos al alta: todo negocio nace en Gratis y el plan se cambia después.
- No tiene página de desarrolladores, marketplace de terceros ni puente local: todas las apps son de ERPlora.
- No cobra ni vende nada en la web pública: el pago está en el panel.
- No nombra normativas fiscales de países a cuyo sistema no se conecta.
- No pide consentimiento de cookies mientras no mide visitas: las cookies técnicas no lo necesitan.
- No tiene una página de documentación aparte: la documentación es el centro de ayuda y la pestaña de cada app.
- No guarda los mensajes del formulario de contacto: los envía al buzón de soporte.
