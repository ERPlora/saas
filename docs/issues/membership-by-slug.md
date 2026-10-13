<!-- Borrador de issue para ERPlora/saas. Título y etiqueta, abajo; el cuerpo empieza en «Qué pasa». -->
- Título: El SaaS no tiene ficha de negocio: un negocio es solo su nombre corto y el Hub no recibe sus datos
- Etiqueta: `prio:P1`

## Qué pasa
En ERPlora (`erplora.com`) un negocio no existe como tal: es solo el nombre corto de su dirección (`a`, `b`…), sin nombre, plan ni apps. Por eso no se puede renombrar, el selector no puede enseñar su nombre y el negocio no recibe del SaaS qué tiene contratado ni quién es miembro. Debería haber una ficha por negocio y el negocio debería recibir su foto completa cada vez que cambie.

## Propuesta
Portar el modelo de negocio y de miembros del ERPlora de hoy, con su identificador único, y que el SaaS empuje al negocio la foto completa (plan, apps, miembros) cada vez que cambie.

## Detalle técnico
- Hoy: `HubMembership(user, hub_slug, role)` y `AuthExchangeCode.hub_slug` (`accounts/models.py`); `services.issue_code`/`redeem_code` comparan por slug.
- PLAN-SAAS §2: mismo `Hub.id` (UUIDv7 que genera el SaaS) en los dos lados; `AuthExchangeCode.destination_hub_id` como `UUIDField` (§2.1); §2.2 `PUT /internal/hubs/{id}/state` con `version` monótona (el Hub ignora una foto más vieja).
- Origen: `ERPlora/saas` `origin/develop` `apps/dashboard/hubs/main/models.py` (`Hub`, `HubMember`). Migración: `HubMembership` → `HubMember` con datos (los `hub_*` ya son los roles finales).

## Origen
- Cómo se llegó: al portar «Continuar con Google» a saas-next (2026-10-13), Ioan pidió abrir una issue por cada parte del login que queda fuera.
- La introdujo una PR: no, ya existía (fuera de la fase 1 por diseño: `saas-next/README.md`, «Fuera de la fase 1»).

## Cómo se reproduce
- No aplica: falta el modelo y el envío de la foto (funcionalidad pendiente de PLAN-SAAS §2.2), no un fallo de algo que exista.

## Flujo
- Flujo: ninguno — la app accounts de saas-next aún no tiene WORKBOOK.md y el modelo de negocio aún no existe en saas-next
