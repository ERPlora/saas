# Usuarios, roles y acceso con PIN

ERPlora separa la cuenta Cloud de los usuarios que trabajan dentro de un Hub:

- La **cuenta Cloud** utiliza email y contraseña, más un segundo factor opcional (TOTP) cuando el titular lo enrola.
- Un **usuario del Hub** es local a un Hub y recibe un rol, permisos y, opcionalmente, un PIN de 4 dígitos para acceder desde un dispositivo de confianza.

## Cómo funciona el acceso con PIN

El PIN es un método rápido para volver a entrar, no la primera credencial de un dispositivo desconocido.

1. Inicia sesión con email y contraseña en el dispositivo nuevo.
2. Selecciona **Confiar en este dispositivo**.
3. Elige y confirma un PIN de 4 dígitos.
4. En accesos posteriores, selecciona tu usuario e introduce el PIN.

Si el dispositivo deja de ser de confianza, no aparecerá la entrada por PIN. Usa la pestaña **Email**, vuelve a iniciar sesión y crea de nuevo la confianza del dispositivo. No compartas un PIN entre empleados.

## Empleados y usuarios de acceso

Una ficha de empleado o personal no concede automáticamente acceso al Hub. La persona que necesite entrar debe tener también un usuario del Hub con un rol asignado. Así se separan los datos operativos del personal de la autenticación y los permisos.

Los administradores gestionan el acceso desde **Empleados**:

- Crear o actualizar usuarios del Hub.
- Asignar roles.
- Revisar los permisos aportados por las apps instaladas.
- Desactivar el acceso cuando una persona ya no deba entrar.
- Gestionar claves API cuando esa función esté disponible.

## Roles y permisos

Los roles son locales al Hub. Sus permisos proceden del núcleo y de las apps instaladas, por lo que la lista disponible cambia con las capacidades del Hub.

Concede únicamente el acceso necesario para el trabajo. Solo los roles propietario o administrador deberían modificar ajustes globales, usuarios, permisos de apps o credenciales fiscales.

## Si un usuario no puede entrar

- **No aparece la pantalla de PIN:** el dispositivo no es de confianza o no hay usuarios del Hub con PIN disponibles.
- **El PIN se rechaza:** confirma el usuario seleccionado; después usa el acceso por email si hay que restablecerlo.
- **Falta una página:** revisa el rol del usuario y los permisos de la app correspondiente.
- **El usuario ya no existe:** un administrador debe recrear o reactivar el usuario del Hub; los datos guardados en el navegador no pueden restaurarlo.
