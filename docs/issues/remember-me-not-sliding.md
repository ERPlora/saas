<!-- Borrador de issue para ERPlora/saas. Título y etiqueta, abajo; el cuerpo empieza en «Qué pasa». -->
- Título: «Mantener la sesión iniciada» cierra la sesión a las dos semanas aunque se use cada día
- Etiqueta: `prio:P2`

## Qué pasa
En la pantalla de entrada de ERPlora, quien marca «Mantener la sesión iniciada» tiene que volver a entrar a las dos semanas exactas de haber entrado, aunque haya usado ERPlora a diario. Debería durar mientras se use (la cuenta atrás vuelve a empezar con cada uso), como en el ERPlora de hoy.

## Propuesta
Portar el «recordarme» del ERPlora de hoy: con la casilla, una sesión larga que se renueva con el uso; sin ella, la sesión normal.

## Detalle técnico
- Hoy: `ACCOUNT_SESSION_REMEMBER = None` (decide la casilla), `SESSION_COOKIE_AGE` por defecto (1 209 600 s) y `SESSION_SAVE_EVERY_REQUEST = False`, así que la caducidad no se mueve con el uso.
- Origen: `ERPlora/saas` `origin/develop` `apps/auth/users/remember_me.py` (`RememberMeLoginForm`, `SESSION_REMEMBER_COOKIE_AGE`, saas#1744) y su test.

## Origen
- Cómo se llegó: al portar «Continuar con Google» a saas-next (2026-10-13), Ioan pidió abrir una issue por cada parte del login que queda fuera.
- La introdujo una PR: no, ya existía (fuera de la fase 1 por diseño: `saas-next/README.md`, «Fuera de la fase 1»).

## Cómo se reproduce
- No aplica: la caducidad fija se lee en la configuración (`SESSION_SAVE_EVERY_REQUEST = False`) y reproducirla pide esperar dos semanas; el test del port debe fijar que una petición renueva la caducidad.

## Flujo
- Flujo: ninguno — la app accounts de saas-next aún no tiene WORKBOOK.md (en el SaaS de hoy es SAAS_AUTH-F03)
