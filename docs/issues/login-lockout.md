<!-- Borrador de issue para ERPlora/saas. Título y etiqueta, abajo; el cuerpo empieza en «Qué pasa». -->
- Título: Cinco contraseñas mal puestas por otra persona bloquean la entrada del dueño de la cuenta
- Etiqueta: `prio:P1`

## Qué pasa
En la pantalla de entrada de ERPlora, si alguien prueba cinco contraseñas falsas con el email de otra persona, el dueño de esa cuenta tampoco puede entrar con su contraseña buena durante un rato: le sale «demasiados intentos». Debería frenarse solo al que se equivoca.

## Propuesta
Portar el freno de intentos del ERPlora anterior: por dirección real antes de comprobar la contraseña y por cuenta solo cuando la contraseña es mala, con un contador compartido entre procesos.

## Detalle técnico
- Hoy (`config/settings.py`, `ACCOUNT_RATE_LIMITS`, leído el 2026-11-11): `login_failed` es `5/5m/ip,5/5m/key`, en la caché compartida (Valkey) y por la dirección real del visitante (`public.client_ip`). La contraseña buena devuelve su intento, pero las cinco malas de otra persona agotan el cupo de la cuenta durante 5 minutos, y allauth lo gasta en `pre_authenticate`, antes de comprobar la contraseña (erplora-old/saas#1015). Lo de la dirección compartida tras el ALB ya no pasa.
- Origen: `erplora-old/saas` `origin/develop` `ERPloraAccountAdapter.get_client_ip`/`pre_authenticate`, `apps/auth/users/login_throttle.py`, `apps/core/client_ip.py`, `ACCOUNT_RATE_LIMITS` y tests `test_shared_ip_budget.py`, `test_login_throttle*.py`. En AWS la dirección del cliente es la última entrada de `X-Forwarded-For` (plan del bloque 1a).

## Origen
- Cómo se llegó: al portar «Continuar con Google» a saas-next (2026-10-13), Ioan pidió abrir una issue por cada parte del login que queda fuera; se comprobó con un test de un solo uso.
- La introdujo una PR: no, ya existía (fuera de la fase 1 por diseño: `README.md`, «Fuera de la fase 1»).

## Cómo se reproduce
- Pasos: en local, con `owner@example.com` de `demo_seed`: cinco envíos del formulario de `http://localhost:8001/launch` con contraseña `mala`; después, desde otro navegador, `owner@example.com` / `owner`. Se espera entrar; sale «Too many failed login attempts. Try again later.» (comprobado con el cliente de pruebas de Django, dos direcciones distintas).

## Flujo
- Flujo: ACCOUNTS-F11 (en el SaaS anterior, SAAS_AUTH-F14)
