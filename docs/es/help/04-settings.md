# Ajustes, dispositivos y datos

Abre **Ajustes** en el menú lateral. Abajo tiene cuatro pestañas: «General», «Negocio», «Impresión» y «Datos y copias». Lo que cambia el negocio entero solo lo cambian el propietario y los administradores; los demás ven esos controles apagados y quién puede cambiarlos.

Tus preferencias personales no están en Ajustes, sino en **Mi perfil** («Perfil», en el menú de usuario): el idioma, el tema, la paleta y el tamaño de la interfaz, que te siguen en cualquier dispositivo.

## General

- **«Este dispositivo»**: si el dispositivo en el que estás es «Compartido — una caja o tablet que usan varias personas» (pide PIN al entrar y lo olvida al acabar el turno) o «Personal — un dispositivo que solo usas tú» (la sesión se queda abierta y nunca pide PIN). Cada dispositivo se decide por separado, desde él mismo.
- **«Pinpad»**: «Mostrar pinpad» decide para todo el negocio si las cajas preguntan quién está. «Volver a preguntar tras inactividad» cierra la sesión de una caja que nadie toca durante 1, 5, 10, 15 o 30 minutos, o la deja abierta «Hasta cerrar sesión». «Dígitos del PIN» elige «4 dígitos» o «6 dígitos»; los PIN que ya se usan siguen funcionando hasta que su dueño los cambie.
- **«Dispositivos»** (solo para quien administra): los dispositivos en los que alguien ha entrado, con su modo y cuándo se usaron por última vez. «Ponerle nombre» les da un nombre («Barra», «Cocina») y «Quitar este dispositivo» cierra su sesión al momento: para volver a usarlo, alguien tiene que entrar en él con su cuenta.
- **«Documentación de la API»**: el interruptor «Mostrar documentación de la API» añade la página de la API y la entrada «API» del menú lateral, para quien conecte otro sistema. Viene apagado. Las llaves de la API se crean en **Empleados › API keys**.

## Negocio

La tarjeta «Tu negocio» enseña «Nombre del negocio», «País», «Zona horaria», «Moneda» e «Idioma del negocio». No se editan aquí: el nombre, la zona horaria y el idioma se cambian en erplora.com con «Cambiar en erplora.com»; la moneda es la del país, y el país no cambia una vez listo el negocio.

«Datos fiscales» abre el emisor de la app Facturación, donde se escriben la razón social, el NIF y el domicilio que usan las facturas. Sin esa app, la pestaña dice «Instala la app Facturación para escribir los datos fiscales».

En un negocio de España, el envío de las facturas a la AEAT se configura en la app VeriFactu, en **VeriFactu › Configuración**: o lo remite ERPlora en nombre del negocio («Lo remite ERPlora»), o el negocio usa su propio certificado («Mi certificado»), que tiene que ser del mismo NIF que el emisor de Facturación.

## Impresión

La pestaña tiene una sola fila, «Impresoras y tique», que abre la app Impresión: allí se dan de alta las impresoras y los dispositivos que imprimen y se decide qué sale al cobrar. Si la app no está, dice «Instala la app Impresión para dar de alta tu impresora y configurar el tique» y lleva a **Apps**.

## Datos y copias

Arriba, un selector con «Importar», «Exportar» y «Restablecer». Todo esto es solo para el propietario y los administradores.

- **Importar**: en «Elige qué cargar», usa una plantilla del catálogo con «Usar plantilla» o pulsa «Subir desde archivo» y elige un .blueprint.zip (una copia de seguridad o una plantilla que exportó otro negocio, de 20 MB como mucho). Antes de cargar nada, «Revisa lo que trae» enseña lo que trae cada app y deja desmarcar las que no quieras; al terminar sale el «Informe de la importación». Lo que ya había en el negocio no se duplica ni se sobrescribe.
- **Exportar**: escribe el nombre y el idioma del archivo, responde «¿Para qué es este archivo?» («Copia de seguridad de este negocio», que lleva también los clientes, o «Plantilla para compartir», que nunca los lleva) y marca, app por app, «App» y «Datos». Ningún archivo lleva personas, PIN ni datos fiscales.
- **Restablecer**: «Deshacer una importación» quita solo lo que trajo esa importación. «Restablecer el negocio» borra definitivamente las secciones que marques, después de escribir el nombre del negocio para confirmarlo; las ventas, las facturas, los registros fiscales, las personas, los archivos y los ajustes del negocio no se borran nunca.

Antes de vaciar nada, se hace una copia completa de los datos del negocio y se guarda 90 días en «Copias de los datos», con su «Descargar». Si dudas, exporta antes una copia.
