# Workbook — Cuentas (accounts)
Prefijo: ACCOUNTS
Alcance MVP: fase 1 (la cuenta de erplora.com: crearla, entrar y salir, su contraseña y lo que acepta)
Estado de la app: en uso (dos flujos parciales: ACCOUNTS-F06, que espera a Google de verdad en el entorno de pruebas, y ACCOUNTS-F48, la QA maestra, que espera flujos de otras apps)

> Manual de uso y especificación de la app `accounts` del SaaS (erplora.com). Cuenta cómo se crea una
> cuenta, cómo se confirma el correo, cómo se entra y se sale, cómo se recupera y se cambia la contraseña,
> qué se acepta al continuar, cómo se frena a quien prueba contraseñas, cómo se pide la app autenticadora
> después de la contraseña, en qué navegadores se confía, cómo se ven y se cierran las sesiones abiertas, cómo
> se cambian el perfil, el idioma, el tema y los avisos por correo, cómo se descargan los datos y se elimina la
> cuenta, cómo se salta a un negocio y se vuelve, cómo se crean, se usan y se revocan las claves de API y se consulta
> su documentación, cuánto se guardan las cuentas sin uso y el registro de auditoría, y cómo se reporta un problema
> a soporte. También cuenta la plataforma de erplora.com: qué deja cargar cada página, qué guarda el registro, cómo
> arranca, qué página ve quien llega a un error, cómo se pone en mantenimiento, qué se limpia cada día, qué se frena,
> cómo salen los correos, cómo se mueve uno por el panel y qué comprueba la QA maestra. Este manual no se publica en
> la tienda: es la referencia del equipo y de la QA.

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
- **Los datos de pagador al eliminar la cuenta** (8 referencias): las facturas emitidas se conservan con su
  propia copia del pagador y lo demás se borra con la cuenta; solo lo que aún se puede cobrar retiene esos datos, y
  con fecha. Stripe recomienda, ante una petición de borrado, no tocar las facturas emitidas, anular las de
  suscripción que siguen abiertas y borrar el cliente (https://docs.stripe.com/privacy/deletion-requests);
  Atlassian borra los datos personales en 30 días y guarda solo lo de las compras que exige la contabilidad
  (https://support.atlassian.com/atlassian-account/docs/delete-your-atlassian-account/); Odoo borra salvo lo que
  la ley le obliga a guardar para facturación e impuestos (https://www.odoo.com/privacy); Holded borra o anonimiza
  al acabar los plazos legales (https://www.holded.com/es/politica-de-privacidad); Shopify y Square no cierran
  con una factura pendiente
  (https://community.shopify.com/t/to-close-your-store-all-outstanding-invoices-must-be-paid/244113,
  https://community.squareup.com/t5/Payments-Troubleshooting/Negative-Balance-Close-Account/m-p/698891); GitHub
  deja de cobrar al borrar la cuenta (https://docs.github.com/en/articles/deleting-your-user-account); Zoho pide
  cancelar las suscripciones y borra todo al cerrar
  (https://help.zoho.com/portal/en/kb/accounts/manage-your-zoho-account/articles/close-your-zoho-account). Aquí no
  se bloquea por una factura sin pagar de un negocio ya eliminado, que deja de cobrarse al eliminarlo: se espera a
  que se pague o se anule, 90 días como mucho (los que se guarda un negocio eliminado), porque la factura tiene que
  identificar a quién se emite (RGPD art. 17.3.b; Código de Comercio art. 30, Ley General Tributaria art. 66).
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
navegadores; **Sesiones de usuario** enseña quién ha entrado dónde («Cuenta», «Inicio de sesión», «Último uso»,
«Dirección IP» y «Navegador», en el idioma del personal), solo para leer, con «Cerrar las sesiones seleccionadas».
Las dos acciones solo las ve un superusuario.

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

### Cerrar la sesión de erplora.com
Adonde lleva «Cerrar sesión» de un negocio abierto en un dispositivo sin teclado de PIN, con el logo y «ERPlora
Cloud · Panel global» de la **Entrada**: «¿Cerrar la sesión de erplora.com?», «Sigues conectado a erplora.com en este
navegador como …», «Cerrar sesión» y «Seguir conectado».

### Menú del panel
«Negocios», «Tienda», «Facturación» y «Cuenta», con la de la página abierta marcada; arriba, la tarjeta de la
persona (el **Menú de usuario**) y abajo, el logo de ERPlora. En una pantalla ancha está siempre a la vista; en
una tableta o un móvil se abre con el botón del menú de la barra superior.

### Página de error
En la web pública, con su menú y su pie: «Página no encontrada» y «La página que buscas no existe o ha cambiado de
dirección.», o «Algo ha fallado» y «Algo ha fallado por nuestra parte. Vuelve a intentarlo en unos minutos.», con
«Volver a la página de inicio». En la parte privada (la cuenta y la entrada): «No hemos podido encontrar esta página»
o «Algo ha ido mal por nuestra parte», con «Inicio» y «Contactar Soporte».

### Página de mantenimiento
«503 · Mantenimiento», «Volvemos enseguida», «Estamos mejorando ERPlora. Vuelve en unos minutos; tus datos están a
salvo.» (o el mensaje que escribió el personal, en el idioma de quien visita), «Reintentar» y «Contactar Soporte».

### admin › Ajustes del sitio
Una sola ficha, «Ajustes del sitio», sin «Añadir» ni «Eliminar»: la casilla «modo mantenimiento», el «mensaje en
inglés» y el «mensaje en español» (vacío, quien visita en español lee el de inglés), y la fecha del último cambio.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | El botón de enviar se apaga mientras va la petición, también «Descargar mis datos» mientras prepara el fichero; el perfil y las preferencias, sus tarjetas cargando; el enlace del correo dice «Comprobando tu enlace…»; los ajustes de la verificación en dos pasos, «Cargando…»; las sesiones, la tabla cargando. |
| Vacío | Sin sesión, toda página del panel lleva a la **Entrada**, que vuelve a ella tras entrar. Con esta sesión sola, «Cerrar las demás sesiones» está apagado; sin códigos de recuperación, «Sin ellos, perder tu autenticador te bloquea el acceso a tu cuenta.» con «Generar códigos de recuperación». |
| Error | Cada error sale debajo de su campo, con las palabras de la regla que falla («La contraseña nueva tiene que ser distinta de la actual.»); un fallo de red, «No hemos podido iniciar tu sesión. Vuelve a intentarlo.» o «Algo ha ido mal. Inténtalo de nuevo.». Los ajustes que no cargan, «No hemos podido cargar tu configuración de seguridad. Vuelve a intentarlo.» con «Reintentar»; las sesiones, «No hemos podido cargar tus sesiones» con «Reintentar»; el perfil, «No hemos podido cargar tu cuenta», y las preferencias, «No hemos podido cargar tus preferencias», con «Reintentar». Un cambio de preferencias que no se guarda vuelve a como estaba. |
| Freno | «Demasiados intentos fallidos. Inténtelo más tarde.» o «Demasiados intentos. Espera unos minutos y vuelve a intentarlo.», igual exista o no la cuenta; si Google no ve una persona, «No hemos podido comprobar que eres una persona. Vuelve a intentarlo.». |
| Enlace caducado | «Este enlace de restablecimiento ha expirado o no es válido.» con «Solicitar Nuevo Enlace». |
| Código caducado | La entrada dice «Tu código ha caducado o se ha escrito mal demasiadas veces. Vuelve a iniciar sesión y te enviaremos uno nuevo.» |
| Mantenimiento | Quien no es del personal ve la **Página de mantenimiento** en cualquier página de erplora.com; el personal con su sesión abierta sigue usándolo todo. |
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
| ACCOUNTS-F27 | Eliminar mi cuenta | hecho |
| ACCOUNTS-F28 | Entrar en mi negocio desde erplora.com | hecho |
| ACCOUNTS-F29 | Volver a erplora.com desde mi negocio | hecho |
| ACCOUNTS-F30 | Abrir mi cuenta sola desde la aplicación | hecho |
| ACCOUNTS-F31 | Crear una clave de API | hecho |
| ACCOUNTS-F32 | Usar una clave de API: qué abre y qué no | hecho |
| ACCOUNTS-F33 | Revocar una clave de API | hecho |
| ACCOUNTS-F34 | Consultar la documentación de la API | hecho |
| ACCOUNTS-F35 | Borrar las cuentas sin uso en dos años | hecho |
| ACCOUNTS-F36 | Ver quién cambió una cuenta | hecho |
| ACCOUNTS-F37 | Borrar el registro de auditoría de más de 90 días | hecho |
| ACCOUNTS-F38 | Reportar un problema a soporte | hecho |
| ACCOUNTS-F39 | Dejar cargar en cada página solo lo de erplora.com | hecho |
| ACCOUNTS-F40 | Guardar en el registro lo que pasa, sin datos personales ni secretos | hecho |
| ACCOUNTS-F41 | Arrancar erplora.com y atender cada petición | hecho |
| ACCOUNTS-F42 | Enseñar una página de error | hecho |
| ACCOUNTS-F43 | Poner erplora.com en mantenimiento | hecho |
| ACCOUNTS-F44 | Limpiar cada día las sesiones caducadas y los códigos vencidos | hecho |
| ACCOUNTS-F45 | Frenar el exceso de peticiones | hecho |
| ACCOUNTS-F46 | Mandar los correos de erplora.com | hecho |
| ACCOUNTS-F47 | Moverse por el panel | hecho |
| ACCOUNTS-F48 | Pasar la QA maestra de erplora.com | parcial |

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
Si falla: una contraseña que no pasa las reglas sale debajo de la contraseña y no se crea nada; un correo no válido (también con letras de ancho completo antes de la arroba), debajo del correo. Un correo que ya tiene cuenta responde igual que uno nuevo y a su buzón le llega «ya existe una cuenta con esa dirección de correo electrónico» con el enlace para poner contraseña, sin código: así pone la suya también la persona invitada, cuya cuenta aún no tiene contraseña, y nadie se queda con una cuenta ajena. Más de 10 altas en una hora desde la misma dirección de red: «Demasiados intentos. Espera unos minutos y vuelve a intentarlo.».
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
Si falla: una contraseña actual equivocada, debajo de su campo, y la nueva no se guarda; la nueva igual a la actual, «La contraseña nueva tiene que ser distinta de la actual.»; una que no pasa las reglas, sus avisos. Los avisos salen en el idioma de la cuenta. Más de 5 intentos por minuto, «Demasiados intentos…» sin mirar la contraseña, ni la buena: una sesión ajena abierta no sirve para adivinarla. Una cuenta sin contraseña (entró con Google) ve «Crear contraseña», que le manda el enlace de ACCOUNTS-F07. Hoy los negocios aún no atienden el aviso (llega en la fase 2): una sesión abierta en un negocio sigue hasta que caduca.
Implicados: hubs (cada negocio cierra las sesiones de la cuenta)

### ACCOUNTS-F09 Cerrar la sesión
<!-- origen: old-saas:SAAS_AUTH-F11 -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Menú de usuario, Entrada, Cerrar la sesión de erplora.com
Pasos:
1. En el panel, la persona abre el **Menú de usuario** (en el móvil, dentro del menú) y pulsa «Cerrar sesión»; en la **Entrada** con sesión, «Cerrar sesión» está bajo su cuenta.
2. La sesión de ese navegador se cierra y vuelve la **Entrada**, lista para entrar.
3. Una página del panel abierta después lleva a la **Entrada**.
4. Desde un negocio, en un dispositivo sin teclado de PIN, su «Cerrar sesión» cierra la del negocio y abre **Cerrar la sesión de erplora.com**: «Cerrar sesión» cierra también esta, como en el paso 2; «Seguir conectado» la deja abierta y vuelve la **Entrada** con los negocios de la cuenta. Sin sesión, lleva a la **Entrada**.
Entra: la sesión del navegador.
Sale: la sesión de ese navegador cerrada. Las demás sesiones, las llaves de API y los negocios no se tocan: para cerrar otras está **Cuenta › Seguridad**.
Si falla: si no se pudo cerrar, «No se ha podido cerrar la sesión. Inténtalo de nuevo.» y sigue dentro. Un enlace suelto no cierra ninguna sesión: abrir **Cerrar la sesión de erplora.com** solo pregunta.
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
Pantalla: Entrada, Revisa tu correo, Restablece tu contraseña, Establece una nueva contraseña, Verificación en dos pasos
Pasos:
1. Antes de nada, si la comprobación de Google está encendida, Google comprueba sin que se vea (sin casilla ni puzle) que quien envía el formulario es una persona: entrar, crear la cuenta, pedir el enlace de restablecer, la contraseña nueva del enlace, el código del correo y «Enviar un código nuevo», el código de cada entrada y el de la app autenticadora. Debajo de cada uno, «Este sitio está protegido por reCAPTCHA y se aplican la Política de Privacidad y las Condiciones del Servicio de Google.». Desde el 2026-10-23 está apagada por defecto (el cortafuegos de la red frena el tráfico sospechoso antes de llegar): los formularios no cargan nada de Google ni muestran ese aviso, y los frenos de abajo siguen igual. «Continuar con Google» no pasa por aquí: lo comprueba Google.
2. Cada contraseña equivocada gasta del presupuesto de su cuenta y del de la dirección de red (5 en 5 minutos cada uno); agotado, ni la buena entra hasta que pasa el plazo. Una entrada buena devuelve su intento: el dueño no gasta presupuesto.
3. Antes de mirar la contraseña, cada dirección de red tiene 30 entradas por minuto.
4. Los códigos del correo admiten 3 intentos; el de la entrada dura 3 minutos. Además, cada dirección de red tiene 10 códigos rechazados en 5 minutos, del correo o de la app autenticadora; uno bueno no gasta.
5. Los enlaces de restablecer, 10 por hora por dirección de red y 5 por hora por cuenta; el formulario del enlace, 20 envíos por minuto por dirección; un código nuevo, uno cada 10 segundos por cuenta; las altas, 10 por hora por dirección; el cambio de contraseña, 5 por minuto por cuenta.
Entra: el correo que se prueba, la dirección de red de quien llama y, con la comprobación encendida, el visto bueno de Google.
Sale: la respuesta de freno, la misma exista o no la cuenta y con el mismo número de intentos: «Demasiados intentos fallidos. Inténtelo más tarde.» en la **Entrada** o «Demasiados intentos. Espera unos minutos y vuelve a intentarlo.»; con la comprobación encendida, si Google no ve una persona, «No hemos podido comprobar que eres una persona. Vuelve a intentarlo.» y no se hace nada.
Si falla: si la memoria compartida de los contadores no responde, el freno se abre (la puerta sigue usable) y queda un aviso en el registro. Con la comprobación encendida, si Google no contesta, entrar, el código de la entrada y el de la app autenticadora siguen (ya los guardan la contraseña, el código y los frenos) y queda un error en el registro; el resto de formularios se rechaza con el mensaje de arriba.
Implicados: ninguno

### ACCOUNTS-F12 Saber quién ha entrado
<!-- origen: fi:saas/auth-services#perfil-del-usuario-actual-me fi:saas/support/auth-services#serializer-userserializer old-saas:SAAS_AUTH-F29 -->
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
2. Al pulsarla se abre el **Menú de usuario**: «Cuenta», «Reportar un problema», «Ayuda», «Tema» y «Cerrar sesión».
3. «Cuenta» lleva a **Cuenta › Perfil**, desde donde están **Seguridad**, **Preferencias** y **Claves de API**; «Reportar un problema», a ACCOUNTS-F38; «Ayuda», a la ayuda; «Tema», a ACCOUNTS-F24; «Cerrar sesión», a ACCOUNTS-F09.
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
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Cuenta › Perfil
Pasos:
1. En **Cuenta › Perfil**, la tarjeta «Eliminar tu cuenta» dice de entrada si algo la retiene: si es propietaria de un negocio, «Eres propietario de 1 negocio: transfiérelo o elimínalo antes de borrar la cuenta.» con el nombre del negocio, que lleva a sus ajustes; si paga el negocio de otra persona (con sus datos de pago, o porque tras un traspaso su plan se sigue cobrando en su tarjeta), que su propietario ponga sus datos de pago. Mientras tanto «Eliminar cuenta» está apagado.
2. Sin nada que la retenga, pulsa «Eliminar cuenta»: el diálogo dice qué se borra (la cuenta, la foto, las preferencias y las claves de API, y todas las sesiones, también en las apps y en sus negocios), que no se puede deshacer y que «Tus facturas de ERPlora se conservan el tiempo que exige la ley.».
3. Escribe su correo para confirmar y pulsa «Eliminar cuenta». Si su última entrada no es reciente, antes confirma que es ella: con su contraseña o, si solo entra con Google, entrando otra vez con Google.
4. La sesión se cierra y llega a la web pública.
Entra: el correo escrito y, si hace falta, la contraseña o Google.
Sale: la cuenta borrada, con su foto, sus preferencias, sus claves y todas sus sesiones, aquí y en sus negocios; deja de ser miembro de los negocios de otros. Sus facturas de ERPlora se quedan, con el destinatario de la fecha de emisión y sin enlace a la cuenta. Sus datos de pagador (nombre fiscal, NIF, dirección y correo de facturación) y su cliente de pago se borran en el momento si ya no queda nada por cobrar; si queda una factura de ERPlora sin pagar, se guardan hasta que se pague o se anule y 90 días como mucho, y ese día la factura pendiente se anula y se borran. Evento `accounts.profile.deleted`.
Si falla: un negocio propio o pagado la retiene (el diálogo lo dice igual si cambió mientras); quien paga un negocio tampoco puede ser quitado de él, así que no hay forma de dejar de verlo y seguir pagándolo; un negocio eliminado, en sus 90 días para recuperarlo, ya no la retiene. Más de 10 contraseñas en un minuto al confirmar se frenan, ni la buena entra: una sesión ajena abierta no sirve para adivinarla. Un fallo de red se dice en el diálogo y no se borra nada.
Implicados: hubs (los negocios que la retienen y los que deja), billing (las facturas que se conservan y los datos de pagador que se borran)

### ACCOUNTS-F28 Entrar en mi negocio desde erplora.com
<!-- origen: old-saas:SAAS_AUTH-F19 old-saas:SAAS_AUTH-F20 gh:saas#2544 -->
Estado: hecho
Actor: cualquier persona con cuenta y miembro de un negocio
Pantalla: Entrada, el negocio, Entrada › error de entrada
Pasos:
1. La persona abre su negocio: con «Abrir» en la **Entrada** o en **Negocios**, o escribiendo la dirección de su negocio. El negocio la manda a erplora.com con una marca de ese navegador.
2. Si ya tiene sesión en erplora.com, erplora.com comprueba que es miembro de ese negocio y la devuelve a él con un pase de un solo uso, sin enseñarle nada.
3. Si no la tiene, la **Entrada** le pide entrar (con su correo, su contraseña y el código del correo, o con Google; ACCOUNTS-F04 y ACCOUNTS-F06) y, ya dentro, sigue sola hacia el negocio.
4. El negocio canjea el pase con erplora.com, abre su propia sesión y la persona aparece dentro, en la página a la que iba.
Entra: el negocio al que va, la página a la que iba dentro de él y la marca del navegador que empezó el salto.
Sale: un pase que vale un minuto, sirve una sola vez y solo para ese negocio; viaja escondido en un formulario, nunca en la dirección, y la página que lo lleva no se guarda ni se cuenta a otras webs. El negocio recibe quién entra (ACCOUNTS-F12) y abre su propia sesión, que no comparte nada con la de erplora.com.
Si falla: si no es miembro de ese negocio, «No tienes acceso a este hub», que nombra solo la dirección del negocio, nunca su nombre, con «Volver al hub» y «Contactar Soporte»; un enlace que no lleva a ningún negocio, «Este enlace de acceso no lleva a ningún hub». Más de 20 saltos en 5 minutos, «Demasiados intentos» con «Has abierto tus negocios demasiadas veces en pocos minutos. Espera unos minutos y vuelve a abrir tu negocio.», sin pase. Un pase caducado, ya usado, de otro negocio o que no canjea el propio negocio no abre nada, y el negocio no deja entrar a un navegador que no empezó el salto. Con la verificación en dos pasos encendida y la app autenticadora activa, antes pide el código de la app.
Implicados: hubs (los negocios de la persona y «Abrir»)

### ACCOUNTS-F29 Volver a erplora.com desde mi negocio
<!-- origen: old-saas:SAAS_AUTH-F21 -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Entrada, Cuenta, Negocios
Pasos:
1. Dentro de su negocio, la persona pulsa un enlace a erplora.com: gestionar su cuenta, su negocio o su plan.
2. Si ese navegador tiene su sesión de erplora.com (la que usó para entrar en el negocio), la página se abre sin pedirle nada.
3. Si no la tiene (otro navegador, el de la aplicación, o la sesión se cerró), la **Entrada** le pide entrar y, ya dentro, la lleva a esa misma página.
Entra: la página de erplora.com a la que va (solo páginas de erplora.com).
Sale: la página abierta con su sesión de erplora.com. El negocio no le pasa ninguna credencial a erplora.com: cada uno guarda su propia sesión.
Si falla: una dirección que no es de erplora.com no se sigue después de entrar: lleva a la **Entrada** con su sesión. Cerrar la sesión de erplora.com no cierra la del negocio (ACCOUNTS-F09).
Implicados: hubs (los enlaces del negocio a erplora.com)

### ACCOUNTS-F30 Abrir mi cuenta sola desde la aplicación
<!-- origen: old-saas:SAAS_DASHBOARD-F209 -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Cuenta › Perfil
Pasos:
1. En la aplicación instalada, la persona pulsa gestionar su cuenta en erplora.com: la aplicación abre la dirección de la cuenta que ya conocía, con la marca de la cuenta sola.
2. erplora.com la lleva a **Cuenta › Perfil** sin perder la marca; las direcciones antiguas de las sesiones y de las preferencias llevan a **Cuenta › Seguridad** y a **Cuenta › Preferencias**.
3. Sin sesión en ese navegador, la **Entrada** le pide entrar y después vuelve a la cuenta con la marca.
4. La cuenta se pinta sin nada que venda: el menú no tiene «Tienda». Desde ahí cambia su perfil, su contraseña, sus sesiones, sus preferencias y sus claves de API, y puede eliminar la cuenta.
Entra: la marca de la cuenta sola.
Sale: la cuenta abierta sin lo que vende; la marca se queda en la sesión de ese navegador hasta que se cierra.
Si falla: sin la marca, la misma dirección abre la cuenta del panel de siempre, con «Tienda».
Implicados: ninguno

### ACCOUNTS-F31 Crear una clave de API
<!-- origen: old-saas:SAAS_AUTH-F23 -->
Estado: hecho
Actor: cualquier persona con cuenta; un superusuario del personal, para una cuenta del equipo
Pantalla: Cuenta › Claves de API, admin › Cuentas › Claves de API
Pasos:
1. En **Cuenta › Claves de API**, la persona pulsa «Nueva clave»: «Nueva clave de API» pide el «Nombre», sus «Permisos» («Negocios · lectura», «Negocios · escritura», «Facturas · lectura») y cuándo «Caduca» («En 90 días», «En 30 días» o «Nunca»).
2. Si su última entrada no es reciente, antes confirma que es ella con su contraseña (o entrando otra vez con Google).
3. Pulsa «Crear clave»: ve la clave entera una sola vez, con «Copiar la clave» y «Cópiala ahora y guárdala en un sitio seguro: no la volverás a ver.»; con «Ya la he guardado», la ventana se cierra, avisa «Clave creada: «…»» y la clave queda en la lista solo con su principio.
4. Un superusuario del personal crea una clave para una cuenta del equipo desde el admin, con «Añadir clave de API»: elige la cuenta, el nombre, los permisos y la caducidad, y la página le enseña la clave una sola vez, «Cópiala ahora: no se volverá a mostrar.».
Entra: el nombre, los permisos, la caducidad y, si hace falta, la contraseña.
Sale: la clave, que actúa como su cuenta y solo con sus permisos; erplora.com guarda solo su huella y su principio. A la cuenta le llega el correo «Nueva clave de API en tu cuenta de ERPlora», sin la clave. Evento `accounts.apikey.created`.
Si falla: sin nombre, «Ponle un nombre: es como distinguirás tus claves.»; un permiso que no existe, «Permiso desconocido: …»; con 50 claves que aún valen, «Ya tienes 50 claves de API: revoca una que ya no uses.». Una clave no se vuelve a enseñar, ni en la lista ni en el admin. Desde el admin no se crea para la cuenta de un cliente, que crea las suyas, y el soporte no crea ninguna. Una clave no sirve para crear claves ni para gestionar la cuenta.
Implicados: ninguno

### ACCOUNTS-F32 Usar una clave de API: qué abre y qué no
<!-- origen: old-saas:SAAS_AUTH-F24 -->
Estado: hecho
Actor: un programa con la clave de una cuenta
Pantalla: ninguna (la API de erplora.com)
Pasos:
1. Un programa (Postman, una integración, un guion) llama a la API de erplora.com con la clave en su cabecera.
2. erplora.com busca la clave por su principio, compara su huella y comprueba que no está revocada ni caducada y que su cuenta sigue activa.
3. La llamada pasa a ser de esa cuenta: ve lo que ve su cuenta, nada de otras, y solo lo que abren sus permisos: «Negocios · lectura» lee sus negocios y «Facturas · lectura», sus facturas de ERPlora.
4. Lo demás de la API (la cuenta, sus sesiones y sus claves, y lo que no se ofrece a las claves) se niega a cualquier clave.
Entra: la clave.
Sale: la respuesta, como si llamara su cuenta; el último uso de la clave se apunta como mucho cada 10 minutos.
Si falla: una clave que no existe, revocada, caducada o de una cuenta desactivada, «Clave de API no válida.»; sin el permiso, «A esta clave de API le falta el permiso que pide esta operación: …»; en lo que no se ofrece a las claves, «Aquí no se pueden usar claves de API: esta operación es solo para personas con la sesión iniciada.». Más de 600 llamadas por minuto con una clave, o más de 30 claves equivocadas por minuto desde la misma dirección, «Demasiadas peticiones. Vuelve a intentarlo en un minuto.». Una cabecera vacía es como no llevar clave.
Implicados: hubs (sus negocios), billing (sus facturas)

### ACCOUNTS-F33 Revocar una clave de API
<!-- origen: old-saas:SAAS_AUTH-F25 -->
Estado: hecho
Actor: cualquier persona con cuenta; un superusuario del personal
Pantalla: Cuenta › Claves de API, admin › Cuentas › Claves de API
Pasos:
1. En **Cuenta › Claves de API**, la persona pulsa «Revocar» en la fila de la clave: «Revocar «…»» dice «Lo que use esta clave dejará de funcionar al momento. No se puede deshacer: tendrías que crear otra.».
2. Confirma con «Revocar clave»: «Clave revocada: «…»» y la clave sale de la lista.
3. Ante un incidente, un superusuario del personal busca la clave en el admin (por su nombre, su principio o su cuenta; cada fila dice sus «Permisos» con las palabras de la cuenta, como «Negocios · lectura»), la marca y elige «Revocar las claves seleccionadas (dejan de funcionar al momento)»: «Claves revocadas: 1.».
Entra: la clave elegida.
Sale: la clave no abre nada desde la siguiente llamada; su fila se queda como rastro, con la fecha en que se revocó, y la lista de su cuenta se actualiza sola. No hay «rotar»: se crea otra y se revoca la vieja. Evento `accounts.apikey.revoked`.
Si falla: revocarla dos veces no cambia nada; la clave de otra cuenta no se encuentra («Esa clave de API no existe.»). Revocar no pide la contraseña. El soporte ve las claves sin poder revocarlas.
Implicados: ninguno

### ACCOUNTS-F34 Consultar la documentación de la API
<!-- origen: old-saas:SAAS_DASHBOARD-F197 fi:saas/auth-services#docs-de-api-swagger-openapi-redoc-gated -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Cuenta › Claves de API, Documentación de la API
Pasos:
1. En **Cuenta › Claves de API**, bajo la lista, la persona pulsa «Documentación de la API»: se abre en otra pestaña.
2. La documentación enseña cada parte de la API (la cuenta, los negocios, las facturas…), con sus llamadas, lo que piden y lo que contestan, y un buscador. Está en inglés, como la propia API.
3. Para probar la API desde un programa, descarga el esquema desde la propia documentación y lo abre en Postman con una clave de API (ACCOUNTS-F31).
Entra: la sesión.
Sale: nada guardado. La documentación es solo para leer: no hace llamadas con los datos de la cuenta.
Si falla: sin sesión, la **Entrada** le pide entrar y después vuelve a la documentación; una clave de API sola no la abre. Si el esquema no carga, «No hemos podido cargar la documentación de la API. Recarga la página para volver a intentarlo.». El esquema en sí es público, como los de Stripe y GitHub, para que Postman lo importe.
Implicados: ninguno

### ACCOUNTS-F35 Borrar las cuentas sin uso en dos años
<!-- origen: old-saas:SAAS_AUTH-F15 fi:saas/auth-services#comando-anonimizar-usuarios-inactivos-gdpr fi:saas/support/auth-services#command-anonymize_old_users fi:saas/support/auth-services#task-anonymize_old_users_task -->
Estado: hecho
Actor: sistema
Pantalla: ninguna (una tarea semanal de erplora.com)
Pasos:
1. Una vez por semana, erplora.com busca las cuentas activas que no son del personal y que no han entrado en erplora.com en dos años (o que nunca entraron y se crearon hace más de dos años).
2. Se salta las que pertenecen a un negocio que no está eliminado, como propietarias, pagadoras o miembros: quien trabaja a diario en su negocio no pasa por erplora.com y parecería sin uso.
3. Cada una de las demás se borra como cuando su dueña elimina la cuenta (ACCOUNTS-F27): con su foto, sus preferencias, sus claves de API, sus direcciones de correo, su cuenta de Google enlazada y todas sus sesiones, aquí y en los negocios.
4. Las facturas de ERPlora se quedan, con el destinatario de la fecha de emisión y sin enlace a la cuenta.
Entra: la fecha de la última entrada en erplora.com (o la del alta) de cada cuenta.
Sale: las cuentas sin uso borradas, cada una con su evento `accounts.profile.deleted` en su propio canal; ninguna otra cuenta cambia. Justo antes de borrarla, la cuenta se vuelve a leer: si ha entrado entre medias, se queda.
Si falla: una cuenta que no se puede borrar queda en el registro (por su identificador, nunca por su correo) y la tarea sigue con las demás; al acabar, la tarea termina con error para que el equipo lo vea, y esa cuenta se vuelve a intentar a la semana siguiente. Si ya hay una pasada en marcha, la segunda no hace nada. El equipo puede contar lo que se borraría sin borrar nada.
Implicados: hubs (los negocios que retienen la cuenta), billing (las facturas que se quedan)

### ACCOUNTS-F36 Ver quién cambió una cuenta
<!-- origen: fi:saas/support/auth-services#auditlog-registro-user fi:saas/support/orgs-users#service-auditlog-registro-gdpr -->
Estado: hecho
Actor: superusuario de ERPlora (o alguien del equipo con permiso para ver el registro)
Pantalla: el admin de erplora.com › «Registro de auditoría»
Pasos:
1. Cada cambio de una cuenta (nombre, correo, idioma, si está activa, si es del equipo), de su acceso a un negocio y de sus claves de API (crearla, revocarla), cada sesión que se abre y cada cambio de lo que se cobra y de la documentación fiscal (la suscripción de un negocio y sus apps de pago, su pagador, sus facturas y su estado en VeriFactu, un cobro que falla, una compra en curso, un cambio de plan que espera, los precios de los planes y de las apps, las reglas de IVA, los datos de ERPlora en las facturas, los códigos promocionales, la autorización firmada de un negocio y su revisión, y el sello de ERPlora) queda anotado: qué cambió, de qué valor a cuál, cuándo, quién lo hizo y desde qué dirección.
2. El superusuario abre «Registro de auditoría» en el admin, filtra por tipo de recurso o busca por correo, y abre una entrada para ver sus cambios.
3. Nadie puede crear, cambiar ni borrar una entrada a mano: solo se leen.
Entra: los cambios de las cuentas, de lo que se cobra y de la documentación fiscal, hechos desde el panel, con una clave de API, desde el admin, por las tareas de erplora.com o por Stripe al cobrar.
Sale: una entrada por cambio, que nombra a quien actuaba en ese momento (la cuenta con la sesión abierta o la dueña de la clave de API; nadie en una tarea de erplora.com o tras cerrar la sesión) y la dirección real del visitante, nunca la que diga su navegador.
Si falla: nunca se anota un secreto (ni la contraseña, ni la clave de API, ni la de una sesión, ni la de una compra con Stripe, ni el enlace que abre una factura de Stripe, ni los documentos de una autorización ni el sello) ni lo que se mueve solo (la última entrada, el último uso de una clave, la última vez que se vio una sesión, los contadores, los reintentos de envío de una factura a la AEAT). Anotar un cambio nunca cambia una factura ni su registro en VeriFactu. Si la cuenta se elimina, sus entradas se quedan con su correo y sin enlace a ella hasta que se borran a los 90 días (ACCOUNTS-F37). Alguien del equipo sin el permiso no puede abrirlo.
Implicados: ninguno

### ACCOUNTS-F37 Borrar el registro de auditoría de más de 90 días
<!-- origen: fi:saas/auth-services#comando-limpiar-logs-antiguos-gdpr fi:saas/support/auth-services#command-cleanup_old_logs fi:saas/support/auth-services#task-cleanup_old_logs_task fi:saas/auth-services#tareas-gdpr-retencion-de-datos -->
Estado: hecho
Actor: sistema
Pantalla: ninguna (una tarea diaria de erplora.com)
Pasos:
1. Una vez al día, erplora.com borra por tandas las entradas del registro de auditoría (ACCOUNTS-F36) de hace más de 90 días.
2. Las de los últimos 90 días se quedan, también las de una cuenta ya eliminada.
Entra: la fecha de cada entrada del registro.
Sale: el registro con solo los últimos 90 días; nada más cambia.
Si falla: si una tanda no se puede borrar, la tarea termina con error para que el equipo lo vea; lo borrado antes se queda borrado y la pasada siguiente sigue desde ahí. Si ya hay una pasada en marcha, la segunda no hace nada. El equipo puede contar lo que se borraría sin borrar nada, y cambiar los días que se guardan.
Implicados: ninguno

### ACCOUNTS-F38 Reportar un problema a soporte
<!-- origen: old-saas:SAAS_DASHBOARD-F219 fi:saas/assistant-help#reportar-un-problema-contacto-de-soporte -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Reportar un problema
Pasos:
1. En el **Menú de usuario**, «Reportar un problema» (también en la cuenta abierta desde la aplicación). La pantalla dice «Cuéntanos qué ha fallado. Te responderemos por correo electrónico.».
2. Escribe «Asunto» y «¿Qué pasó?» («Describe los pasos y lo que esperabas que pasara») y pulsa «Enviar informe», que espera a que los dos estén escritos. Debajo, la pantalla avisa: «Con tu informe van tu cuenta, tus negocios, la página de la que vienes y tu navegador.».
3. Ve «Informe enviado», con el correo al que soporte le responderá, y «Volver», que lleva a la pantalla de la que venía.
4. Desde un negocio, «Reportar un problema» del menú de usuario del hub abre lo mismo en una ventana, sin salir del negocio, a quien entró con su cuenta (nunca con un PIN): el informe llega igual, con el negocio desde el que se envía (BASE-F108).
Entra: el asunto y lo que pasó.
Sale: un correo al buzón de soporte con el asunto, el texto y, debajo, la cuenta, sus negocios, de dónde llega (el panel o el hub, y desde el hub, el negocio), la pantalla de la que venía y su navegador; al contestar, soporte escribe directamente a la persona. No se guarda nada en erplora.com ni se abre ninguna incidencia.
Si falla: «Añade un asunto.» o «Describe el problema, por favor.» bajo su campo; tras cinco informes en una hora, «Demasiados intentos. Vuelve a intentarlo en unos minutos.» (el límite cuenta los del panel y los del hub juntos); si el correo no sale, un aviso con la dirección de soporte para escribir directamente. En todos los casos lo escrito se queda y se puede volver a enviar.
Implicados: el hub (su menú de usuario, BASE-F108)

### ACCOUNTS-F39 Dejar cargar en cada página solo lo de erplora.com
<!-- origen: fi:saas/auth-services#content-security-policy-estricta-sin-unsafe-eval -->
Estado: hecho
Actor: sistema
Pantalla: ninguna (cada página del panel y de la web pública)
Pasos:
1. Cada página de erplora.com le dice al navegador qué puede cargar y ejecutar en ella: los programas, los estilos, las letras y las imágenes del propio erplora.com, y solo los programas que la página marca como suyos al servirla. Nada de bibliotecas de otros servidores.
2. El panel admite además lo que necesitan sus pagos con Stripe y la entrada con Google, y sus formularios solo envían a erplora.com, a Google y a los negocios. Ninguna página del panel se puede meter dentro de otra web; la web pública, solo dentro de erplora.com.
3. El admin de erplora.com sigue la lista del panel, salvo la regla que su propio código no cumple, para que todos sus controles funcionen.
4. La aplicación instalada sigue hablando con su impresora y su cajón desde cualquier página.
5. Si el navegador bloquea algo, se lo cuenta a erplora.com.
Entra: la página que se sirve.
Sale: nada guardado: la lista viaja con cada página. Lo que el navegador bloquea queda en el registro de erplora.com.
Si falla: lo que no está en la lista no se carga ni se ejecuta, aunque alguien lo cuele en la página; los avisos de un mismo navegador se frenan a 60 por hora (ACCOUNTS-F45).
Implicados: public (la web pública)

### ACCOUNTS-F40 Guardar en el registro lo que pasa, sin datos personales ni secretos
<!-- origen: fi:saas/auth-services#formatter-de-logging-gdpr-safe fi:saas/support/public-core-config#service-logging-py-gdprsafeformatter-sensitivedatafilter -->
Estado: hecho
Actor: sistema
Pantalla: ninguna (el registro de erplora.com que lee el equipo)
Pasos:
1. Cada línea que erplora.com escribe en su registro pasa antes por un filtro.
2. El filtro tapa los correos, los teléfonos, el NIF, el NIE y el CIF, el IBAN, los números de tarjeta, las contraseñas (también la de una dirección de conexión) y las claves de API, de Stripe, de sesión y de acceso, cada una con una marca que dice qué había.
3. Lo demás se queda tal cual: los nombres de los avisos de erplora.com, los identificadores y las cifras, para que el equipo pueda seguir lo que pasó.
Entra: cada línea del registro.
Sale: la línea con lo personal y lo secreto tapado; nada más cambia. Un intento de entrada fallido se registra entero, salvo la contraseña.
Si falla: ninguna línea se tira por llevar un secreto: se tapa y se escribe. Una línea enorme o hecha para atascar el filtro se limpia sin frenar el registro.
Implicados: ninguno

### ACCOUNTS-F41 Arrancar erplora.com y atender cada petición
<!-- origen: fi:saas/auth-services#settings-asgi-wsgi-y-monedas fi:saas/support/public-core-config#asgi-py-wsgi-py fi:saas/support/public-core-config#settings-py -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. erplora.com arranca con los ajustes de su entorno (producción, pre o el ordenador de quien programa): los secretos, la base de datos, la caché y el correo salen del entorno, nunca del código.
2. Atiende cada petición detrás del balanceador de AWS, que le dice si llegó cifrada; en producción las cookies solo viajan cifradas y el navegador se queda en la versión cifrada.
3. Una conexión en tiempo real que nadie ha pedido (un WebSocket) se cierra limpia, sin dejar un error en el registro.
4. Cobra en euros: los planes y Stripe usan esa moneda y no hay otra que elegir.
Entra: los ajustes del entorno del despliegue.
Sale: el servicio en marcha; nada guardado.
Si falla: sin una clave obligatoria (la de los documentos fiscales en producción) no arranca y dice cuál falta. Con la caché caída, los frenos dejan pasar y todo sigue funcionando. Con la base de datos caída, la comprobación de vida sigue contestando y la de «preparado» avisa.
Implicados: ninguno

### ACCOUNTS-F42 Enseñar una página de error
<!-- origen: fi:saas/auth-services#urlconf-raiz-handlers-de-error-branding-admin old-saas:SAAS-F09 -->
Estado: hecho
Actor: cualquiera
Pantalla: Página de error, el admin de erplora.com
Pasos:
1. Quien llega a una dirección de la web pública que no existe ve «Página no encontrada» y «La página que buscas no existe o ha cambiado de dirección.», con el menú y el pie de la web y «Volver a la página de inicio».
2. En la parte privada (la cuenta, la entrada) ve «No hemos podido encontrar esta página», con «Inicio» y «Contactar Soporte».
3. Si erplora.com falla, la web pública enseña «Algo ha fallado» y «Algo ha fallado por nuestra parte. Vuelve a intentarlo en unos minutos.»; la parte privada, «Algo ha ido mal por nuestra parte». Las dos, en el idioma de quien visita.
4. El personal ve el admin con el nombre de ERPlora: «ERPlora Cloud» arriba y «Administración» en su portada.
Entra: la dirección pedida y el idioma de quien visita.
Sale: la página de error; nada guardado. Un programa conectado por la API recibe el error en su formato, nunca la página.
Si falla: la página del fallo se pinta aunque la base de datos esté caída: no lee nada de ella.
Implicados: public (sus páginas de error)

### ACCOUNTS-F43 Poner erplora.com en mantenimiento
<!-- origen: fi:saas/django-admin#admin-sitesettings-singleton fi:saas/support/orgs-users#modelo-sitesettings old-saas:SAAS-F11 -->
Estado: hecho
Actor: superusuario de ERPlora; cualquier visitante
Pantalla: admin › Ajustes del sitio, Página de mantenimiento
Pasos:
1. Un superusuario abre «Ajustes del sitio» en el admin (siempre la misma ficha: no hay otra que crear ni que borrar), marca el «modo mantenimiento» y, si quiere, escribe el «mensaje en inglés» y el «mensaje en español».
2. Al guardar, el admin dice «El modo mantenimiento está encendido: solo el personal de ERPlora con su sesión abierta usa erplora.com.».
3. Desde ese momento, quien visita erplora.com ve «Volvemos enseguida» con «Estamos mejorando ERPlora. Vuelve en unos minutos; tus datos están a salvo.» (o el mensaje del personal, en su idioma), «Reintentar» y «Contactar Soporte»; los buscadores entienden que la web vuelve pronto.
4. El personal con su sesión abierta sigue usándolo todo, y quien es del personal y no la tiene entra por la **Entrada** camino del admin, también con el código de su app autenticadora.
5. Al desmarcarlo, el admin dice «El modo mantenimiento está apagado: erplora.com está abierto a todo el mundo.» y todos vuelven a entrar.
Entra: el interruptor y los dos mensajes.
Sale: el interruptor guardado, que todos los servidores de erplora.com aplican al momento (y, si se perdiera el aviso, en un minuto como mucho). Siguen funcionando las comprobaciones de vida, el admin, las llamadas de los negocios y los avisos de Stripe y de Meta. Un programa conectado por la API recibe «ERPlora está en mantenimiento. Vuelve a intentarlo en unos minutos.».
Si falla: si el interruptor no se puede leer (la base de datos caída), erplora.com sigue abierto y el registro dice por qué. El mensaje del personal se enseña como texto, nunca como código. Una clave de API no cuenta como sesión del personal, ni una cuenta del personal desactivada.
Implicados: hubs (sus llamadas siguen), billing (los avisos de Stripe siguen), whatsapp (los avisos de Meta siguen)

### ACCOUNTS-F44 Limpiar cada día las sesiones caducadas y los códigos vencidos
<!-- origen: fi:saas/support/orgs-users#task-clearsessions_task-flush_expired_tokens_task-backup_database_task-rotate_backups_task-triage_error_report_task old-saas:SAAS-F08 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna (una tarea diaria de erplora.com)
Pasos:
1. Una vez al día, erplora.com borra las sesiones caducadas, las filas de «Sesiones activas» cuya sesión ya no existe (con su dirección y su navegador), los códigos de un solo uso del salto a un negocio pasados sus 60 segundos y los cambios de correo cuyo código pasó sus 15 minutos.
2. Lo vigente se queda: ninguna sesión abierta ni ningún código aún válido cambia.
3. Como las demás tareas de erplora.com, la lanza a su hora el reloj de la infraestructura; una tarea que falla deja su error a la vista del equipo y vuelve a correr en su siguiente turno.
Entra: la fecha de caducidad de cada sesión y de cada código.
Sale: lo caducado, borrado; nada se anota en el registro de auditoría.
Si falla: si ya hay una pasada en marcha, la segunda no hace nada; un fallo termina la tarea con error y lo borrado antes se queda borrado. El equipo puede contar lo que se borraría sin borrar nada.
Implicados: ninguno

### ACCOUNTS-F45 Frenar el exceso de peticiones
<!-- origen: old-saas:SAAS-F05 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada puerta que se puede abusar lleva su propio freno, contado por dirección o por cuenta: la entrada, los códigos y los enlaces (ACCOUNTS-F11), el salto a un negocio (ACCOUNTS-F28), las claves de API (ACCOUNTS-F32), reportar un problema (ACCOUNTS-F38), el formulario de contacto de la web y los avisos de seguridad del navegador (60 por hora y dirección).
2. Pasado el freno, la petición se rechaza sin hacer nada y la pantalla lo dice.
3. La dirección que cuenta es la real de quien llama, la que da el balanceador: una dirección escrita a mano en la petición no estrena contador, y el freno de una cuenta o de una clave no lo gasta otra.
Entra: la dirección o la cuenta de quien llama.
Sale: los contadores, en la caché que comparten los servidores; nada en la base de datos.
Si falla: con la caché caída, los frenos dejan pasar y erplora.com sigue funcionando. Un aviso de seguridad frenado no se escribe en el registro.
Implicados: public (el formulario de contacto)

### ACCOUNTS-F46 Mandar los correos de erplora.com
<!-- origen: old-saas:SAAS-F07 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Algo en erplora.com tiene que avisar a una persona: un código, un enlace, una invitación, una factura, un cambio en su negocio.
2. El correo lleva la marca de ERPlora, igual en todos: la franja de color arriba, el logo, el texto y el pie «Enviado por ERPlora» con el enlace a erplora.com. Un código va solo, en su recuadro, y los enlaces se pueden pulsar.
3. Cada correo va en dos versiones que dicen lo mismo, con formato y en texto, para que se lea en cualquier programa de correo, y en el idioma de quien lo recibe; los del equipo de ERPlora (los problemas reportados, el formulario de contacto, las autorizaciones por revisar), en el del equipo.
4. Del correo solo se descarga el logo, desde erplora.com: nada más se pide a otra web.
5. El correo sale desde la dirección de ERPlora por el servicio de correo de AWS.
6. Si el servicio no contesta, erplora.com espera unos segundos, nunca minutos, y lo vuelve a intentar una vez.
Entra: el aviso, sus datos, el destinatario y su idioma.
Sale: el correo enviado, con formato y en texto. En el ordenador de quien programa y en las pruebas, el correo se escribe en una carpeta y nunca sale.
Si falla: un correo que no sale lo trata quien lo pide (por ejemplo, reportar un problema enseña la dirección de soporte para escribir directamente) y la pantalla nunca se queda esperando.
Implicados: billing, fiscal y whatsapp (sus correos ya salen con la marca); hubs (los de las personas, las invitaciones y los roles de un negocio pasan a ella con su porte)

### ACCOUNTS-F47 Moverse por el panel
<!-- origen: old-saas:SAAS_DASHBOARD-F201 fi:saas/support/public-core-config#context_processors-py-config -->
Estado: hecho
Actor: cualquier persona con cuenta
Pantalla: Menú del panel
Pasos:
1. El menú del panel tiene «Negocios», «Tienda», «Facturación» y «Cuenta»; arriba, la tarjeta de la persona abre el **Menú de usuario** (ACCOUNTS-F25), y abajo está el logo de ERPlora.
2. En una pantalla ancha el menú está siempre a la vista; en una tableta o un móvil se abre con el botón del menú de la barra superior.
3. Cada entrada abre su página sin recargar el panel y queda marcada como la actual.
4. Las páginas que no son del panel (la entrada, las de error, la de mantenimiento) usan el tema de la persona, o el de su navegador si no ha entrado.
Entra: la sesión.
Sale: nada guardado.
Si falla: sin sesión, la **Entrada**, que vuelve a la página tras entrar.
Implicados: hubs («Negocios»), billing («Tienda» y «Facturación»)

### ACCOUNTS-F48 Pasar la QA maestra de erplora.com
<!-- origen: qa:shared/qa-saas -->
Estado: parcial — lo que la QA pide y aún falta ya es un flujo parcial de su app: el paquete de salida al eliminar un negocio y la medida de su uso (hubs), el umbral de ventas a distancia en la UE (billing), borrar lo creado dentro de una demo (public) y abrir el cajón al cobrar (impresión, en el Hub); las personas, las invitaciones y los roles de un negocio llegan con su porte en hubs
Actor: el equipo de QA de ERPlora
Pantalla: todas las de erplora.com
Pasos:
1. El equipo recorre erplora.com como un cliente nuevo: la web pública con sus planes (el Gratis como entrada, sin tarjeta) y la demo; crear la cuenta y confirmar el correo; crear el negocio gratuito con una sola pregunta y entrar en él; pasarlo a un plan de pago con una tarjeta de prueba de Stripe.
2. Comprueba en el panel lo que el cliente hace con sus negocios: verlos con su estado y su uso, cambiar de plan, reintentar un pago, cancelar, eliminar un negocio y recuperarlo.
3. Comprueba el cobro: las facturas con su IVA (también la inversión del sujeto pasivo dentro de la UE), los códigos promocionales que dan días de prueba y la vuelta a Gratis al terminar la suscripción.
4. Sobre un negocio real, vende y comprueba que el tique sale con su QR, firmado para la AEAT en su entorno de pruebas, y que se imprime.
Entra: el entorno pre y cuentas de prueba.
Sale: cada punto de la QA, con el flujo que lo cubre y su prueba automática en el navegador; lo que no tiene sentido en la plataforma de ahora queda fuera con su motivo (ver «Para quien lo mantiene»).
Si falla: un punto que ningún flujo cubre es un fallo de la QA y se apunta en la app que lo tiene.
Implicados: hubs, billing, public, apps y fiscal; del Hub, verifactu, invoice y printing

## Para quien lo mantiene

- Anatomía, operaciones y decisiones: `accounts/README.md` (allauth headless, puertas cerradas, sesiones,
  reautenticación, correo por código propio, foto, preferencias y llaves de API).
- Partes del porte (MIGRATION-TASK APP-ACCOUNTS-1…5): este WORKBOOK nace en la parte 1 (F01–F13); la parte 2
  (segundo factor, navegadores de confianza y sesiones) cierra F05 y añade F14–F20; la parte 3 (perfil,
  preferencias, avisos, menú de usuario, exportar y borrar la cuenta) añade F21–F27 y amplía F13; la parte 4
  (salto al Hub, llaves de API y su documentación, retención GDPR, auditlog y reportar un problema) añade F28–F38
  y amplía F12 y F25; la parte 5 (plataforma del SaaS) añade F39–F48.
- Equivalencia de claves del registro: G83, G124, G22 y G59 = F01; G84 y G21 = F02; G107 = F03; G85 y G17 =
  F04; G125 = F05; G86 = F06; G91, G123, G120, G121 y G122 = F07; G109, G92, G42, G45 y G46 = F08; G93 = F09;
  G119 = F10; G96 = F11; G20 y G58 = F12; G18 y G56 = F13. Parte 2: G60 = F04; G88, G12, G19, G55 y G57 =
  F05; G87, G02 y G126 = F14; G116 y G05 = F15; G89 y G03 = F16; G23, G16 y G48 = F17; G94, G110, G15, G50,
  G24 y G25 = F18; G09, G54, G37 y G34 = F19; G90 = F20. Parte 3: G108, G49, G43, G63, G66, G69, G70 y G118 =
  F21; G114, G39, G38, G44, G65 y G67 = F22; G115 = F23; G29, G11, G74 y G127 = F24; G128 = F25; G111 y G41 =
  F26; G112, G95, G40 y G47 = F27; G32, G35 y G36 = F13. Parte 4: G98 y G99 = F28; G104 = F12; G100 = F29;
  G113 = F30; G101 = F31; G102 = F32; G103 = F33; G105 y G13 = F34; G97, G07, G52 y G61 = F35; G51 y G68 = F36;
  G08, G53, G62 y G28 = F37; G117 y G01 = F38. Parte 5: G10 = F39; G14 y G76 = F40; G26, G72 y G77 = F41; G30 y
  G81 = F42; G33, G64 y G82 = F43; G71 y G80 = F44; G78 = F45; G79 = F46; G106 y G73 = F47; G129 = F48.
  Descartadas: G04 (activar o apagar el código por
  correo: se pide en toda entrada con contraseña y no se apaga, PLAN-SAAS ronda 19, §3.7 punto 3) y G31
  (el Hub verificaba en el SaaS un dispositivo de confianza: el Hub nunca consulta al SaaS por petición y
  sus dispositivos y su PIN son suyos, PLAN-SAAS §2). De la parte 5: G06 y G75 (el circuit breaker del viejo,
  `apps/core/circuit_breaker.py`: estado en memoria de cada proceso, solo alrededor de las llamadas a Stripe de sus
  webhooks; aquí cada llamada de fuera lleva su tiempo de espera corto y su error visible, Stripe con 10 s y un
  reintento (`billing/stripe_service.py`), VIES 3 + 5 s, Meta 5 + 15 s, la AEAT 5 + 30 s, el Hub 5 s, S3 2 + 3 s,
  IndexNow 15 s y SES 3 + 10 s, y un aviso de Stripe que falla lo reintenta Stripe; un breaker por proceso no se
  comparte entre tareas y no añade nada: simplicidad primero) y G27 (la etiqueta `{% card %}` del panel viejo: el
  panel es la SPA, con sus componentes de `@erplora/ui`, y la web pública pinta sus tarjetas con sus parciales de
  `public/templates/public/components/`, ronda 16). Las dos chocan con PLAN-SAAS §6 («Utilidades», casi tal cual):
  ronda propuesta en la PR de la parte 5. De G71, `backup_database` y `rotate_backups` no siguen (las copias las
  hace Aurora, PLAN-DB y PLAN-AWS) y `triage_error_report` tampoco: el embudo de errores es una línea de registro que
  CloudWatch cuenta (PLAN-SAAS §1.1) y lo que cuenta una persona es ACCOUNTS-F38.
- Puertas propias sobre allauth.headless (`accounts/doors.py`, montadas en `config/urls.py` antes de las de
  allauth): la entrada pliega el correo como el alta (NFKC, `adapters.plain_email`; trampa del SaaS viejo
  #1018) y el alta comprueba la contraseña contra su propio correo (headless la validaba sin cuenta y el
  validador de parecido no veía nada; saas#2542). `AccountAdapter.clean_password` rechaza la contraseña
  actual como nueva (saas#2612), en el cambio y en el restablecimiento.
- Términos (ACCOUNTS-F10): `TERMS_VERSION` y `PRIVACY_VERSION` en `accounts/models.py` son la fecha de
  «Last updated» de `/legal/terms/` y `/legal/privacy/`; `tests/test_terms.py` falla si una página cambia
  su fecha sin la versión. `services.accept_legal_texts` escucha `user_signed_up` de allauth y
  `user_logged_in` de Django.
- Freno (ACCOUNTS-F11): todos los límites escritos en `ACCOUNT_RATE_LIMITS` de `config/settings.py` (saas#88:
  `login_failed` 5/5m por dirección y por cuenta, `reset_password` 10/h por dirección y 5/h por cuenta y
  `code_attempts`, nuestro, 10 códigos rechazados en 5 minutos por dirección) sobre la caché de Django (Valkey en
  AWS, `base.cache.FailSoftRedisCache`); `tests/test_throttle.py`. reCAPTCHA Enterprise por puntuación, **apagado
  por defecto desde el 2026-10-23** (Ioan: el WAF del ALB y estos límites; `RECAPTCHA_ENABLED=true` más las dos
  claves lo encienden sin tocar código; apagado, ni token, ni script, ni aviso, ni Google en la CSP)
  (`live.recaptcha`, mínimo `RECAPTCHA_MIN_SCORE` 0.5) delante de las puertas de allauth.headless en
  `accounts/bot_check.py` (400 `recaptcha_failed`; abre sin Google solo en `login`, `login_code` y
  `mfa_authenticate`), aviso en `components/RecaptchaNotice.vue`; `tests/test_bot_check.py`. Detalle y runbook,
  README de la raíz, «Protección contra bots»; PLAN-SAAS §3.7, ronda 2026-10-23.
  Los pases del salto a un negocio tienen su propio freno: 20 en 5 minutos por cuenta (`HUB_LOGIN_RATELIMIT`, F28).
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
  allauth no nombra su modelo ni sus campos (salían en inglés en todo idioma): `UserSessionAdmin` nombra columnas
  y etiquetas con `admin.display`, y `AccountsConfig.ready()` el modelo con su `_meta` en vivo; las migraciones
  leen las opciones propias del modelo (`_meta.original_attrs`), así que allauth no gana ninguna
  (`makemigrations --check` en `tests/test_admin.py` lo vigila).
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
- Parte 4 (F28–F38): el salto es el contrato de PLAN-SAAS §2 (`accounts/handoff.py`, `internal.py` con
  `/internal/auth/redeem`, `signing.py`): código de un solo uso atado al negocio y al `state` del navegador, enviado
  por `form_post` sin `Referer`. Las direcciones viejas de la cuenta (`/dashboard/profile/…`) son 301 de
  `accounts/redirects.py` a Cuenta bajo `/dashboard/account/…` en un salto, que conservan `?surface=account` (la app
  nativa no cambia; FIX-SAAS-PANEL-UNDER-DASHBOARD-PREFIX). Las claves de API del SaaS
  (`erps_live_…`, `accounts/api_auth.py`) solo abren las operaciones con `expose_api=True` de su permiso; el
  superusuario emite las de una cuenta del equipo desde el admin (`ApiKeyAdmin`, `services.issue_api_key`).
  `/api/docs` es ReDoc con nonce y solo con sesión (`accounts/api_docs.py`); `/api/openapi.json` sigue abierto (lo
  leen Postman y los tests de otras apps). `anonymize_old_users` (F35, semanal) y `cleanup_old_logs` (F37, diaria)
  son comandos con candado propio (`services.run_exclusively`) que lanza `saas-cron` con sus valores por defecto:
  `anonymize-old-users-weekly` los lunes a las 00:35 UTC y `cleanup-old-logs-nightly` cada noche a las 00:45 UTC
  (`aws/stacks/prod/scheduler.tf`). El registro de auditoría (F36) es `django-auditlog`
  (`accounts/auditlog.py`): la cuenta, su acceso a negocios, sus claves y sus sesiones, sin secretos ni lo que se
  mueve en cada visita; `AuditActorMiddleware` toma la dirección que ya resolvió `public.client_ip` y lee quién
  actúa al escribir cada entrada (una clave de API pone su cuenta después del middleware), y
  `services.forget_deleted_actor` suelta el autor cuando su cuenta se elimina. Los modelos de cobro y de VeriFactu
  los registran sus apps. «Reportar un problema» (F38) es `accounts.support.report`: un correo en inglés a
  `SUPPORT_EMAIL` con «Reply-To» la cuenta, limitado por cuenta (`SUPPORT_REPORT_RATELIMIT`, 5 por hora).
- Parte 5 (F39–F48): la política de contenido del panel es `settings.SECURE_CSP` sobre `live.csp.base_policy` (más
  lo que añade `base/csp.py` en una página que cobra), con nonce, `strict-dynamic` y Trusted Types en producción; la
  de la web pública es `public/csp.py`, sin `strict-dynamic` ni Trusted Types a propósito, y la del admin,
  `base.csp.admin_policy` (la del panel sin Trusted Types, por `AdminCSPMiddleware`): su jQuery escribe `innerHTML` al
  cargar y moría con ellos, y con él todos los controles del admin (trampa saas#1828 del viejo, vista de nuevo con
  `ui-clip-sweep.sh` en la parte 5). Las tres llevan `connect-src`
  con `ipc:` y `http://ipc.localhost` (la app Tauri), y `config/tests/test_csp_policy.py` las lee directiva a
  directiva en un proceso con los ajustes de producción. Los
  informes del navegador van a `base/csp_report.py`, frenados por `CSP_REPORT_RATELIMIT` (60/h por dirección,
  `public.client_ip`). El registro pasa por `base.logging.GDPRSafeFormatter` (portado de `apps/core/logging.py` con
  sus casos), puesto en `LOGGING` con `"()"`. `config/asgi.py` cierra con 1008 el saludo de un WebSocket
  (`refuse_websockets`; el SaaS no sirve `/ws`) y `config/wsgi.py` sirve el mismo proyecto. La marca del admin está
  en `config/urls.py`. El mantenimiento es `base.models.SiteSettings` (fila única, `base/0001`),
  `base.queries.maintenance_state` (caché compartida 60 s, borrada tras el COMMIT de un cambio; falla abierta con
  `base.maintenance_unreadable`) y `base.maintenance.MaintenanceModeMiddleware` (503, `Retry-After: 300`, `no-store`,
  el sobre con el código `maintenance` en la API), que lee el interruptor antes que la sesión y deja fuera salud,
  estáticos, admin, `/internal`, webhooks, informes de CSP, la API de allauth, la vuelta de Google y las páginas de la
  entrada con `next=/admin/…` (las dos trampas del viejo: la salud en 503 y el segundo factor cortado). Se enciende
  solo desde el admin (working-rules §4). `purge_expired_sessions` (F44) es diaria, con candado propio
  (`services.run_exclusively`), y la lanza `saas-cron` a las 00:20 UTC (`purge-expired-sessions-nightly` de
  `aws/stacks/prod/scheduler.tf`, que por eso no programa `clearsessions` aparte); suelta a mano el candado de su conexión copiada del pool. Los correos (F46) salen por `django-ses` con
  `AWS_SES_CONFIG` (3 s para conectar, 10 s para leer, dos intentos), cada uno en texto y en HTML sobre la plantilla
  común `templates/emails/base.html` (PLAN-SAAS §7, bloque 13; la vieja saas#1044): `base/emails.py`
  (`branded_message`, con el idioma del destinatario explícito, porque cada remitente envía fuera de su
  `translation.override`) en `accounts`, `billing`, `fiscal`, `whatsapp` y el contacto de `public`; los de allauth, por
  `AccountAdapter.render_mail`, que pone su texto en la plantilla (allauth solo trae `.txt`) salvo los avisos propios,
  que tienen su `_message.html` junto al `.txt`. `URLIZE_ASSUME_HTTPS` abre por HTTPS un enlace sin esquema. Los de
  `hubs/emails.py` siguen en texto hasta que los pase su porte. La navegación (F47) es `base/navigation.py` y el shell de `@erplora/ui`; el procesador de contexto que queda es
  `base.context_processors.theme`. La QA maestra (F48) es `flows/shared/qa-saas.md` del repo `qa` viejo: §3 →
  PUBLIC-F01–F37; §4.1 → HUBS-F04, F06, F09, F21 y F22; §4.2 → HUBS-F03, BILLING-F07, F08, F10 y F11; §4.4 →
  HUBS-F18 y F19; §5 → APPS-F01–F07 y BILLING-F31–F35; §6 → BILLING-F02–F06, F12, F13, F15–F17 y F25,
  ACCOUNTS-F28 y F32; §7 → ACCOUNTS-F01–F03, HUBS-F01 y F11, BILLING-F08 y F29, y en el Hub PRINTING-F07 y F13;
  §8 → VERIFACTU-F13, F15 y F19 e INVOICE-F01 del Hub. No siguen, por la plataforma de ahora: arrancar, parar,
  reiniciar y actualizar el contenedor de cada negocio y el inventario de servidores (un solo servicio para todos los
  hubs en ECS y una Aurora, PLAN-AWS), la descarga de módulos y el portal de desarrolladores (todos los módulos son
  nuestros y van en la imagen del Hub, PLAN §13–§15), OutfitKit (PLAN §16.11), la suspensión al 25 % (al terminar se
  vuelve a Gratis, BILLING-F15) y los 15 días de prueba de los planes de pago (sin prueba desde 2026-10-15).
- Pruebas: cada test cita su clave en el nombre o el docstring. Los e2e de la parte 1 están en
  `tests/e2e/panel/accounts-flows.spec.ts`, los de la parte 2 en `tests/e2e/panel/accounts-security.spec.ts`
  los de la parte 3 en `tests/e2e/panel/accounts-profile.spec.ts` y los de la parte 4 en
  `tests/e2e/panel/accounts-jump.spec.ts`, `accounts-keys.spec.ts` y `accounts-report.spec.ts`, los de la parte 5 en
  `tests/e2e/panel/accounts-platform.spec.ts` (menú y mantenimiento), `tests/e2e/public-errors.spec.ts` (404 y 500) y
  `tests/e2e/panel/accounts-mails.spec.ts` (F46: tres correos leídos de la carpeta de correo y pintados a tres tamaños),
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
- No avisa antes de borrar una cuenta sin uso en dos años (el SaaS viejo tampoco avisaba), ni borra nunca una
  cuenta que pertenece a un negocio vivo.
- No borra el registro de auditoría de una cuenta al eliminarla: ese registro se borra entero a los 90 días.
- No abre una incidencia con cada informe de «Reportar un problema» ni lo guarda: llega por correo a soporte, que
  contesta a la persona.
- No se pone en mantenimiento por consola ni por un ajuste del despliegue: solo desde el admin.
- No deja fuera del mantenimiento a quien usa una clave de API, aunque sea del personal.
- No hace copias de la base de datos: las hace AWS.
- No corta una llamada a un servicio de fuera que ha fallado varias veces seguidas: cada llamada espera poco y dice
  su error.
