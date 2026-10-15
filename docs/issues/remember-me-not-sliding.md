<!-- Borrador de issue para ERPlora/saas. Título y etiqueta, abajo; el cuerpo empieza en «Qué pasa». -->
- Título: La sesión caduca a las dos semanas de entrar aunque se use cada día
- Etiqueta: `prio:P2`

## Qué pasa
Quien entra en ERPlora tiene que volver a entrar a las dos semanas exactas de haber entrado, aunque haya usado ERPlora a diario. Debería durar mientras se use (la cuenta atrás vuelve a empezar con cada uso), como en el ERPlora de hoy.

## Propuesta
Que la sesión se renueve con el uso: la caducidad se cuenta desde la última vez que se usó, no desde la entrada. La pantalla de entrada no pregunta nada (no hay casilla de «recordarme»): toda sesión dura lo mismo.

## Detalle técnico
- Hoy: `ACCOUNT_SESSION_REMEMBER = True` (allauth.headless no recibe `remember`, así que toda entrada dura `SESSION_COOKIE_AGE`), `SESSION_COOKIE_AGE` por defecto (1 209 600 s) y `SESSION_SAVE_EVERY_REQUEST` sin fijar (`False`), así que la caducidad no se mueve con el uso.
- Origen: `ERPlora/saas` `origin/develop` `apps/auth/users/remember_me.py` (`SESSION_REMEMBER_COOKIE_AGE`, saas#1744) y su test; la parte de la casilla ya no aplica (pantalla única sobre allauth.headless).

## Origen
- Cómo se llegó: al portar «Continuar con Google» a saas-next (2026-10-13), Ioan pidió abrir una issue por cada parte del login que queda fuera. Reescrita el 2026-10-15 al pasar el login a la SPA (solo headless): la casilla desapareció y queda la caducidad que no se renueva.
- La introdujo una PR: no, ya existía (fuera de la fase 1 por diseño: `saas-next/README.md`, «Fuera de la fase 1»).

## Cómo se reproduce
- No aplica: la caducidad fija se lee en la configuración (`SESSION_SAVE_EVERY_REQUEST` sin fijar) y reproducirla pide esperar dos semanas; el test del arreglo debe fijar que una petición renueva la caducidad.

## Flujo
- Flujo: ninguno — la app accounts de saas-next aún no tiene WORKBOOK.md (en el SaaS de hoy es SAAS_AUTH-F03)
