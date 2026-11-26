# Workbook — Facturación (billing)
Prefijo: BILLING
Alcance MVP: fase 1 (lo que una cuenta paga a ERPlora: planes, módulos, IVA y facturas)
Estado de la app: completa (2026-11-03)

> Manual de uso y especificación de la app `billing` del SaaS (erplora.com). Cuenta cómo se paga y se
> cambia el plan de un negocio, cómo se contratan y se cancelan sus aplicaciones de pago, qué pasa si un
> cobro falla, qué IVA lleva cada cobro y cómo se ven y descargan las facturas de ERPlora. Este manual no
> se publica en la tienda: es la referencia del equipo y de la QA. Lo que erplora.com hace solo cada noche con
> Stripe (olvidar avisos viejos y releer las suscripciones) está en BILLING-F37 y BILLING-F38, y lo que comprueba cada
> día de su aviso (que Stripe mande todos los que trata), en BILLING-F39.

## Para qué sirve y para quién

Facturación es lo que una cuenta paga a ERPlora por sus negocios. Cada negocio empieza en **Gratis** y,
cuando lo necesita, su propietario lo pasa a un plan de pago desde la **Tienda**. ERPlora cobra con
tarjeta a través de Stripe, pone el IVA que toca según dónde está quien paga y emite su propia factura
legal por cada cobro, que se ve y se descarga en **Facturación**. Por ahora solo vende a quien paga con dirección
de facturación en España; en Canarias, Ceuta y Melilla, solo a empresas y profesionales.

- Una sola suscripción por negocio: el plan y los módulos que se compren van juntos y se cobran en una
  sola factura al mes (o al año).
- Cancelar nunca borra nada: el negocio sigue con su plan hasta el final del periodo pagado y después
  vuelve a Gratis.
- Si un cobro falla, el negocio sigue funcionando 7 días mientras se reintenta; después se suspende
  hasta que se pague, sin perder ningún dato.

Hoy ninguna aplicación es de pago: todas van en todos los planes.
Lo que este manual cuenta de las aplicaciones de pago (la pantalla **Tienda › Módulos** y contratar, cancelar,
terminar y llevar una a otro negocio, BILLING-F31 a BILLING-F35) funciona y está probado, pero no se usa hasta que
vuelva a haber una.

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
periodo («Mensual» o «Anual · −n %»), sus líneas como en /pricing/ (tras «Todas las apps incluidas» o «Todo lo
del plan …», «Hasta 40 apps activadas a la vez», o «Todas las apps activadas a la vez» si el plan no tiene tope;
después los mensajes al mes, «Dominio propio para tu web (www.tunegocio.com)» en los planes que lo incluyen y, al final, la prueba), «Tu plan actual» en el que se tiene y el botón de cada uno:
«Mejorar a …», «Cambiar a …», «Cambiar a anual · …» o «Bajar a Gratis»; con el plan cancelado o una bajada
programada, «Mantener el plan». Un plan que no se vende con el periodo elegido, porque le falta su precio de Stripe,
tiene el botón desactivado y debajo dice por qué: «Solo con pago mensual», «Solo con pago anual» o «No está a la venta
ahora mismo». Cada tarjeta enseña sus cinco primeras líneas, con el botón justo debajo del
precio; «Ver todas las características» despliega las demás en todas las tarjetas a la vez y «Ver menos» las
recoge. Un negocio que el personal de ERPlora marcó en el admin (BILLING-F27) ve también,
al final, el plan interno «Prueba de pago (interno)»; ningún otro negocio lo ve. Si el negocio tiene una factura sin pagar, arriba sale el aviso con «Pagar la factura» y no se
vende nada a ese negocio.

**Módulos** enseña cada aplicación de pago con su icono, su nombre, su resumen y su precio sin IVA al
periodo del negocio, y lo único que el negocio puede hacer con ella: «Añadir · …» (el icono «+» con su precio), «Ya lo tienes» (o
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
«Cancelar plan») y **Datos de pago** (la tarjeta con el icono «Cambiar tarjeta» y los datos de facturación con
el icono «Editar datos»; su nombre sale al pasar el ratón). Las facturas sin pagar no se avisan dentro de las pestañas: se avisan en la campana de la barra
superior (Avisos de la campana).

### Avisos de la campana
La campana de la barra superior del panel, en todas las pantallas. Con una factura sin pagar se vuelve una píldora
roja con el número de negocios que la tienen. Un aviso nuevo llega como tarjeta arriba a la derecha (a lo ancho en el
móvil) y a los pocos segundos se recoge en la campana. Al pulsarla se abre el panel «Avisos», con el negocio más
urgente arriba: «… tiene una factura sin pagar», el importe, «quedan … días» (o «suspendido»), lo que pasa si no se
paga («Si no se paga antes del …, el negocio se suspende. No se borra nada.») y «Pagar la factura · …» con «Cambiar
tarjeta» al lado; si el banco rechazó la tarjeta, solo «Cambiar tarjeta». Los demás negocios, en filas debajo. Un
aviso no se descarta: desaparece cuando se paga la factura. Quien no paga el negocio ve el aviso sin botones y «Solo
la cuenta que paga este negocio puede pagar sus facturas.»; en la app, «Para pagarla, entra en erplora.com desde el
navegador.»

### Factura
Página de una factura, que se abre con «Ver la factura»: su número (o «no cobrada»), la fecha, el negocio,
el cobro y su estado en VeriFactu; «Lo que se cobra», una línea por concepto con su periodo, su base, su
IVA y su descuento si lo tiene; la base imponible, el IVA y el total; y «A nombre de», los datos de quien paga tal como estaban ese
día. Arriba, el icono «Descargar PDF» cuando ya está emitida y, si no se cobró, «Pagar la factura · …», la tarjeta con el importe; una rectificativa enlaza la
factura que rectifica. La flecha de arriba vuelve a Facturas.

### Resumen del negocio
En la página de cada negocio, la tarjeta **Plan** dice en qué plan está, cuántos usuarios y dispositivos
caben, cuántas apps se pueden tener activadas a la vez («Apps activadas a la vez»: el número o «Ilimitadas») y,
al propietario, el botón para mejorarlo o cambiarlo.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» o el esqueleto de la tabla mientras llegan los datos; «Calculando lo que se cobra hoy…» en un cambio de plan. |
| Vacío | Facturas: «Aún no hay facturas» y «Ver planes»; Suscripciones: «Todos tus negocios están en Gratis»; Datos de pago: «Aún no hay ninguna tarjeta guardada». |
| Error | «No hemos podido cargar …» con «Reintentar»; un pago que no se abre dice «No se ha cobrado nada» con «Reintentar». Si no se pudo comprobar si hay facturas sin pagar, el panel de la campana dice «No se pudieron cargar los avisos» con «Reintentar». |
| Stripe no responde | La tarjeta: «Ahora no podemos enseñarte la tarjeta: inténtalo en unos minutos»; un pago: el aviso de que no se ha cobrado nada. |
| Factura sin pagar | La campana de la barra superior, en rojo con su número; en su panel, el aviso de cada negocio con el importe, hasta cuándo funciona y «Pagar la factura · …»; con la tarjeta rechazada, «Cambiar tarjeta». |
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
| BILLING-F12 | Dar días de prueba o un descuento con un código promocional | hecho |
| BILLING-F13 | Cancelar el plan al final del periodo | hecho |
| BILLING-F14 | Deshacer una cancelación o una bajada pendiente | hecho |
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
| BILLING-F33 | Cancelar una aplicación de pago | hecho |
| BILLING-F34 | Terminar una aplicación de pago al final de su periodo | hecho |
| BILLING-F35 | Llevar una aplicación de pago a otro negocio | hecho |
| BILLING-F36 | Ver una factura | hecho |
| BILLING-F37 | Olvidar los avisos de Stripe de más de 30 días | hecho |
| BILLING-F38 | Releer cada noche las suscripciones en Stripe y corregir lo que se desvió | hecho |
| BILLING-F39 | Comprobar cada día que Stripe avisa de todo lo que erplora.com trata | hecho |
| BILLING-F40 | Sacar el informe de facturación de un periodo para la gestoría | hecho |
| BILLING-F41 | Ver qué clientes pagan, con qué plan, desde cuándo y cuánto | hecho |

### BILLING-F01 Decir dónde se factura el negocio y con qué identificación fiscal
Estado: hecho
Actor: propietario, cuenta que paga
Pantalla: Pago seguro, Facturación › Datos de pago
Pasos:
1. La primera vez que se paga un plan o un módulo, el diálogo de pago pregunta «¿A nombre de quién facturamos?»: «Razón social», «NIF (opcional)», «Dirección», «Ciudad», «Código postal», «País» y «Correo para las facturas (opcional)», o «Usar el nombre y el país del negocio». «País» solo ofrece España y dice debajo «Por ahora ERPlora solo factura a pagadores en España.»; el NIF dice «Obligatorio en Canarias, Ceuta y Melilla, donde solo vendemos a empresas y profesionales.».
2. Pulsa «Continuar al pago»: los datos se guardan y sigue el pago. Las veces siguientes el diálogo solo dice «Factura a nombre de …» con el icono «Cambiar los datos de facturación».
3. En cualquier momento, en **Facturación › Datos de pago**, la tarjeta «Datos de facturación» enseña razón social, NIF, dirección, correo y qué negocios paga, con el icono «Editar datos».
4. Al escribir el NIF, la ventana dice «NIF válido.». Un NIF-IVA de otro país de la UE se comprueba en VIES y dice «Comprobado en VIES: …. Se factura en España, así que la factura lleva IVA.», «VIES no reconoce este número: la factura llevará IVA» o «VIES no responde ahora: lo volvemos a comprobar al facturar». «Comprobado en VIES: … La factura va sin IVA» solo sale cuando la venta va con inversión del sujeto pasivo, que hoy no ocurre: solo se factura en España.
5. Pulsa «Guardar datos»: «Datos de facturación guardados». Valen para las próximas facturas y para lo que manda Stripe (la página para confirmar un cobro que el banco quiere autenticar, sus recibos y su portal de pagos); las facturas ya emitidas no cambian. Lo que manda Stripe lleva solo el NIF actual: el anterior se quita, y también desaparece si se borra el NIF.
Entra: lo que escribe la persona; el país y el nombre del negocio si elige usarlos.
Sale: los datos de facturación del negocio (los comparten los negocios que paga la misma cuenta), la comprobación de VIES anotada y, si quien paga ya pagó alguna vez, su ficha de cliente en Stripe al día, con el NIF actual como único identificador fiscal (ninguno si no tiene o si es un NIF-IVA que VIES no ha comprobado); se avisa del cambio (`hubs.billing_profile.updated`).
Si falla: un código postal español que no tiene cinco dígitos, un país que falta o un NIF que no vale para su país salen debajo de su campo, con «Revisa los datos marcados.» arriba hasta que corriges algo, y no se guarda nada. Un país que no sea España sale debajo de «País» y arriba con «Por ahora ERPlora solo factura a pagadores en España.», también al «Usar el nombre y el país del negocio» de un negocio de fuera de España (que puede existir: el negocio se crea en cualquier país de la UE), y no se guarda nada. Tras un traspaso, si el negocio lo pagaba otra cuenta, el diálogo dice «Hasta ahora pagaba este negocio otra cuenta: di quién paga a partir de ahora». Si Stripe no contesta, los datos se guardan igual y Stripe los recibe en el siguiente pago desde el panel. Si Stripe no deja quitar el NIF anterior, los datos se guardan igual, el pago sigue y el equipo lo ve en el registro de errores.
Implicados: hubs (los datos del negocio y de quien paga)

### BILLING-F02 Calcular el impuesto de una venta según dónde está el pagador
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Antes de abrir cualquier pago (un plan, un cambio de plan, un módulo, mantener el plan tras un traspaso o recuperar un módulo cancelado), erplora.com lee el país y el código postal de quien paga. Sin los dos, el pago no empieza y se piden los datos de facturación. Por ahora solo se vende a quien paga en España: con otro país, el pago no empieza y el diálogo vuelve a los datos con «Por ahora ERPlora solo vende a pagadores con dirección de facturación en España: cambia los datos de facturación.» (`billing.country_not_sold`), también a una empresa con NIF-IVA comprobado en VIES.
2. Califica la venta con la misma regla que luego usa la factura: península y Baleares, IVA español; Canarias, Ceuta y Melilla, sin IVA (se cobra el precio sin nada encima) y solo a empresas y profesionales, que declaran ellas el IGIC o el IPSI: sin NIF, el pago no empieza y el diálogo vuelve a los datos con «En Canarias, Ceuta y Melilla solo vendemos a empresas y profesionales: añade el NIF de quien paga.» (`billing.business_required`). El motor conserva las reglas de fuera de España (inversión del sujeto pasivo con NIF-IVA comprobado en VIES; un particular de otro país de la UE, IVA español hasta superar el umbral de ventas a distancia y después el de su país; Reino Unido, solo a empresas y sin IVA) para lo que ya se cobra y para cuando se vuelva a vender fuera, que es añadir el país a la lista de los que se venden.
3. Si el total con IVA pasa de 400 € y quien paga no tiene NIF, la venta se niega y se pide (una factura simplificada no puede pasar de ahí).
4. El tipo resultante viaja a Stripe con cada línea de la suscripción; Stripe solo suma lo que se le da.
5. Al guardar los **datos de facturación**, la suscripción que ya se cobra toma el tipo del lugar nuevo desde la siguiente factura, sin tocar lo ya pagado (por ejemplo, quien se muda de Madrid a Las Palmas deja de pagar IVA). Lo que ya se cobra no se niega por el país ni por ser un consumidor de Canarias, Ceuta o Melilla: quien ya pagaba desde otro país sigue renovándose con el motor y solo deja de poder comprar nada nuevo; cancelar siempre se puede. Con un cambio a un plan menor ya programado, también cambia el tipo de lo que se cobrará al cambiar, así la primera factura del plan nuevo ya lleva el tipo de hoy. Una revisión diaria repite lo mismo con todas las suscripciones vivas por si un cambio no llegó.
Entra: país, código postal y NIF de quien paga, la última comprobación de VIES, el precio sin IVA y qué se vende (plan o módulo).
Sale: el tipo de cada línea en Stripe, o la negativa con su motivo.
Si falla: «Faltan los datos de facturación» lleva al formulario; quien paga fuera de España o un consumidor de Canarias, Ceuta o Melilla vuelve al formulario con su motivo; un territorio sin regla en la tabla no se vende; un consumidor del Reino Unido no compra; más de 400 € sin NIF pide el NIF. Un precio de 0 € nunca se niega. Si al guardar los datos Stripe no contesta, los datos se guardan igual y la revisión diaria aplica el tipo; si el lugar nuevo no se vende, la suscripción sigue con su tipo y la revisión diaria se pone en rojo para el equipo.
Implicados: hubs (los datos de quien paga)

### BILLING-F03 Decidir el IVA de cada cobro
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al poner precio (antes de cobrar) y al facturar (después), el mismo motor califica la venta: nacional, no sujeta (Canarias, Ceuta, Melilla, Reino Unido), inversión del sujeto pasivo o IVA del país del cliente (ventas a distancia por encima del umbral). Como hoy solo se vende en España (BILLING-F02), las dos últimas solo salen en lo que ya se cobraba a quien paga desde otro país.
2. Al facturar, reparte lo que Stripe cobró en base y cuota y sella en la factura el tipo nominal de la tabla (21 %, nunca un 21,01 % que salga de dividir céntimos).
3. Si Stripe no cobró impuesto en una venta sujeta, la factura saca el IVA de lo cobrado y deja una alarma para el equipo: el IVA nunca se deja de declarar.
Entra: país, código postal y NIF de quien paga, su comprobación de VIES a la fecha del cobro, la política fiscal y la tabla de tipos.
Sale: el tratamiento, el tipo, la base y la cuota, sellados en cada línea de la factura.
Si falla: si VIES no contesta y no hay ninguna comprobación anterior, la factura espera y Stripe vuelve a avisar: nunca se pone IVA español a una venta entre empresas de la UE porque VIES no respondía. Si las líneas no suman lo cobrado, la factura no se emite y queda la alarma.
Implicados: ninguno

### BILLING-F04 Mantener la tabla de tipos de IVA y no vender con ella rota
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
Estado: hecho
Actor: sistema, personal de ERPlora
Pantalla: Facturación › Datos de pago, Admin › Comprobaciones de IVA
Pasos:
1. Al escribir un NIF-IVA de otro país de la UE en los datos de facturación, y al cobrar, erplora.com pregunta a VIES identificándose con el NIF de ERPlora, así VIES devuelve el número de consulta, que es la prueba. Un NIF español no se consulta; uno británico no es de VIES. Como hoy solo se factura en España, la prueba solo quita el IVA en lo que ya se cobraba a una empresa de otro país de la UE.
2. Cada respuesta es una fila nueva que nunca se reescribe (comprobado, no válido, no disponible). Solo un «comprobado» vigente con número de consulta (o el forzado manual) permite facturar sin IVA.
3. El personal puede volver a preguntar con la acción «Comprobar ahora en VIES» de **Comprobaciones de IVA**, o dejar a mano un «comprobado» con su motivo, que guarda quién y cuándo.
4. Cada persona tiene 20 consultas por minuto y hay un tope global; una sola consulta a la vez por persona.
Entra: el NIF-IVA y el país.
Sale: el historial de comprobaciones (`billing.vat_check.completed`) y el número de consulta sellado en la factura.
Si falla: VIES sin contestar es «no disponible» y la venta lleva IVA; pasado el tope, «Demasiadas consultas: espera un minuto»; un número sin formato válido sale debajo del campo. El admin de comprobaciones solo se abre con la entrada del SaaS, que pide el código por correo y la app de autenticación.
Implicados: ninguno

### BILLING-F06 Seguir el umbral de ventas a distancia en la UE (OSS)
Estado: hecho
Actor: sistema, personal de ERPlora
Pantalla: Admin › Política fiscal, Admin › Avisos de la OSS
Pasos:
1. Cada factura a un particular de otro país de la UE suma su base al total del año (las rectificativas restan); el total facturado fuera de erplora.com se carga una vez a mano en **Política fiscal**. Como hoy solo se vende en España (BILLING-F02), el total solo crece con lo que ya se cobraba a particulares de otro país.
2. **Política fiscal** enseña el total del año contra el umbral (10.000 € por defecto) y los interruptores del alta en OSS y en el ROI.
3. Por encima del umbral (o con el alta voluntaria en OSS, o si el año anterior cerró por encima) las ventas nuevas a particulares de la UE llevan el IVA del país del cliente.
4. La venta cobrada que lleva el total del año por encima del 80 % del umbral manda un aviso al buzón del equipo para empezar ya el alta en la OSS, que tarda días; la que lo cruza (o la primera del año si el anterior cerró por encima) manda otro: desde ella esas ventas llevan el IVA del país del cliente. Cada aviso sale una sola vez al año y queda en **Admin › Avisos de la OSS**, de solo lectura.
5. La revisión diaria de las suscripciones vivas pasa a esos clientes al tipo de su país desde la siguiente factura (y de vuelta al español cuando el año vuelve a origen); lo que Stripe ya tiene no se le manda otra vez.
Entra: las facturas y la política.
Sale: el tipo de cada venta nueva y el de las suscripciones vivas, y los avisos al buzón del equipo.
Si falla: un negocio que Stripe no deja cambiar no para la revisión: se reintenta al día siguiente y el equipo lo ve en rojo. Un aviso que no pudo salir se reenvía en la revisión diaria, que sigue en rojo mientras quede alguno; anotar el aviso nunca para el cobro. Mientras el total del año no se ha cargado, el admin dice «desconocido» y con claves reales no se vende nada (es preferible no vender a cruzar el umbral sin verlo).
Implicados: ninguno

### BILLING-F07 Pagar el plan de un negocio recién creado
Estado: hecho
Actor: propietario
Pantalla: Resumen del negocio, Tienda, Pago seguro
Pasos:
1. El negocio nace siempre en Gratis (el alta solo pide nombre, país y tipo de negocio).
2. En el Resumen del negocio, la tarjeta Plan dice «Gratis» y ofrece «Mejorar plan» (en un plan de pago, «Cambiar plan»), que abre la Tienda con ese negocio elegido. Solo lo ve quien gestiona la facturación del negocio, y solo en la web: en las apps dice que se entre en erplora.com desde el navegador.
3. Elige el plan y el periodo y pulsa «Mejorar a …»: el pago sigue como en BILLING-F08.
Entra: el negocio recién creado y los planes que se ofrecen a ese negocio (los internos, solo si el personal de ERPlora lo marcó en el admin, BILLING-F27).
Sale: lo mismo que BILLING-F08.
Si falla: los mismos rechazos que BILLING-F08.
Implicados: hubs (el alta y la página del negocio)

### BILLING-F08 Pasar un negocio gratuito a un plan de pago
Estado: hecho
Actor: propietario
Pantalla: Tienda, Pago seguro
Pasos:
1. En **Tienda › Planes**, con el negocio elegido arriba, el propietario ve cada plan con su precio sin IVA y sus primeras características, como sus usuarios y sus dispositivos; «Ver todas las características» despliega el resto, entre ellas, cuando caen más allá de la quinta línea, las apps que puede tener activadas a la vez y el dominio propio. Elige «Mensual» o «Anual» (que dice cuánto se ahorra) y pulsa «Mejorar a …».
2. Se abre el pago seguro: los datos de facturación si faltan y después el formulario de tarjeta de Stripe dentro del diálogo, titulado «Mejorar a …» con «Para … · se renueva cada mes» (o cada año).
3. Mete la tarjeta; si el banco pide autenticación, la muestra Stripe en el mismo formulario.
4. Al terminar, «Pagando…» hasta que llega la página del negocio, que avisa «… ya está en …» y cuya tarjeta Plan cambia en cuanto Stripe lo confirma. El negocio sigue funcionando todo el tiempo.
Entra: el plan elegido (solo los que se ofrecen a ese negocio; los internos, solo a uno que el personal marcó), el periodo, los datos de facturación y el código promocional si lo hay.
Sale: el negocio en el plan nuevo, su suscripción y su cliente en Stripe, el plan nuevo enviado al negocio (`hubs.subscription.changed`) y la factura de ERPlora del primer cobro (BILLING-F25), llegue antes o después el aviso del pago.
Si falla: si el pago no se puede abrir, «No hemos podido abrir el pago seguro» y «No se ha cobrado nada» con «Reintentar»; un plan sin su precio de Stripe para el periodo elegido no se puede pulsar: debajo de su botón dice «Solo con pago mensual», «Solo con pago anual» o «No está a la venta ahora mismo», y pedido igualmente por la API se rechaza, «Esto no se puede comprar ahora mismo. Contacta con soporte.» (`billing.not_on_sale`); un plan que no se ofrece a ese negocio (uno interno sin la marca, aunque se pida por la API) se rechaza antes de abrir el pago, «No hay ningún plan con este identificador»; sin datos de facturación, el formulario; con una factura sin pagar, no se vende nada a ese negocio. Si la persona cierra el diálogo, no se cobra nada y el negocio sigue en Gratis.
Implicados: hubs (la suscripción del negocio), el negocio (recibe su plan)

### BILLING-F09 Volver del pago: confirmado, pendiente o cerrado
Estado: hecho
Actor: propietario
Pantalla: Pago seguro, Resumen del negocio
Pasos:
1. Al terminar el pago en el formulario de Stripe, el diálogo dice «Pagando…», cierra el formulario y abre la página del negocio; cuando esa página ha llegado, el diálogo se va y el aviso «… ya está en …» (o «… añadido a …: se enciende en unos segundos» para un módulo) sale en ella, con el negocio que se pagó, justo encima de su barra de secciones y sin taparla, aunque la página tarde en llegar.
2. El plan del negocio (o la aplicación comprada) cambia cuando Stripe confirma el cobro: si el medio de pago tarda en confirmarse, como un adeudo SEPA, el negocio sigue como estaba hasta entonces y cambia solo, sin recargar.
3. Si la persona cierra el diálogo antes de pagar, no se cobra nada y puede volver a abrirlo (BILLING-F10); el negocio sigue como estaba y no se borra nada.
Entra: el pago que Stripe da por terminado.
Sale: el mismo plan nuevo que deja el aviso de Stripe (BILLING-F19); la vuelta y el aviso nunca aplican dos veces el mismo pago.
Si falla: un pago que Stripe da por fallido después cierra ese intento sin cambiar el plan; un pago de otra cosa (un módulo) nunca cambia el plan. Un pago terminado por quien ya no es el propietario (el negocio se traspasó con el pago abierto, HUBS-F28) no se aplica: su suscripción se cancela, el cobro se devuelve entero (BILLING-F26 hace su rectificativa), el intento queda «Devuelto: ya no era el propietario» (`billing.checkout.refunded`) y le llega «Te hemos devuelto el pago de …» con el enlace a Facturación; si no se cobró nada, «Hemos cancelado tu plan de …». Una vez, aunque Stripe repita el aviso; si Stripe no responde, no se marca nada y Stripe lo vuelve a enviar.
Implicados: el negocio (recibe su plan)

### BILLING-F10 Reintentar un pago que no se terminó
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
Estado: hecho
Actor: propietario que paga
Pantalla: Tienda, Cambiar de plan
Pasos:
1. En **Tienda › Planes** de un negocio que ya paga, el propietario pulsa «Cambiar a …», «Cambiar a anual · …» o «Cambiar a mensual · …».
2. El diálogo calcula lo que se cobra hoy («Calculando lo que se cobra hoy…») y enseña «Hoy (prorrateado)», el IVA, el «Total hoy» y lo que se cobrará «Después», con la nota de que los módulos siguen igual.
3. Una subida se confirma con «Pagar … y cambiar»: se cobra ya con la tarjeta guardada y el negocio pasa al plan nuevo en el acto. Una bajada (un plan más barato, o de anual a mensual) no cobra nada hoy: pasa al plan nuevo al final del periodo pagado, y **Facturación › Suscripciones** dice «Cambia a … el …» y su próxima factura ya es la de ese plan. Hasta esa fecha se deshace con «Mantener el plan», en esa fila y en la tarjeta del plan actual de la Tienda (BILLING-F14).
4. Aviso: «… ya está en …» (o «…, con pago anual»); una bajada, que espera, avisa «… pasa a … el …» (o «… pasa a …, con pago mensual, el …»).
Entra: el plan y el periodo nuevos y la suscripción del negocio con su tarjeta; al cambiar de periodo, también cambia el precio de cada módulo.
Sale: el plan cambiado (`billing.plan.changed`) o la bajada programada (`billing.plan.change_scheduled`), con el IVA de la tabla en cada línea, y el plan nuevo enviado al negocio.
Si falla: «El precio estaba desactualizado: aquí lo tienes de nuevo, revísalo antes de confirmar» si pasó demasiado tiempo; la tarjeta rechazada no cambia nada; el mismo plan y periodo no es un cambio; bajar a Gratis es cancelar (BILLING-F13); con una cancelación pendiente, «Mantén antes el plan para cambiarlo»; con una factura sin pagar, «Antes, paga la factura pendiente»; un plan o un periodo sin su precio de Stripe no se puede pulsar, como en BILLING-F08; más de 400 € sin NIF pide el NIF.
Implicados: el negocio (recibe su plan), ASSISTANT-F25 (pedido al asistente del panel, que manda aquí)

### BILLING-F12 Dar días de prueba o un descuento con un código promocional
Estado: hecho
Actor: personal de ERPlora, propietario
Pantalla: Admin › Descuentos, Admin › Códigos promocionales, Pago seguro, Facturación › Suscripciones
Pasos:
1. Una persona de ERPlora crea un descuento en el admin: un porcentaje (de 1 a 100) o un importe en euros, uno de los dos; cuánto dura (el primer pago, unos meses, de 1 a 36, o para siempre); los planes a los que se aplica (ninguno = todos los de pago; nunca a una aplicación), si está activo y una nota. Debajo, sus códigos: el código, si está activo, hasta cuándo vale, cuántos usos y una nota. Un código también puede dar días de prueba (de 1 a 365) en lugar de un descuento.
2. El propietario, en el pago seguro de un negocio que aún no paga, pulsa «¿Tienes un código promocional?», lo escribe y pulsa «Aplicar». Con días de prueba: «Código …: n días gratis antes del primer cobro.». Con un descuento: «Código …: Gratis durante 6 meses.», «Código …: 20 % de descuento en el primer pago.» o «Código …: 10,00 € de descuento para siempre.».
3. Con días de prueba, paga: el primer cobro llega al acabar esos días.
4. Con un descuento, el pago seguro avisa, junto a la tarjeta, «Gratis durante 6 meses. Después, 29,99 €/mes + IVA. Hoy no se carga nada en tu tarjeta.» (sin «Después» si es para siempre, y sin la última frase si hoy se cobra algo); da su tarjeta y el plan empieza ya. Cada factura lleva su descuento en la línea del plan, también la de 0 €, numerada y registrada en VeriFactu como cualquier otra; al acabar el descuento se cobra el precio normal sin hacer nada.
5. Mientras dura, **Facturación › Suscripciones** dice «Gratis hasta el …» (o «10,00 € de descuento para siempre») y la próxima factura con el descuento. Subir de plan lo conserva; bajar de plan también, en la renovación; una aplicación se cobra entera. Si el negocio cambia de dueño y el nuevo mantiene el plan con su tarjeta, el descuento sigue: uno para siempre, igual; uno de unos meses, durante los meses enteros que le quedan (ninguno si le queda menos de uno); uno del primer pago, ya gastado, no vuelve.
Entra: el código (sin distinguir mayúsculas ni espacios).
Sale: los días de prueba en la suscripción, o el descuento en Stripe y cuándo acaba; el uso contado una vez por negocio y por quien paga.
Si falla: un código desconocido, inactivo, caducado o agotado (o cuyo descuento está apagado) dice «Este código no es válido o ya se ha usado» y no impide pagar sin él; probar códigos tiene un tope por persona; un código nunca pasa de su número de usos: el uso se reserva al abrir el pago seguro y se devuelve si ese pago no se completa. Si el código deja de valer entre comprobarlo y pagar, el pago no empieza y dice «Este código no es válido o ya se ha usado: quítalo para pagar sin él.». Un descuento de unos meses solo va con la facturación mensual: con la anual, el pago no empieza y dice «El descuento de este código dura unos meses: elige la facturación mensual para usarlo.»; un plan que el descuento no nombra dice «Este código no se aplica al plan elegido.»; en un cambio de plan, «Este código da un descuento a un negocio que empieza a pagar un plan, no a un cambio de plan.». Mientras dura uno de unos meses, pasar a anual dice «Este negocio tiene un descuento hasta el …: podrá pasar a la facturación anual después.» y no cambia nada. Cambiar a un plan que el descuento no cubre (no lo nombra, o se creó después del código) sí se puede: ese plan se cobra entero y Suscripciones ya no enseña el descuento. Cancelar siempre se puede, y el plan acaba al final del periodo. En el admin, usado un código, su descuento ya no cambia de condiciones, y ni el descuento ni el código se borran (se desactivan).
Implicados: el negocio de plataforma de ERPlora (emite las facturas con descuento, también las de 0 €, BILLING-F25)

### BILLING-F13 Cancelar el plan al final del periodo
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
Implicados: el negocio (recibe la fecha de fin), ASSISTANT-F25 (pedido desde el asistente del panel, su tarjeta enseña lo mismo que el diálogo)

### BILLING-F14 Deshacer una cancelación o una bajada pendiente
Estado: hecho
Actor: propietario que paga
Pantalla: Facturación › Suscripciones, Tienda
Pasos:
1. En la fila de un negocio con el plan cancelado o con una bajada programada («Cambia a … el …»), el propietario pulsa «Mantener el plan». En la Tienda, la tarjeta del plan actual dice «Cancelado: … hasta el … y después Gratis» o «Bajada programada: … hasta el … y después …», con «Mantener el plan»; la tarjeta del plan al que se baja dice «El negocio pasa a … el …», sin botón.
2. Aviso: «… sigue en …» o «… se mantiene: se renovará el …». La fila vuelve a tener próxima factura.
Entra: la suscripción con su final marcado o con su bajada programada.
Sale: la suscripción vuelve a renovarse en Stripe, con el estado que diga Stripe (`billing.plan.kept`); una bajada programada se deshace y la fila deja de decir «Cambia a … el …».
Si falla: con una factura sin pagar, un plan cancelado no se mantiene: primero se paga (no se recupera un plan sin pagarlo). Una bajada programada sí se deshace con una factura sin pagar: no cobra nada ni devuelve un plan que se haya perdido. Mantener un plan que no estaba cancelado ni tenía una bajada no cambia nada.
Implicados: ninguno

### BILLING-F15 Terminar la suscripción: el negocio vuelve a Gratis
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
Estado: hecho
Actor: sistema, propietario, cuenta que paga
Pantalla: Avisos de la campana, el propio negocio
Pasos:
1. Falla el cobro de una renovación. Stripe lo reintenta durante unos días y avisa de cada fallo. Las aplicaciones de pago van en la misma factura que el plan: su impago es el del negocio entero, y al pagar vuelve todo.
2. erplora.com relee la suscripción en Stripe: si el reintento ya cobró, no hace nada; si no, apunta la factura como «No cobrada», con por qué no se cobró (tarjeta rechazada, autenticación o fallo).
3. **Gracia**: durante 7 días desde la factura que falló, el negocio sigue funcionando con todo su plan. La cuenta que paga recibe un correo, una vez por factura: cuánto no se pudo cobrar, hasta qué día sigue funcionando y el enlace a Facturación para pagarla (si el banco rechazó la tarjeta, que la cambie antes). En la barra superior del panel, la campana se vuelve roja y llega el aviso «… tiene una factura sin pagar»: el importe, «quedan … días» y «Si no se paga antes del …, el negocio se suspende. No se borra nada.», con «Pagar la factura · …» y «Cambiar tarjeta» (solo «Cambiar tarjeta» si el banco la rechazó). Es un solo aviso por negocio, el mismo en todas las pantallas.
4. **Suspensión**: pasados los 7 días, o si Stripe agota sus reintentos, el negocio se suspende y la cuenta que paga recibe otro correo, una sola vez. El negocio no se abre: ni desde el panel ni desde su propia dirección, tampoco en los dispositivos que ya tenían la sesión abierta, que enseñan «Este negocio está suspendido» con el camino a ERPlora. El aviso de la campana dice «suspendido» y «Se suspendió por una factura sin pagar. No se borra nada: en cuanto se pague vuelve a funcionar.»
5. **Red de seguridad**: cada hora se repasan los negocios con el plan en impago y se mira su factura abierta más antigua, por si Stripe dejó de reintentar sin volver a avisar.
6. **Vuelta**: al pagar la factura (con «Pagar la factura», o porque un reintento la cobra), el negocio vuelve a estar activo en el acto: «Factura pagada: … vuelve a estar al día», y su aviso se va de la campana.
Entra: los avisos de Stripe del cobro fallido y de la suscripción, y la suscripción viva.
Sale: la factura «No cobrada», los correos a quien paga y el estado del negocio (pago pendiente, suspendido o al día) enviados al negocio (`hubs.subscription.changed`).
Si falla: si Stripe no contesta al releer la suscripción, no se aplica nada y Stripe vuelve a avisar. Un aviso repetido de una factura ya pagada no la reabre. Un fallo posterior del mismo impago no mueve la fecha de la gracia ni repite el correo. Un correo que no pudo salir se vuelve a mandar en el repaso de cada hora, que avisa al equipo mientras quede alguno.
Implicados: hubs (el estado del negocio), el negocio (recibe el estado)

### BILLING-F17 Reactivar un negocio suspendido pagando su factura
Estado: hecho
Actor: cuenta que paga
Pantalla: Avisos de la campana, Facturación › Facturas
Pasos:
1. En el aviso del negocio suspendido, en la campana de la barra superior, la cuenta que paga pulsa «Pagar la factura · …» (si el banco rechazó la tarjeta, antes «Cambiar tarjeta»); también puede pagarla desde la factura, en **Facturación › Facturas**.
2. Se abre la página de pago de Stripe de esa factura; paga.
3. Al volver, «Factura pagada: … vuelve a estar al día» y el negocio funciona otra vez con sus datos y su plan, sin abrir otra suscripción.
Entra: la factura sin pagar y su página de pago en Stripe.
Sale: la factura pagada y numerada (BILLING-F25), el negocio activo y su estado enviado al negocio.
Si falla: «Pagando…» bloquea un segundo clic; solo la cuenta que paga el negocio puede pagar su factura («Solo la cuenta que paga este negocio puede pagar sus facturas»); una factura ya pagada o anulada no se paga otra vez. Un negocio cuyo plan ya terminó está en Gratis y vuelve a un plan de pago desde la Tienda (BILLING-F08).
Implicados: hubs (el estado del negocio), el negocio (vuelve a abrirse)

### BILLING-F18 Ver, cancelar o mantener el plan del negocio por la API
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
Estado: hecho
Actor: propietario, cuenta que paga
Pantalla: Facturación › Facturas
Pasos:
1. **Facturación** se abre en **Facturas**, con las facturas de ERPlora de todos los negocios de la cuenta: Factura, Fecha, Negocio, Importe y Estado, de la más nueva a la más antigua. Lo pagado por una aplicación es una línea de la factura de su negocio.
2. Filtra por negocio, estado («Pagadas», «No cobradas») y año, o busca por número; los filtros se guardan en la dirección.
3. Pulsa «Descargar PDF» en una fila (o selecciona varias y «Descargar PDF (n)», el icono de descarga con el número de las que tienen PDF), o «Descargar Excel» para la lista de lo filtrado, lista para la gestoría.
4. Una rectificativa dice «Rectificativa R1 · motivo» y la factura que rectifica.
5. «Ver la factura» abre su página (BILLING-F36).
6. Una integración de la cuenta, con una clave de lectura de Facturación, lee la misma lista con los mismos filtros, cada factura con su negocio, sus líneas, su IVA y a quién va, su PDF y la hoja de cálculo.
Entra: las facturas que pagó la cuenta y las de los negocios de los que es propietaria.
Sale: el PDF de la factura emitida, que hace en cada descarga el negocio de plataforma de ERPlora con su QR de VeriFactu (BILLING-F25), y la hoja de cálculo de lo filtrado.
Si falla: una factura que aún se emite dice «Emitiéndose» y no ofrece PDF; si el servicio de facturas no responde, «El servicio de facturas no responde. Prueba de nuevo en un momento»; si en «Descargar PDF (n)» unas fallan y otras aún se emiten, un solo aviso dice las dos cosas (una descarga, un aviso); sin facturas, «Aún no hay facturas». Una factura de otra cuenta no se encuentra.
Implicados: ninguno

### BILLING-F23 Ver las suscripciones de cada negocio
Estado: hecho
Actor: propietario, cuenta que paga
Pantalla: Facturación › Suscripciones
Pasos:
1. En **Facturación › Suscripciones** hay una fila por negocio que paga: el plan y sus aplicaciones de pago a precio sin IVA (una cancelada dice «(hasta el …)» y deja de salir cuando termina), la próxima factura con IVA (con una bajada programada, la del plan y el periodo nuevos, con sus aplicaciones al precio de ese periodo; al mantener el plan, vuelve a la del actual) y el estado. Un negocio eliminado sale «En eliminación», como su página, sin próxima factura ni nada que cambiar, hasta que la pasada siguiente termina su suscripción en Stripe; después deja de salir.
2. Cada fila lleva sus acciones: la principal a la vista («Ver la factura» si hay una sin cobrar; si no, «Mantenerlo con mi tarjeta», «Cambiar plan» o «Mantener el plan») y en «⋮» «Ver facturas» y «Cancelar plan».
Entra: las suscripciones de los negocios que paga la cuenta o de los que es propietaria.
Sale: nada.
Si falla: sin negocios de pago, «Todos tus negocios están en Gratis» con «Ver planes»; sin los datos de quien paga, la próxima factura no puede calcular su IVA y se dice. Un propietario cuyo plan cobra la tarjeta de otra cuenta (la del propietario anterior tras un traspaso) ve «Se paga con la tarjeta de otra cuenta»: no lo cambia ni lo cancela, lo mantiene con su tarjeta (HUBS-F28).
Implicados: hubs (HUBS-F28: el plan de un negocio traspasado; HUBS-F18: un negocio eliminado)

### BILLING-F24 Abrir el portal de pagos de Stripe para cambiar la tarjeta
Estado: hecho
Actor: cuenta que paga
Pantalla: Facturación › Datos de pago, Avisos de la campana
Pasos:
1. En **Facturación › Datos de pago**, la tarjeta «Método de pago» dice qué tarjeta paga qué negocios y, si el último cobro falló, cuándo y de qué negocio.
2. Pulsa el icono «Cambiar tarjeta» (o «Cambiar tarjeta» en el aviso de la campana de un negocio con la factura sin pagar): se abre la página segura de Stripe de esa cuenta, que solo permite cambiar la tarjeta y ver los recibos.
3. Al volver, el panel vuelve a Facturación y, si había una factura rechazada, su aviso de la campana dice «Tarjeta cambiada: ya puedes pagarla.» y «Pagar la factura · …» vuelve.
Entra: la cuenta que paga el negocio.
Sale: la tarjeta nueva en Stripe; los cambios de plan nunca se hacen allí.
Si falla: antes del primer pago no hay nada que cambiar; si Stripe no contesta, se dice; solo la cuenta que paga lo abre, nunca otro propietario.
Implicados: ninguno

### BILLING-F25 Emitir la factura de ERPlora por un cobro
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Stripe avisa de un cobro pagado (alta, renovación, cambio de plan o módulo).
2. erplora.com califica la venta (BILLING-F03), le pone número de su serie (ERP-año-número, correlativo sin huecos) y la fecha del día, y copia los datos de quien paga ese día.
3. La manda al negocio de plataforma de ERPlora, que la registra con VeriFactu y devuelve su estado y su QR; cuando la emite, quien paga recibe un correo con el PDF de la factura adjunto, sin enlaces: «La factura va adjunta. También la tienes en tu panel, en Facturación.».
Entra: el cobro de Stripe con sus líneas y los datos de quien paga.
Sale: la factura y sus líneas (`billing.invoice.recorded`), su estado fiscal y el correo con su PDF.
Si falla: si el negocio de plataforma no responde, la factura queda «emitiéndose» y se reintenta (a los 15 minutos, después el doble cada vez, como mucho 6 horas); si lo rechaza, se guarda el motivo y se reintenta. Si aún no entrega el PDF, el correo no sale sin él: se vuelve a mandar en la pasada siguiente. Una renovación sin cobrar se lista «No cobrada», sin número, y se numera al pagarla. Un cobro de 0 € de una prueba no hace factura; el de un descuento de un código sí (BILLING-F12), con el descuento en cada línea. El mismo cobro avisado varias veces hace una sola. Con claves reales, sin ruta de emisión no se cobra.
Implicados: el negocio de plataforma de ERPlora (emite la factura)

### BILLING-F26 Devolver un cobro
Estado: hecho
Actor: personal de ERPlora
Pantalla: ninguna
Pasos:
1. El personal de ERPlora devuelve un cobro (entero o en parte) o emite una nota de crédito en el panel de Stripe.
2. Stripe avisa a erplora.com, que emite una factura rectificativa con importes negativos, la calificación y el destinatario de la original, su tipo (R1 para devoluciones y cambios de precio, R4 para lo demás) y su motivo.
3. La rectificativa sale en **Facturación › Facturas** con «Rectificativa R1 · motivo» y la factura que rectifica.
Entra: el aviso de la devolución o de la nota de crédito.
Sale: la rectificativa de su serie propia (ERPR-año-número), emitida como cualquier factura (`billing.credit_note.recorded`), y su correo con el PDF adjunto: «La factura rectificativa va adjunta. También la tienes en tu panel, en Facturación.».
Si falla: una devolución de una factura que aún no existe espera y Stripe vuelve a avisar; la misma devolución nunca rectifica dos veces. Una nota de crédito anulada en Stripe (solo se puede mientras su factura no está cobrada) nunca se vuelve rectificativa, aunque su aviso llegue después; y si ya lo era, la rectificativa no se toca —una factura enviada a la AEAT no se modifica— y soporte recibe un correo para emitir a mano la factura que la anula.
Implicados: el negocio de plataforma de ERPlora (emite la rectificativa)

### BILLING-F27 Lo que el personal de ERPlora puede hacer sobre el cobro de un cliente
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin
Pasos:
1. Una persona de ERPlora entra en el admin con la cuenta del SaaS (código por correo y app de autenticación).
2. Ve, solo para leer, las suscripciones y sus líneas, los avisos de Stripe, los intentos de pago, los códigos promocionales usados, los contadores de cada serie de facturas y los cambios de plan que esperan al final del periodo: lo que dice Stripe no se edita aquí, se cambia en Stripe y llega por su aviso.
3. En los negocios puede «Enviar el último estado al negocio» y «Reintentar lo que el negocio aún debe» y, solo un superusuario, «Dejar a su propietario comprar los planes internos» y «Dejar de venderle los planes internos»: con la marca, el propietario de ese negocio ve «Prueba de pago (interno)» (1 € + IVA) en la Tienda y lo compra como cualquier plan, también en producción, para hacer una compra real y ver su factura con el QR; la columna «planes internos» de la lista dice qué negocios la tienen. En las facturas, con sus líneas, «Reenviar al negocio de plataforma», «Reenviar el correo de la factura», «Descargar el PDF» de cualquier factura ya emitida y, eligiendo varias en la lista, «Descargar los PDF (ZIP)»; desde la lista, el «Informe de facturación» de un mes, un trimestre o un año (BILLING-F40). En **Clientes de pago**, qué negocios pagan, con qué plan, desde cuándo y cuánto, con su Excel (BILLING-F41).
4. Mantiene los códigos promocionales, la tabla de IVA, la política fiscal y los datos de ERPlora (nacen con los del Modelo 036 y son los que VIES ve de quien pregunta); las devoluciones y las cancelaciones al momento se hacen en el panel de Stripe.
5. Una aplicación de pago que algún negocio tiene no se borra del catálogo: el admin dice qué negocio la tiene y que se quite de la venta.
Entra: la cuenta del personal con su papel.
Sale: lo que hacen sus acciones; nada de lo que es de Stripe cambia desde el admin. Quitar la marca no cancela un plan interno ya comprado: el negocio lo sigue viendo como su plan y deja de poder comprarlo.
Si falla: sin el papel, el admin no se abre; el grupo de soporte solo mira, no lanza acciones. El PDF de una factura que aún no se ha emitido no existe: el admin lo dice («Aún no se ha emitido»), y si el negocio de plataforma no responde, vuelve a la factura diciendo por qué. En el ZIP, las facturas sin PDF (aún emitiéndose o que el negocio de plataforma no devuelve) quedan fuera con su motivo, en un aviso del admin y en `not-included.txt` dentro del ZIP; si ninguna tiene PDF, no se descarga nada y el aviso lo dice.
Implicados: hubs (el estado de los negocios)

### BILLING-F28 Mantener en Stripe los precios de los planes
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
Si falla: un precio que no cuadra no se guarda y dice por qué debajo de su campo («Este precio no está en euros», «Stripe cobra … y el plan dice …», «Este precio incluye el IVA o no lo dice…», un precio de pruebas en producción no se encuentra…). Si Stripe no contesta, no se guarda y se pide repetir; sin claves de Stripe (en desarrollo) se guarda y el admin avisa de que no se comprobó. Un plan sin su precio de Stripe para un periodo no se vende con ese periodo: en la Tienda su botón está desactivado y dice por qué (BILLING-F08).
Implicados: hubs (el admin de los planes)

### BILLING-F29 Probar el cobro real en PRE con un reloj de prueba de Stripe
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
Estado: hecho
Actor: propietario
Pantalla: Tienda
Pasos:
1. En **Tienda › Módulos**, con el negocio elegido arriba, el propietario ve cada aplicación de pago con su icono, su nombre, su resumen y su precio sin IVA al periodo del negocio («… /mes + IVA» o «… /año + IVA»), en su idioma.
2. Cada tarjeta dice lo que la aplicación es en ese negocio: «Añadir · …» (el «+» con el precio) si no la tiene; «Ya lo tienes» con «Cancelar el módulo» si la paga; «Incluido en tu plan» si viene con el plan; «Ya lo tienes hasta el … (cancelado)» con «Mantener · sin cobro hoy» si está cancelada; «Activando… en …» justo después de comprarla.
3. Una aplicación que ERPlora ya no vende sigue saliendo al negocio que la paga, con «Ya no se vende: lo conservas mientras lo pagues y puedes cancelarlo cuando quieras»; a los demás negocios no se les ofrece.
Entra: el negocio elegido (solo los de los que esa persona es propietaria), el catálogo de aplicaciones y la suscripción del negocio.
Sale: nada.
Si falla: «No hemos podido cargar los precios» con «Reintentar»; sin aplicaciones a la venta, «Ahora mismo no hay módulos a la venta»; con una factura sin pagar, lo que cobra se desactiva con «Antes, paga la factura pendiente»; con pago anual, una aplicación que solo se vende al mes dice «Solo con pago mensual». En la app no se vende: se dice que se entre en erplora.com desde el navegador.
Implicados: apps (el nombre, el resumen y el icono de cada aplicación)

### BILLING-F32 Contratar una aplicación de pago para un negocio
Estado: hecho
Actor: propietario
Pantalla: Tienda, Cambiar de plan, Pago seguro
Pasos:
1. En **Tienda › Módulos**, con el negocio elegido arriba, el propietario pulsa «Añadir · …» (el «+» con el precio) en la aplicación.
2. Si el negocio ya paga, el diálogo «Añadir …» dice «Se suma a la suscripción de …» y lo que se cobra: «Hoy (prorrateado)», el IVA, el «Total hoy» y lo que se cobrará «Desde el …»; confirma con «Pagar … y añadir», que cobra con la tarjeta guardada.
3. Si el negocio está en Gratis, se abre el pago seguro con la aplicación sola, como en BILLING-F08; una aplicación no tiene días de prueba.
4. Aviso «… añadido a …: se enciende en unos segundos»; la tarjeta dice «Activando… en …» y después «Ya lo tienes». La aplicación va en la misma factura mensual (o anual) que el plan.
Entra: el negocio, la aplicación (solo una que está a la venta y que el negocio no tiene) y el periodo del negocio.
Sale: la aplicación en la suscripción del negocio (`billing.module.added`), su factura (BILLING-F25), cuyo correo es la confirmación de la compra, y la aplicación enviada al negocio.
Si falla: una aplicación que el negocio ya tiene no se vende dos veces; una retirada o desconocida no se vende; una gratuita no se compra, viene con cualquier negocio; con una factura sin pagar, «Antes, paga la factura pendiente»; si pasó demasiado tiempo, «El precio estaba desactualizado: aquí lo tienes de nuevo, revísalo antes de confirmar»; la tarjeta rechazada no añade nada. Con un medio de pago que tarda (adeudo SEPA), la aplicación llega cuando Stripe confirma el cobro (BILLING-F09).
Implicados: hubs (la suscripción del negocio), el negocio (recibe la aplicación)

### BILLING-F33 Cancelar una aplicación de pago
Estado: hecho
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
Estado: hecho
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
Estado: hecho
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
Estado: hecho
Actor: propietario, cuenta que paga
Pantalla: Factura
Pasos:
1. En **Facturación › Facturas**, la persona pulsa «Ver la factura» en una fila.
2. La página dice su número (o «Factura … (no cobrada)»), la fecha, el negocio, el cobro y su estado en VeriFactu; «Lo que se cobra», una línea por concepto con su periodo, «Prorrateado» si lo es, su base y su IVA, y su «Descuento» si un código lo rebajó; la base imponible, el IVA y el total; y «A nombre de», con los datos de quien paga tal como estaban ese día.
3. Desde ella descarga el PDF de una factura emitida, paga una no cobrada o, en una rectificativa, abre la factura que rectifica. Mientras se emite, la página pasa sola a su número y su QR.
4. La flecha de arriba vuelve a Facturas.
Entra: una factura de la cuenta.
Sale: nada.
Si falla: una factura de otra cuenta no se encuentra; si no carga, «No hemos podido cargar esta factura» con «Reintentar»; una que aún se emite dice que su PDF estará cuando termine. En la app se ve, pero no se paga.
Implicados: ninguno

### BILLING-F37 Olvidar los avisos de Stripe de más de 30 días
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

### BILLING-F39 Comprobar cada día que Stripe avisa de todo lo que erplora.com trata
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada día, erplora.com lee en Stripe los destinos de sus avisos.
2. Comprueba que uno activo apunta a su dirección de avisos (`/webhooks/stripe/`) y que manda exactamente los avisos que erplora.com trata (BILLING-F19), ni uno menos ni uno más.
3. Si todo cuadra, lo anota y termina; si no, termina con error, que avisa al equipo, diciendo qué falta y qué sobra.
Entra: los destinos de avisos de la cuenta de Stripe.
Sale: nada que cambie: lo que se vio y, si algo no cuadra, el aviso al equipo.
Si falla: ningún destino activo hacia la dirección, uno que apunta a una ruta que erplora.com no sirve o a otro entorno, más de uno hacia la dirección, o uno que manda todos los avisos (`*`) o le falta o le sobra alguno, termina con error y lo nombra. Si Stripe no contesta, también. Sin clave de Stripe (en desarrollo) no hay nada que comprobar: lo dice y termina bien.
Implicados: ninguno

### BILLING-F40 Sacar el informe de facturación de un periodo para la gestoría
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin › Facturas › Informe de facturación
Pasos:
1. En el admin, en la lista de **Facturas**, pulsa «Informe de facturación».
2. Se abre en el trimestre en curso; elige el año y el periodo (el año completo, un trimestre o un mes) y pulsa «Ver».
3. Lee los totales del periodo: base imponible, IVA y total de las facturas (serie ERP), de las rectificativas (serie ERPR, en negativo) y el neto de las dos.
4. Debajo, el desglose por tratamiento del IVA, país del cliente y tipo de IVA, sacado de las líneas tal como llegaron a VeriFactu (lo nacional va al modelo 303, la inversión del sujeto pasivo al 349 y la ventanilla única, OSS, al 369), y el desglose por tipo de cliente: empresa (NIF español de una sociedad o un NIF de fuera de España), autónomo o particular con NIF español, y particular sin NIF.
5. Pulsa «Descargar Excel»: una fila por factura del periodo con su número, fecha, negocio, pagador, NIF, país, tratamiento del IVA, % de IVA, base, IVA, total, moneda, cobro y estado, en el formato del Excel del panel (BILLING-F22).
Entra: el año y el periodo.
Sale: los totales en pantalla y la hoja de cálculo para la gestoría; nada cambia.
Si falla: solo cuentan las facturas cobradas y ya emitidas por el negocio de plataforma, por su fecha de expedición; las cobradas del periodo que aún se emiten o que el negocio de plataforma rechazó no suman, y un aviso las nombra («Cobradas en este periodo pero aún sin emitir, así que no se cuentan: …»). Un periodo que no existe dice el error junto al campo, y su Excel vuelve al informe. Sin facturas en el periodo, los totales salen a cero y el desglose dice «No se facturó nada en este periodo». Quien no puede ver las facturas en el admin no lo abre.
Implicados: ninguno

### BILLING-F41 Ver qué clientes pagan, con qué plan, desde cuándo y cuánto
Estado: hecho
Actor: personal de ERPlora
Pantalla: Admin › Facturación › Clientes de pago
Pasos:
1. En el admin, abre **Facturación › Clientes de pago**: una fila por negocio que Stripe cobra hoy (también si está en prueba, con un cobro pendiente o en pausa), por orden de negocio.
2. Cada fila dice el negocio, quién lo paga (el nombre fiscal de su pagador), su país, el tipo de cliente (empresa, autónomo o particular con NIF español, o particular sin NIF, como en el informe de facturación, BILLING-F40), el plan, si paga al mes o al año, el importe mensual sin IVA, desde cuándo es cliente y el estado de su suscripción.
3. El importe mensual es la base de su última factura cobrada por un periodo entero, con sus aplicaciones de pago y sin los prorrateos de un cambio a mitad de periodo; la de un pago anual, entre 12. «Cliente desde» es la fecha de su primera factura cobrada.
4. Filtra por plan, estado o país (cada filtro ofrece solo lo que tiene algún cliente de pago) o busca por negocio, pagador o NIF.
5. Pulsa «Descargar Excel»: una fila por cliente de lo que enseña la lista (con sus filtros y su búsqueda) y las mismas columnas, en el formato del Excel del informe de facturación (BILLING-F40).
Entra: los filtros y la búsqueda.
Sale: la lista en pantalla y la hoja de cálculo; nada cambia.
Si falla: un negocio sin ninguna factura cobrada todavía (en prueba con un código promocional) sale con el importe y «cliente desde» vacíos («-»). Una suscripción que terminó (cancelada, o caducada sin llegar a pagarse) ya no es un cliente de pago y no sale. Sin clientes de pago, la lista dice «0 clientes de pago». Quien no puede ver las suscripciones en el admin no la ve ni la descarga.
Implicados: hubs (las suscripciones y los pagadores de los negocios)

## Para quien lo mantiene

- Anatomía y operaciones: `billing/README.md` (IVA, Stripe, facturas, impago y la Tienda).
- Sin colas de tareas: lo periódico son tareas programadas o pasadas del `saas-worker`, y el correo de la factura
  sale tras el COMMIT.
- Las aplicaciones de pago (BILLING-F31 a BILLING-F35) están hechas y probadas con los dobles de Stripe y del Hub
  (`billing/tests/test_module_end_reaches_the_hub.py`; en el Hub, `base/tests/test_entitlement.py`), pero hoy no se
  usan: todos los módulos van en todos los planes y ninguno es `premium`, así que no hay fila `Module` a la venta. Vuelven a usarse en cuanto la haya.
- Los tests de cada flujo citan su clave en el nombre o en el docstring; los e2e, en el título o en
  `// flow: …`. Los e2e `tests/e2e/panel/billing-flows.spec.ts`, `billing-apps.spec.ts` y `billing-support.spec.ts`
  (y, en el Hub, `tests/e2e/hub-suspended.spec.ts`) citan la clave `BILLING-Gnn` y llevan en su cabecera la
  equivalencia con la de este WORKBOOK.
- BILLING-F25, el reintento de la factura de ERPlora (`reconcile_platform_invoices`), corre cada 15 minutos (:00, :15,
  :30, :45 UTC) dentro del proceso `saas-worker` (`manage.py run_worker`, `base/worker.py`); la pasada es `services.platform_invoices.reconcile_platform_invoices_exclusively`, la misma del comando, que queda para
  lanzarla a mano. Lo que deja pendiente escribe la línea ERROR `saas.worker.pass_failed task=reconcile_platform_invoices
  left work owed: …`, que es lo que avisa la alarma. En el worker la pasada
  tiene 50 s y oye la parada entre dos facturas (`go_on`): lo que no entra va en la pasada siguiente (`cut_short=1`).
- Tareas programadas (ECS, `saas-cron`): `manage.py audit_tax_rules` (BILLING-F04),
  `manage.py retax_subscriptions` (BILLING-F02, BILLING-F06) y `manage.py sync_subscriptions` (BILLING-F38;
  `--dry-run` solo informa) salen con error si dejan algo por hacer, que es lo que la alarma `task_failed`
  avisa al equipo; `manage.py purge_webhook_events` (BILLING-F37) solo borra. Las programa el repo de
  infraestructura (`stacks/prod/scheduler.tf` de `ERPlora/aws`): `sync_subscriptions` cada noche a las 00:10 UTC
  (antes de la foto de las 00:30 y de la re-tarificación), `purge_webhook_events` a las 00:50 UTC,
  `audit_tax_rules` cada día a las 05:10 UTC, `retax_subscriptions` a las 05:20 UTC y `audit_stripe_webhooks`
  (BILLING-F39) a las 05:40 UTC (`audit-stripe-webhooks-daily`). Solo cuenta un endpoint activo: la cuenta de Stripe
  tiene otros tres en `erplora.com`, `disabled` y sin borrar (`we_1UIyXWG5mOoM2dqitS8TFImp` a
  `/marketplace/webhooks/stripe/`, `we_1UIyXVG5mOoM2dqidg2Ai6WD` a `/dashboard/billing/webhooks/stripe-connect/` y
  `we_1UIyXUG5mOoM2dqiftLTSFdL` a `/assistant/stripe/webhook/`); si uno de esos tres volviera a activarse,
  `endpoint_problems` lo contaría y la tarea saldría con error, que `task_failed` avisa. Los avisos que trata el webhook son una
  sola lista, `billing.services.webhook_dispatch.STRIPE_WEBHOOK_EVENTS`, que el comando compara con el destino de Stripe.
- Las facturas de ERPlora las emite el Hub, pero en producción no se cobra con clave live mientras
  `PLATFORM_INVOICING_ENABLED` siga en `false` (reglas de trabajo §15: la transmisión real queda bajo la supervisión de
  Ioan). La compra suelta de BILLING-F32 choca con `PLAN.md` (nuestros módulos no se venden sueltos): la contradicción
  está señalada en los planes.

## Lo que NO hace, a propósito

- No vende en las apps ni desde la cuenta abierta en la app (reglas de las tiendas de apps).
- No usa Stripe Tax ni deja que Stripe recoja el NIF: el IVA y el NIF son de erplora.com.
- No cobra una cuota por conservar un negocio que ya no paga: vuelve a Gratis.
- No tiene un estado «pendiente de pago» en el alta: el negocio nace en Gratis.
- No sincroniza solo los productos de Stripe: sus identificadores se pegan en el admin.
- No cambia el plan desde el portal de Stripe: allí solo se cambia la tarjeta y se ven los recibos.
- No traspasa una aplicación contratada de un negocio a otro: se cancela en uno y se contrata en el otro
  (BILLING-F35).
- No vende aplicaciones sueltas fuera de la suscripción del negocio: no hay compras aparte; lo pagado por
  una aplicación es una línea de la factura de su negocio.
- No hace facturas a mano desde el admin: cada factura sale de un cobro de Stripe.
- No presenta los modelos 303, 349 ni 369: el informe de facturación (BILLING-F40) da sus totales a la gestoría.
- No cobra por uso ni por excesos (sin medidores ni plan «Flex»): quien necesita más sube de plan.
- No pide ni guarda una moneda: ERPlora cobra siempre en euros.
- No manda un correo aparte por cada compra ni al «vendedor» de una aplicación: todas son de ERPlora, y la
  confirmación de una compra es el correo de su factura (BILLING-F25).
