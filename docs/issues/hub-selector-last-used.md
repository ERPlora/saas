<!-- Borrador de issue para ERPlora/saas. Título y etiqueta, abajo; el cuerpo empieza en «Qué pasa». -->
- Título: El selector de negocios no pone primero el último que usaste
- Etiqueta: `prio:P2`

## Qué pasa
Al entrar en ERPlora con una cuenta que pertenece a varios negocios, la lista sale en orden alfabético por el nombre corto de la dirección, y el negocio en el que trabajas cada día puede quedar abajo del todo. Debería salir primero el último en el que entraste, como en el ERPlora de hoy.

## Propuesta
Recordar cuándo entra cada persona en cada negocio y ordenar el selector por el más reciente.

## Detalle técnico
- `queries.hub_slugs_of` ordena por `hub_slug` (`accounts/queries.py`); la consulta `accounts.hub.list` (mismo fichero) la sirve y la página Vue `/launch` (`accounts/frontend/pages/LaunchPage.vue`) la pinta.
- Origen: `ERPlora/saas` `origin/develop` `apps/dashboard/hubs/main/business_selector.py` (orden por último acceso). Depende de la ficha de negocio (`membership-by-slug.md`) para mostrar el nombre.

## Origen
- Cómo se llegó: al portar «Continuar con Google» a saas-next (2026-10-13), Ioan pidió abrir una issue por cada parte del login que queda fuera.
- La introdujo una PR: no, ya existía (fuera de la fase 1 por diseño: `saas-next/README.md`, «Fuera de la fase 1»).

## Cómo se reproduce
- Pasos: en local (dentro de `saas-next/`), `uv run python manage.py demo_seed`, entrar en `http://localhost:8001/hub-login/?hub=b` como `owner@example.com` y volver a `http://localhost:8001/launch`. Se espera `b` primero; sale `a`, `b`.

## Flujo
- Flujo: ninguno — la app accounts de saas-next aún no tiene WORKBOOK.md
