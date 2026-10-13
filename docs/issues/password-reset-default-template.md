<!-- Borrador de issue para ERPlora/saas. Título y etiqueta, abajo; el cuerpo empieza en «Qué pasa». -->
- Título: La página para recuperar la contraseña sale sin el diseño de ERPlora
- Etiqueta: `prio:P1`

## Qué pasa
En la pantalla de entrada de ERPlora, al pulsar «¿Has olvidado tu contraseña?», se abre una página en blanco con un formulario sin estilos, sin logo ni traducción cuidada; lo mismo al volver desde el enlace del correo para poner la nueva contraseña. Debería verse como la pantalla de entrada, igual que en el ERPlora de hoy, y el correo debería llevar la marca.

## Propuesta
Portar las cuatro páginas de recuperación del ERPlora de hoy con el mismo envoltorio que el login, y el correo de marca.

## Detalle técnico
- Las sirve allauth con sus plantillas por defecto: `account/password_reset.html`, `password_reset_done.html`, `password_reset_from_key.html`, `password_reset_from_key_done.html` (no existen en `saas-next/templates/account/`; la respuesta de `/accounts/password/reset/` pesa 1,8 KB, sin `<title>`).
- Ya hecho al portar Google (2026-10-13): `templates/account/email/base_message.txt` («Hello from ERPlora!», sin depender de `Site`) y `AccountAdapter.format_email_subject` (sin el prefijo «[example.com]»). Falta el HTML de marca (`emails/base.html`, `send_branded_email`) y el backend de correo real (hoy `console`).
- Origen: `ERPlora/saas` `origin/develop` `templates/account/password_reset*.html`, `apps/auth/users/views.py` (`PasswordResetView`), `templates/account/email/password_reset_key_message.html`.

## Origen
- Cómo se llegó: al portar «Continuar con Google» a saas-next (2026-10-13), Ioan pidió abrir una issue por cada parte del login que queda fuera.
- La introdujo una PR: no, ya existía (fuera de la fase 1 por diseño: `saas-next/README.md`, «Fuera de la fase 1»).

## Cómo se reproduce
- Pasos: en local, `http://localhost:8001/accounts/login/` → «Forgot your password?». Se espera la tarjeta de ERPlora (logo, Ionic, `en`/`es`); sale el formulario sin estilos de allauth.

## Flujo
- Flujo: ninguno — la app accounts de saas-next aún no tiene WORKBOOK.md (en el SaaS de hoy es SAAS_AUTH-F09)
