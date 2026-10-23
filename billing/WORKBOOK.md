# Workbook — Facturación (billing)
Prefijo: BILLING
Alcance MVP: fase 1 (lo que una cuenta paga a ERPlora: planes, módulos, IVA y facturas)
Estado de la app: en uso (tres flujos parciales: BILLING-F33, BILLING-F34 y BILLING-F35, la parte del Hub que apaga una aplicación de pago)

> Manual de uso y especificación de la app `billing` del SaaS (erplora.com). Cuenta cómo se paga y se
> cambia el plan de un negocio, cómo se contratan y se cancelan sus aplicaciones de pago, qué pasa si un
> cobro falla, qué IVA lleva cada cobro y cómo se ven y descargan las facturas de ERPlora. Este manual no
> se publica en la tienda: es la referencia del equipo y de la QA. Lo que erplora.com hace solo cada noche con
> Stripe (olvidar avisos viejos y releer las suscripciones) está en BILLING-F37 y BILLING-F38.

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

**Módulos** enseña cada aplicación de pago con su icono, su nombre, su resumen y su precio sin IVA al
periodo del negocio, y lo único que el negocio puede hacer con ella: «Añadir · …», «Ya lo tienes» (o
«Incluido en tu plan»), «Cancelar el módulo», «Mantener · sin cobro hoy» en una cancelada o «Activando… en
…» justo después de comprarla. Una que ya no se vende solo la ve el negocio que la paga, con «Ya no se
vende».

### Pago seguro
Diálogo que se abre al mejorar un negocio que aún no paga: primero «¿A nombre de quién facturamos?» (solo
la primera vez), después el formulario de tarjeta de Stripe dentro del diálogo, con «¿Tienes un código
promocional?». Al terminar, «Pagando…» y la página del negocio.

### Cambiar de plan
Diálogo de un negocio que ya paga: lo que se cobra hoy prorrateado, el IVA, el total y lo que se cobrará
después, con «Pagar … y cambiar» (o «Cambiar de plan» si hoy no se cobra nada, como en una bajada, que
espera al final del periodo). Añadir una aplicación a un negocio que ya paga abre el mismo diálogo, titulado
«Añadir …», con «Pagar … y añadir».

### Facturación
Menú **Facturación**, con tres pestañas: **Facturas** (tabla con Factura, Fecha, Negocio, Importe y
Estado; filtros por negocio, estado y año; buscador por número; «Descargar PDF», «Ver la factura»,
«Descargar Excel» y «Pagar» en las no cobradas), **Suscripciones** (una fila por negocio que paga: plan, módulos, próxima
factura con IVA y estado; «Cambiar plan», «Mantener el plan», «Ver la factura», «Ver facturas» y
«Cancelar plan») y **Datos de pago** (la tarjeta con «Cambiar tarjeta» y los datos de facturación con
«Editar datos»). Arriba, en las tres, los avisos de facturas sin pagar.

### Factura
Página de una factura, que se abre con «Ver la factura»: su número (o «no cobrada»), la fecha, el negocio,
el cobro y su estado en VeriFactu; «Lo que se cobra», una línea por concepto con su periodo, su base y su
IVA; la base imponible, el IVA y el total; y «A nombre de», los datos de quien paga tal como estaban ese
día. Arriba, «Descargar PDF» cuando ya está emitida y «Pagar» si no se cobró; una rectificativa enlaza la
factura que rectifica. La flecha de arriba vuelve a Facturas.

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
| BILLING-F02 | Calcular el impuesto de una venta según dónde está el pagador | hecho |
| BILLING-F03 | Decidir el IVA de cada cobro | hecho |
| BILLING-F04 | Mantener la tabla de tipos de IVA y no vender con ella rota | hecho |
| BILLING-F05 | Comprobar en VIES el NIF-IVA de quien paga | hecho |
| BILLING-F06 | Seguir el umbral de ventas a distancia en la UE (OSS) | hecho |
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
| BILLING-F28 | Mantener en Stripe los precios de los planes | hecho |
| BILLING-F29 | Probar el cobro real en PRE con un reloj de prueba de Stripe | hecho |
| BILLING-F30 | Usar claves reales de Stripe solo en producción y de prueba fuera de ella | hecho |
| BILLING-F31 | Ver las aplicaciones de pago y su estado en cada negocio | hecho |
| BILLING-F32 | Contratar una aplicación de pago para un negocio | hecho |
| BILLING-F33 | Cancelar una aplicación de pago | parcial |
| BILLING-F34 | Terminar una aplicación de pago al final de su periodo | parcial |
| BILLING-F35 | Llevar una aplicación de pago a otro negocio | parcial |
| BILLING-F36 | Ver una factura | hecho |
| BILLING-F37 | Olvidar los avisos de Stripe de más de 30 días | hecho |
| BILLING-F38 | Releer cada noche las suscripciones en Stripe y corregir lo que se desvió | hecho |

### BILLING-F01 Decir dónde se factura el negocio y con qué identificación fiscal
<!-- origen: old-saas:SAAS_DASHBOARD-F90 fi:saas/orgs-users#informacion-de-facturacion-de-la-organizacion-ver-editar -->
Estado: hecho
Actor: propietario, cuenta que paga
Pantalla: Pago seguro, Facturación › Datos de pago
Pasos:
1. La primera vez que se paga un plan o un módulo, el diálogo de pago pregunta «¿A nombre de quién facturamos?»: «Razón social», «NIF (opcional)», «Dirección», «Ciudad», «Código postal», «País» y «Correo para las facturas (opcional)», o «Usar el nombre y el país del negocio».
2. Pulsa «Continuar al pago»: los datos se guardan y sigue el pago. Las veces siguientes el diálogo solo dice «Factura a nombre de …» con «Cambiar».
3. En cualquier momento, en **Facturación › Datos de pago**, la tarjeta «Datos de facturación» enseña razón social, NIF, dirección, correo y qué negocios paga, con «Editar datos».
4. Al escribir un NIF-IVA de otro país de la UE, la ventana lo comprueba en VIES y dice «Comprobado en VIES: … La factura va sin IVA», «VIES no reconoce este número: la factura llevará IVA» o «VIES no responde ahora: lo volvemos a comprobar al facturar».
5. Pulsa «Guardar datos»: «Datos de facturación guardados». Valen para las próximas facturas y para lo que manda Stripe (la página para confirmar un cobro que el banco quiere autenticar, sus recibos y su portal de pagos); las facturas ya emitidas no cambian.
Entra: lo que escribe la persona; el país y el nombre del negocio si elige usarlos.
Sale: los datos de facturación del negocio (los comparten los negocios que paga la misma cuenta), la comprobación de VIES anotada y, si quien paga ya pagó alguna vez, su ficha de cliente en Stripe al día; se avisa del cambio (`hubs.billing_profile.updated`).
Si falla: un código postal español que no tiene cinco dígitos, un país que falta o un NIF que no vale para su país salen debajo de su campo y no se guarda nada. Tras un traspaso, si el negocio lo pagaba otra cuenta, el diálogo dice «Hasta ahora pagaba este negocio otra cuenta: di quién paga a partir de ahora». Si Stripe no contesta, los datos se guardan igual y Stripe los recibe en el siguiente pago desde el panel.
Implicados: hubs (los datos del negocio y de quien paga)

### BILLING-F02 Calcular el impuesto de una venta según dónde está el pagador
<!-- origen: old-saas:SAAS_DASHBOARD-F91 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Antes de abrir cualquier pago (un plan, un cambio de plan o un módulo), erplora.com lee el país y el código postal de quien paga. Sin los dos, el pago no empieza y se piden los datos de facturación.
2. Califica la venta con la misma regla que luego usa la factura: península y Baleares, IVA español; Canarias, Ceuta y Melilla, sin IVA (se cobra el precio sin nada encima); otro país de la UE con NIF-IVA comprobado en VIES, inversión del sujeto pasivo, sin IVA; un particular de otro país de la UE, IVA español hasta superar el umbral de ventas a distancia y después el de su país; Reino Unido, solo a empresas y sin IVA.
3. Si el total con IVA pasa de 400 € y quien paga no tiene NIF, la venta se niega y se pide (una factura simplificada no puede pasar de ahí).
4. El tipo resultante viaja a Stripe con cada línea de la suscripción; Stripe solo suma lo que se le da.
5. Al guardar los **datos de facturación**, la suscripción que ya se cobra toma el tipo del lugar nuevo desde la siguiente factura, sin tocar lo ya pagado (por ejemplo, quien se muda de Madrid a Las Palmas deja de pagar IVA). Con un cambio a un plan menor ya programado, también cambia el tipo de lo que se cobrará al cambiar, así la primera factura del plan nuevo ya lleva el tipo de hoy. Una revisión diaria repite lo mismo con todas las suscripciones vivas por si un cambio no llegó.
Entra: país, código postal y NIF de quien paga, la última comprobación de VIES, el precio sin IVA y qué se vende (plan o módulo).
Sale: el tipo de cada línea en Stripe, o la negativa con su motivo.
Si falla: «Faltan los datos de facturación» lleva al formulario; un territorio sin regla en la tabla no se vende; un consumidor del Reino Unido no compra; más de 400 € sin NIF pide el NIF. Un precio de 0 € nunca se niega. Si al guardar los datos Stripe no contesta, los datos se guardan igual y la revisión diaria aplica el tipo; si el lugar nuevo no se vende, la suscripción sigue con su tipo y la revisión diaria se pone en rojo para el equipo.
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
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin › Reglas fiscales
Pasos:
1. Una persona de ERPlora edita en el admin las **reglas fiscales** (país, región, categoría, tipo, sujeta o no, desde y hasta) y las **categorías**. Gana la regla más concreta.
2. La lista enseña lo necesario para operar y se filtra por país y por categoría; dos reglas del mismo territorio que empiezan el mismo día se rechazan al guardar.
3. Toda venta lee la tabla en el momento: un territorio sin regla vigente no se vende.
4. Cada día, la **revisión de la tabla** mira cada venta posible y se pone en rojo para el equipo, con qué arreglar y dónde, si falta la regla del país que factura, si Canarias, Ceuta o Melilla dejan de salir sin IVA (regla borrada, desactivada, marcada como sujeta o un código postal que ya no las reconoce) o si un país con un pagador dado de alta no tiene tipo. Un país que solo cubre el tipo general de respaldo sale como aviso, no como fallo.
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
Estado: hecho
Actor: sistema, personal de ERPlora
Pantalla: Admin › Política fiscal, Admin › Avisos de la OSS
Pasos:
1. Cada factura a un particular de otro país de la UE suma su base al total del año (las rectificativas restan); el total de lo vendido por el SaaS anterior se carga una vez a mano en **Política fiscal**.
2. **Política fiscal** enseña el total del año contra el umbral (10.000 € por defecto) y los interruptores del alta en OSS y en el ROI.
3. Por encima del umbral (o con el alta voluntaria en OSS, o si el año anterior cerró por encima) las ventas nuevas a particulares de la UE llevan el IVA del país del cliente.
4. La venta cobrada que lleva el total del año por encima del 80 % del umbral manda un aviso al buzón del equipo para empezar ya el alta en la OSS, que tarda días; la que lo cruza (o la primera del año si el anterior cerró por encima) manda otro: desde ella esas ventas llevan el IVA del país del cliente. Cada aviso sale una sola vez al año y queda en **Admin › Avisos de la OSS**, de solo lectura.
5. La revisión diaria de las suscripciones vivas pasa a esos clientes al tipo de su país desde la siguiente factura (y de vuelta al español cuando el año vuelve a origen); lo que Stripe ya tiene no se le manda otra vez.
Entra: las facturas y la política.
Sale: el tipo de cada venta nueva y el de las suscripciones vivas, y los avisos al buzón del equipo.
Si falla: un negocio que Stripe no deja cambiar no para la revisión: se reintenta al día siguiente y el equipo lo ve en rojo. Un aviso que no pudo salir se reenvía en la revisión diaria, que sigue en rojo mientras quede alguno; anotar el aviso nunca para el cobro. Mientras el total del año no se ha cargado, el admin dice «desconocido» y con claves reales no se vende nada (es preferible no vender a cruzar el umbral sin verlo).
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
<!-- origen: old-saas:SAAS_DASHBOARD-F95 gh:saas#2527 pc:cloud/dashboard/hubs-pricing fi:saas/hubs#pagina-de-planes-precios fi:saas/hubs#stripe-gestion-de-suscripciones-servicio-interno fi:saas/support/hubs#service-stripeservice -->
Estado: hecho
Actor: propietario
Pantalla: Tienda, Pago seguro
Pasos:
1. En **Tienda › Planes**, con el negocio elegido arriba, el propietario ve cada plan con su precio sin IVA, sus usuarios y sus dispositivos, elige «Mensual» o «Anual» (que dice cuánto se ahorra) y pulsa «Mejorar a …».
2. Se abre el pago seguro: los datos de facturación si faltan y después el formulario de tarjeta de Stripe dentro del diálogo, titulado «Mejorar a …» con «Para … · se renueva cada mes» (o cada año).
3. Mete la tarjeta; si el banco pide autenticación, la muestra Stripe en el mismo formulario.
4. Al terminar, «Pagando…», el aviso «… ya está en …» y la página del negocio, cuya tarjeta Plan cambia en cuanto Stripe lo confirma. El negocio sigue funcionando todo el tiempo.
Entra: el plan elegido (solo los que se ofrecen a esa persona), el periodo, los datos de facturación y el código promocional si lo hay.
Sale: el negocio en el plan nuevo, su suscripción y su cliente en Stripe, el plan nuevo enviado al negocio (`hubs.subscription.changed`) y la factura de ERPlora del primer cobro (BILLING-F25), llegue antes o después el aviso del pago.
Si falla: si el pago no se puede abrir, «No hemos podido abrir el pago seguro» y «No se ha cobrado nada» con «Reintentar»; un plan sin precio en Stripe, «no está a la venta»; sin datos de facturación, el formulario; con una factura sin pagar, no se vende nada a ese negocio. Si la persona cierra el diálogo, no se cobra nada y el negocio sigue en Gratis.
Implicados: hubs (la suscripción del negocio), el negocio (recibe su plan)

### BILLING-F09 Volver del pago: confirmado, pendiente o cerrado
<!-- origen: old-saas:SAAS_DASHBOARD-F93 old-saas:SAAS_DASHBOARD-F109 gh:saas#2566 fi:saas/hubs#paginas-de-resultado-de-pago-success-cancel fi:saas/public#paginas-de-resultado-de-pago-success-cancel -->
Estado: hecho
Actor: propietario
Pantalla: Pago seguro, Resumen del negocio
Pasos:
1. Al terminar el pago en el formulario de Stripe, el diálogo dice «Pagando…», cierra el formulario, avisa «… ya está en …» (o «… añadido a …: se enciende en unos segundos» para un módulo) y abre la página del negocio.
2. El plan del negocio (o la aplicación comprada) cambia cuando Stripe confirma el cobro: si el medio de pago tarda en confirmarse, como un adeudo SEPA, el negocio sigue como estaba hasta entonces y cambia solo, sin recargar.
3. Si la persona cierra el diálogo antes de pagar, no se cobra nada y puede volver a abrirlo (BILLING-F10); el negocio sigue como estaba y no se borra nada.
Entra: el pago que Stripe da por terminado.
Sale: el mismo plan nuevo que deja el aviso de Stripe (BILLING-F19); la vuelta y el aviso nunca aplican dos veces el mismo pago.
Si falla: un pago que Stripe da por fallido después cierra ese intento sin cambiar el plan; un pago de otra cosa (un módulo) nunca cambia el plan. Un pago terminado por quien ya no es el propietario (el negocio se traspasó con el pago abierto, HUBS-F28) no se aplica: su suscripción se cancela, el cobro se devuelve entero (BILLING-F26 hace su rectificativa), el intento queda «Devuelto: ya no era el propietario» (`billing.checkout.refunded`) y le llega «Te hemos devuelto el pago de …» con el enlace a Facturación; si no se cobró nada, «Hemos cancelado tu plan de …». Una vez, aunque Stripe repita el aviso; si Stripe no responde, no se marca nada y Stripe lo vuelve a enviar.
Implicados: el negocio (recibe su plan)

### BILLING-F10 Reintentar un pago que no se terminó
<!-- origen: old-saas:SAAS_DASHBOARD-F94 gh:saas#2527 fi:saas/hubs#reintento-de-pago-retry-payment -->
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
<!-- origen: old-saas:SAAS_DASHBOARD-F96 fi:saas/hubs#cambio-de-plan-upgrade -->
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
<!-- origen: old-saas:SAAS_DASHBOARD-F100 old-saas:SAAS_DASHBOARD-F111 gh:saas#2529 gh:saas#2574 gh:saas#2593 gh:saas#2594 -->
Estado: hecho
Actor: sistema, propietario, cuenta que paga
Pantalla: Facturación, Negocios, el propio negocio
Pasos:
1. Falla el cobro de una renovación. Stripe lo reintenta durante unos días y avisa de cada fallo. Las aplicaciones de pago van en la misma factura que el plan: su impago es el del negocio entero, y al pagar vuelve todo.
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
<!-- origen: old-saas:SAAS_DASHBOARD-F64 fi:saas/billing#api-rest-de-suscripciones-drf gh:saas#2529 gh:saas#2574 fi:saas/hubs#subscriptions-cancelar-reanudar-estado-stripe fi:saas/hubs#subscriptions-rest-listado-detalle-scoped-por-usuario fi:saas/support/billing-fiscal#serializer-subscriptionlistserializer-subscriptiondetailserializer -->
Estado: hecho
Actor: propietario, integración
Pantalla: ninguna
Pasos:
1. Con su sesión, el propietario (o una integración de su cuenta, con una clave de lectura de Facturación) pide la lista de suscripciones: una fila por negocio que Stripe cobra, con plan, módulos, próxima factura y estado (el que dijo Stripe en su último aviso, BILLING-F21, o en la pasada de cada noche, BILLING-F38). Puede pedir solo la de un negocio o solo las de un estado.
2. Pide cancelar el plan al final del periodo o mantenerlo, con las mismas reglas que la pantalla.
Entra: la sesión de la cuenta.
Sale: lo mismo que BILLING-F13 y BILLING-F14.
Si falla: un negocio que no es de esa cuenta no se encuentra (filtrar por él da la lista vacía); mantener un plan con una factura sin pagar se niega; sin sesión, «No has iniciado sesión». Las de todos los negocios solo las ve el personal de ERPlora, en el admin (BILLING-F27).
Implicados: ninguno

### BILLING-F19 Recibir y validar un aviso de Stripe
<!-- origen: old-saas:SAAS_DASHBOARD-F97 gh:saas#2530 gh:saas#2539 fi:saas/hubs#webhook-de-stripe-pagos-suscripciones fi:saas/support/billing-fiscal#modelo-webhookevent fi:saas/support/public-core-config#service-stripe_webhook-handlers-webhooks-py -->
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
Sale: la fila del aviso con su tipo y su resultado, de solo lectura en el admin durante 30 días (BILLING-F37).
Si falla: un error al procesarlo se apunta y se contesta con error, para que Stripe lo reenvíe; un reclamo de una entrega que murió a medias caduca y la siguiente lo retoma. Sin el secreto configurado, Stripe recibe «vuelve más tarde».
Implicados: ninguno

### BILLING-F20 Renovar el plan cada periodo
<!-- origen: old-saas:SAAS_DASHBOARD-F98 old-saas:SAAS_DASHBOARD-F110 gh:saas#2527 gh:saas#2529 gh:saas#2530 gh:saas#2540 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al final de cada periodo Stripe cobra la tarjeta guardada y avisa del cobro. Las aplicaciones de pago del negocio se renuevan en el mismo cobro que el plan, una línea cada una; una cancelada cuyo periodo acabó ya no se cobra (BILLING-F34).
2. erplora.com relee la suscripción viva y guarda su periodo nuevo y su estado (una prueba sigue siendo prueba).
3. Si el negocio estaba en impago, vuelve a estar al día en el acto.
4. Registra y numera la factura de ese cobro y la manda a emitir (BILLING-F25).
Entra: el aviso del cobro pagado.
Sale: el periodo y el estado de la suscripción del negocio y su factura (`billing.invoice.recorded`).
Si falla: si Stripe no contesta al releer la suscripción, no se aplica nada y Stripe vuelve a avisar. Un cobro de 0 € no hace factura. El cobro tardío de una factura vieja, con la suscripción aún en impago, no reactiva nada.
Implicados: el negocio (recibe su estado)

### BILLING-F21 Mantener el plan al día con lo que dice Stripe
<!-- origen: old-saas:SAAS_DASHBOARD-F99 gh:saas#2530 gh:saas#2540 fi:saas/support/hubs#modelo-subscription-alias-hubsubscription -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Stripe avisa de que la suscripción del negocio cambió (precio, estado, periodo o cancelación).
2. erplora.com relee la suscripción viva y busca el plan y los módulos por sus precios.
3. Guarda plan, periodicidad, estado, periodo y si se cancela al final del periodo, también cuando la cancelación se hizo fuera del panel.
Entra: el aviso de la suscripción cambiada.
Sale: la suscripción del negocio con lo que dice Stripe (`hubs.subscription.changed`) y su plan enviado al negocio.
Si falla: un precio que no vende ningún plan deja el plan como estaba, pero el estado, el periodo y la cancelación se guardan igual y queda una alarma; una suscripción desconocida no se lee de Stripe. Un aviso que no llega nunca lo corrige la pasada de cada noche (BILLING-F38).
Implicados: el negocio (recibe su plan)

### BILLING-F22 Ver las facturas y descargarlas
<!-- origen: old-saas:SAAS_DASHBOARD-F117 fi:saas/billing#api-rest-de-facturas-drf fi:saas/billing#descarga-de-pdf-de-factura fi:saas/billing#exportar-facturas-a-csv fi:saas/billing#historial-de-compras-pagos fi:saas/billing#listado-de-facturas-invoices fi:saas/billing#redireccion-raiz-de-billing fi:saas/hubs#facturas-del-hub pc:cloud/dashboard/billing-invoices fi:saas/support/billing-fiscal#serializer-hubbasicserializer fi:saas/support/billing-fiscal#serializer-invoiceitemserializer fi:saas/support/billing-fiscal#serializer-invoicelistserializer-invoicedetailserializer fi:saas/support/billing-fiscal#service-invoicepdfgenerator-generate_invoice_pdf -->
Estado: hecho
Actor: propietario, cuenta que paga
Pantalla: Facturación › Facturas
Pasos:
1. **Facturación** se abre en **Facturas**, con las facturas de ERPlora de todos los negocios de la cuenta: Factura, Fecha, Negocio, Importe y Estado, de la más nueva a la más antigua. Lo pagado por una aplicación es una línea de la factura de su negocio.
2. Filtra por negocio, estado («Pagadas», «No cobradas») y año, o busca por número; los filtros se guardan en la dirección.
3. Pulsa «Descargar PDF» en una fila (o selecciona varias y «Descargar PDF (n)»), o «Descargar Excel» para la lista de lo filtrado, lista para la gestoría.
4. Una rectificativa dice «Rectificativa R1 · motivo» y la factura que rectifica.
5. «Ver la factura» abre su página (BILLING-F36).
6. Una integración de la cuenta, con una clave de lectura de Facturación, lee la misma lista con los mismos filtros, cada factura con su negocio, sus líneas, su IVA y a quién va, su PDF y la hoja de cálculo.
Entra: las facturas que pagó la cuenta y las de los negocios de los que es propietaria.
Sale: el PDF de la factura emitida, que hace en cada descarga el negocio de plataforma de ERPlora con su QR de VeriFactu (BILLING-F25), y la hoja de cálculo de lo filtrado.
Si falla: una factura que aún se emite dice «Emitiéndose» y no ofrece PDF; si el servicio de facturas no responde, «El servicio de facturas no responde. Prueba de nuevo en un momento»; sin facturas, «Aún no hay facturas». Una factura de otra cuenta no se encuentra.
Implicados: ninguno

### BILLING-F23 Ver las suscripciones de cada negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F118 fi:saas/billing#compras-de-modulos-purchases fi:saas/billing#suscripciones pc:cloud/dashboard/billing-purchases pc:cloud/dashboard/billing-subscriptions fi:saas/support/billing-fiscal#serializer-modulebasicserializer -->
Estado: hecho
Actor: propietario, cuenta que paga
Pantalla: Facturación › Suscripciones
Pasos:
1. En **Facturación › Suscripciones** hay una fila por negocio que paga: el plan y sus aplicaciones de pago a precio sin IVA (una cancelada dice «(hasta el …)» y deja de salir cuando termina), la próxima factura con IVA y el estado.
2. Cada fila lleva sus acciones: la principal a la vista («Ver la factura» si hay una sin cobrar; si no, «Mantenerlo con mi tarjeta», «Cambiar plan» o «Mantener el plan») y en «⋮» «Ver facturas» y «Cancelar plan».
Entra: las suscripciones de los negocios que paga la cuenta o de los que es propietaria.
Sale: nada.
Si falla: sin negocios de pago, «Todos tus negocios están en Gratis» con «Ver planes»; sin los datos de quien paga, la próxima factura no puede calcular su IVA y se dice. Un propietario cuyo plan cobra la tarjeta de otra cuenta (la del propietario anterior tras un traspaso) ve «Se paga con la tarjeta de otra cuenta»: no lo cambia ni lo cancela, lo mantiene con su tarjeta (HUBS-F28).
Implicados: hubs (HUBS-F28: el plan de un negocio traspasado)

### BILLING-F24 Abrir el portal de pagos de Stripe para cambiar la tarjeta
<!-- origen: old-saas:SAAS_DASHBOARD-F120 gh:saas#2554 fi:saas/orgs-users#portal-de-facturacion-stripe fi:saas/support/orgs-users#service-organizationstripeservice -->
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
<!-- origen: old-saas:SAAS_DASHBOARD-F130 gh:saas#2527 gh:saas#2528 fi:saas/support/billing-fiscal#modelo-invoice fi:saas/support/billing-fiscal#modelo-invoiceitem fi:saas/support/billing-fiscal#service-create_hub_invoice fi:saas/support/billing-fiscal#task-generate_invoice_pdf_async-regenerate_all_invoice_pdfs -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Stripe avisa de un cobro pagado (alta, renovación, cambio de plan o módulo).
2. erplora.com califica la venta (BILLING-F03), le pone número de su serie (ERP-año-número, correlativo sin huecos) y la fecha del día, y copia los datos de quien paga ese día.
3. La manda al negocio de plataforma de ERPlora, que la registra con VeriFactu y devuelve su estado y su QR; cuando la emite, se avisa por correo a quien paga.
Entra: el cobro de Stripe con sus líneas y los datos de quien paga.
Sale: la factura y sus líneas (`billing.invoice.recorded`), su estado fiscal y el correo.
Si falla: si el negocio de plataforma no responde, la factura queda «emitiéndose» y se reintenta (a los 15 minutos, después el doble cada vez, como mucho 6 horas); si lo rechaza, se guarda el motivo y se reintenta. Una renovación sin cobrar se lista «No cobrada», sin número, y se numera al pagarla. Un cobro de 0 € no hace factura, y el mismo cobro avisado varias veces hace una sola. Con claves reales, sin ruta de emisión no se cobra.
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
<!-- origen: old-saas:SAAS_DASHBOARD-F123 fi:saas/django-admin#admin-companyconfig-singleton fi:saas/django-admin#admin-invoice fi:saas/django-admin#admin-invoiceitem fi:saas/django-admin#admin-modulepurchase fi:saas/django-admin#admin-subscription fi:saas/django-admin#admin-subscription-2 fi:saas/hubs#admin-django-subscription-hub-subscriptions gh:saas#2529 gh:saas#2575 fi:saas/support/billing-fiscal#command-seed_company_036 fi:saas/support/billing-fiscal#modelo-companyconfig -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin
Pasos:
1. Una persona de ERPlora entra en el admin con la cuenta del SaaS (código por correo y app de autenticación).
2. Ve, solo para leer, las suscripciones y sus líneas, los avisos de Stripe y los intentos de pago: lo que dice Stripe no se edita aquí, se cambia en Stripe y llega por su aviso.
3. En los negocios puede «Enviar el último estado al negocio» y «Reintentar lo que el negocio aún debe»; en las facturas, con sus líneas, «Reenviar al negocio de plataforma», «Reenviar el correo de la factura» y «Descargar el PDF» de cualquier factura ya emitida.
4. Mantiene los códigos promocionales, la tabla de IVA, la política fiscal y los datos de ERPlora (nacen con los del Modelo 036 y son los que VIES ve de quien pregunta); las devoluciones y las cancelaciones al momento se hacen en el panel de Stripe.
5. Una aplicación de pago que algún negocio tiene no se borra del catálogo: el admin dice qué negocio la tiene y que se quite de la venta.
Entra: la cuenta del personal con su papel.
Sale: lo que hacen sus acciones; nada de lo que es de Stripe cambia desde el admin.
Si falla: sin el papel, el admin no se abre; el grupo de soporte solo mira, no lanza acciones. El PDF de una factura que aún no se ha emitido no existe: el admin lo dice («Aún no se ha emitido»), y si el negocio de plataforma no responde, vuelve a la factura diciendo por qué.
Implicados: hubs (el estado de los negocios)

### BILLING-F28 Mantener en Stripe los precios de los planes
<!-- origen: old-saas:SAAS_DASHBOARD-F124 -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin › Planes
Pasos:
1. Una persona de ERPlora crea en Stripe el producto del plan y sus precios mensual y anual, sin IVA incluido.
2. En **Admin › Planes**, en el plan, pega el producto y sus dos precios de Stripe junto al precio mensual y anual del plan, y guarda.
3. Al guardar, erplora.com pregunta a Stripe por cada precio y solo lo acepta si existe con las claves de ese entorno, está activo, en euros, se cobra cada mes (o cada año) como dice su campo, cobra lo mismo que el plan, es sin IVA y es de ese producto.
4. Desde ese momento el plan se vende a ese precio; sin sus precios, no está a la venta.
Entra: el plan y sus precios de Stripe.
Sale: el plan a la venta con sus precios comprobados.
Si falla: un precio que no cuadra no se guarda y dice por qué debajo de su campo («Este precio no está en euros», «Stripe cobra … y el plan dice …», «Este precio incluye el IVA o no lo dice…», un precio de pruebas en producción no se encuentra…). Si Stripe no contesta, no se guarda y se pide repetir; sin claves de Stripe (en desarrollo) se guarda y el admin avisa de que no se comprobó. Un plan sin su precio de Stripe no se vende y la Tienda lo dice.
Implicados: hubs (el admin de los planes)

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

### BILLING-F31 Ver las aplicaciones de pago y su estado en cada negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F107 gh:saas#2504 gh:saas#2535 -->
Estado: hecho
Actor: propietario
Pantalla: Tienda
Pasos:
1. En **Tienda › Módulos**, con el negocio elegido arriba, el propietario ve cada aplicación de pago con su icono, su nombre, su resumen y su precio sin IVA al periodo del negocio («… /mes + IVA» o «… /año + IVA»), en su idioma.
2. Cada tarjeta dice lo que la aplicación es en ese negocio: «Añadir · …» si no la tiene; «Ya lo tienes» con «Cancelar el módulo» si la paga; «Incluido en tu plan» si viene con el plan; «Ya lo tienes hasta el … (cancelado)» con «Mantener · sin cobro hoy» si está cancelada; «Activando… en …» justo después de comprarla.
3. Una aplicación que ERPlora ya no vende sigue saliendo al negocio que la paga, con «Ya no se vende: lo conservas mientras lo pagues y puedes cancelarlo cuando quieras»; a los demás negocios no se les ofrece.
Entra: el negocio elegido (solo los de los que esa persona es propietaria), el catálogo de aplicaciones y la suscripción del negocio.
Sale: nada.
Si falla: «No hemos podido cargar los precios» con «Reintentar»; sin aplicaciones a la venta, «Ahora mismo no hay módulos a la venta»; con una factura sin pagar, lo que cobra se desactiva con «Antes, paga la factura pendiente»; con pago anual, una aplicación que solo se vende al mes dice «Solo con pago mensual». En la app no se vende: se dice que se entre en erplora.com desde el navegador.
Implicados: apps (el nombre, el resumen y el icono de cada aplicación)

### BILLING-F32 Contratar una aplicación de pago para un negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F108 gh:saas#2566 gh:saas#2629 gh:saas#2639 gh:saas#2640 fi:saas/public#compra-de-un-modulo-stripe-embedded-checkout fi:saas/public#webhook-de-stripe-compras-de-modulos fi:saas/support/billing-fiscal#modelo-subscription fi:saas/support/public-core-config#modelo-modulepurchase fi:saas/support/public-core-config#service-send_module_purchase_email-send_vendor_sale_email-emails-py fi:saas/support/public-core-config#task-send_module_purchase_email_task-send_vendor_sale_email_task-tasks-py -->
Estado: hecho
Actor: propietario
Pantalla: Tienda, Cambiar de plan, Pago seguro
Pasos:
1. En **Tienda › Módulos**, con el negocio elegido arriba, el propietario pulsa «Añadir · …» en la aplicación.
2. Si el negocio ya paga, el diálogo «Añadir …» dice «Se suma a la suscripción de …» y lo que se cobra: «Hoy (prorrateado)», el IVA, el «Total hoy» y lo que se cobrará «Desde el …»; confirma con «Pagar … y añadir», que cobra con la tarjeta guardada.
3. Si el negocio está en Gratis, se abre el pago seguro con la aplicación sola, como en BILLING-F08; una aplicación no tiene días de prueba.
4. Aviso «… añadido a …: se enciende en unos segundos»; la tarjeta dice «Activando… en …» y después «Ya lo tienes». La aplicación va en la misma factura mensual (o anual) que el plan.
Entra: el negocio, la aplicación (solo una que está a la venta y que el negocio no tiene) y el periodo del negocio.
Sale: la aplicación en la suscripción del negocio (`billing.module.added`), su factura (BILLING-F25), cuyo correo es la confirmación de la compra, y la aplicación enviada al negocio.
Si falla: una aplicación que el negocio ya tiene no se vende dos veces; una retirada o desconocida no se vende; una gratuita no se compra, viene con cualquier negocio; con una factura sin pagar, «Antes, paga la factura pendiente»; si pasó demasiado tiempo, «El precio estaba desactualizado: aquí lo tienes de nuevo, revísalo antes de confirmar»; la tarjeta rechazada no añade nada. Con un medio de pago que tarda (adeudo SEPA), la aplicación llega cuando Stripe confirma el cobro (BILLING-F09).
Implicados: hubs (la suscripción del negocio), el negocio (recibe la aplicación)

### BILLING-F33 Cancelar una aplicación de pago
<!-- origen: old-saas:SAAS_DASHBOARD-F112 gh:saas#2535 gh:saas#2568 gh:saas#2589 -->
Estado: parcial — el negocio todavía no apaga una aplicación que dejó de pagarse: hoy todas las aplicaciones están encendidas en todos los negocios
Actor: propietario que paga
Pantalla: Tienda
Pasos:
1. En **Tienda › Módulos**, con el negocio elegido arriba, el propietario pulsa «Cancelar el módulo» en una aplicación que paga.
2. El diálogo «Cancelar el módulo» dice «… sigue funcionando en … hasta el …; después se apaga y no se vuelve a cobrar», que no se borra nada de lo que el negocio escribió con ella y que hasta entonces se puede deshacer con «Mantener».
3. Pulsa «Cancelar el módulo»: «… cancelado: funciona hasta el …». La tarjeta dice «Ya lo tienes hasta el … (cancelado)» con «Mantener · sin cobro hoy», y **Facturación › Suscripciones**, «(hasta el …)».
4. «Mantener · sin cobro hoy» deshace la cancelación: «… se mantiene: se renovará el …».
Entra: la aplicación comprada del negocio (no una que viene con el plan).
Sale: la aplicación fuera de la suscripción en Stripe sin devolver nada, con su fecha de fin (`billing.module.cancelled`; al mantenerla, `billing.module.kept`), y esa fecha enviada al negocio.
Si falla: una aplicación que viene con el plan se quita cambiando de plan; una que el negocio no tiene no se encuentra; con un cambio de plan programado, se deshace antes; si Stripe la rechaza o no contesta, el diálogo sigue abierto y dice por qué. Una aplicación que ya no se vende se cancela igual, pero no se puede mantener; una que ya terminó se vuelve a comprar. Mantener con una factura sin pagar se niega.
Implicados: hubs (la suscripción del negocio), el negocio (recibe hasta cuándo la tiene)

### BILLING-F34 Terminar una aplicación de pago al final de su periodo
<!-- origen: old-saas:SAAS_DASHBOARD-F113 -->
Estado: parcial — el negocio todavía no apaga la aplicación terminada: hoy todas las aplicaciones están encendidas en todos los negocios
Actor: sistema
Pantalla: Tienda, Facturación › Suscripciones
Pasos:
1. Llega la fecha de fin de una aplicación cancelada.
2. Deja de enviarse al negocio, la renovación ya no la cobra, **Facturación › Suscripciones** ya no la lista y la Tienda la vuelve a ofrecer con «Añadir · …».
3. No se borra ningún dato: si se vuelve a contratar, el negocio la tiene como estaba.
Entra: la fecha de fin de la aplicación.
Sale: el negocio sin la aplicación desde ese día.
Si falla: si se cancela el plan, sus aplicaciones terminan con él (BILLING-F15).
Implicados: el negocio (deja de recibir la aplicación)

### BILLING-F35 Llevar una aplicación de pago a otro negocio
<!-- origen: old-saas:SAAS_DASHBOARD-F114 gh:saas#2589 -->
Estado: parcial — depende de BILLING-F33: el negocio de origen todavía no apaga la aplicación cuando termina
Actor: propietario
Pantalla: Tienda
Pasos:
1. Una aplicación no se traspasa: se cancela en un negocio y se contrata en el otro, como hacen Square, Shopify, Toast, Clover y Lightspeed.
2. En **Tienda › Módulos**, con el negocio de origen elegido, el propietario pulsa «Cancelar el módulo» (BILLING-F33): sigue funcionando allí hasta el final de lo pagado.
3. Elige arriba el negocio de destino y pulsa «Añadir · …» (BILLING-F32): se cobra prorrateado en la suscripción de ese negocio.
Entra: los dos negocios, de los que es propietario.
Sale: lo mismo que BILLING-F33 en el origen y que BILLING-F32 en el destino.
Si falla: los rechazos de BILLING-F33 y BILLING-F32.
Implicados: hubs (las suscripciones de los dos negocios)

### BILLING-F36 Ver una factura
<!-- origen: fi:saas/billing#detalle-de-factura -->
Estado: hecho
Actor: propietario, cuenta que paga
Pantalla: Factura
Pasos:
1. En **Facturación › Facturas**, la persona pulsa «Ver la factura» en una fila.
2. La página dice su número (o «Factura … (no cobrada)»), la fecha, el negocio, el cobro y su estado en VeriFactu; «Lo que se cobra», una línea por concepto con su periodo, «Prorrateado» si lo es, su base y su IVA; la base imponible, el IVA y el total; y «A nombre de», con los datos de quien paga tal como estaban ese día.
3. Desde ella descarga el PDF de una factura emitida, paga una no cobrada o, en una rectificativa, abre la factura que rectifica. Mientras se emite, la página pasa sola a su número y su QR.
4. La flecha de arriba vuelve a Facturas.
Entra: una factura de la cuenta.
Sale: nada.
Si falla: una factura de otra cuenta no se encuentra; si no carga, «No hemos podido cargar esta factura» con «Reintentar»; una que aún se emite dice que su PDF estará cuando termine. En la app se ve, pero no se paga.
Implicados: ninguno

### BILLING-F37 Olvidar los avisos de Stripe de más de 30 días
<!-- origen: fi:saas/support/billing-fiscal#task-cleanup_old_webhook_events -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada noche, erplora.com borra los avisos de Stripe que recibió hace más de 30 días, procesados o no.
2. Los de los últimos 30 días se quedan: son los que Stripe aún puede reenviar y los que el personal consulta en el admin (BILLING-F27).
Entra: los avisos guardados (BILLING-F19).
Sale: los avisos de más de 30 días borrados y, en el registro de la tarea, cuántos.
Si falla: la noche siguiente borra lo que quedó. Stripe solo reenvía un aviso durante 3 días, así que uno borrado nunca se procesa dos veces.
Implicados: ninguno

### BILLING-F38 Releer cada noche las suscripciones en Stripe y corregir lo que se desvió
<!-- origen: fi:saas/support/hubs#command-sync_subscriptions -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada noche, erplora.com relee en Stripe la suscripción de cada negocio que paga, uno a uno.
2. Si algo no cuadra (el plan, el periodo, una cancelación, una prueba o una aplicación cambiados en Stripe cuyo aviso nunca llegó), lo corrige como lo habría hecho ese aviso (BILLING-F21) y lo anota para el equipo con lo que se desvió.
3. Una suscripción que aún espera su primer pago se deja para la noche siguiente; un negocio en Gratis no se lee.
Entra: las suscripciones que Stripe cobra.
Sale: cada suscripción como dice Stripe (`hubs.subscription.changed` si cambió algo) y su plan enviado al negocio.
Si falla: una suscripción que Stripe no conoce, o que no se pudo leer, no se toca y la tarea termina con error, que avisa al equipo; un negocio que falla no para a los demás. Puede ejecutarse en prueba, sin escribir nada, para ver solo qué se desvió.
Implicados: hubs (la suscripción del negocio), el negocio (recibe su plan)

## Para quien lo mantiene

- Anatomía y operaciones: `billing/README.md` (IVA, Stripe, facturas, impago y la Tienda).
- Partes del porte (MIGRATION-TASK APP-BILLING-1/2/3): este WORKBOOK nace en la parte 1 con los flujos del
  plan y su dinero; la parte 2 añade las aplicaciones de pago (BILLING-F31 a BILLING-F35), la página de una
  factura (BILLING-F36) y amplía los flujos de la API y del admin; la parte 3 une a los flujos que ya
  existían el soporte de Stripe del SaaS viejo (precios, vuelta del pago, servicio de Stripe, modelos,
  serializadores y tareas) y añade BILLING-F37 y BILLING-F38. Lo que allí eran tareas de Celery aquí son
  tareas programadas o se hace tras el COMMIT (el correo de la factura).
- Fuera del modelo viejo, a propósito: sin cuota de mantenimiento del 25 % al terminar un plan (PLAN-SAAS
  §3.3: vuelve a Gratis), sin estado «pendiente de pago» en el alta (el negocio nace en Gratis) y sin
  sincronización automática de productos de Stripe (los identificadores se pegan en el admin).
- Los tests de cada flujo citan su clave en el nombre o en el docstring; los e2e, en el título o en
  `// flow: …`. Los e2e de la parte 1 (`tests/e2e/panel/billing-flows.spec.ts` y, en el Hub,
  `tests/e2e/hub-suspended.spec.ts`) citan la clave del registro (`BILLING-Gnn`) y llevan en su cabecera la
  equivalencia con la de este WORKBOOK. Igual los de la parte 2 (`tests/e2e/panel/billing-apps.spec.ts`) y
  los de la parte 3 (`tests/e2e/panel/billing-support.spec.ts`).
- Tareas programadas (ECS, `saas-cron`): `manage.py audit_tax_rules` (BILLING-F04),
  `manage.py retax_subscriptions` (BILLING-F02, BILLING-F06) y `manage.py sync_subscriptions` (BILLING-F38;
  `--dry-run` solo informa) salen con error si dejan algo por hacer, que es lo que la alarma `task_failed`
  avisa al equipo; `manage.py purge_webhook_events` (BILLING-F37) solo borra. Las programa el repo de
  infraestructura (`stacks/prod/scheduler.tf` de `ERPlora/aws`): `sync_subscriptions` cada noche a las 00:10 UTC
  (antes de la foto de las 00:30 y de la re-tarificación), `purge_webhook_events` a las 00:50 UTC,
  `audit_tax_rules` cada día a las 05:10 UTC y `retax_subscriptions` a las 05:20 UTC.

## Lo que NO hace, a propósito

- No vende en las apps ni desde la cuenta abierta en la app (reglas de las tiendas de apps).
- No usa Stripe Tax ni deja que Stripe recoja el NIF: el IVA y el NIF son de erplora.com.
- No cobra una cuota por conservar un negocio que ya no paga: vuelve a Gratis.
- No cambia el plan desde el portal de Stripe: allí solo se cambia la tarjeta y se ven los recibos.
- No traspasa una aplicación contratada de un negocio a otro: se cancela en uno y se contrata en el otro
  (BILLING-F35).
- No vende aplicaciones sueltas fuera de la suscripción del negocio: no hay compras aparte; lo pagado por
  una aplicación es una línea de la factura de su negocio.
- No hace facturas a mano desde el admin: cada factura sale de un cobro de Stripe.
- No cobra por uso ni por excesos (sin medidores ni plan «Flex»): quien necesita más sube de plan.
- No pide ni guarda una moneda: ERPlora cobra siempre en euros, y la preferencia de moneda de la cuenta del
  panel viejo no se porta (el panel único la quitó).
- No manda un correo aparte por cada compra ni al «vendedor» de una aplicación: todas son de ERPlora, y la
  confirmación de una compra es el correo de su factura (BILLING-F25).
