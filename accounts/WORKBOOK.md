# Workbook — Cuentas (accounts)
Prefijo: ACCOUNTS
Alcance MVP: fase 1 (la cuenta de erplora.com: crearla, entrar y salir, su contraseña y lo que acepta)
Estado de la app: en construcción (parte 1 de 5: crear la cuenta, entrar, la contraseña, salir, los términos y el freno)

> Manual de uso y especificación de la app `accounts` del SaaS (erplora.com). Cuenta cómo se crea una
> cuenta, cómo se confirma el correo, cómo se entra y se sale, cómo se recupera y se cambia la contraseña,
> qué se acepta al continuar y cómo se frena a quien prueba contraseñas. Esta parte del manual no se
> publica en la tienda: es la referencia del equipo y de la QA. El segundo factor, los dispositivos y las
> sesiones, el perfil y las preferencias, el salto a un negocio y las llaves de API se escriben en las
> partes 2 a 5.

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
- **La persona con cuenta** cambia su contraseña desde **Cuenta › Seguridad**.
- El **personal de ERPlora** ve y gestiona las cuentas desde el admin, sin poder cambiar lo que una cuenta
  aceptó.

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

## Antes de empezar

- Se entra en erplora.com. En desarrollo, el panel está en el puerto 8001 y cada correo (los códigos y los
  enlaces) queda en la carpeta de correo local en vez de enviarse.
- «Continuar con Google» solo sale con las credenciales de Google configuradas; sin ellas el botón no se
  pinta.
- El segundo paso con la app autenticadora está apagado en la fase 1: hoy nadie lo ve.

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
código, «Verificar» y «Volver a iniciar sesión».

### Cuenta › Seguridad › Cambiar tu contraseña
La fila «Contraseña» con «Cambiar contraseña» abre el diálogo «Cambiar tu contraseña»: «Contraseña actual»,
«Contraseña nueva» con su pista, «Cancelar» y «Cambiar contraseña». Una cuenta que solo entra con Google ve
en su lugar «Crear contraseña».

### Menú de usuario
El nombre y el correo arriba del menú lateral (en el móvil, dentro del menú): «Cuenta», «Ayuda», el tema y
«Cerrar sesión».

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | El botón de enviar se apaga mientras va la petición; el enlace del correo dice «Comprobando tu enlace…». |
| Vacío | Sin sesión, toda página del panel lleva a la **Entrada**, que vuelve a ella tras entrar. |
| Error | Cada error sale debajo de su campo, con las palabras de la regla que falla («La contraseña nueva tiene que ser distinta de la actual.»); un fallo de red, «No hemos podido iniciar tu sesión. Vuelve a intentarlo.» o «Algo ha ido mal. Inténtalo de nuevo.». |
| Freno | «Demasiados intentos fallidos. Inténtelo más tarde.» o «Demasiados intentos. Espera unos minutos y vuelve a intentarlo.», igual exista o no la cuenta. |
| Enlace caducado | «Este enlace de restablecimiento ha expirado o no es válido.» con «Solicitar Nuevo Enlace». |
| Código caducado | La entrada dice «Tu código ha caducado o se ha escrito mal demasiadas veces. Vuelve a iniciar sesión y te enviaremos uno nuevo.» |
| Sin permiso | Una cuenta sin la marca de personal que abre el admin vuelve a la **Entrada**; con sesión, el admin la rechaza. |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| ACCOUNTS-F01 | Crear la cuenta | hecho |
| ACCOUNTS-F02 | Confirmar el correo con el código | hecho |
| ACCOUNTS-F03 | Confirmar el correo antes de usar el panel | hecho |
| ACCOUNTS-F04 | Entrar con el correo y la contraseña | hecho |
| ACCOUNTS-F05 | Entrar con el código de la app autenticadora o uno de recuperación | parcial |
| ACCOUNTS-F06 | Entrar o crear la cuenta con Google | parcial |
| ACCOUNTS-F07 | Recuperar la contraseña olvidada | hecho |
| ACCOUNTS-F08 | Cambiar la contraseña y cerrar con ella las demás sesiones | hecho |
| ACCOUNTS-F09 | Cerrar la sesión | hecho |
| ACCOUNTS-F10 | Aceptar los términos y la política de privacidad | hecho |
| ACCOUNTS-F11 | Frenar a quien prueba contraseñas, códigos o enlaces | hecho |
| ACCOUNTS-F12 | Saber quién ha entrado | hecho |
| ACCOUNTS-F13 | Gestionar las cuentas desde el admin | hecho |

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
Entra: el correo (sin espacios, en minúsculas y con las letras de ancho completo pasadas a las normales, para que una dirección que se parece a otra no cree una segunda cuenta), la contraseña y adónde iba (solo páginas de erplora.com).
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
<!-- origen: old-saas:SAAS_AUTH-F03 fi:saas/auth-services#login-html-con-redireccion-a-subdominios-dispositivo-de-confianza -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Entrada › «Entrar», Revisa tu correo
Pasos:
1. En la **Entrada**, la persona escribe su correo y su contraseña y pulsa «Entrar».
2. erplora.com le manda un código de seis cifras al correo de la cuenta y la pantalla pasa a **Revisa tu correo**.
3. Escribe el código y pulsa «Verificar».
4. Dentro, va adonde iba (una página de erplora.com o el salto a un negocio) o a la **Entrada** con su sesión, que enseña sus negocios.
Entra: correo, contraseña, el código y adónde iba (solo páginas de erplora.com).
Sale: la sesión de ese navegador, que dura aunque se cierre el navegador; su nombre y su correo en el menú de usuario.
Si falla: un correo o una contraseña que no casan, «La dirección de correo electrónico y/o la contraseña que ha indicado no son correctas.» debajo de la contraseña, igual exista o no la cuenta, con «¿Es tu primera vez? Crea tu cuenta». Un código equivocado, debajo del código. Con una sesión ya abierta, la **Entrada** enseña los negocios.
Implicados: hubs (la **Entrada** con los negocios y el salto a un negocio)

### ACCOUNTS-F05 Entrar con el código de la app autenticadora o uno de recuperación
<!-- origen: pc:cloud/auth/two_factor_login -->
Estado: parcial — el segundo paso está apagado en la fase 1 y nadie lo ve todavía; su pantalla y su puerta están hechas y probadas con él encendido, y su prueba de punta a punta va con el segundo factor
Actor: cualquier persona con cuenta y app autenticadora
Pantalla: Verificación en dos pasos
Pasos:
1. Tras la contraseña y el código del correo, una cuenta con app autenticadora pasa a **Verificación en dos pasos**.
2. Escribe el código de 6 dígitos de su app, o uno de sus códigos de recuperación, y pulsa «Verificar».
3. Dentro, va adonde iba.
Entra: el código de la app o uno de recuperación.
Sale: la sesión abierta; un código de recuperación usado deja de valer.
Si falla: un código equivocado sale debajo del campo; «Volver a iniciar sesión» abandona la entrada a medias.
Implicados: ninguno

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
<!-- origen: fi:saas/auth-services#modelo-de-usuario-user-usermanager-admin fi:saas/support/auth-services#modelo-user -->
Estado: hecho
Actor: personal de ERPlora
Pantalla: admin › Cuentas › Usuarios
Pasos:
1. El personal busca una cuenta por correo o nombre, o filtra por activa, personal e idioma.
2. Su ficha enseña el correo, la contraseña (solo «Restablecer contraseña»), los datos personales y el idioma, los permisos y grupos, las fechas, «Términos y privacidad» (solo lectura), las preferencias, la foto y sus negocios.
3. «Añadir usuario» crea una cuenta con su correo y una contraseña (o sin ella, que se pone con el enlace del correo).
Entra: lo que escribe el personal.
Sale: la cuenta, identificada por su correo (en minúsculas y único) y con su identificador propio.
Si falla: un correo que ya tiene cuenta no se guarda. El soporte ve las cuentas sin poder añadir, cambiar ni borrar; una cuenta sin la marca de personal no entra en el admin.
Implicados: hubs (los negocios de la cuenta)

## Para quien lo mantiene

- Anatomía, operaciones y decisiones: `accounts/README.md` (allauth headless, puertas cerradas, sesiones,
  reautenticación, correo por código propio, foto, preferencias y llaves de API).
- Partes del porte (MIGRATION-TASK APP-ACCOUNTS-1…5): este WORKBOOK nace en la parte 1 con estos flujos; las
  partes 2 (segundo factor, dispositivos y sesiones), 3 (perfil, preferencias, exportar y borrar la cuenta),
  4 (salto al Hub, llaves de API, retención GDPR y auditlog) y 5 (plataforma del SaaS) añaden los suyos a
  continuación. La parte 2 cierra ACCOUNTS-F05 (su e2e con el segundo factor encendido).
- Equivalencia de claves del registro: G83, G124, G22 y G59 = F01; G84 y G21 = F02; G107 = F03; G85 y G17 =
  F04; G125 = F05; G86 = F06; G91, G123, G120, G121 y G122 = F07; G109, G92, G42, G45 y G46 = F08; G93 = F09;
  G119 = F10; G96 = F11; G20 y G58 = F12; G18 y G56 = F13.
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
- Pruebas: cada test cita su clave en el nombre o el docstring; los e2e de esta parte están en
  `tests/e2e/panel/accounts-flows.spec.ts`, con la clave del registro (`ACCOUNTS-Gnn`) en el título y la
  equivalencia con este WORKBOOK en su cabecera. `signup.spec.ts` y `login.spec.ts` siguen cubriendo las
  pestañas de la entrada.

## Lo que NO hace, a propósito

- No pide repetir la contraseña: el ojo la enseña (como Shopify y Square).
- No deja entrar solo con el código del correo: siempre con la contraseña o con Google.
- No dice nunca qué correos tienen cuenta.
- No enlaza Google desde una sesión abierta ni guarda los tokens de Google.
- No lleva a otro dominio al entrar: solo a páginas de erplora.com; el salto a un negocio es otro flujo.
