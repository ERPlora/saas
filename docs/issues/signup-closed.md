<!-- Borrador de issue para ERPlora/saas. Título y etiqueta, abajo; el cuerpo empieza en «Qué pasa». -->
- Título: El SaaS no permite crear cuenta aunque el login dice «te creamos la cuenta»
- Etiqueta: `prio:P1`

## Qué pasa
En la pantalla de entrada de ERPlora (`erplora.com`), una persona nueva escribe su email y una contraseña, como le indica el texto «¿Es tu primera vez? Te creamos la cuenta», y recibe «el email o la contraseña no son correctos»: no se crea nada. Con «Continuar con Google» le sale «No hay ninguna cuenta de ERPlora para esta cuenta de Google». Debería crearse la cuenta en esa misma pantalla, como en el ERPlora de hoy.

## Propuesta
Portar el alta en una sola pantalla del ERPlora de hoy: email desconocido + contraseña válida crea la cuenta y pide el código de confirmación por email; con Google, el alta es automática.

## Detalle técnico
- Hoy `accounts/adapters.py`: `AccountAdapter.is_open_for_signup` devuelve `False`; `SocialAccountAdapter.is_open_for_signup` redirige a la página Vue `/login/error?code=google_no_account` (`accounts/frontend/pages/LoginErrorPage.vue`). `SOCIALACCOUNT_AUTO_SIGNUP = True` ya está puesto para cuando se abra.
- Origen a portar (`ERPlora/saas` `origin/develop`): `SubdomainLoginView` (`apps/auth/users/views.py`, rama de email desconocido), `services.create_user`, verificación por código (`ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED`, ADR-0159), throttle del alta (`UNIFIED_SIGNUP_RATELIMIT`, paridad de estados #1018) y sus tests (`tests/test_unified_auth.py`). Plan: `docs/superpowers/plans/2026-10-11-saas-next-bloque-1a-auth.md`.
- Al abrirla, revisar que el texto del login y el caso `google_no_account` de `/login/error` dejan de aplicar.

## Origen
- Cómo se llegó: al portar «Continuar con Google» a saas-next (2026-10-13), Ioan pidió abrir una issue por cada parte del login que queda fuera.
- La introdujo una PR: no, ya existía (fuera de la fase 1 por diseño: `saas-next/README.md`, «Fuera de la fase 1»).

## Cómo se reproduce
- Pasos: en local, `http://localhost:8001/accounts/login/`: email `nueva@example.com`, contraseña `una-clave-larga-1`, «Continuar». Se espera la cuenta creada y el código de confirmación; sale «The email address and/or password you specified are not correct.» y no hay ninguna cuenta nueva en `/admin/accounts/user/`.

## Flujo
- Flujo: ninguno — la app accounts de saas-next aún no tiene WORKBOOK.md (en el SaaS de hoy es SAAS_AUTH-F01)
