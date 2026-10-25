# Workbook — Apps (apps)
Prefijo: APPS
Alcance MVP: fase 1 (el catálogo de apps que lee la tienda y lo que erplora.com vende de cada app de pago)
Estado de la app: en uso

> Manual de uso y especificación de la app `apps` del SaaS (erplora.com). Cuenta cómo llega a erplora.com
> el catálogo de las apps del Hub, cómo se lee desde fuera (la lista, la ficha y la documentación de cada
> app), cómo el personal de ERPlora pone a la venta una app de pago y la retira, y por qué nada se compra
> dentro de un negocio. Este manual no se publica en la tienda: es la referencia del equipo y de la QA. Las
> pantallas que enseñan el catálogo son de otras apps: la tienda pública de apps (`public`) y la Tienda del
> panel (`billing`).

## Para qué sirve y para quién

Las apps de ERPlora (Facturas, Citas, Inventario, WhatsApp…) viven en el Hub, que las registra en
erplora.com con cada versión que se despliega: su nombre, su resumen, su descripción, su icono, su
sección, si son de pago, los tipos de negocio para los que están pensadas y su manual de uso. Con eso,
erplora.com enseña la tienda de apps a cualquiera, con cuenta o sin ella, en español o en inglés.

De las apps de pago, erplora.com guarda además lo que vende: el plan más bajo que las incluye y su precio
mensual y anual sin IVA, con sus precios de Stripe. Una app gratuita no tiene nada que vender: viene con
cualquier negocio.

- El catálogo lo escribe solo el Hub: erplora.com lo lee y no lo cambia.
- Una app nunca se borra: se saca de la tienda o se deja de vender, y quien la tiene la conserva.
- Dentro de un negocio no se compra nada: todo se compra en la Tienda de erplora.com.

Quién la usa:

- Cualquier **visitante**, sin cuenta, recorre la tienda pública de apps y lee su documentación.
- El **propietario** de un negocio compra las apps de pago en la **Tienda** del panel.
- El **personal de ERPlora** pone a la venta las apps de pago, les pone precio y las retira, desde el
  admin.

## Referencia adoptada

- **Shopify App Store y Apple App Store**: la tienda la recorre cualquiera sin cuenta, agrupada por
  categorías y con buscador; una app retirada deja de ofrecerse a nadie nuevo, pero quien la tiene la
  conserva (https://shopify.dev/docs/apps/launch/app-store-review/delist-app).
- **Odoo Apps**: cada app trae su ficha y su manual, escritos por quien la hace, y la tienda los publica
  tal cual en el idioma de quien la lee, con el inglés como respaldo (https://apps.odoo.com/apps).
- **Stripe Billing**: un producto por app de pago con un precio mensual y otro anual, netos, que la
  suscripción del negocio suma como una línea más (https://docs.stripe.com/products-prices/overview).

## Antes de empezar

- El catálogo aparece cuando arranca el Hub: en desarrollo, el Hub de la propia máquina lo registra al
  arrancar su proceso de fondo. Sin Hub, la tienda sale vacía.
- Las apps de pago se ponen a la venta en el admin de erplora.com, con una cuenta del personal de ERPlora.
- Stripe va siempre en modo de prueba fuera de producción.

## Pantallas

### Admin › Apps
Lista de solo lectura de las apps que el Hub registró: etiqueta, nombre, sección, si es de pago, si está
en la tienda, versión del Hub que la registró y fecha. Filtros por sección, de pago y en la tienda, y un
buscador por etiqueta y nombre. No se puede añadir, cambiar ni borrar nada: lo escribe el Hub.

### Admin › Documentación de la app
Lista de solo lectura con una fila por app e idioma del manual de uso que registró el Hub, con su huella y
su fecha.

### Admin › Módulos
Lista de las apps de pago a la venta: app, nivel, precio mensual, precio anual, si está activo y la última
modificación, con filtros por nivel y activo y un buscador. La ficha de cada módulo: «App», «Nivel»,
«Precio mensual (céntimos)», «Precio anual (céntimos)», «Producto de Stripe», «Precio mensual de Stripe»,
«Precio anual de Stripe» y «Activo».

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Vacío | Las tres listas dicen que hay cero filas; Apps y Documentación de la app quedan vacías hasta que arranca un Hub. |
| Error | Un módulo que no se puede guardar dice por qué debajo de su campo y no se guarda nada. |
| Sin permiso | Sin cuenta del personal de ERPlora, el admin pide entrar; en Apps y Documentación de la app no hay botones de añadir, cambiar ni borrar para nadie. |
| Borrado rechazado | Al borrar un módulo que algún negocio tiene, el admin nombra cada negocio y no borra nada. |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| APPS-F01 | Consultar el catálogo de apps | hecho |
| APPS-F02 | Leer la documentación de una app | hecho |
| APPS-F03 | Poner a la venta una app de pago | hecho |
| APPS-F04 | Enlazar una app de pago con su producto y sus precios de Stripe | hecho |
| APPS-F05 | Sacar una app de la tienda o dejar de venderla | hecho |
| APPS-F06 | Clasificar una app por sección y tipo de negocio | hecho |
| APPS-F07 | Comprar una app de pago siempre en erplora.com, nunca dentro del negocio | hecho |

### APPS-F01 Consultar el catálogo de apps
<!-- origen: old-saas:SAAS_PUBLIC-F12 old-saas:SAAS_PUBLIC-F13 fi:saas/support/public-core-config#serializer-modulelistserializer-moduledetailserializer -->
Estado: hecho
Actor: visitante, sistema
Pantalla: ninguna (la enseñan la tienda pública de apps y la Tienda del panel)
Pasos:
1. Cualquiera, con cuenta o sin ella, pide a erplora.com la lista de apps: la tienda pública, la Tienda del panel o una integración.
2. erplora.com devuelve las apps que están en la tienda, agrupadas por sección (ventas, catálogo, personas, restaurante y organización) y, dentro de cada sección, por nombre, sin mirar mayúsculas ni acentos.
3. Cada app lleva su nombre, su resumen, su icono, su sección, si es de pago y los tipos de negocio para los que está pensada, en el idioma de quien la pide: en español si su navegador o su preferencia es el español, y en inglés en cualquier otro idioma.
4. Se puede filtrar por texto (en el nombre y en el resumen), por sección, por si es de pago y por tipo de negocio; un filtro que no se entiende se ignora y la lista sale entera.
5. La ficha de una app añade su descripción, las apps que necesita (con su nombre, y enlazadas solo si están en la tienda) y si tiene documentación.
Entra: el idioma de quien pide y, si los hay, los filtros o la app.
Sale: nada guardado; la respuesta dice en qué idioma está, y una caché compartida nunca da a una persona la de otro idioma.
Si falla: una app que no existe, o que ERPlora sacó de la tienda, responde que no hay ninguna app con esa etiqueta en el catálogo; un icono que no se puede pintar se cambia por el genérico de apps y queda anotado para el equipo; una sección que esta versión de erplora.com aún no conoce sale al final, sin sección. Pedir la lista cuesta lo mismo con tres apps que con treinta.
Implicados: el Hub (registra sus apps con cada versión), public (la tienda pública de apps), billing (la Tienda del panel)

### APPS-F02 Leer la documentación de una app
<!-- origen: old-saas:SAAS_PUBLIC-F31 fi:saas/support/public-core-config#service-module_readme_api-api-py fi:saas/support/public-core-config#service-render_markdown-services-rendering-py fi:saas/support/public-core-config#service-s3_docs-services-s3_docs-py -->
Estado: hecho
Actor: visitante, sistema
Pantalla: ninguna (la enseña la pestaña de documentación de la ficha de la tienda pública)
Pasos:
1. Alguien pide la documentación de una app de la tienda: el manual de uso que el Hub registra con cada versión, en español y en inglés.
2. erplora.com la devuelve lista para pintar y limpia de todo lo que no sea texto, títulos, tablas, listas, enlaces, imágenes de la propia app y diagramas.
3. Va en el idioma de quien la pide; si la app aún no tiene el manual en ese idioma, va el español, diciendo que es el original.
4. Las imágenes salen de los ficheros de la propia app en el Hub; una imagen de cualquier otro sitio se quita.
Entra: la app y el idioma de quien pide.
Sale: nada guardado en la app; la página ya pintada se guarda un día y se rehace sola en cuanto el Hub registra un manual nuevo.
Si falla: una app que no existe, o que está fuera de la tienda, responde que no está en el catálogo; una app sin manual responde que aún no tiene documentación.
Implicados: el Hub (registra el manual), public (la pestaña de documentación y el mapa del sitio)

### APPS-F03 Poner a la venta una app de pago
<!-- origen: fi:saas/django-admin#admin-module fi:saas/support/public-core-config#modelo-module old-saas:SAAS_PUBLIC-F27 -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin › Módulos
Pasos:
1. Una app que el Hub registró como de pago sale en **Admin › Apps**, pero no se vende hasta que tiene su módulo.
2. En **Admin › Módulos**, el personal pulsa «Añadir módulo» y escribe en «App» la etiqueta de la app, tal como sale en Admin › Apps.
3. Elige el «Nivel», que es el plan más bajo que la incluye sin pagarla aparte, y escribe su «Precio mensual (céntimos)» y su «Precio anual (céntimos)», sin IVA (un precio anual de 0 = sin opción anual).
4. Guarda: desde ese momento la app sale a la venta en la Tienda del panel con ese precio, y los negocios cuyo plan llega a su nivel la tienen incluida.
Entra: la etiqueta de una app de pago del catálogo, su nivel y sus precios.
Sale: el módulo a la venta.
Si falla: una etiqueta que no está en el catálogo no se guarda y dice que el Hub registra sus apps al arrancar; una app gratuita tampoco, porque solo se vende una app de pago; un precio negativo o con decimales no se acepta. Un módulo cuya app ya no está en el catálogo (escrito por otro camino que el admin) lo denuncia la comprobación que corre en cada despliegue.
Implicados: billing (la Tienda y el cobro), hubs (qué apps incluye cada plan)

### APPS-F04 Enlazar una app de pago con su producto y sus precios de Stripe
<!-- origen: fi:saas/support/public-core-config#service-modulestripeservice-services-stripe-py -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin › Módulos
Pasos:
1. Una persona de ERPlora crea en Stripe el producto de la app y sus precios mensual y anual, sin IVA incluido.
2. En **Admin › Módulos**, en el módulo de la app, pega «Producto de Stripe», «Precio mensual de Stripe» y «Precio anual de Stripe», y guarda.
3. Al guardar, erplora.com pregunta a Stripe por cada precio y solo lo acepta si existe con las claves de ese entorno, está activo, en euros, se cobra cada mes (o cada año) como dice su campo, cobra lo mismo que el módulo, es sin IVA y es de ese producto. Solo pregunta cuando cambia un precio o su identificador.
4. Desde ese momento la app se cobra con esos precios dentro de la suscripción de cada negocio que la compra, al mismo precio que enseña la Tienda.
Entra: el producto y los precios de Stripe de la app.
Sale: el módulo con sus precios de Stripe comprobados.
Si falla: un precio que no cuadra no se guarda y dice por qué debajo de su campo («Este precio no está en euros.», «Este precio está archivado en Stripe.», «Este precio es de otro producto de Stripe.», que Stripe cobra otra cantidad que el módulo, que incluye el IVA…); un precio de pruebas en producción no se encuentra. Si Stripe no contesta, no se guarda nada y se pide repetir; sin claves de Stripe (en desarrollo) se guarda y el admin avisa de que no se comprobó. Sin el precio del periodo del negocio, la Tienda no la cobra y dice que ahora no se puede comprar y que se contacte con soporte.
Implicados: billing (la comprobación en Stripe y el cobro en la Tienda)

### APPS-F05 Sacar una app de la tienda o dejar de venderla
<!-- origen: old-saas:SAAS_PUBLIC-F22 -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin › Módulos
Pasos:
1. Para dejar de vender una app de pago, el personal desmarca «Activo» en su módulo y guarda: ningún negocio nuevo la puede comprar.
2. Los negocios que ya la tienen la conservan y la siguen pagando; en su Tienda sale como que ya no se vende, y la pueden cancelar cuando quieran.
3. Para sacar una app de la tienda del todo, de pago o gratuita, ERPlora la marca en el Hub como fuera de la tienda: con la siguiente versión deja de salir en el catálogo, en la tienda pública y en el mapa del sitio, y su ficha deja de existir.
4. Ni una ni otra se borran: los negocios que la tienen la siguen usando, y su Tienda la sigue llamando por su nombre.
5. Un módulo que algún negocio tiene no se puede borrar: el admin nombra esos negocios y dice que se quite de la venta en su lugar.
Entra: el «Activo» del módulo; la marca de fuera de la tienda, en el Hub.
Sale: la app fuera de la venta o fuera de la tienda; nada se borra.
Si falla: borrar un módulo que algún negocio tiene, también desde la acción de borrar varios, se rechaza con el nombre de cada negocio.
Implicados: billing (la Tienda y las suscripciones), el Hub (marca la app fuera de la tienda), public (la tienda pública y el mapa del sitio)

### APPS-F06 Clasificar una app por sección y tipo de negocio
<!-- origen: old-saas:SAAS_PUBLIC-F26 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada app del Hub declara su sección (ventas, catálogo, personas, restaurante u organización) y los tipos de negocio para los que está pensada (peluquería, restaurante…; ninguno = sirve a todos), y el Hub los registra con cada versión.
2. erplora.com agrupa la tienda por esas secciones, la filtra por tipo de negocio y enseña en la página de cada sector las apps de sus tipos de negocio.
3. En el admin, un tipo de negocio del alta solo se puede unir a un tipo que alguna app del catálogo declare.
Entra: la sección y los tipos de negocio de cada app, tal como los registra el Hub.
Sale: la tienda por secciones y por tipo de negocio; aquí no se guarda nada.
Si falla: una sección que esta versión de erplora.com aún no conoce sale al final, sin sección, y queda anotada para el equipo; un tipo de negocio que ninguna app declara no se guarda.
Implicados: el Hub (declara la clasificación), hubs (los tipos de negocio del alta), public (las páginas de cada sector)

### APPS-F07 Comprar una app de pago siempre en erplora.com, nunca dentro del negocio
<!-- origen: old-saas:SAAS_PUBLIC-F21 -->
Estado: hecho
Actor: propietario, sistema
Pantalla: Tienda
Pasos:
1. Dentro del negocio no se compra nada: en Apps del Hub, una app de pago que el negocio no tiene sale con «Necesita suscripción» y, para quien administra el negocio en el navegador, «Mejorar plan», que abre la Tienda de erplora.com (BASE-F20). Hoy ninguna app se vende aparte (todas van en todos los planes): este paso vale para la que vuelva a venderse aparte.
2. El enlace abre **Tienda › Módulos** con ese negocio ya elegido arriba, y allí se compra como cualquier otra (BILLING-F32).
3. Desde la app instalada (Android, Windows) la Tienda no vende: dice «La tienda no está en la app» y «Para cambiar de plan o añadir módulos, entra en erplora.com desde el navegador.», sin enlace.
Entra: el negocio que lleva el enlace.
Sale: lo comprado, como en BILLING-F32; nada se cobra fuera de la Tienda.
Si falla: arriba solo se pueden elegir los negocios de los que se es propietario. erplora.com no tiene ninguna puerta por la que un negocio compre por su cuenta.
Implicados: el Hub (su página de apps, BASE-F20), billing (la Tienda)

## Para quien lo mantiene

- Anatomía: `App` y `AppDoc` (esquema `shared` de la BD `saas`, los escribe el `register_apps` del Hub con cada
  release; aquí solo se leen) y `Module` (lo comercial, a mano en el admin). Operaciones públicas (`auth=None`,
  sin permiso): `apps.app.list`, `apps.app.get`, `apps.app.doc` y `apps.app.sitemap`; para otras apps del SaaS,
  `cards_of` (billing nombra un módulo retirado) y `known_verticals` (`BusinessType.clean()` de hubs). El check de
  BD `apps.E001` (un `Module.slug` sin app) corre con `manage.py check --database default` en la tarea
  `saas-migrate`. Sin `live.py`: el catálogo solo cambia con un despliegue del Hub, que no avisa a nadie.
- Ronda 16 (PLAN §21) y PLAN-SAAS §2.6: el SaaS no guarda nombre, textos, icono ni documentación de una app.
- Tests por flujo (los citan en el nombre o en el docstring): F01 `apps/tests/test_queries.py` (lista, ficha,
  iconos, consultas planas) y `apps/tests/test_api.py` (rutas, idioma y `Vary`); F02 `test_queries.py`
  (documentación, caché, imágenes) y `packages/live/tests/test_markdown.py`; F03 `apps/tests/test_models.py`
  (`clean()`, `apps.E001`, admin); F04 `apps/tests/test_admin.py` (el formulario del admin con el doble de Stripe)
  y `billing/tests/test_services.py::TestThePricesOfAModule` (`module_price_problems`); F05 `test_queries.py` (no listadas), `billing/tests/test_store_catalog.py`,
  `billing/tests/test_module_cancel.py` y `billing/tests/test_admin.py` (borrado protegido); F06
  `test_queries.py` (secciones, filtros, `known_verticals`) y `hubs/tests/test_models.py`; F07 el e2e
  `tests/e2e/panel/billing-support.spec.ts` (`/dashboard/store/modules?business=`), `billing/frontend/pages/StorePage.test.ts`
  (la app instalada no vende) y, en el Hub, `base/tests/test_queries_apps.py::test_the_store_of_this_business` y
  `base/frontend/pages/AppsPage.test.ts` (BASE-F20: «Mejorar plan» a la Tienda, solo en el navegador y para quien
  administra).
- Filas del registro: G01, G02 y G13 → F03; G03, G08 y G09 → F01; G04, G06, G07 y G14 → F02; G05 → F04;
  G10 → F07; G11 → F05; G12 → F06.
- Se tiraron con la entrega de código (rondas 15 y 16): `module.json`, git-sync, zips, firma, carriles y
  versiones, la documentación en S3, el CHANGELOG, el catálogo por hub con credencial de máquina (`is_owned`,
  `can_install`, descarga), `?lang=` (el idioma va por `Accept-Language` o la cookie `_lang`), CORS de la
  documentación, los planes por app (`ModuleTier`), las pruebas gratuitas, el cobro por uso, la aprobación y
  la clasificación por unidad funcional y por país.
- APPS-F04 comparte con BILLING-F28 la comprobación de `billing/services.py` (`_price_problems`, con
  `plan_price_problems` y `module_price_problems` encima): `PriceCheckSkipped` (sin claves: se guarda con aviso) y
  `PriceCheckFailed` (Stripe no contesta: no se guarda y se pide repetir), en `ModuleForm` y en `PlanForm`.
- APPS-F07: la parte del Hub es BASE-F20 (hub#229; el enlace se llama «Mejorar plan» desde hub#256). Con la ronda
  2026-10-24b (PLAN §32, PLAN-SAAS §9) ningún módulo es `premium`: el enlace no le sale a nadie hasta que vuelva uno.

## Lo que NO hace, a propósito

- No escribe el catálogo: nombre, textos, icono, sección y manual de cada app los registra el Hub.
- No sirve un catálogo distinto a cada negocio: el Hub conoce sus propias apps y sus derechos le llegan con
  su plan.
- No vende planes distintos de una misma app, ni pruebas gratuitas, ni cobro por uso: una app de pago tiene
  un precio mensual y otro anual.
- No clasifica las apps por país ni por región: todas van en cada versión del Hub.
- No sirve el historial de cambios de una app.
- No crea solo el producto ni los precios en Stripe: se crean en Stripe y se pegan en el admin, que los comprueba.
- No publica ni aprueba apps de terceros: todas son de ERPlora.
- No borra una app ni un módulo que algún negocio tiene.
