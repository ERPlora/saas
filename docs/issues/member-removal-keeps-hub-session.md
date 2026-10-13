<!-- Borrador de issue para ERPlora/saas. Título y etiqueta, abajo; el cuerpo empieza en «Qué pasa». -->
- Título: Quitar a alguien de un negocio no le cierra la sesión en ese negocio
- Etiqueta: `prio:P1`

## Qué pasa
Cuando el dueño quita a una persona de su negocio en ERPlora (o esa persona cierra sesión o cambia su contraseña), quien ya estaba dentro del negocio sigue dentro con su rol de antes hasta que su sesión caduca. Debería quedar fuera al momento.

## Propuesta
Que el SaaS avise al negocio en cuanto se quita a alguien, se cierra sesión o se cambia la contraseña, y que el negocio cierre al instante las sesiones de esa persona.

## Detalle técnico
- PLAN-SAAS §2.1: `POST /internal/sessions/revoke {user_id, hub_id?}` (back-channel logout de OIDC), firmado con HMAC-SHA256 + marca de tiempo como `/internal/auth/redeem`.
- No existe en ninguno de los dos lados: saas-next no lo llama al borrar un `HubMembership` ni en el logout; hub-next guarda la cuenta del SaaS en la sesión (`base/services.py`, `SAAS_USER_ID_SESSION_KEY`, «phase 2») y su `Membership` local es una copia hecha al entrar (`open_session_from_saas`), que nadie borra después.
- Necesita la parte del Hub (issue hermana en `ERPlora/hub`) y, del lado del SaaS, el envío con reintentos tras el COMMIT.

## Origen
- Cómo se llegó: al portar «Continuar con Google» a saas-next (2026-10-13), Ioan pidió abrir una issue por cada parte del login que queda fuera.
- La introdujo una PR: no, ya existía (fuera de la fase 1 por diseño: `saas-next/README.md`, «Fuera de la fase 1»).

## Cómo se reproduce
- No aplica: falta el canal entero (ni el SaaS llama ni el Hub expone `/internal/sessions/revoke`); es funcionalidad pendiente del contrato de PLAN-SAAS §2.1, no un fallo de algo que exista.

## Flujo
- Flujo: ninguno — la app accounts de saas-next aún no tiene WORKBOOK.md (en el SaaS de hoy es SAAS_AUTH-F22)
