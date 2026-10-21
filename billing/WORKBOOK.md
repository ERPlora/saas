# Workbook — Facturación (billing)
Prefijo: BILLING
Alcance MVP: fase 1 (lo que una cuenta paga a ERPlora: planes, módulos, IVA y facturas)
Estado de la app: en construcción (parte 1 de 3: el plan y su dinero)

> Manual de uso y especificación de la app `billing` del SaaS (erplora.com). Cuenta cómo se paga y se
> cambia el plan de un negocio, qué pasa si un cobro falla, qué IVA lleva cada cobro y cómo se ven y
> descargan las facturas de ERPlora. Esta parte del manual no se publica en la tienda: es la referencia
> del equipo y de la QA. Las aplicaciones de pago, la API y el admin de facturas y suscripciones y el
> soporte interno de Stripe se escriben en las partes 2 y 3.

## Para qué sirve y para quién

Facturación es lo que una cuenta paga a ERPlora por sus negocios. Cada negocio empieza en **Gratis** y,
cuando lo necesita, su propietario lo pasa a un plan de pago desde la **Tienda**. ERPlora cobra con
tarjeta a través de Stripe, pone el IVA que toca según dónde está quien paga y emite su propia factura
legal por cada cobro, que se ve y se descarga en **Facturación**.

- Una sola suscripción por negocio: el plan y los módulos que se compren van juntos y se cobran en una
  sola factura al mes (o al año).
- Cancelar nunca borra nada: el negocio sigue con su plan hasta el final del periodo pagado y después
  vuelve a Gratis.
- Si un cobro falla, el negocio sigue funcionando 7 días mientras se reintenta; después se suspende
  hasta que se pague, sin perder ningún dato.

Quién la usa:

- El **propietario** del negocio paga, cambia y cancela su plan, y ve sus facturas.
- La **cuenta que paga** un negocio (normalmente el propietario; tras un traspaso puede seguir siendo la
  anterior hasta que el nuevo propietario lo cambie) ve sus facturas y es la única que puede pagarlas.
- El **personal de ERPlora** mantiene la tabla de IVA, los precios en Stripe y los códigos
  promocionales, y revisa lo que hizo Stripe desde el admin.

## Referencia adoptada

- **Stripe Billing** como pasarela y modelo de ciclo de vida: una suscripción por negocio, pago con el
  formulario seguro de Stripe dentro de la página, cambio de precio con prorrateo, reintentos automáticos
  de un cobro fallido y cancelación al final del periodo pagado
  (https://docs.stripe.com/billing/subscriptions/overview).
- **Square Free** y **Shopify**: un plan por tienda; al cancelar se vuelve al plan gratuito sin borrar
  nada; la subida se cobra al momento y la bajada espera al final del periodo.
- **WooCommerce Subscriptions, Square y Lightspeed**: gracia corta tras un cobro fallido (7 días, 9 y 21)
  con aviso en el panel y por correo antes de suspender.
- **El IVA lo pone ERPlora, no Stripe Tax**: precios netos y el tipo sale de nuestra tabla según dónde
  está quien paga, como hace el mercado europeo con Canarias, Ceuta y Melilla (fuera del IVA) y con la
  inversión del sujeto pasivo de un NIF-IVA comprobado en VIES.
- **El recibo de Stripe no es la factura legal**: ERPlora numera su factura y la emite su propio negocio
  de plataforma, con VeriFactu, como hace cualquier empresa española que cobra con Stripe.

## Antes de empezar

- Se entra en erplora.com con la cuenta del propietario. En desarrollo, el panel está en el puerto 8001
  y Stripe va siempre en modo de prueba (tarjeta de prueba 4242 4242 4242 4242).
- Los planes viven en el admin, con el precio mensual y anual que Stripe cobra; un plan sin su precio de
  Stripe no se vende. Desde el 15 de octubre de 2026 ningún plan trae días de prueba: el plan Gratis es
  la entrada.
- Sin la tabla de IVA del territorio de quien paga, no se vende: es preferible no cobrar a cobrar mal.
- En las apps (Android, Windows) y desde la cuenta abierta en la app no se vende ni se cobra nada: allí
  se ven las facturas y las suscripciones, y para pagar o cambiar de plan se dice que se entre en
  erplora.com desde el navegador.

## Pantallas

### Tienda
Menú **Tienda**, con dos secciones: **Planes** y **Módulos**, y arriba el negocio para el que se compra
(solo los negocios de los que se es propietario). Planes enseña cada plan con su precio sin IVA, el
periodo («Mensual» o «Anual · −n %»), «Tu plan actual» en el que se tiene y el botón de cada uno:
«Mejorar a …», «Cambiar a …», «Cambiar a anual · …» o «Bajar a Gratis»; con el plan cancelado, «Mantener
el plan». Si el negocio tiene una factura sin pagar, arriba sale el aviso con «Pagar la factura» y no se
vende nada a ese negocio.

### Pago seguro
Diálogo que se abre al mejorar un negocio que aún no paga: primero «¿A nombre de quién facturamos?» (solo
la primera vez), después el formulario de tarjeta de Stripe dentro del diálogo, con «¿Tienes un código
promocional?». Al terminar, «Pagando…» y la página del negocio.

### Cambiar de plan
Diálogo de un negocio que ya paga: lo que se cobra hoy prorrateado, el IVA, el total y lo que se cobrará
después, con «Pagar … y cambiar» (o «Cambiar de plan» si hoy no se cobra nada, como en una bajada, que
espera al final del periodo).

### Facturación
Menú **Facturación**, con tres pestañas: **Facturas** (tabla con Factura, Fecha, Negocio, Importe y
Estado; filtros por negocio, estado y año; buscador por número; «Descargar PDF», «Descargar Excel» y
«Pagar» en las no cobradas), **Suscripciones** (una fila por negocio que paga: plan, módulos, próxima
factura con IVA y estado; «Cambiar plan», «Mantener el plan», «Ver la factura», «Ver facturas» y
«Cancelar plan») y **Datos de pago** (la tarjeta con «Cambiar tarjeta» y los datos de facturación con
«Editar datos»). Arriba, en las tres, los avisos de facturas sin pagar.

### Resumen del negocio
En la página de cada negocio, la tarjeta **Plan** dice en qué plan está, cuántos usuarios y dispositivos
caben y, al propietario, el botón para mejorarlo o cambiarlo.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» o el esqueleto de la tabla mientras llegan los datos; «Calculando lo que se cobra hoy…» en un cambio de plan. |
| Vacío | Facturas: «Aún no hay facturas» y «Ver planes»; Suscripciones: «Todos tus negocios están en Gratis»; Datos de pago: «Aún no hay ninguna tarjeta guardada». |
| Error | «No hemos podido cargar …» con «Reintentar»; un pago que no se abre dice «No se ha cobrado nada» con «Reintentar». |
| Stripe no responde | La tarjeta: «Ahora no podemos enseñarte la tarjeta: inténtalo en unos minutos»; un pago: el aviso de que no se ha cobrado nada. |
| Factura sin pagar | Aviso arriba con el importe, el negocio y hasta cuándo funciona, y «Pagar la factura»; con la tarjeta rechazada, primero «Cambiar tarjeta». |
| En la app | Se ve todo lo que no cobra; donde habría un botón de pago, «entra en erplora.com desde el navegador», sin enlace. |
| Sin permiso | Un negocio que no es tuyo no aparece; por la API, «No encontrado». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| BILLING-F01 | Decir dónde se factura el negocio y con qué identificación fiscal | hecho |
| BILLING-F02 | Calcular el impuesto de una venta según dónde está el pagador | parcial |
| BILLING-F03 | Decidir el IVA de cada cobro | hecho |
| BILLING-F04 | Mantener la tabla de tipos de IVA y no vender con ella rota | parcial |
| BILLING-F05 | Comprobar en VIES el NIF-IVA de quien paga | hecho |
| BILLING-F06 | Seguir el umbral de ventas a distancia en la UE (OSS) | parcial |
| BILLING-F07 | Pagar el plan de un negocio recién creado | hecho |
| BILLING-F08 | Pasar un negocio gratuito a un plan de pago | hecho |
| BILLING-F09 | Volver del pago: confirmado, pendiente o cerrado | hecho |
| BILLING-F10 | Reintentar un pago que no se terminó | hecho |
| BILLING-F11 | Cambiar de plan entre planes de pago | hecho |
| BILLING-F12 | Dar días de prueba con un código promocional | hecho |
| BILLING-F13 | Cancelar el plan al final del periodo | hecho |
| BILLING-F14 | Deshacer una cancelación pendiente | hecho |
| BILLING-F15 | Terminar la suscripción: el negocio vuelve a Gratis | hecho |
| BILLING-F16 | Impago del plan: reintentos, suspensión y vuelta | hecho |
| BILLING-F17 | Reactivar un negocio suspendido pagando su factura | hecho |
| BILLING-F18 | Ver, cancelar o mantener el plan del negocio por la API | hecho |
| BILLING-F19 | Recibir y validar un aviso de Stripe | hecho |
| BILLING-F20 | Renovar el plan cada periodo | hecho |
| BILLING-F21 | Mantener el plan al día con lo que dice Stripe | hecho |
| BILLING-F22 | Ver las facturas y descargarlas | hecho |
| BILLING-F23 | Ver las suscripciones de cada negocio | hecho |
| BILLING-F24 | Abrir el portal de pagos de Stripe para cambiar la tarjeta | hecho |
| BILLING-F25 | Emitir la factura de ERPlora por un cobro | hecho |
| BILLING-F26 | Devolver un cobro | hecho |
| BILLING-F27 | Lo que el personal de ERPlora puede hacer sobre el cobro de un cliente | hecho |
| BILLING-F28 | Mantener en Stripe los precios de los planes | parcial |
| BILLING-F29 | Probar el cobro real en PRE con un reloj de prueba de Stripe | hecho |
| BILLING-F30 | Usar claves reales de Stripe solo en producción y de prueba fuera de ella | hecho |

### BILLING-F01 Decir dónde se factura el negocio y con qué identificación fiscal
<!-- origen: old-saas:SAAS_DASHBOARD-F90 -->
Estado: hecho
Actor: propietario, cuenta que paga
Pantalla: Pago seguro, Facturación › Datos de pago
Pasos:
1. La primera vez que se paga un plan o un módulo, el diálogo de pago pregunta «¿A nombre de quién facturamos?»: «Razón social», «NIF (opcional)», «Dirección», «Ciudad», «Código postal», «País» y «Correo para las facturas (opcional)», o «Usar el nombre y el país del negocio».
2. Pulsa «Continuar al pago»: los datos se guardan y sigue el pago. Las veces siguientes el diálogo solo dice «Factura a nombre de …» con «Cambiar».
3. En cualquier momento, en **Facturación › Datos de pago**, la tarjeta «Datos de facturación» enseña razón social, NIF, dirección, correo y qué negocios paga, con «Editar datos».
4. Al escribir un NIF-IVA de otro país de la UE, la ventana lo comprueba en VIES y dice «Comprobado en VIES: … La factura va sin IVA», «VIES no reconoce este número: la factura llevará IVA» o «VIES no responde ahora: lo volvemos a comprobar al facturar».
5. Pulsa «Guardar datos»: «Datos de facturación guardados». Valen para las próximas facturas; las ya emitidas no cambian.
Entra: lo que escribe la persona; el país y el nombre del negocio si elige usarlos.
Sale: los datos de facturación del negocio (los comparten los negocios que paga la misma cuenta) y la comprobación de VIES anotada; se avisa del cambio (`hubs.billing_profile.updated`).
Si falla: un código postal español que no tiene cinco dígitos, un país que falta o un NIF que no vale para su país salen debajo de su campo y no se guarda nada. Tras un traspaso, si el negocio lo pagaba otra cuenta, el diálogo dice «Hasta ahora pagaba este negocio otra cuenta: di quién paga a partir de ahora».
Implicados: hubs (los datos del negocio y de quien paga)

### BILLING-F02 Calcular el impuesto de una venta según dónde está el pagador
<!-- origen: old-saas:SAAS_DASHBOARD-F91 -->
Estado: parcial — cambiar los datos de facturación no cambia el impuesto de una suscripción que ya se cobra hasta el siguiente cambio de plan
Actor: sistema
Pantalla: ninguna
Pasos:
1. Antes de abrir cualquier pago (un plan, un cambio de plan o un módulo), erplora.com lee el país y el código postal de quien paga. Sin los dos, el pago no empieza y se piden los datos de facturación.
2. Califica la venta con la misma regla que luego usa la factura: península y Baleares, IVA español; Canarias, Ceuta y Melilla, sin IVA (se cobra el precio sin nada encima); otro país de la UE con NIF-IVA comprobado en VIES, inversión del sujeto pasivo, sin IVA; un particular de otro país de la UE, IVA español hasta superar el umbral de ventas a distancia y después el de su país; Reino Unido, solo a empresas y sin IVA.
3. Si el total con IVA pasa de 400 € y quien paga no tiene NIF, la venta se niega y se pide (una factura simplificada no puede pasar de ahí).
4. El tipo resultante viaja a Stripe con cada línea de la suscripción; Stripe solo suma lo que se le da.
Entra: país, código postal y NIF de quien paga, la última comprobación de VIES, el precio sin IVA y qué se vende (plan o módulo).
Sale: el tipo de cada línea en Stripe, o la negativa con su motivo.
Si falla: «Faltan los datos de facturación» lleva al formulario; un territorio sin regla en la tabla no se vende; un consumidor del Reino Unido no compra; más de 400 € sin NIF pide el NIF. Un precio de 0 € nunca se niega.
Implicados: hubs (los datos de quien paga)

### BILLING-F03 Decidir el IVA de cada cobro
<!-- origen: old-saas:SAAS_DASHBOARD-F142 gh:saas#2528 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al poner precio (antes de cobrar) y al facturar (después), el mismo motor califica la venta: nacional, no sujeta (Canarias, Ceuta, Melilla, Reino Unido), inversión del sujeto pasivo o IVA del país del cliente (ventas a distancia por encima del umbral).
2. Al facturar, reparte lo que Stripe cobró en base y cuota y sella en la factura el tipo nominal de la tabla (21 %, nunca un 21,01 % que salga de dividir céntimos).
3. Si Stripe no cobró impuesto en una venta sujeta, la factura saca el IVA de lo cobrado y deja una alarma para el equipo: el IVA nunca se deja de declarar.
Entra: país, código postal y NIF de quien paga, su comprobación de VIES a la fecha del cobro, la política fiscal y la tabla de tipos.
Sale: el tratamiento, el tipo, la base y la cuota, sellados en cada línea de la factura.
Si falla: si VIES no contesta y no hay ninguna comprobación anterior, la factura espera y Stripe vuelve a avisar: nunca se pone IVA español a una venta entre empresas de la UE porque VIES no respondía. Si las líneas no suman lo cobrado, la factura no se emite y queda la alarma.
Implicados: ninguno

### BILLING-F04 Mantener la tabla de tipos de IVA y no vender con ella rota
<!-- origen: old-saas:SAAS_DASHBOARD-F143 -->
Estado: parcial — falta la revisión diaria de la tabla con aviso al equipo
Actor: personal de ERPlora
Pantalla: Admin › Reglas fiscales
Pasos:
1. Una persona de ERPlora edita en el admin las **reglas fiscales** (país, región, categoría, tipo, sujeta o no, desde y hasta) y las **categorías**. Gana la regla más concreta.
2. La lista enseña lo necesario para operar y se filtra por país y por categoría; dos reglas del mismo territorio que empiezan el mismo día se rechazan al guardar.
3. Toda venta lee la tabla en el momento: un territorio sin regla vigente no se vende.
Entra: la tabla y los datos de facturación de los negocios.
Sale: la tabla cambiada.
Si falla: desactivar la regla de un territorio hace que toda venta a él se niegue desde ese momento.
Implicados: ninguno

### BILLING-F05 Comprobar en VIES el NIF-IVA de quien paga
<!-- origen: old-saas:SAAS_DASHBOARD-F144 gh:saas#2665 -->
Estado: hecho
Actor: sistema, personal de ERPlora
Pantalla: Facturación › Datos de pago, Admin › Comprobaciones de IVA
Pasos:
1. Al escribir un NIF-IVA de otro país de la UE en los datos de facturación, y al cobrar, erplora.com pregunta a VIES identificándose con el NIF de ERPlora, así VIES devuelve el número de consulta, que es la prueba. Un NIF español no se consulta; uno británico no es de VIES.
2. Cada respuesta es una fila nueva que nunca se reescribe (comprobado, no válido, no disponible). Solo un «comprobado» vigente con número de consulta (o el forzado manual) permite facturar sin IVA.
3. El personal puede volver a preguntar con la acción «Comprobar ahora en VIES» de **Comprobaciones de IVA**, o dejar a mano un «comprobado» con su motivo, que guarda quién y cuándo.
4. Cada persona tiene 20 consultas por minuto y hay un tope global; una sola consulta a la vez por persona.
Entra: el NIF-IVA y el país.
Sale: el historial de comprobaciones (`billing.vat_check.completed`) y el número de consulta sellado en la factura.
Si falla: VIES sin contestar es «no disponible» y la venta lleva IVA; pasado el tope, «Demasiadas consultas: espera un minuto»; un número sin formato válido sale debajo del campo. El admin de comprobaciones solo se abre con la entrada del SaaS, que pide el código por correo y la app de autenticación.
Implicados: ninguno

### BILLING-F06 Seguir el umbral de ventas a distancia en la UE (OSS)
<!-- origen: old-saas:SAAS_DASHBOARD-F145 -->
Estado: parcial — no hay aviso al equipo al acercarse al umbral ni cambio de tipo de las suscripciones ya vivas al cruzarlo
Actor: sistema, personal de ERPlora
Pantalla: Admin › Política fiscal
Pasos:
1. Cada factura a un particular de otro país de la UE suma su base al total del año (las rectificativas restan); el total de lo vendido por el SaaS anterior se carga una vez a mano en **Política fiscal**.
2. **Política fiscal** enseña el total del año contra el umbral (10.000 € por defecto) y los interruptores del alta en OSS y en el ROI.
3. Por encima del umbral (o con el alta voluntaria en OSS, o si el año anterior cerró por encima) las ventas nuevas a particulares de la UE llevan el IVA del país del cliente.
Entra: las facturas y la política.
Sale: el tipo de cada venta nueva.
Si falla: mientras el total del año no se ha cargado, el admin dice «desconocido» y con claves reales no se vende nada (es preferible no vender a cruzar el umbral sin verlo).
Implicados: ninguno

### BILLING-F07 Pagar el plan de un negocio recién creado
<!-- origen: old-saas:SAAS_DASHBOARD-F92 gh:saas#2527 -->
Estado: hecho
Actor: propietario
Pantalla: Resumen del negocio, Tienda, Pago seguro
Pasos:
1. El negocio nace siempre en Gratis (el alta solo pide nombre, país y tipo de negocio).
2. En el Resumen del negocio, la tarjeta Plan dice «Gratis» y ofrece «Mejorar plan» (en un plan de pago, «Cambiar plan»), que abre la Tienda con ese negocio elegido. Solo lo ve quien gestiona la facturación del negocio, y solo en la web: en las apps dice que se entre en erplora.com desde el navegador.
3. Elige el plan y el periodo y pulsa «Mejorar a …»: el pago sigue como en BILLING-F08.
Entra: el negocio recién creado y los planes que se ofrecen a esa persona (los internos, solo al personal).
Sale: lo mismo que BILLING-F08.
Si falla: los mismos rechazos que BILLING-F08.
Implicados: hubs (el alta y la página del negocio)

### BILLING-F08 Pasar un negocio gratuito a un plan de pago
<!-- origen: old-saas:SAAS_DASHBOARD-F95 gh:saas#2527 -->
Estado: hecho
Actor: propietario
Pantalla: Tienda, Pago seguro
Pasos:
1. En **Tienda › Planes**, con el negocio elegido arriba, el propietario elige «Mensual» o «Anual» y pulsa «Mejorar a …».
2. Se abre el pago seguro: los datos de facturación si faltan y después el formulario de tarjeta de Stripe dentro del diálogo, titulado «Mejorar a …» con «Para … · se renueva cada mes» (o cada año).
3. Mete la tarjeta; si el banco pide autenticación, la muestra Stripe en el mismo formulario.
4. Al terminar, «Pagando…», el aviso «… ya está en …» y la página del negocio, cuya tarjeta Plan cambia en cuanto Stripe lo confirma. El negocio sigue funcionando todo el tiempo.
Entra: el plan elegido (solo los que se ofrecen a esa persona), el periodo, los datos de facturación y el código promocional si lo hay.
Sale: el negocio en el plan nuevo, su suscripción y su cliente en Stripe, el plan nuevo enviado al negocio (`hubs.subscription.changed`) y la factura de ERPlora del primer cobro (BILLING-F25), llegue antes o después el aviso del pago.
Si falla: si el pago no se puede abrir, «No hemos podido abrir el pago seguro» y «No se ha cobrado nada» con «Reintentar»; un plan sin precio en Stripe, «no está a la venta»; sin datos de facturación, el formulario; con una factura sin pagar, no se vende nada a ese negocio. Si la persona cierra el diálogo, no se cobra nada y el negocio sigue en Gratis.
Implicados: hubs (la suscripción del negocio), el negocio (recibe su plan)

### BILLING-F09 Volver del pago: confirmado, pendiente o cerrado
<!-- origen: old-saas:SAAS_DASHBOARD-F93 -->
Estado: hecho
Actor: propietario
Pantalla: Pago seguro, Resumen del negocio
Pasos:
1. Al terminar el pago en el formulario de Stripe, el diálogo dice «Pagando…», cierra el formulario, avisa «… ya está en …» (o «… añadido a …: se enciende en unos segundos» para un módulo) y abre la página del negocio.
2. El plan del negocio cambia cuando Stripe confirma el cobro: si el medio de pago tarda en confirmarse, el negocio sigue en su plan anterior hasta entonces y cambia solo, sin recargar.
3. Si la persona cierra el diálogo antes de pagar, no se cobra nada y puede volver a abrirlo.
Entra: el pago que Stripe da por terminado.
Sale: el mismo plan nuevo que deja el aviso de Stripe (BILLING-F19); la vuelta y el aviso nunca aplican dos veces el mismo pago.
Si falla: un pago que Stripe da por fallido después cierra ese intento sin cambiar el plan; un pago de otra cosa (un módulo) nunca cambia el plan.
Implicados: el negocio (recibe su plan)

### BILLING-F10 Reintentar un pago que no se terminó
<!-- origen: old-saas:SAAS_DASHBOARD-F94 gh:saas#2527 -->
Estado: hecho
Actor: propietario
Pantalla: Tienda, Pago seguro
Pasos:
1. El propietario abre otra vez «Mejorar a …» con la misma elección: se reabre el mismo pago, sin crear otro.
2. Si cambia de plan o de periodo, el pago anterior se anula en Stripe y se abre uno nuevo; nunca quedan dos pagos abiertos para el mismo negocio.
3. Paga como en BILLING-F08.
Entra: el negocio que aún no paga y su elección.
Sale: un solo pago abierto por negocio; al pagarlo, lo mismo que BILLING-F08.
Si falla: si por un descuido se llegasen a pagar dos (dos pestañas a la vez), el segundo no se aplica: su suscripción se cancela en el acto con lo no usado como crédito y queda una alarma para el equipo. Un pago caducado no se reutiliza: se abre otro.
Implicados: ninguno

### BILLING-F11 Cambiar de plan entre planes de pago
<!-- origen: old-saas:SAAS_DASHBOARD-F96 -->
Estado: hecho
Actor: propietario que paga
Pantalla: Tienda, Cambiar de plan
Pasos:
1. En **Tienda › Planes** de un negocio que ya paga, el propietario pulsa «Cambiar a …», «Cambiar a anual · …» o «Cambiar a mensual · …».
2. El diálogo calcula lo que se cobra hoy («Calculando lo que se cobra hoy…») y enseña «Hoy (prorrateado)», el IVA, el «Total hoy» y lo que se cobrará «Después», con la nota de que los módulos siguen igual.
3. Una subida se confirma con «Pagar … y cambiar»: se cobra ya con la tarjeta guardada y el negocio pasa al plan nuevo en el acto. Una bajada (un plan más barato, o de anual a mensual) no cobra nada hoy: pasa al plan nuevo al final del periodo pagado, y **Facturación › Suscripciones** dice «Cambia a … el …».
4. Aviso: «… ya está en …» (o «…, con pago anual»).
Entra: el plan y el periodo nuevos y la suscripción del negocio con su tarjeta; al cambiar de periodo, también cambia el precio de cada módulo.
Sale: el plan cambiado (`billing.plan.changed`) o la bajada programada (`billing.plan.change_scheduled`), con el IVA de la tabla en cada línea, y el plan nuevo enviado al negocio.
Si falla: «El precio estaba desactualizado: aquí lo tienes de nuevo, revísalo antes de confirmar» si pasó demasiado tiempo; la tarjeta rechazada no cambia nada; el mismo plan y periodo no es un cambio; bajar a Gratis es cancelar (BILLING-F13); con una cancelación pendiente, «Mantén antes el plan para cambiarlo»; con una factura sin pagar, «Antes, paga la factura pendiente»; más de 400 € sin NIF pide el NIF.
Implicados: el negocio (recibe su plan)

### BILLING-F12 Dar días de prueba con un código promocional
<!-- origen: old-saas:SAAS_DASHBOARD-F122 -->
Estado: hecho
Actor: personal de ERPlora, propietario
Pantalla: Admin › Códigos promocionales, Pago seguro
Pasos:
1. Una persona de ERPlora crea un código en el admin: el código, los días de prueba (de 1 a 365), si está activo, hasta cuándo vale, cuántos usos y una nota.
2. El propietario, en el pago seguro de un negocio que aún no paga, pulsa «¿Tienes un código promocional?», lo escribe y pulsa «Aplicar»: «Código …: n días gratis antes del primer cobro».
3. Paga: el primer cobro llega al acabar esos días.
Entra: el código (sin distinguir mayúsculas ni espacios).
Sale: los días de prueba en la suscripción y el uso contado una vez por negocio y por quien paga.
Si falla: un código desconocido, inactivo, caducado o agotado dice «Este código no es válido o ya se ha usado» y no impide pagar sin él; probar códigos tiene un tope por persona. Un código nunca rebaja el precio y nunca pasa de su número de usos.
Implicados: ninguno

### BILLING-F13 Cancelar el plan al final del periodo
<!-- origen: old-saas:SAAS_DASHBOARD-F101 gh:saas#2530 -->
Estado: hecho
Actor: propietario que paga
Pantalla: Facturación › Suscripciones, Tienda
Pasos:
1. En **Facturación › Suscripciones**, en la fila del negocio, el propietario abre «⋮» y pulsa «Cancelar plan» (o, en la Tienda, «Bajar a Gratis»).
2. El diálogo «Cancelar el plan» habla de ese negocio: «Sigue en … hasta el …; después pasa a Gratis y no se vuelve a cobrar», qué módulos se desactivan ese día, cuántos usuarios y dispositivos caben en Gratis frente a los que tiene, y que hasta entonces se puede deshacer con «Mantener el plan».
3. Pulsa «Cancelar plan»: «Plan cancelado: … sigue en … hasta el …». La fila dice «Gratis desde el …» y ya no tiene próxima factura.
Entra: la suscripción de Stripe del negocio.
Sale: la suscripción marcada en Stripe para terminar al final del periodo (`billing.plan.cancelled`); nada más cambia hasta esa fecha (BILLING-F15).
Si falla: si Stripe la rechaza o no contesta, nada cambia y se dice. Cancelar con una factura sin pagar se permite, pero no la anula: el diálogo lo avisa. Un negocio en Gratis no tiene nada que cancelar.
Implicados: el negocio (recibe la fecha de fin)

### BILLING-F14 Deshacer una cancelación pendiente
<!-- origen: old-saas:SAAS_DASHBOARD-F102 gh:saas#2529 gh:saas#2574 -->
Estado: hecho
Actor: propietario que paga
Pantalla: Facturación › Suscripciones, Tienda
Pasos:
1. En la fila de un negocio con el plan cancelado, el propietario pulsa «Mantener el plan» (en la Tienda: «Cancelado: … hasta el … y después Gratis» con «Mantener el plan»).
2. Aviso: «… sigue en …» o «… se mantiene: se renovará el …». La fila vuelve a tener próxima factura.
Entra: la suscripción con su final marcado.
Sale: la suscripción vuelve a renovarse en Stripe, con el estado que diga Stripe (`billing.plan.kept`); una bajada programada también se deshace.
Si falla: con una factura sin pagar no se mantiene: primero se paga (no se recupera un plan sin pagarlo). Mantener un plan que no estaba cancelado no cambia nada.
Implicados: ninguno

### BILLING-F15 Terminar la suscripción: el negocio vuelve a Gratis
<!-- origen: old-saas:SAAS_DASHBOARD-F103 gh:saas#2575 gh:saas#2527 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Llega el final del periodo de un plan cancelado (o Stripe da la suscripción por terminada). Stripe avisa.
2. erplora.com pasa el negocio a Gratis: sin suscripción en Stripe, sin nada que deber y con los módulos comprados terminados ese día. No se borra ningún dato.
3. El negocio recibe su plan nuevo y sigue funcionando con los límites de Gratis.
Entra: el aviso de Stripe de que la suscripción terminó.
Sale: el negocio en Gratis (`hubs.subscription.changed`) y su plan enviado al negocio. No hay correo al terminar: desde que se cancela, el panel ya dice «Gratis desde el …».
Si falla: un aviso de una suscripción desconocida se da por recibido sin tocar nada; el de un negocio eliminado no crea ni mueve nada.
Implicados: el negocio (recibe Gratis)

### BILLING-F16 Impago del plan: reintentos, suspensión y vuelta
<!-- origen: old-saas:SAAS_DASHBOARD-F100 gh:saas#2529 gh:saas#2574 gh:saas#2593 gh:saas#2594 -->
Estado: hecho
Actor: sistema, propietario, cuenta que paga
Pantalla: Facturación, Negocios, el propio negocio
Pasos:
1. Falla el cobro de una renovación. Stripe lo reintenta durante unos días y avisa de cada fallo.
2. erplora.com relee la suscripción en Stripe: si el reintento ya cobró, no hace nada; si no, apunta la factura como «No cobrada», con por qué no se cobró (tarjeta rechazada, autenticación o fallo).
3. **Gracia**: durante 7 días desde la factura que falló, el negocio sigue funcionando con todo su plan. La cuenta que paga recibe un correo, una vez por factura: cuánto no se pudo cobrar, hasta qué día sigue funcionando y el enlace a Facturación para pagarla (si el banco rechazó la tarjeta, que la cambie antes). En **Negocios** y en **Facturación** sale el aviso «No pudimos cobrar … de …»: «Págala antes del … o el negocio se suspende; no se borra nada», con «Pagar la factura» (o «Cambiar tarjeta» primero si el banco la rechazó).
4. **Suspensión**: pasados los 7 días, o si Stripe agota sus reintentos, el negocio se suspende y la cuenta que paga recibe otro correo, una sola vez. El negocio no se abre: ni desde el panel ni desde su propia dirección, tampoco en los dispositivos que ya tenían la sesión abierta, que enseñan «Este negocio está suspendido» con el camino a ERPlora. El aviso del panel dice «… está suspendido: … sin pagar» y que los datos están a salvo.
5. **Red de seguridad**: cada hora se repasan los negocios con el plan en impago y se mira su factura abierta más antigua, por si Stripe dejó de reintentar sin volver a avisar.
6. **Vuelta**: al pagar la factura (con «Pagar la factura», o porque un reintento la cobra), el negocio vuelve a estar activo en el acto: «Factura pagada: … vuelve a estar al día».
Entra: los avisos de Stripe del cobro fallido y de la suscripción, y la suscripción viva.
Sale: la factura «No cobrada», los correos a quien paga y el estado del negocio (pago pendiente, suspendido o al día) enviados al negocio (`hubs.subscription.changed`).
Si falla: si Stripe no contesta al releer la suscripción, no se aplica nada y Stripe vuelve a avisar. Un aviso repetido de una factura ya pagada no la reabre. Un fallo posterior del mismo impago no mueve la fecha de la gracia ni repite el correo. Un correo que no pudo salir se vuelve a mandar en el repaso de cada hora, que avisa al equipo mientras quede alguno.
Implicados: hubs (el estado del negocio), el negocio (recibe el estado)

### BILLING-F17 Reactivar un negocio suspendido pagando su factura
<!-- origen: old-saas:SAAS_DASHBOARD-F104 gh:saas#2575 gh:saas#2527 gh:saas#2529 -->
Estado: hecho
Actor: cuenta que paga
Pantalla: Facturación › Facturas, Negocios
Pasos:
1. En el aviso del negocio suspendido (en **Negocios** o en **Facturación**), la cuenta que paga pulsa «Pagar la factura · …» (si el banco rechazó la tarjeta, antes «Cambiar tarjeta»).
2. Se abre la página de pago de Stripe de esa factura; paga.
3. Al volver, «Factura pagada: … vuelve a estar al día» y el negocio funciona otra vez con sus datos y su plan, sin abrir otra suscripción.
Entra: la factura sin pagar y su página de pago en Stripe.
Sale: la factura pagada y numerada (BILLING-F25), el negocio activo y su estado enviado al negocio.
Si falla: «Pagando…» bloquea un segundo clic; solo la cuenta que paga el negocio puede pagar su factura («Solo la cuenta que paga este negocio puede pagar sus facturas»); una factura ya pagada o anulada no se paga otra vez. Un negocio cuyo plan ya terminó está en Gratis y vuelve a un plan de pago desde la Tienda (BILLING-F08).
Implicados: hubs (el estado del negocio), el negocio (vuelve a abrirse)

### BILLING-F18 Ver, cancelar o mantener el plan del negocio por la API
<!-- origen: old-saas:SAAS_DASHBOARD-F64 gh:saas#2529 gh:saas#2574 -->
Estado: hecho
Actor: propietario, integración
Pantalla: ninguna
Pasos:
1. Con su sesión, el propietario (o una integración de su cuenta) pide la lista de suscripciones: una fila por negocio que Stripe cobra, con plan, módulos, próxima factura y estado.
2. Pide cancelar el plan al final del periodo o mantenerlo, con las mismas reglas que la pantalla.
Entra: la sesión de la cuenta.
Sale: lo mismo que BILLING-F13 y BILLING-F14.
Si falla: un negocio que no es de esa cuenta no se encuentra; mantener un plan con una factura sin pagar se niega; sin sesión, «No has iniciado sesión».
Implicados: ninguno

### BILLING-F19 Recibir y validar un aviso de Stripe
<!-- origen: old-saas:SAAS_DASHBOARD-F97 gh:saas#2530 gh:saas#2539 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Stripe manda un aviso a erplora.com, a una sola dirección para todo.
2. erplora.com comprueba la firma con su secreto; sin firma válida, o con un aviso antiguo repetido, lo rechaza sin hacer nada.
3. Reclama el aviso una sola vez: si ya se procesó, contesta «duplicado»; si otra entrega lo está procesando, pide a Stripe que vuelva más tarde.
4. Si es un pago, mira qué paga por la etiqueta que erplora.com puso al abrirlo: uno que no es nuestro se da por recibido sin tocar nada.
5. Lo procesa según su tipo (alta, renovación, impago, fin, devolución) y lo apunta como procesado.
Entra: el aviso firmado.
Sale: la fila del aviso con su tipo y su resultado, de solo lectura en el admin.
Si falla: un error al procesarlo se apunta y se contesta con error, para que Stripe lo reenvíe; un reclamo de una entrega que murió a medias caduca y la siguiente lo retoma. Sin el secreto configurado, Stripe recibe «vuelve más tarde».
Implicados: ninguno

### BILLING-F20 Renovar el plan cada periodo
<!-- origen: old-saas:SAAS_DASHBOARD-F98 gh:saas#2527 gh:saas#2529 gh:saas#2530 gh:saas#2540 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al final de cada periodo Stripe cobra la tarjeta guardada y avisa del cobro.
2. erplora.com relee la suscripción viva y guarda su periodo nuevo y su estado (una prueba sigue siendo prueba).
3. Si el negocio estaba en impago, vuelve a estar al día en el acto.
4. Registra y numera la factura de ese cobro y la manda a emitir (BILLING-F25).
Entra: el aviso del cobro pagado.
Sale: el periodo y el estado de la suscripción del negocio y su factura (`billing.invoice.recorded`).
Si falla: si Stripe no contesta al releer la suscripción, no se aplica nada y Stripe vuelve a avisar. Un cobro de 0 € no hace factura. El cobro tardío de una factura vieja, con la suscripción aún en impago, no reactiva nada.
Implicados: el negocio (recibe su estado)

### BILLING-F21 Mantener el plan al día con lo que dice Stripe
<!-- origen: old-saas:SAAS_DASHBOARD-F99 gh:saas#2530 gh:saas#2540 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Stripe avisa de que la suscripción del negocio cambió (precio, estado, periodo o cancelación).
2. erplora.com relee la suscripción viva y busca el plan y los módulos por sus precios.
3. Guarda plan, periodicidad, estado, periodo y si se cancela al final del periodo, también cuando la cancelación se hizo fuera del panel.
Entra: el aviso de la suscripción cambiada.
Sale: la suscripción del negocio con lo que dice Stripe (`hubs.subscription.changed`) y su plan enviado al negocio.
Si falla: un precio que no vende ningún plan deja el plan como estaba, pero el estado, el periodo y la cancelación se guardan igual y queda una alarma; una suscripción desconocida no se lee de Stripe.
Implicados: el negocio (recibe su plan)

### BILLING-F22 Ver las facturas y descargarlas
<!-- origen: old-saas:SAAS_DASHBOARD-F117 -->
Estado: hecho
Actor: propietario, cuenta que paga
Pantalla: Facturación › Facturas
Pasos:
1. En **Facturación › Facturas** se ven las facturas de ERPlora de todos los negocios de la cuenta: Factura, Fecha, Negocio, Importe y Estado, de la más nueva a la más antigua.
2. Filtra por negocio, estado («Pagadas», «No cobradas») y año, o busca por número; los filtros se guardan en la dirección.
3. Pulsa «Descargar PDF» en una fila (o selecciona varias y «Descargar PDF (n)»), o «Descargar Excel» para la lista de lo filtrado, lista para la gestoría.
4. Una rectificativa dice «Rectificativa R1 · motivo» y la factura que rectifica.
Entra: las facturas que pagó la cuenta y las de los negocios de los que es propietaria.
Sale: el PDF de la factura emitida y la hoja de cálculo de lo filtrado.
Si falla: una factura que aún se emite dice «Emitiéndose» y no ofrece PDF; si el servicio de facturas no responde, «El servicio de facturas no responde. Prueba de nuevo en un momento»; sin facturas, «Aún no hay facturas». Una factura de otra cuenta no se encuentra.
Implicados: ninguno

### BILLING-F23 Ver las suscripciones de cada negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F118 -->
Estado: hecho
Actor: propietario, cuenta que paga
Pantalla: Facturación › Suscripciones
Pasos:
1. En **Facturación › Suscripciones** hay una fila por negocio que paga: el plan y sus módulos a precio sin IVA (un módulo cancelado dice «(hasta el …)»), la próxima factura con IVA y el estado.
2. Cada fila lleva sus acciones: la principal a la vista («Ver la factura» si hay una sin cobrar; si no, «Cambiar plan» o «Mantener el plan») y en «⋮» «Ver facturas» y «Cancelar plan».
Entra: las suscripciones de los negocios que paga la cuenta o de los que es propietaria.
Sale: nada.
Si falla: sin negocios de pago, «Todos tus negocios están en Gratis» con «Ver planes»; sin los datos de quien paga, la próxima factura no puede calcular su IVA y se dice. Un propietario que no paga solo consulta.
Implicados: ninguno

### BILLING-F24 Abrir el portal de pagos de Stripe para cambiar la tarjeta
<!-- origen: old-saas:SAAS_DASHBOARD-F120 gh:saas#2554 -->
Estado: hecho
Actor: cuenta que paga
Pantalla: Facturación › Datos de pago
Pasos:
1. En **Facturación › Datos de pago**, la tarjeta «Método de pago» dice qué tarjeta paga qué negocios y, si el último cobro falló, cuándo y de qué negocio.
2. Pulsa «Cambiar tarjeta»: se abre la página segura de Stripe de esa cuenta, que solo permite cambiar la tarjeta y ver los recibos.
3. Al volver, el panel vuelve a Facturación y, si había una factura rechazada, el aviso dice «Tarjeta cambiada» y «Pagar» vuelve.
Entra: la cuenta que paga el negocio.
Sale: la tarjeta nueva en Stripe; los cambios de plan nunca se hacen allí.
Si falla: antes del primer pago no hay nada que cambiar; si Stripe no contesta, se dice; solo la cuenta que paga lo abre, nunca otro propietario.
Implicados: ninguno

### BILLING-F25 Emitir la factura de ERPlora por un cobro
<!-- origen: old-saas:SAAS_DASHBOARD-F130 gh:saas#2527 gh:saas#2528 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Stripe avisa de un cobro pagado (alta, renovación, cambio de plan o módulo).
2. erplora.com califica la venta (BILLING-F03), le pone número de su serie (ERP-año-número, correlativo sin huecos) y la fecha del día, y copia los datos de quien paga ese día.
3. La manda al negocio de plataforma de ERPlora, que la registra con VeriFactu y devuelve su estado y su QR; cuando la emite, se avisa por correo a quien paga.
Entra: el cobro de Stripe con sus líneas y los datos de quien paga.
Sale: la factura y sus líneas (`billing.invoice.recorded`), su estado fiscal y el correo.
Si falla: si el negocio de plataforma no responde, la factura queda «emitiéndose» y se reintenta (a los 15 minutos, después el doble cada vez, como mucho 6 horas); si lo rechaza, se guarda el motivo y se reintenta. Una renovación sin cobrar se lista «No cobrada», sin número, y se numera al pagarla. Con claves reales, sin ruta de emisión no se cobra.
Implicados: el negocio de plataforma de ERPlora (emite la factura)

### BILLING-F26 Devolver un cobro
<!-- origen: old-saas:SAAS_DASHBOARD-F121 gh:saas#2527 -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: ninguna
Pasos:
1. El personal de ERPlora devuelve un cobro (entero o en parte) o emite una nota de crédito en el panel de Stripe.
2. Stripe avisa a erplora.com, que emite una factura rectificativa con importes negativos, la calificación y el destinatario de la original, su tipo (R1 para devoluciones y cambios de precio, R4 para lo demás) y su motivo.
3. La rectificativa sale en **Facturación › Facturas** con «Rectificativa R1 · motivo» y la factura que rectifica.
Entra: el aviso de la devolución o de la nota de crédito.
Sale: la rectificativa de su serie propia (ERPR-año-número), emitida como cualquier factura (`billing.credit_note.recorded`).
Si falla: una devolución de una factura que aún no existe espera y Stripe vuelve a avisar; la misma devolución nunca rectifica dos veces.
Implicados: el negocio de plataforma de ERPlora (emite la rectificativa)

### BILLING-F27 Lo que el personal de ERPlora puede hacer sobre el cobro de un cliente
<!-- origen: old-saas:SAAS_DASHBOARD-F123 gh:saas#2529 gh:saas#2575 -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin
Pasos:
1. Una persona de ERPlora entra en el admin con la cuenta del SaaS (código por correo y app de autenticación).
2. Ve, solo para leer, las suscripciones y sus líneas, los avisos de Stripe y los intentos de pago: lo que dice Stripe no se edita aquí, se cambia en Stripe y llega por su aviso.
3. En los negocios puede «Enviar el último estado al negocio» y «Reintentar lo que el negocio aún debe»; en las facturas, «Reenviar al negocio de plataforma» y «Reenviar el correo de la factura».
4. Mantiene los códigos promocionales, la tabla de IVA, la política fiscal y los datos de ERPlora; las devoluciones y las cancelaciones al momento se hacen en el panel de Stripe.
Entra: la cuenta del personal con su papel.
Sale: lo que hacen sus acciones; nada de lo que es de Stripe cambia desde el admin.
Si falla: sin el papel, el admin no se abre; el grupo de soporte solo mira, no lanza acciones.
Implicados: hubs (el estado de los negocios)

### BILLING-F28 Mantener en Stripe los precios de los planes
<!-- origen: old-saas:SAAS_DASHBOARD-F124 -->
Estado: parcial — el admin no comprueba en Stripe el precio que se pega
Actor: personal de ERPlora
Pantalla: Admin › Planes
Pasos:
1. Una persona de ERPlora crea en Stripe el producto del plan y sus precios mensual y anual, sin IVA incluido.
2. En el admin, en el plan, pega sus identificadores de Stripe junto al precio mensual y anual.
3. Desde ese momento el plan se vende a ese precio; sin ellos, no está a la venta.
Entra: el plan y sus precios de Stripe.
Sale: el plan a la venta.
Si falla: un plan sin su precio de Stripe no se vende y la Tienda lo dice.
Implicados: ninguno

### BILLING-F29 Probar el cobro real en PRE con un reloj de prueba de Stripe
<!-- origen: old-saas:SAAS_DASHBOARD-F105 -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin › Negocios
Pasos:
1. En PRE, una persona de ERPlora crea un negocio de pruebas con una cuenta nueva y rellena sus datos de facturación.
2. En **Admin › Negocios** selecciona ese negocio y lanza «Atar su pagador a un reloj de prueba de Stripe (solo claves de prueba)»: el admin dice en qué reloj quedó su pagador, que nace en Stripe atado a él.
3. Desde el panel, contrata un plan normal con la tarjeta de prueba.
4. Vuelve al admin y lanza «Adelantar un mes su reloj de prueba de Stripe»: el reloj salta un mes desde su propia hora y Stripe renueva y cobra como en producción, con sus avisos (BILLING-F20).
Entra: el negocio de pruebas y las claves de prueba de PRE.
Sale: un pagador de Stripe en un reloj de prueba y, al adelantarlo, la renovación con su factura de prueba, sin un plan interno de 1 €.
Si falla: con claves reales las dos acciones ni se ofrecen y, si se llegan a pedir, se niegan antes de llamar a Stripe; un pagador que ya es cliente de Stripe no se ata a un reloj (Stripe solo lo permite al crearlo); un reloj que aún avanza no se vuelve a adelantar («inténtalo de nuevo en un minuto»); un negocio sin reloj dice que se ate antes. Solo un superusuario las lanza; el grupo de soporte solo mira.
Implicados: hubs (el admin de los negocios)

### BILLING-F30 Usar claves reales de Stripe solo en producción y de prueba fuera de ella
<!-- origen: old-saas:SAAS_DASHBOARD-F106 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al desplegar, las comprobaciones del SaaS revisan las claves de Stripe: en producción solo vale la clave real restringida; la secreta de la cuenta, nunca.
2. En PRE, cualquier clave real (secreta, restringida o pública) para el despliegue; en producción, cualquier clave de prueba también.
3. Aunque el despliegue llegase a arrancar, la puerta a Stripe trata una clave del entorno equivocado como si no hubiera clave: no se cobra nada y el pago dice que no está disponible.
4. Las herramientas de prueba (el reloj de Stripe) se niegan con una clave real.
Entra: las claves de Stripe y el entorno.
Sale: nada guardado; el despliegue parado si la clave no es la del entorno.
Si falla: sin clave, ningún pago empieza y se dice que los pagos no están disponibles; en desarrollo se trabaja siempre con claves de prueba.
Implicados: ninguno

## Para quien lo mantiene

- Anatomía y operaciones: `billing/README.md` (IVA, Stripe, facturas, impago y la Tienda).
- Partes del porte (MIGRATION-TASK APP-BILLING-1/2/3): este WORKBOOK nace en la parte 1 con los flujos del
  plan y su dinero; las partes 2 (aplicaciones de pago, API y admin de facturas y suscripciones) y 3
  (precios, Stripe interno, modelos y tareas del soporte) añaden los suyos a continuación.
- Fuera del modelo viejo, a propósito: sin cuota de mantenimiento del 25 % al terminar un plan (PLAN-SAAS
  §3.3: vuelve a Gratis), sin estado «pendiente de pago» en el alta (el negocio nace en Gratis) y sin
  sincronización automática de productos de Stripe (los identificadores se pegan en el admin).
- Los tests de cada flujo citan su clave en el nombre o en el docstring; los e2e, en el título o en
  `// flow: BILLING-Fnn`.

## Lo que NO hace, a propósito

- No vende en las apps ni desde la cuenta abierta en la app (reglas de las tiendas de apps).
- No usa Stripe Tax ni deja que Stripe recoja el NIF: el IVA y el NIF son de erplora.com.
- No cobra una cuota por conservar un negocio que ya no paga: vuelve a Gratis.
- No cambia el plan desde el portal de Stripe: allí solo se cambia la tarjeta y se ven los recibos.
