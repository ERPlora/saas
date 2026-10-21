# Workbook — Cuentas (accounts)
Prefijo: ACCOUNTS
Alcance MVP: fase 1 (la cuenta de erplora.com: crearla, entrar y salir, su contraseña y lo que acepta)
Estado de la app: en construcción (partes 1 a 3 de 5: crear la cuenta, entrar, la contraseña, salir, los términos y el freno; la verificación en dos pasos, los navegadores de confianza y las sesiones abiertas; el perfil, las preferencias, los avisos, el menú de usuario, descargar los datos y eliminar la cuenta)

> Manual de uso y especificación de la app `accounts` del SaaS (erplora.com). Cuenta cómo se crea una
> cuenta, cómo se confirma el correo, cómo se entra y se sale, cómo se recupera y se cambia la contraseña,
> qué se acepta al continuar, cómo se frena a quien prueba contraseñas, cómo se pide la app autenticadora
> después de la contraseña, en qué navegadores se confía, cómo se ven y se cierran las sesiones abiertas, cómo
> se cambian el perfil, el idioma, el tema y los avisos por correo, y cómo se descargan los datos y se elimina la
> cuenta. Esta parte del manual no se publica en la tienda: es la referencia del equipo y de la QA. El salto a un
> negocio y las llaves de API se escriben en las partes 4 y 5.

## Para qué sirve y para quién

Una cuenta de erplora.com es la persona que entra: con ella se crean y se usan los negocios, se paga a
ERPlora y se entra en cada negocio desde la pantalla de entrada. Se entra con el correo y una contraseña
(más un código que llega al correo) o con Google, y la cuenta guarda qué términos aceptó y cuándo.

- Una cuenta por correo: una dirección que se parece a otra (con otras mayúsculas o con letras de ancho
  completo) es la misma cuenta, nunca una segunda.
- Nadie usa el panel con un correo sin confirmar: el código que llega al correo lo prueba.
- La pantalla de entrada nunca dice qué correos tienen cuenta: un correo desconocido responde como una
  contraseña equivocada, y un alta con un correo ya registrado responde como una nueva.

Quién la usa:

- **Cualquiera** crea su cuenta, entra y sale, y recupera su contraseña.
- **La persona con cuenta** cambia su contraseña, activa la app autenticadora y ve y cierra sus sesiones
  desde **Cuenta › Seguridad**; cambia su perfil, descarga sus datos y elimina su cuenta desde **Cuenta ›
  Perfil**, y elige su idioma, su tema y sus avisos desde **Cuenta › Preferencias** (el tema, también desde el
  **Menú de usuario**).
- El **personal de ERPlora** ve y gestiona las cuentas desde el admin, sin poder cambiar lo que una cuenta
  aceptó; ante un incidente cierra todas las sesiones de una cuenta y, con la verificación en dos pasos
  encendida, solo entra en el admin con su app autenticadora.

## Referencia adoptada

- **Shopify, Square y Stripe**: una sola pantalla de entrada con «Entrar» y «Crear cuenta», un correo y
  una contraseña con el ojo para verla (sin repetirla), y un código de un solo uso al correo para
  confirmarlo (https://help.shopify.com/en/manual/your-account/account-security).
- **Google y Microsoft**: el código por correo como segundo paso de cada entrada con contraseña, y una
  contraseña nueva nunca es la actual.
- **OWASP (Authentication y Forgot Password Cheat Sheets)**: la misma respuesta exista o no la cuenta, un
  enlace de restablecer que caduca y sirve una vez, y un freno por cuenta y por dirección de red que no
  deja fuera al dueño con la contraseña buena
  (https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).
- **Stripe (`tos_acceptance`)**: la aceptación de los términos se guarda con su fecha y la versión
  aceptada, y continuar tras un cambio acepta la nueva.
- **Odoo y Shopify**: cerrar la sesión solo cierra la de ese navegador; cambiar la contraseña cierra las
  demás.
- **Google y GitHub**: la app autenticadora se activa escaneando un código QR (o escribiendo su clave) y deja
  códigos de recuperación que se enseñan una vez y se descargan; generar otros invalida los anteriores.
- **Google («No volver a preguntar en este ordenador», «Revocar todos») y Microsoft**: confiar en un
  navegador se ofrece sin marcar junto al código, vale solo en ese navegador y se deja de confiar en todos
  de una vez.
- **Google («Tus dispositivos») y GitHub («Sessions»)**: la lista de las sesiones abiertas con el
  dispositivo, el navegador, la dirección y el último uso, la de este navegador la primera, y cerrar una o
  todas las demás.
- **GitHub (organizaciones que exigen la verificación en dos pasos)**: la consola de administración solo
  deja entrar a su gente con el segundo factor activado, y la manda a activarlo.
- **Eliminar la cuenta** (8 referencias): quien es dueño de algo que otros usan lo traspasa o lo cierra antes de
  irse, y la pantalla dice qué lo retiene. GitHub no borra una cuenta propietaria única de una organización
  (https://docs.github.com/en/enterprise-server@3.11/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-your-personal-account/deleting-your-personal-account);
  Slack pide transferir la propiedad principal (https://slack.com/help/articles/203953146); Shopify, transferir la
  tienda antes de cerrarla (https://community.shopify.com/t/brand-assets-and-store-closure-concerns/400728); Zoom y
  Square, cancelar lo que se paga antes de borrar, con la contraseña o un código para confirmar
  (https://www.ionos.com/digitalguide/online-marketing/social-media/how-to-delete-your-zoom-account,
  https://community.squareup.com/t5/Your-Square-Account-Information/Re-Negative-Balance-Close-Account/m-p/701366);
  Odoo borra la cuenta desde su portal y avisa de que no se recupera
  (https://www.odoo.com/documentation/18.0/administration/odoo_accounts.html); Stripe conserva lo que la ley le
  obliga a guardar (https://support.stripe.com/questions/i-would-like-to-delete-the-information-stripe-has-collected-from-me).
  Notion borra con la cuenta sus espacios (https://supademo.com/tutorials/notion/how-to-delete-your-notion-account):
  aquí no, porque eliminar un negocio cancela su plan y apaga su caja, y eso es su propio flujo.
- **GitHub («Export account data»)**: descargar los datos de la cuenta está junto a eliminarla, en la misma página.

## Antes de empezar

- Se entra en erplora.com. En desarrollo, el panel está en el puerto 8001 y cada correo (los códigos y los
  enlaces) queda en la carpeta de correo local en vez de enviarse.
- «Continuar con Google» solo sale con las credenciales de Google configuradas; sin ellas el botón no se
  pinta.
- La verificación en dos pasos (la app autenticadora, sus códigos de recuperación y los navegadores de
  confianza) está apagada en la fase 1: no se pinta su fila en **Cuenta › Seguridad**, ninguna entrada pide
  el código de la app y el personal entra en el admin sin ella. Encenderla es una decisión de fase de la
  plataforma; las sesiones abiertas y el código por correo funcionan siempre.

## Pantallas

### Entrada
La primera pantalla de erplora.com sin sesión: el logo, «ERPlora Cloud · Panel global» y una tarjeta con
dos pestañas, **Entrar** (la de siempre) y **Crear cuenta**. Cada una pide «Correo electrónico» y
«Contraseña» (con el ojo para verla); «Entrar» lleva además «¿Olvidaste tu contraseña?». Debajo, «¿Es tu
primera vez? Crea tu cuenta» o «¿Ya tienes cuenta? Entra», «o» y «Continuar con Google». Al pie, «Al
continuar aceptas nuestros Términos & Política de Privacidad».

### Revisa tu correo
«Revisa tu correo electrónico» con «Te hemos enviado un código a …», el campo «Código de verificación»,
«Verificar», «Enviar un código nuevo» (solo para confirmar un correo) y «Usar otro correo electrónico». En
el código de cada entrada, en vez de reenviar: «El código dura 3 minutos. ¿No te ha llegado? Vuelve a
iniciar sesión y te enviaremos uno nuevo.»

### Restablece tu contraseña
«Restablece tu contraseña» con el correo y «Enviar Enlace»; enviado, «Hemos enviado instrucciones para
restablecer la contraseña a tu correo…», «Volver al Inicio de Sesión» y «¿No recibiste el correo? Inténtalo
de nuevo».

### Establece una nueva contraseña
La pantalla del enlace del correo: «Nueva Contraseña» con el ojo, la pista «Al menos 8 caracteres; mejor
larga y sin tu correo.» (y, al escribir, lo fuerte que parece) y «Cambiar contraseña». Con un enlace caducado
o usado, «Este enlace de restablecimiento ha expirado o no es válido.», «Solicitar Nuevo Enlace» y «Volver al
Inicio de Sesión».

### Verificación en dos pasos
«Introduce el código de 6 dígitos de tu app autenticadora, o uno de tus códigos de recuperación.», el
código, la casilla «Confiar en este navegador durante 14 días» (sin marcar, con «Aquí no se te volverá a
pedir el código de tu app durante 14 días. No lo marques en un ordenador compartido.»), «Verificar» y
«Volver a iniciar sesión».

### Ajustes de la verificación en dos pasos
Se abre desde **Cuenta › Seguridad**. Tres bloques: «App autenticadora» («Activada» o «Desactivada», con
«Configurar app autenticadora» o «Desactivar»), «Códigos de recuperación» (cuántos quedan sin usar, «Ver» y
«Generar nuevos») y, con la app activada, «Navegadores de confianza» (si lo es este y «Dejar de confiar en
todos los navegadores»). Cada acción abre su paso en la misma tarjeta: «Configura tu app autenticadora» con
el código QR y la clave, «Códigos de recuperación» con «Descargar», «¿Generar nuevos códigos de
recuperación?» y «¿Desactivar la app autenticadora?». Al pie, «Volver a configuración»; si se llegó desde el
admin, «Continuar».

### Cuenta › Seguridad › Cambiar tu contraseña
La fila «Contraseña» con «Cambiar contraseña» abre el diálogo «Cambiar tu contraseña»: «Contraseña actual»,
«Contraseña nueva» con su pista, «Cancelar» y «Cambiar contraseña». Una cuenta que solo entra con Google ve
en su lugar «Crear contraseña». En el mismo bloque «Acceso», la fila «Verificación en dos pasos» dice si
está activada, con «Activar» o «Gestionar».

### Cuenta › Seguridad › Sesiones activas
Una tabla a toda la altura con «Dispositivo», «Navegador», «Dirección IP» y «Último uso»; la de este
navegador va la primera, marcada «Esta sesión», y cada otra lleva «Cerrar sesión». Arriba, «Cerrar las
demás sesiones»; debajo, «Al cerrar una sesión también se cierra en tus negocios.». En el móvil, «Cargar
más» en vez de páginas.

### admin › Cuentas › Usuarios y Sesiones de usuario
La lista de cuentas lleva la acción «Cerrar todas sus sesiones», que también acaba la confianza de sus
navegadores; **Sesiones de usuario** enseña quién ha entrado dónde, solo para leer, con «Cerrar las
sesiones seleccionadas». Las dos acciones solo las ve un superusuario.

### Cuenta › Perfil
«Tus datos» (la foto o las iniciales con «Cambiar foto», «Nombre», «Apellidos», el «Correo con el que entras» con
«Cambiar» y «Guardar cambios»), «Exportar tus datos» para descargar («Descargar mis datos») y la tarjeta roja «Eliminar tu
cuenta». Abajo, las pestañas de **Cuenta**: «Perfil», «Seguridad», «Preferencias» y «Claves de API».

### Cuenta › Preferencias
Tres tarjetas que se guardan solas: «Apariencia» («Sistema», «Claro», «Oscuro»), «Idioma» («English»,
«Español») y «Avisos por correo» («Seguridad, facturas y pagos», siempre encendido, y «Avisos de mis negocios»).

### Menú de usuario
El nombre y el correo arriba del menú lateral (en el móvil, dentro del menú): «Cuenta», «Ayuda», el tema y
«Cerrar sesión».

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | El botón de enviar se apaga mientras va la petición, también «Descargar mis datos» mientras prepara el fichero; el perfil y las preferencias, sus tarjetas cargando; el enlace del correo dice «Comprobando tu enlace…»; los ajustes de la verificación en dos pasos, «Cargando…»; las sesiones, la tabla cargando. |
| Vacío | Sin sesión, toda página del panel lleva a la **Entrada**, que vuelve a ella tras entrar. Con esta sesión sola, «Cerrar las demás sesiones» está apagado; sin códigos de recuperación, «Sin ellos, perder tu autenticador te bloquea el acceso a tu cuenta.» con «Generar códigos de recuperación». |
| Error | Cada error sale debajo de su campo, con las palabras de la regla que falla («La contraseña nueva tiene que ser distinta de la actual.»); un fallo de red, «No hemos podido iniciar tu sesión. Vuelve a intentarlo.» o «Algo ha ido mal. Inténtalo de nuevo.». Los ajustes que no cargan, «No hemos podido cargar tu configuración de seguridad. Vuelve a intentarlo.» con «Reintentar»; las sesiones, «No hemos podido cargar tus sesiones» con «Reintentar»; el perfil, «No hemos podido cargar tu cuenta», y las preferencias, «No hemos podido cargar tus preferencias», con «Reintentar». Un cambio de preferencias que no se guarda vuelve a como estaba. |
| Freno | «Demasiados intentos fallidos. Inténtelo más tarde.» o «Demasiados intentos. Espera unos minutos y vuelve a intentarlo.», igual exista o no la cuenta. |
| Enlace caducado | «Este enlace de restablecimiento ha expirado o no es válido.» con «Solicitar Nuevo Enlace». |
| Código caducado | La entrada dice «Tu código ha caducado o se ha escrito mal demasiadas veces. Vuelve a iniciar sesión y te enviaremos uno nuevo.» |
| Sin permiso | Una cuenta sin la marca de personal que abre el admin vuelve a la **Entrada**; con sesión, el admin la rechaza. Con la verificación en dos pasos encendida, el personal sin app va a sus ajustes con «Activa la app autenticadora para continuar.». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| ACCOUNTS-F01 | Crear la cuenta | hecho |
| ACCOUNTS-F02 | Confirmar el correo con el código | hecho |
| ACCOUNTS-F03 | Confirmar el correo antes de usar el panel | hecho |
| ACCOUNTS-F04 | Entrar con el correo y la contraseña | hecho |
| ACCOUNTS-F05 | Entrar con el código de la app autenticadora o uno de recuperación | hecho |
| ACCOUNTS-F06 | Entrar o crear la cuenta con Google | parcial |
| ACCOUNTS-F07 | Recuperar la contraseña olvidada | hecho |
| ACCOUNTS-F08 | Cambiar la contraseña y cerrar con ella las demás sesiones | hecho |
| ACCOUNTS-F09 | Cerrar la sesión | hecho |
| ACCOUNTS-F10 | Aceptar los términos y la política de privacidad | hecho |
| ACCOUNTS-F11 | Frenar a quien prueba contraseñas, códigos o enlaces | hecho |
| ACCOUNTS-F12 | Saber quién ha entrado | hecho |
| ACCOUNTS-F13 | Gestionar las cuentas desde el admin | hecho |
| ACCOUNTS-F14 | Activar la app autenticadora y guardar los códigos de recuperación | hecho |
| ACCOUNTS-F15 | Ver si la verificación en dos pasos está activa | hecho |
| ACCOUNTS-F16 | Desactivar la app autenticadora o generar códigos nuevos | hecho |
| ACCOUNTS-F17 | Ver si este navegador es de confianza y dejar de confiar en todos | hecho |
| ACCOUNTS-F18 | Ver y cerrar las sesiones abiertas | hecho |
| ACCOUNTS-F19 | Cerrar las sesiones de una cuenta desde el admin | hecho |
| ACCOUNTS-F20 | Exigir la app autenticadora al personal en el admin | hecho |
| ACCOUNTS-F21 | Ver y cambiar mi perfil | hecho |
| ACCOUNTS-F22 | Elegir el idioma y la apariencia | hecho |
| ACCOUNTS-F23 | Elegir qué avisos recibir por correo | hecho |
| ACCOUNTS-F24 | Cambiar el tema desde el menú de usuario | hecho |
| ACCOUNTS-F25 | Abrir el menú de usuario | hecho |
| ACCOUNTS-F26 | Descargar mis datos | hecho |
| ACCOUNTS-F27 | Eliminar mi cuenta | parcial |

### ACCOUNTS-F01 Crear la cuenta
<!-- origen: old-saas:SAAS_AUTH-F01 pc:cloud/auth/signup fi:saas/auth-services#registro-de-usuario-por-api-signup fi:saas/support/auth-services#service-create_user gh:saas#2542 gh:saas#2536 gh:saas#2560 gh:saas#2562 -->
Estado: hecho
Actor: cualquiera
Pantalla: Entrada › «Crear cuenta»
Pasos:
1. La persona pulsa «Empieza gratis» en la web o abre la **Entrada** y elige «Crear cuenta» (las direcciones antiguas del alta llevan a esta pestaña y conservan adónde iba). Ve «Introduce tu email y elige una contraseña. Te enviaremos un código para confirmarlo.».
2. Escribe su correo y una contraseña (con el ojo para comprobarla) y pulsa «Crear cuenta».
3. erplora.com comprueba la contraseña: al menos 8 caracteres, que no se parezca a su correo, que no sea una contraseña común y que no sea solo números. Crea la cuenta y le manda un código de seis cifras.
4. La pantalla pasa a **Revisa tu correo** (ACCOUNTS-F02); con el código bueno entra sola y llega a «Crea tu negocio».
Entra: el correo (sin espacios, en minúsculas y con las letras de ancho completo pasadas a las normales, para que una dirección que se parece a otra no cree una segunda cuenta; igual al invitarla a un negocio, que invita a esa cuenta), la contraseña y adónde iba (solo páginas de erplora.com).
Sale: la cuenta, activa, con su correo aún sin confirmar y los términos aceptados (ACCOUNTS-F10). No se crea ningún negocio. La aplicación que pinta esta pantalla es la misma puerta que cualquier otro programa: las mismas reglas valen para todos.
Si falla: una contraseña que no pasa las reglas sale debajo de la contraseña y no se crea nada; un correo no válido (también con letras de ancho completo antes de la arroba), debajo del correo. Un correo que ya tiene cuenta responde igual que uno nuevo y a su buzón le llega «ya existe una cuenta con esta dirección» con el enlace para poner contraseña, sin código: así pone la suya también la persona invitada, cuya cuenta aún no tiene contraseña, y nadie se queda con una cuenta ajena. Más de 10 altas en una hora desde la misma dirección de red: «Demasiados intentos. Espera unos minutos y vuelve a intentarlo.».
Implicados: hubs (la **Entrada** y «Crea tu negocio»)

### ACCOUNTS-F02 Confirmar el correo con el código
<!-- origen: old-saas:SAAS_AUTH-F02 fi:saas/auth-services#reenviar-email-de-verificacion -->
Estado: hecho
Actor: cualquiera
Pantalla: Revisa tu correo
Pasos:
1. Tras crear la cuenta (o al entrar con un correo que nunca se confirmó, ACCOUNTS-F03) la pantalla dice «Revisa tu correo electrónico» y «Te hemos enviado un código a …».
2. La persona escribe las seis cifras y pulsa «Verificar».
3. Si no le llegó, pulsa «Enviar un código nuevo» (pasados unos segundos del anterior); si se equivocó de dirección, «Usar otro correo electrónico» vuelve a la **Entrada** sin nada de la dirección equivocada.
4. Con el código bueno queda confirmada y dentro, sin volver a escribir la contraseña: va adonde iba o a la **Entrada** con su sesión.
Entra: el código de seis cifras.
Sale: el correo confirmado y la sesión abierta.
Si falla: un código equivocado sale debajo del campo y se puede volver a escribir; tras 3 fallos o pasado su tiempo, el código deja de valer y la **Entrada** dice «Tu código ha caducado o se ha escrito mal demasiadas veces…»; un código nuevo antes de tiempo se frena.
Implicados: ninguno

### ACCOUNTS-F03 Confirmar el correo antes de usar el panel
<!-- origen: old-saas:SAAS_DASHBOARD-F203 gh:saas#2541 gh:saas#2561 -->
Estado: hecho
Actor: sistema
Pantalla: Revisa tu correo
Pasos:
1. Una persona cuyo correo nunca se confirmó abre una página del panel: sin sesión, va a la **Entrada**, que guarda adónde iba.
2. Escribe su correo y su contraseña: en vez de entrar, la pantalla pasa a **Revisa tu correo** con un código nuevo.
3. Con el código bueno, el correo queda confirmado y la persona llega a la página a la que iba.
Entra: la cuenta y su correo.
Sale: ninguna sesión hasta confirmar el correo: sin ella no se abre el panel, ni sus páginas ni su API, ni se pueden crear llaves de API.
Si falla: sin el código no hay sesión. Una cuenta creada por una invitación prueba su correo al poner su contraseña con el enlace del correo (ACCOUNTS-F07).
Implicados: hubs (las invitaciones solo valen para correos confirmados)

### ACCOUNTS-F04 Entrar con el correo y la contraseña
<!-- origen: old-saas:SAAS_AUTH-F03 fi:saas/auth-services#login-html-con-redireccion-a-subdominios-dispositivo-de-confianza fi:saas/support/auth-services#signal-create_email_otp_device -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Entrada › «Entrar», Revisa tu correo
Pasos:
1. En la **Entrada**, la persona escribe su correo y su contraseña y pulsa «Entrar».
2. erplora.com le manda un código de seis cifras al correo de la cuenta y la pantalla pasa a **Revisa tu correo**.
3. Escribe el código y pulsa «Verificar».
4. Dentro, va adonde iba (una página de erplora.com o el salto a un negocio) o a la **Entrada** con su sesión, que enseña sus negocios.
Entra: correo, contraseña, el código y adónde iba (solo páginas de erplora.com).
Sale: la sesión de ese navegador, que dura aunque se cierre el navegador; su nombre y su correo en el menú de usuario. Toda cuenta recibe el código por correo en cada entrada con contraseña, sin activarlo ni poder apagarlo; con la app autenticadora, después del código del correo se pide el de la app (ACCOUNTS-F05).
Si falla: un correo o una contraseña que no casan, «La dirección de correo electrónico y/o la contraseña que ha indicado no son correctas.» debajo de la contraseña, igual exista o no la cuenta, con «¿Es tu primera vez? Crea tu cuenta». Un código equivocado, debajo del código. Con una sesión ya abierta, la **Entrada** enseña los negocios.
Implicados: hubs (la **Entrada** con los negocios y el salto a un negocio)

### ACCOUNTS-F05 Entrar con el código de la app autenticadora o uno de recuperación
<!-- origen: pc:cloud/auth/two_factor_login old-saas:SAAS_AUTH-F06 fi:saas/auth-services#crear-dispositivo-de-confianza fi:saas/auth-services#modelo-trusteddevice-admin fi:saas/support/auth-services#modelo-trusteddevice fi:saas/support/auth-services#serializer-trusteddeviceserializer-createtrusteddeviceserializer-verifytrusteddeviceserializer -->
Estado: hecho
Actor: cualquier persona con cuenta y app autenticadora
Pantalla: Verificación en dos pasos
Pasos:
1. Tras la contraseña y el código del correo, una cuenta con app autenticadora pasa a **Verificación en dos pasos**.
2. Escribe el código de 6 dígitos de su app, o uno de sus códigos de recuperación; si el navegador es suyo y no es compartido, marca «Confiar en este navegador durante 14 días» (viene sin marcar).
3. Pulsa «Verificar». Dentro, va adonde iba.
4. Con la casilla marcada, las siguientes entradas en ese navegador piden solo la contraseña y el código del correo durante 14 días; cualquier otro navegador sigue pidiendo el código de la app.
Entra: el código de la app o uno de recuperación, y la respuesta a «Confiar en este navegador durante 14 días».
Sale: la sesión abierta; un código de recuperación usado deja de valer; con la casilla, este navegador queda como de confianza durante 14 días, solo en erplora.com. Al saltar a un negocio, la entrada cuenta como hecha con la app.
Si falla: un código equivocado sale debajo del campo y la entrada sigue esperando; «Volver a iniciar sesión» abandona la entrada a medias. Si tras un código bueno se pierde la respuesta a la casilla (se recarga la página), la pantalla dice «Tu código es correcto. ¿Quieres confiar en este navegador?» con «Continuar», sin volver a pedir el código. Cambiar la contraseña o «Dejar de confiar en todos los navegadores» (ACCOUNTS-F17) acaba la confianza de todos.
Implicados: hubs (el salto a un negocio)

### ACCOUNTS-F06 Entrar o crear la cuenta con Google
<!-- origen: old-saas:SAAS_AUTH-F04 gh:saas#2552 -->
Estado: parcial — la prueba de punta a punta necesita Google de verdad (el entorno de pruebas no tiene sus credenciales y el botón no se pinta); la ida y la vuelta están probadas con las respuestas de Google simuladas
Actor: cualquiera
Pantalla: Entrada
Pasos:
1. En la **Entrada**, la persona pulsa «Continuar con Google».
2. Elige su cuenta de Google y acepta.
3. Si ya hay una cuenta de erplora.com con ese correo, entra en ella, Google queda enlazado y a su correo le llega el aviso «cuenta de terceros vinculada»; si no la hay, la cuenta se crea con el correo ya confirmado y sin formulario.
4. Dentro, va adonde iba o a la **Entrada** con su sesión; con la app autenticadora, primero pasa por **Verificación en dos pasos**.
Entra: lo que Google confirma (correo, nombre y apellidos) y adónde iba.
Sale: la cuenta de Google enlazada y, si es nueva, la cuenta, sin contraseña (se pone con «¿Olvidaste tu contraseña?»). Google no pide el código del correo: ya lo prueba él.
Si falla: «Cancelar» en Google vuelve a la **Entrada**; un error de Google o un correo que Google no confirma lleva a la página de error de la entrada, sin crear ni enlazar nada. Enlazar Google a una sesión abierta sin entrar con él no se permite: dice que Google solo se vincula entrando con la cuenta de Google del correo.
Implicados: ninguno

### ACCOUNTS-F07 Recuperar la contraseña olvidada
<!-- origen: old-saas:SAAS_AUTH-F09 pc:cloud/auth/password_reset_request pc:cloud/auth/password_reset_done pc:cloud/auth/password_reset_from_key pc:cloud/auth/password_reset_from_key_done -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Restablece tu contraseña, Establece una nueva contraseña, Entrada
Pasos:
1. En la **Entrada**, la persona pulsa «¿Olvidaste tu contraseña?», escribe su correo en «Restablece tu contraseña» y pulsa «Enviar Enlace».
2. La pantalla dice «Hemos enviado instrucciones para restablecer la contraseña a tu correo…», con «Volver al Inicio de Sesión» y «¿No recibiste el correo? Inténtalo de nuevo».
3. Abre el enlace del correo: **Establece una nueva contraseña**, con la pista «Al menos 8 caracteres; mejor larga y sin tu correo.» y lo fuerte que parece mientras la escribe; pulsa «Cambiar contraseña».
4. Vuelve a la **Entrada** con «Tu contraseña ha sido cambiada exitosamente.» y entra con ella (ACCOUNTS-F04).
Entra: el correo; el enlace, que caduca a los tres días y deja de valer al usarse; la contraseña nueva.
Sale: la contraseña nueva, con todo lo que cierra un cambio de contraseña (ACCOUNTS-F08), y el correo de la cuenta confirmado. Es también el camino para poner la primera contraseña de una cuenta que entró con Google o nació de una invitación.
Si falla: la pantalla y el correo enviado son iguales exista o no la cuenta (a un correo sin cuenta le llega la invitación a crearla). Un enlace caducado o usado, «Este enlace de restablecimiento ha expirado o no es válido.» con «Solicitar Nuevo Enlace». La contraseña actual o una que no pasa las reglas sale debajo del campo («La contraseña nueva tiene que ser distinta de la actual.»). Más de 5 peticiones por minuto para un correo, frenadas (ACCOUNTS-F11).
Implicados: hubs (los negocios cierran las sesiones de la cuenta)

### ACCOUNTS-F08 Cambiar la contraseña y cerrar con ella las demás sesiones
<!-- origen: old-saas:SAAS_AUTH-F10 old-saas:SAAS_DASHBOARD-F205 fi:saas/orgs-users#api-rest-cambiar-contrasena-settings fi:saas/orgs-users#cambiar-contrasena-perfil fi:saas/orgs-users#cambiar-contrasena-settings gh:saas#2612 gh:saas#2614 gh:saas#2545 gh:saas#2668 -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Cuenta › Seguridad › Cambiar tu contraseña
Pasos:
1. En **Cuenta › Seguridad**, fila «Contraseña», la persona pulsa «Cambiar contraseña».
2. Escribe la «Contraseña actual» y la «Contraseña nueva», que pasa las mismas reglas que en el alta; la pista dice lo fuerte que parece.
3. Pulsa «Cambiar contraseña»: «Contraseña cambiada. Tus negocios te pedirán entrar otra vez.»; sigue dentro en este navegador.
4. Los demás navegadores con su cuenta salen, y erplora.com pide a cada uno de sus negocios que cierre las sesiones abiertas con ella.
Entra: la contraseña actual y la nueva.
Sale: la contraseña nueva; las otras sesiones de erplora.com cerradas, este navegador dentro; el aviso a sus negocios. Lo mismo pasa al restablecerla (ACCOUNTS-F07).
Si falla: una contraseña actual equivocada, debajo de su campo, y la nueva no se guarda; la nueva igual a la actual, «La contraseña nueva tiene que ser distinta de la actual.»; una que no pasa las reglas, sus avisos. Los avisos salen en el idioma de la cuenta. Más de 5 intentos por minuto, «Demasiados intentos…» sin mirar la contraseña, ni la buena: una sesión ajena abierta no sirve para adivinarla. Una cuenta sin contraseña (entró con Google) ve «Crear contraseña», que le manda el enlace de ACCOUNTS-F07.
Implicados: hubs (cada negocio cierra las sesiones de la cuenta)

### ACCOUNTS-F09 Cerrar la sesión
<!-- origen: old-saas:SAAS_AUTH-F11 -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Menú de usuario, Entrada
Pasos:
1. En el panel, la persona abre el **Menú de usuario** (en el móvil, dentro del menú) y pulsa «Cerrar sesión»; en la **Entrada** con sesión, «Cerrar sesión» está bajo su cuenta.
2. La sesión de ese navegador se cierra y vuelve la **Entrada**, lista para entrar.
3. Una página del panel abierta después lleva a la **Entrada**.
Entra: la sesión del navegador.
Sale: la sesión de ese navegador cerrada. Las demás sesiones, las llaves de API y los negocios no se tocan: para cerrar otras está **Cuenta › Seguridad**.
Si falla: si no se pudo cerrar, «No se ha podido cerrar la sesión. Inténtalo de nuevo.» y sigue dentro. Un enlace suelto no cierra ninguna sesión.
Implicados: ninguno

### ACCOUNTS-F10 Aceptar los términos y la política de privacidad
<!-- origen: old-saas:SAAS_PUBLIC-F72 -->
Estado: hecho
Actor: cualquiera
Pantalla: Entrada, Revisa tu correo, admin › ficha de la cuenta
Pasos:
1. Al pie de la **Entrada** (en las dos pestañas y bajo «Continuar con Google») y de **Revisa tu correo** se lee «Al continuar aceptas nuestros Términos & Política de Privacidad», con un enlace a cada texto.
2. Crear la cuenta (con contraseña o con Google) o entrar acepta las versiones vigentes: la cuenta guarda cuándo y qué versión de cada texto (la fecha de «Última actualización» de cada página).
3. Cuando un texto cambia, la siguiente entrada acepta la versión nueva y guarda su fecha; mientras no cambie, la fecha de la primera aceptación se queda.
4. El personal lo ve en el admin, en la ficha de la cuenta, «Términos y privacidad», sin poder cambiarlo.
Entra: crear la cuenta o entrar bajo el aviso.
Sale: en la cuenta, la fecha de la aceptación y la versión de los términos y de la política de privacidad.
Si falla: una contraseña equivocada no acepta nada. Una cuenta creada por una invitación o por el personal no ha aceptado nada hasta su primera entrada, y así lo dice su ficha.
Implicados: public (las páginas de los términos y de la privacidad)

### ACCOUNTS-F11 Frenar a quien prueba contraseñas, códigos o enlaces
<!-- origen: old-saas:SAAS_AUTH-F14 -->
Estado: hecho
Actor: sistema
Pantalla: Entrada, Revisa tu correo, Restablece tu contraseña
Pasos:
1. Cada contraseña equivocada gasta del presupuesto de su cuenta (5 en 5 minutos) y del de la dirección de red (10 por minuto); agotado, ni la buena entra hasta que pasa el plazo. Una entrada buena devuelve su intento: el dueño no gasta presupuesto.
2. Antes de mirar la contraseña, cada dirección de red tiene 30 entradas por minuto.
3. Los códigos del correo admiten 3 intentos; el de la entrada dura 3 minutos.
4. Los enlaces de restablecer, 5 por minuto por correo y 20 por dirección de red; las altas, 10 por hora por dirección; el cambio de contraseña, 5 por minuto por cuenta.
Entra: el correo que se prueba y la dirección de red de quien llama.
Sale: la respuesta de freno, la misma exista o no la cuenta y con el mismo número de intentos: «Demasiados intentos fallidos. Inténtelo más tarde.» en la **Entrada** o «Demasiados intentos. Espera unos minutos y vuelve a intentarlo.».
Si falla: si la memoria compartida de los contadores no responde, el freno se abre (la puerta sigue usable) y queda un aviso en el registro.
Implicados: ninguno

### ACCOUNTS-F12 Saber quién ha entrado
<!-- origen: fi:saas/auth-services#perfil-del-usuario-actual-me fi:saas/support/auth-services#serializer-userserializer -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Menú de usuario, Cuenta › Perfil
Pasos:
1. Al entrar, el panel pinta la cuenta: su nombre (o su correo, si no tiene nombre) y su correo en el **Menú de usuario**, en su idioma y con su tema.
2. **Cuenta › Perfil** enseña su correo, si está confirmado, su nombre y apellidos y su foto.
3. Al entrar en un negocio, erplora.com le dice al negocio quién entra: su identificador, su correo, su nombre, su idioma y su papel en él.
Entra: la sesión.
Sale: nada guardado.
Si falla: sin sesión, el panel lleva a la **Entrada**.
Implicados: hubs (el salto a un negocio)

### ACCOUNTS-F13 Gestionar las cuentas desde el admin
<!-- origen: fi:saas/auth-services#modelo-de-usuario-user-usermanager-admin fi:saas/support/auth-services#modelo-user fi:saas/django-admin#admin-profile fi:saas/django-admin#admin-user fi:saas/django-admin#admin-userpreferences -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: admin › Cuentas › Usuarios
Pasos:
1. El personal busca una cuenta por correo o nombre, o filtra por activa, personal e idioma.
2. Su ficha enseña el correo, la contraseña (solo «Restablecer contraseña»), los datos personales y el idioma, los permisos y grupos, las fechas, «Términos y privacidad» (solo lectura), las preferencias y la foto si las cambió (solo lectura) y sus negocios.
3. «Añadir usuario» crea una cuenta con su correo y una contraseña (o sin ella, que se pone con el enlace del correo).
Entra: lo que escribe el personal.
Sale: la cuenta, identificada por su correo (en minúsculas y único) y con su identificador propio.
Si falla: un correo que ya tiene cuenta no se guarda. El soporte ve las cuentas sin poder añadir, cambiar ni borrar; una cuenta sin la marca de personal no entra en el admin.
Implicados: hubs (los negocios de la cuenta)

### ACCOUNTS-F14 Activar la app autenticadora y guardar los códigos de recuperación
<!-- origen: old-saas:SAAS_AUTH-F05 fi:saas/auth-services#2fa-alta-de-totp-setup pc:cloud/auth/two_factor_setup -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Cuenta › Seguridad, Ajustes de la verificación en dos pasos
Pasos:
1. En **Cuenta › Seguridad**, la fila «Verificación en dos pasos» dice «Desactivada»; la persona pulsa «Activar».
2. En **Ajustes de la verificación en dos pasos** pulsa «Configurar app autenticadora»: «Configura tu app autenticadora» enseña un código QR y, bajo «¿No puedes escanear? Introduce esta clave a mano:», la clave.
3. Lo escanea con su app (Google Authenticator, 1Password…), escribe el número que muestra y pulsa «Activar». Si su última entrada no es reciente, antes confirma que es ella con su contraseña y el mismo número sigue valiendo.
4. Ve una sola vez sus diez «Códigos de recuperación» («10 de 10 sin usar»), los guarda con «Descargar» y pulsa «Volver»: la app queda «Activada».
Entra: el número de la app y, si hace falta, la contraseña.
Sale: la app autenticadora de la cuenta y diez códigos de recuperación de un solo uso; desde la siguiente entrada se pide el código de la app (ACCOUNTS-F05). Los códigos se descargan como un fichero de texto hecho en el propio navegador.
Si falla: un número equivocado sale debajo del campo y la app no se activa; «Cancelar» vuelve sin activar nada; un fallo de red, «Algo ha ido mal. Inténtalo de nuevo.».
Implicados: ninguno

### ACCOUNTS-F15 Ver si la verificación en dos pasos está activa
<!-- origen: old-saas:SAAS_DASHBOARD-F213 fi:saas/auth-services#2fa-perfil-estado -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Cuenta › Seguridad, Ajustes de la verificación en dos pasos
Pasos:
1. En **Cuenta › Seguridad**, bloque «Acceso», la fila «Verificación en dos pasos» dice «Activada» («Tras tu contraseña, un código de tu app autenticadora. Guarda tus códigos de recuperación.») o «Desactivada».
2. «Gestionar» (o «Activar») lleva a **Ajustes de la verificación en dos pasos**, que dice lo mismo de la app y cuántos códigos de recuperación quedan sin usar.
Entra: la sesión.
Sale: nada guardado.
Si falla: si no se puede leer, la fila no dice ni activada ni desactivada y sigue llevando a los ajustes. Con la verificación en dos pasos apagada en la plataforma, la fila no se pinta.
Implicados: ninguno

### ACCOUNTS-F16 Desactivar la app autenticadora o generar códigos nuevos
<!-- origen: old-saas:SAAS_AUTH-F07 fi:saas/auth-services#2fa-desactivar-totp-re-activa-email-otp -->
Estado: hecho
Actor: cualquier persona con cuenta y app autenticadora
Pantalla: Ajustes de la verificación en dos pasos
Pasos:
1. En **Ajustes de la verificación en dos pasos**, «Códigos de recuperación» dice cuántos quedan sin usar; «Ver» los enseña y «Generar nuevos» pregunta «¿Generar nuevos códigos de recuperación?» con «Esto reemplaza tus 10 códigos sin usar.».
2. «Generar» enseña los nuevos, para descargarlos otra vez; los anteriores dejan de valer.
3. Para quitar la app, «Desactivar» pregunta «¿Desactivar la app autenticadora?» con «Entrarás con tu contraseña y el código que te enviamos por correo.»; «Desactivar» la quita y «Mantenerla activada» vuelve sin tocar nada.
4. Si su última entrada no es reciente, antes de generar o de desactivar confirma que es ella con el código de su app.
Entra: la confirmación y, si hace falta, el código de la app.
Sale: códigos de recuperación nuevos, o la app quitada: la entrada vuelve a ser la contraseña y el código del correo, que nunca se apaga.
Si falla: un fallo de red, «Algo ha ido mal. Inténtalo de nuevo.» y no cambia nada. Sin códigos sin usar, «Has usado todos tus códigos de recuperación. Genera un nuevo conjunto ahora.» con «Generar nuevos códigos».
Implicados: ninguno

### ACCOUNTS-F17 Ver si este navegador es de confianza y dejar de confiar en todos
<!-- origen: fi:saas/auth-services#revocar-dispositivo-de-confianza fi:saas/orgs-users#revocar-dispositivo-de-confianza fi:saas/auth-services#listar-dispositivos-de-confianza fi:saas/orgs-users#dispositivos-de-confianza-listar -->
Estado: hecho
Actor: cualquier persona con cuenta y app autenticadora
Pantalla: Ajustes de la verificación en dos pasos
Pasos:
1. En **Ajustes de la verificación en dos pasos**, con la app activada, «Navegadores de confianza» dice «Los navegadores en los que confías no piden el código de tu app durante 14 días.» y si este lo es: «Este navegador es de confianza hasta el …» o «Este navegador no es de confianza.».
2. Si ha perdido un dispositivo o entró en un ordenador ajeno, la persona pulsa «Dejar de confiar en todos los navegadores».
3. La pantalla dice «Ya no confías en ningún navegador: cada uno te pedirá el código de tu app la próxima vez que entres.» y «Este navegador no es de confianza.».
Entra: la sesión.
Sale: ningún navegador de la cuenta es de confianza; la app y los códigos de recuperación siguen valiendo sin configurar nada, y esta sesión sigue dentro. Evento `accounts.browser_trust.revoked`.
Si falla: si no se puede comprobar este navegador, «No hemos podido comprobar este navegador.»; un fallo al dejar de confiar, «Algo ha ido mal. Inténtalo de nuevo.» y no cambia nada. Cambiar la contraseña también acaba la confianza de todos.
Implicados: ninguno

### ACCOUNTS-F18 Ver y cerrar las sesiones abiertas
<!-- origen: old-saas:SAAS_AUTH-F12 old-saas:SAAS_DASHBOARD-F206 fi:saas/auth-services#listado-de-sesiones-activas fi:saas/orgs-users#sesiones-activas-listar-revocar fi:saas/auth-services#revocar-las-demas-sesiones-logout-del-resto-de-dispositivos fi:saas/auth-services#revocar-una-sesion-concreta -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Cuenta › Seguridad › Sesiones activas
Pasos:
1. En **Cuenta › Seguridad**, «Sesiones activas» lista cada sesión abierta con su «Dispositivo», «Navegador», «Dirección IP» y «Último uso»; la de este navegador va la primera, marcada «Esta sesión».
2. «Cerrar sesión» en una fila la cierra al momento y avisa «Sesión cerrada en …»; si es la app de ERPlora, antes pregunta «Cerrar la app en …», porque puede estar cobrando en una caja.
3. «Cerrar las demás sesiones» dice cuántas se cerrarán, también las apps, y al confirmarlo las cierra todas menos esta: «Sesiones cerradas: 2».
Entra: la sesión elegida, o «las demás».
Sale: esas sesiones cerradas, aquí y en los negocios de la cuenta; esta sigue dentro y la lista se actualiza sola. Evento `accounts.session.closed`.
Si falla: la lista que no carga dice «No hemos podido cargar tus sesiones» con «Reintentar»; un cierre rechazado sale en un aviso y la sesión sigue en la lista. Una sesión de otra cuenta no se encuentra. Hoy los negocios aún no atienden el aviso (llega en la fase 2): una sesión abierta en un negocio sigue hasta que caduca.
Implicados: hubs (cada negocio cierra las sesiones de la cuenta)

### ACCOUNTS-F19 Cerrar las sesiones de una cuenta desde el admin
<!-- origen: fi:saas/auth-services#comando-revocar-sesiones-de-un-usuario fi:saas/support/auth-services#command-revoke_user_sessions fi:saas/django-admin#admin-usersession fi:saas/django-admin#admin-trusteddevice -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: admin › Cuentas › Usuarios y Sesiones de usuario
Pasos:
1. Ante un incidente, un superusuario busca la cuenta en **admin › Cuentas › Usuarios**, la marca y elige «Cerrar todas sus sesiones».
2. El admin dice «Sesiones cerradas: 1.»: la cuenta sale de todos sus navegadores y cada uno le pedirá el código de su app la próxima vez.
3. En **Sesiones de usuario** se ve quién ha entrado dónde (cuenta, dirección, navegador y fechas); un superusuario marca unas y elige «Cerrar las sesiones seleccionadas».
Entra: las cuentas o las sesiones marcadas.
Sale: esas sesiones cerradas, también en los negocios de la cuenta; con la acción de la cuenta, además, ningún navegador suyo es de confianza (su app y sus códigos de recuperación siguen valiendo). La lista de sesiones de la propia cuenta se actualiza sola, y el registro guarda quién lo hizo. Evento `accounts.session.closed`.
Si falla: el soporte ve las sesiones sin poder cerrarlas; nadie cambia ni borra una sesión a mano, porque borrar la fila no la cerraría. Una cuenta que ya no existe no se encuentra. Hoy los negocios aún no atienden el aviso (llega en la fase 2): una sesión abierta en un negocio sigue hasta que caduca.
Implicados: hubs (cada negocio cierra las sesiones de la cuenta)

### ACCOUNTS-F20 Exigir la app autenticadora al personal en el admin
<!-- origen: old-saas:SAAS_AUTH-F08 gh:saas#2543 gh:saas#2618 gh:saas#2627 gh:saas#2659 -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: admin, Ajustes de la verificación en dos pasos
Pasos:
1. Con la verificación en dos pasos encendida en la plataforma, una persona del personal (también del soporte) sin app autenticadora abre el admin.
2. En vez del admin llega a **Ajustes de la verificación en dos pasos**, con «Activa la app autenticadora para continuar.».
3. Activa la app (ACCOUNTS-F14) y pulsa «Continuar»: vuelve a la página del admin que abría.
4. Desde entonces cada entrada le pide el código de la app (o se lo salta un navegador de confianza) y el admin la deja pasar.
Entra: la cuenta del personal y adónde iba (solo páginas de erplora.com).
Sale: el personal entra en el admin, y salta al admin de los negocios, solo con su app autenticadora; con la verificación en dos pasos apagada, como hasta ahora.
Si falla: los códigos de recuperación solos no bastan; una cuenta sin la marca de personal no entra en el admin aunque tenga la app; «Continuar» nunca lleva fuera de erplora.com.
Implicados: hubs (el salto al admin de los negocios)

### ACCOUNTS-F21 Ver y cambiar mi perfil
<!-- origen: old-saas:SAAS_DASHBOARD-F204 fi:saas/orgs-users#mi-perfil-ver-actualizar-datos-billing-avatar fi:saas/orgs-users#api-rest-perfil-retrieveupdate fi:saas/support/orgs-users#modelo-profile fi:saas/support/orgs-users#serializer-profileserializer-billingaddressserializer fi:saas/support/orgs-users#service-signals-create_user_profile-save_user_profile fi:saas/support/orgs-users#service-user_profile-context-processor old-saas:SAAS_DASHBOARD-F222 gh:saas#2553 -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Cuenta › Perfil
Pasos:
1. Desde el **Menú de usuario**, «Cuenta» abre **Cuenta › Perfil**: «Tus datos» con la foto (o las iniciales), «Nombre», «Apellidos» y el «Correo con el que entras».
2. La persona cambia su nombre o sus apellidos: «Guardar cambios» se activa al tocar algo («Se activa al cambiar algo.»).
3. Pulsa «Guardar cambios»: «Cambios guardados», y el menú de usuario y los negocios en los que entre la nombran así.
4. «Cambiar foto» sube una foto (JPEG, PNG o WebP), que se guarda limpia de los datos ocultos de la cámara; «Quitar foto» vuelve a las iniciales.
5. El correo se cambia con «Cambiar»: le llega un código a la dirección nueva y, al escribirlo, esa pasa a ser la de entrar; a la antigua le llega un aviso del cambio.
Entra: nombre y apellidos, la foto o el correo nuevo y su código.
Sale: el perfil cambiado, en el panel y en cada negocio en el que entre después. Toda cuenta tiene su perfil desde que nace, sin rellenar nada. Lo mismo se lee y se guarda desde cualquier programa con la sesión de la persona.
Si falla: un nombre vacío no se guarda («Escribe tu nombre.»); una foto que no es imagen o es demasiado grande dice por qué y no cambia la que había; un fallo de red, «No hemos podido conectar con ERPlora…» y no cambia nada. Los datos de facturación no están aquí: son de **Facturación**.
Implicados: hubs (los negocios reciben el nombre al entrar)

### ACCOUNTS-F22 Elegir el idioma y la apariencia
<!-- origen: old-saas:SAAS_DASHBOARD-F210 fi:saas/orgs-users#ajustes-preferencias-del-usuario fi:saas/orgs-users#actualizar-preferencias-auto-save-htmx fi:saas/orgs-users#api-rest-preferencias-del-usuario-retrieveupdate fi:saas/support/orgs-users#modelo-userpreferences fi:saas/support/orgs-users#serializer-userpreferencesserializer-changepasswordserializer -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Cuenta › Preferencias
Pasos:
1. En **Cuenta › Preferencias**, «Apariencia» ofrece «Sistema», «Claro» y «Oscuro» («Sistema» sigue el modo de su dispositivo).
2. La persona elige uno: el panel se pinta así al momento y sale «Preferencias guardadas»; no hay botón de guardar.
3. En «Idioma» elige «English» o «Español»: el panel cambia de idioma al momento, también los correos que le enviamos.
4. En otro navegador o tras recargar, el panel abre con la apariencia y el idioma de la cuenta.
Entra: la apariencia y el idioma.
Sale: la apariencia y el idioma de la cuenta, iguales en todos sus dispositivos; el idioma es también el de sus correos y el que reciben sus negocios al entrar. En el panel manda el idioma de la cuenta; la web pública sigue el que se elige en ella o el del navegador.
Si falla: si no se puede guardar, el control vuelve a lo que había y un aviso dice por qué; si las preferencias no cargan, «No hemos podido cargar tus preferencias» con «Reintentar». La moneda no se elige: ERPlora cobra en euros.
Implicados: hubs (el idioma al entrar en un negocio)

### ACCOUNTS-F23 Elegir qué avisos recibir por correo
<!-- origen: old-saas:SAAS_DASHBOARD-F211 -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Cuenta › Preferencias
Pasos:
1. En **Cuenta › Preferencias**, «Avisos por correo» enseña «Seguridad, facturas y pagos», siempre encendido («Siempre activos: códigos para entrar, avisos de seguridad, facturas, pagos y lo que te pide hacer algo.»).
2. Debajo, «Avisos de mis negocios» («Cuando un negocio tuyo está listo para abrir.»), encendido de entrada.
3. La persona lo apaga: «Preferencias guardadas», y el siguiente negocio que cree ya no le manda el correo de que está listo.
4. Lo vuelve a encender y el correo vuelve.
Entra: «Avisos de mis negocios».
Sale: con él apagado, el correo de un negocio listo no se manda; el negocio abre igual y el panel lo dice. Los demás correos se mandan siempre: los códigos y los avisos de seguridad, las facturas y los pagos fallidos, el negocio eliminado con su fecha para recuperarlo y lo que pide hacer algo, como volver a conectar WhatsApp.
Si falla: si no se puede guardar, el interruptor vuelve a como estaba y un aviso dice por qué.
Implicados: hubs (el correo de un negocio listo), billing (las facturas y los pagos, siempre)

### ACCOUNTS-F24 Cambiar el tema desde el menú de usuario
<!-- origen: fi:saas/auth-services#toggle-de-tema-server-side-sin-js fi:saas/auth-services#context-processor-de-tema fi:saas/support/public-core-config#context_processors-py-theme-apps-py-coreconfig pc:cloud/dashboard/theme_picker -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Menú de usuario
Pasos:
1. La persona abre el **Menú de usuario** (en el móvil, dentro del menú) y ve «Tema» con tres botones: claro, oscuro y sistema, con el de ahora marcado.
2. Pulsa uno: el panel se pinta así al momento.
3. El tema queda en su cuenta: es el mismo de **Cuenta › Preferencias › Apariencia** y el panel abre con él en cualquier dispositivo, sin pasar antes por el otro.
4. Las páginas de la web pública se pintan con el tema de la cuenta mientras tiene la sesión abierta; sin sesión, siguen el modo del dispositivo.
Entra: el tema elegido.
Sale: el tema de la cuenta.
Si falla: si no se puede guardar, el panel se queda con el tema elegido y un aviso dice «No se ha podido guardar la apariencia en tu cuenta.».
Implicados: ninguno

### ACCOUNTS-F25 Abrir el menú de usuario
<!-- origen: pc:cloud/dashboard/user_dropdown -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Menú de usuario
Pasos:
1. Arriba del menú lateral (en el móvil, dentro del menú) está la tarjeta de la persona: sus iniciales, su nombre y su correo.
2. Al pulsarla se abre el **Menú de usuario**: «Cuenta», «Ayuda», «Tema» y «Cerrar sesión».
3. «Cuenta» lleva a **Cuenta › Perfil**, desde donde están **Seguridad**, **Preferencias** y **Claves de API**; «Ayuda», a la ayuda; «Tema», a ACCOUNTS-F24; «Cerrar sesión», a ACCOUNTS-F09.
Entra: la sesión.
Sale: nada guardado.
Si falla: sin sesión no hay menú: el panel lleva a la **Entrada**.
Implicados: ninguno

### ACCOUNTS-F26 Descargar mis datos
<!-- origen: old-saas:SAAS_DASHBOARD-F207 fi:saas/orgs-users#api-exportar-mis-datos-gdpr-art-20 -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Cuenta › Perfil
Pasos:
1. En **Cuenta › Perfil**, la tarjeta «Exportar tus datos» dice «Una copia de tu cuenta, tus negocios y tus facturas de ERPlora, en un fichero que otras aplicaciones pueden leer.».
2. La persona pulsa «Descargar mis datos»: el botón se apaga mientras se prepara.
3. El navegador guarda el fichero «erplora-data-» con la fecha del día.
Entra: la sesión.
Sale: un fichero con sus datos: la cuenta (correo, nombre, idioma, alta, último acceso y los términos aceptados), su apariencia y sus avisos, su foto, sus direcciones de correo, su cuenta de Google enlazada, sus sesiones abiertas, sus claves de API (sin la clave), los negocios a los que pertenece con su papel en cada uno y las facturas de ERPlora que ve, cada una con sus líneas y su destinatario tal como se emitió. Nada de otra cuenta.
Si falla: si no se puede preparar, un aviso dice por qué y el botón vuelve; sin conexión, «No hemos podido conectar con ERPlora…». No se guarda nada a medias.
Implicados: hubs (sus negocios), billing (sus facturas de ERPlora)

### ACCOUNTS-F27 Eliminar mi cuenta
<!-- origen: old-saas:SAAS_DASHBOARD-F208 old-saas:SAAS_AUTH-F13 fi:saas/orgs-users#api-borrar-mi-cuenta-gdpr-art-17 fi:saas/orgs-users#confirmar-borrado-de-cuenta-gdpr gh:saas#2567 gh:saas#2583 gh:saas#2584 gh:saas#2587 gh:saas#2664 -->
Estado: parcial — los datos de pagador de sus negocios (nombre fiscal, NIF y dirección) se quedan guardados sin dueño al eliminar la cuenta; quitarlos espera a que el cobro garantice que ya no llega ninguna factura de esos negocios
Actor: cualquier persona con cuenta
Pantalla: Cuenta › Perfil
Pasos:
1. En **Cuenta › Perfil**, la tarjeta «Eliminar tu cuenta» dice de entrada si algo la retiene: si es propietaria de un negocio, «Eres propietario de 1 negocio: transfiérelo o elimínalo antes de borrar la cuenta.» con el nombre del negocio, que lleva a sus ajustes; si paga el negocio de otra persona, que su propietario ponga sus datos de pago. Mientras tanto «Eliminar cuenta» está apagado.
2. Sin nada que la retenga, pulsa «Eliminar cuenta»: el diálogo dice qué se borra (la cuenta, la foto, las preferencias y las claves de API, y todas las sesiones, también en las apps y en sus negocios), que no se puede deshacer y que «Tus facturas de ERPlora se conservan el tiempo que exige la ley.».
3. Escribe su correo para confirmar y pulsa «Eliminar cuenta». Si su última entrada no es reciente, antes confirma que es ella: con su contraseña o, si solo entra con Google, entrando otra vez con Google.
4. La sesión se cierra y llega a la web pública.
Entra: el correo escrito y, si hace falta, la contraseña o Google.
Sale: la cuenta borrada, con su foto, sus preferencias, sus claves y todas sus sesiones, aquí y en sus negocios; deja de ser miembro de los negocios de otros. Sus facturas de ERPlora se quedan, con el destinatario de la fecha de emisión y sin enlace a la cuenta. Evento `accounts.profile.deleted`.
Si falla: un negocio propio o pagado la retiene (el diálogo lo dice igual si cambió mientras); un negocio eliminado, en sus 90 días para recuperarlo, ya no la retiene. Más de 10 contraseñas en un minuto al confirmar se frenan, ni la buena entra: una sesión ajena abierta no sirve para adivinarla. Un fallo de red se dice en el diálogo y no se borra nada.
Implicados: hubs (los negocios que la retienen y los que deja), billing (las facturas que se conservan)

## Para quien lo mantiene

- Anatomía, operaciones y decisiones: `accounts/README.md` (allauth headless, puertas cerradas, sesiones,
  reautenticación, correo por código propio, foto, preferencias y llaves de API).
- Partes del porte (MIGRATION-TASK APP-ACCOUNTS-1…5): este WORKBOOK nace en la parte 1 (F01–F13); la parte 2
  (segundo factor, navegadores de confianza y sesiones) cierra F05 y añade F14–F20; la parte 3 (perfil,
  preferencias, avisos, menú de usuario, exportar y borrar la cuenta) añade F21–F27 y amplía F13; las partes 4
  (salto al Hub, llaves de API, retención GDPR y auditlog) y 5 (plataforma del SaaS) añaden los suyos a
  continuación.
- Equivalencia de claves del registro: G83, G124, G22 y G59 = F01; G84 y G21 = F02; G107 = F03; G85 y G17 =
  F04; G125 = F05; G86 = F06; G91, G123, G120, G121 y G122 = F07; G109, G92, G42, G45 y G46 = F08; G93 = F09;
  G119 = F10; G96 = F11; G20 y G58 = F12; G18 y G56 = F13. Parte 2: G60 = F04; G88, G12, G19, G55 y G57 =
  F05; G87, G02 y G126 = F14; G116 y G05 = F15; G89 y G03 = F16; G23, G16 y G48 = F17; G94, G110, G15, G50,
  G24 y G25 = F18; G09, G54, G37 y G34 = F19; G90 = F20. Parte 3: G108, G49, G43, G63, G66, G69, G70 y G118 =
  F21; G114, G39, G38, G44, G65 y G67 = F22; G115 = F23; G29, G11, G74 y G127 = F24; G128 = F25; G111 y G41 =
  F26; G112, G95, G40 y G47 = F27; G32, G35 y G36 = F13. Descartadas: G04 (activar o apagar el código por
  correo: se pide en toda entrada con contraseña y no se apaga, PLAN-SAAS ronda 19, §3.7 punto 3) y G31
  (el Hub verificaba en el SaaS un dispositivo de confianza: el Hub nunca consulta al SaaS por petición y
  sus dispositivos y su PIN son suyos, PLAN-SAAS §2).
- Puertas propias sobre allauth.headless (`accounts/doors.py`, montadas en `config/urls.py` antes de las de
  allauth): la entrada pliega el correo como el alta (NFKC, `adapters.plain_email`; trampa del SaaS viejo
  #1018) y el alta comprueba la contraseña contra su propio correo (headless la validaba sin cuenta y el
  validador de parecido no veía nada; saas#2542). `AccountAdapter.clean_password` rechaza la contraseña
  actual como nueva (saas#2612), en el cambio y en el restablecimiento.
- Términos (ACCOUNTS-F10): `TERMS_VERSION` y `PRIVACY_VERSION` en `accounts/models.py` son la fecha de
  «Last updated» de `/legal/terms/` y `/legal/privacy/`; `tests/test_terms.py` falla si una página cambia
  su fecha sin la versión. `services.accept_legal_texts` escucha `user_signed_up` de allauth y
  `user_logged_in` de Django.
- Freno (ACCOUNTS-F11): los límites son los de allauth (`ACCOUNT_RATE_LIMITS` solo sube el de altas a
  10/h) sobre la caché de Django (Valkey en AWS, `base.cache.FailSoftRedisCache`); `tests/test_throttle.py`.
  Los pases del salto a un negocio se frenan en la parte 4.
- Lo que no sigue del viejo, a propósito: el asistente de `two_factor` (retirado en el viejo, ADR-0417), el
  `EmailDevice` creado a cada cuenta (lo sustituye el código por correo de cada entrada), el par de
  credenciales que devolvía el alta por la API (hoy la sesión del navegador; el Hub recibe al usuario con el
  canje del código de un solo uso) y la organización personal al crear la cuenta (ADR-0201).
- Segundo factor (F05, F14–F17, F20): `allauth.mfa` sobre headless (TOTP y códigos de recuperación, sin
  passkeys), detrás de `ACCOUNTS_MFA_ENABLED` (apagado por defecto en la fase 1: sus rutas responden 404 y
  `mfa.mfa_completed` es falso). La confianza de 14 días es `MFA_TRUST_ENABLED` de allauth, con la cookie
  solo en el host de erplora.com (`MFA_TRUST_COOKIE_DOMAIN = None`); allauth no guarda en el servidor qué
  navegadores confían, solo una huella firmada de la contraseña y de los autenticadores, así que
  `forget_trusted_browsers` vuelve a crear los autenticadores con otro id (el mismo secreto: la app y los
  códigos siguen valiendo) y esta sesión sigue sus ids nuevos (`_follow_new_authenticator_ids`). La página de la
  entrada responde la etapa con `mfaTrust` del cliente de allauth de `@erplora/ui`.
- Sesiones (F18, F19): las de `allauth.usersessions`, sin `UserSession` propio ni JWT (PLAN-SAAS: nadie
  consume tokens). Cerrar una pide a sus negocios que cierren las suyas (`signals.sessions_ended`). El
  admin cierra por `accounts.session.close_any` (sin ruta: solo el admin, por el canal de la cuenta); sus
  dos acciones solo las ve el superusuario y el soporte solo lee. La «revocación del comando»
  `revoke_user_sessions` del viejo es esa acción del admin (working-rules §4: todo por la UI o la API).
- Personal (F20): `admin_has_permission` (instalado en `config/urls.py`) exige, con el interruptor
  encendido, un autenticador TOTP; `admin_login` lleva al personal sin él a `/2fa?next=…`. En el SaaS nuevo
  el personal no tiene API propia: sus poderes viven en el admin y en el salto `hub-admin`, que ya exige el
  segundo factor con el interruptor encendido. Las trampas del viejo (saas#2543, #2618, #2627: puertas del
  personal abiertas con la contraseña sola) quedan cubiertas por esas dos puertas; saas#2659 (marketplace)
  no aplica: no hay marketplace.
- Parte 3 (F21–F27): el perfil del viejo (`Profile`, su señal y su procesador de contexto) es la propia cuenta,
  con su foto y unas preferencias que no necesitan fila (`queries.preferences_of`), y el panel la lee de
  `base.session.me`; sus DRF son las operaciones `accounts.profile.*` y `accounts.preferences.*`; su
  `ChangePasswordSerializer` es F08. El tema de las plantillas es `base.context_processors.theme` (cuenta, o la
  cookie `theme` del viejo, o el sistema) y el del panel, el del shell de `@erplora/ui`, que pinta el de la sesión
  embebida antes de arrancar. Avisos (F23): `hub_alerts` gobierna `hubs.emails.send_ready` por
  `queries.receives_business_notices`; «Novedades de ERPlora» no gobernaba ningún correo y sale (accounts 0009:
  fuera del modelo, columna con valor por defecto hasta su `DROP COLUMN`, el paso de contrato). Descargar mis datos
  (F26): `accounts.data.export`, que lee los negocios y las facturas por sus operaciones (`hubs.business.list`,
  `billing.invoice.list` y `.get`), sin importar esas apps. Eliminar (F27): ver accounts/README.md; las facturas
  conservan el destinatario porque su enlace a la cuenta es `SET_NULL` (`test_delete_account`). La moneda del viejo
  no sigue: ERPlora cobra en euros y ninguna pantalla ni correo la leía (SAAS_DASHBOARD-F210).
- Pruebas: cada test cita su clave en el nombre o el docstring. Los e2e de la parte 1 están en
  `tests/e2e/panel/accounts-flows.spec.ts`, los de la parte 2 en `tests/e2e/panel/accounts-security.spec.ts`
  y los de la parte 3 en `tests/e2e/panel/accounts-profile.spec.ts`,
  con la clave del registro (`ACCOUNTS-Gnn`) en el título y la equivalencia con este WORKBOOK en su cabecera;
  el segundo factor se juega en el gemelo del panel con el interruptor encendido (`PANEL_MFA_URL`).
  `signup.spec.ts` y `login.spec.ts` siguen cubriendo las pestañas de la entrada.

## Lo que NO hace, a propósito

- No pide repetir la contraseña: el ojo la enseña (como Shopify y Square).
- No deja entrar solo con el código del correo: siempre con la contraseña o con Google.
- No dice nunca qué correos tienen cuenta.
- No enlaza Google desde una sesión abierta ni guarda los tokens de Google.
- No lleva a otro dominio al entrar: solo a páginas de erplora.com; el salto a un negocio es otro flujo.
- No deja apagar el código por correo de cada entrada, ni con la app autenticadora activa.
- No lista los navegadores de confianza uno a uno: dice si lo es este y deja de confiar en todos a la vez,
  como «Revocar todos» de Google.
- No ofrece llaves de acceso (passkeys) ni códigos por SMS: la app autenticadora y sus códigos de
  recuperación.
- No pide moneda: ERPlora cobra en euros.
- No manda boletines ni novedades, así que no hay interruptor para ellos; los correos de seguridad, facturas y
  pagos no se pueden apagar.
- No deja eliminar la cuenta a quien es propietario de un negocio o paga el de otra persona, ni borra con ella
  sus facturas de ERPlora.
