# Workbook — Web pública (public)
Prefijo: PUBLIC
Alcance MVP: fase 1 (la web pública de erplora.com: lo que lee quien todavía no tiene cuenta y la puerta hacia el alta)
Estado de la app: en construcción (parte 1 de 3: la portada, los planes y precios, los sectores, el producto y la seguridad, el cumplimiento por país, la empresa, adónde lleva cada «Empieza gratis», las páginas «Muy pronto», el idioma y los buscadores)

> Manual de uso y especificación de la app `public` del SaaS (erplora.com). Cuenta lo que ve una persona que llega a
> erplora.com sin cuenta: qué es ERPlora, cuánto cuesta, para qué negocios sirve, cómo protege los datos, en qué
> países cumple con la facturación y cómo se empieza. Esta parte del manual no se publica en la tienda: es la
> referencia del equipo y de la QA. La ayuda, el contacto, las cookies, los textos legales, la documentación, la
> tienda de apps y las descargas (parte 2) y la demo (parte 3) se escriben a continuación.

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

## Para quien lo mantiene

- Rutas y vistas: `public/urls.py` (`PUBLIC_PREFIXES`) y un módulo por área: `landing.py` (F01, F07, F11),
  `pricing.py` (F02–F04), `industries.py` (F05), `product.py` (F06, F08), `compliance.py` (F09), `company.py` (F10),
  `store.py` (redirecciones de F12), `language.py` (F13), `seo.py`, `sitemaps.py` y `structured_data.py` (F14).
  Plantillas en `public/templates/public/`, catálogo en `public/locale/es/`.
- Partes del porte (MIGRATION-TASK APP-PUBLIC-1…3): este WORKBOOK nace en la parte 1 con estos flujos; la parte 2
  (ayuda, contacto, cookies, legales, documentación, tienda de apps, descargas) y la 3 (la demo) añaden los suyos a
  continuación; la revisión flujo a flujo de los `hecho` la hace la parte 3.
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
  `APP-PUBLIC-1-<clave>-<ancho>.png` en `tests/e2e/.artifacts/`).

## Lo que NO hace, a propósito

- No tiene direcciones por idioma (`/es/`): una sola dirección por página y el idioma por la elección o el navegador.
- No lleva el plan ni el sector elegidos al alta: todo negocio nace en Gratis y el plan se cambia después.
- No tiene página de desarrolladores, marketplace de terceros ni puente local: todas las apps son de ERPlora.
- No cobra ni vende nada en la web pública: el pago está en el panel.
- No nombra normativas fiscales de países a cuyo sistema no se conecta.
