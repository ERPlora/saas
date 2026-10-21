# Peticiones del panel del SaaS a `@erplora/ui`

Lo que el panel (`hubs/`, `billing/`, `accounts/` de `saas-next`) necesita de los componentes compartidos y que
hoy resuelve con un rodeo mínimo en su propio carril. `packages/ui` es de otra sesión: aquí solo se pide; cuando
el componente lo traiga, se quita el rodeo y se dice en la misma tarea.

Origen: pase de limpieza del panel del 2026-10-14 (Ioan: «no es solo un TPV, es un SaaS… la interfaz lo más
limpia posible… las tablas tienen que ocupar la altura de la página, el espacio entre topbar y tabbar»).

## 1. `DataTable`: los filtros de columna dentro de un popover «Filtros»

- **Qué pasa**: los filtros de columna de `DataTable` (`DataTableColumn.filter`, `v-model:filters`,
  `filtersChange`) pintan una **fila propia** bajo la barra. Con la regla del panel (barra en **una** línea a
  1440 px y en dos a 390 px) esa fila sobra, y además no hay filtro de **año** (el de fecha es un día).
- **Rodeo hoy**: `billing/frontend/components/InvoiceFilters.vue` en el slot `filters`: un botón «Filtros» con
  el número de filtros activos y un `ion-popover` con negocio (`ion-select` popover), estado (`ion-segment`, tres
  opciones visibles), año (`ion-select` popover) y «Quitar filtros». Probado anidando el popover del select
  dentro del de filtros (Chrome, 390 y 1440).
- **Propuesta**: una opción de `DataTable` (p. ej. `filtersIn: 'row' | 'popover'`) que meta sus filtros de
  columna en un popover «Filtros» con su contador y «Limpiar filtros», con `select` de 2–4 opciones como
  `ion-segment`, y un tipo de filtro `year` (o `select` con opciones libres que no sea de una columna). Con eso,
  `InvoiceFilters.vue` desaparece y Facturas declara sus filtros en las columnas.
- **Estado (2026-10-16)**: `DataTable` ya trae el embudo con contador y su panel dentro de la tabla (un cajón; bajo
  834 px, una hoja), opt-in con `filterable`, y filtros sin columna propia con `filterFields` (ui#4, 070e74f). El panel
  **no** lo adopta y se queda con `InvoiceFilters.vue` (PLAN-MIGRATIONS §13, 2026-10-15: las tablas del SaaS no
  cambian). Guardia: `tests/e2e/panel/fix-datatable.spec.ts` (el popover filtra a 390, 834 y 1440 px y el
  embudo de `DataTable` no aparece).

## 2. `DataTable`: en el móvil, sin el título cuando hay buscador

- **Qué pasa**: a ≤640 px el buscador ocupa su línea (`flex-basis: 100%`) y el título va en otra: una lista con
  título y buscador gasta tres líneas de barra (título · buscador · resto). En el panel la topbar y la tabbar ya
  nombran la lista y el pie la cuenta.
- **Resuelto en `@erplora/ui`** (ui#4, 070e74f; rodeo `frontend/panel-fill.css` retirado en FIX-DATATABLE-SAAS):
  `packages/ui/src/shell/theme/polish.css`, en `@media (max-width: 640px)`, solo bajo el `.panel-fill` del SaaS
  (las listas del Hub conservan su título): `.panel-fill .data-table__bar-main:has(> .data-table__search) >
  .data-table__title-wrap { display: none }`. Guardia: `AppPage.test.ts` de ui.

## 3. `DataTable`: «Columnas» y «Filas por página» solo cuando hacen falta

- **Qué pasa**: la regla de las maquetas (`mockups/saas-panel/README.md` §3b) dice «Columnas» y «Filas por
  página» solo desde 1024 px y **cuando hacen falta** (más de 4 columnas; más filas que la página más corta).
  `DataTable` enseña «Filas por página» siempre que `pageSizeChooser` sea `true`.
- **Rodeo hoy**: cada página lo calcula: `:page-size-chooser="total > PAGE_SIZES[0]"` en Negocios, Miembros y
  Facturas.
- **Propuesta**: que `DataTable` oculte el selector cuando `total` no pasa de la página más corta (y el de
  columnas con 4 o menos), sin que cada página lo repita.

## 4. `AppPage` `detail-fill`: la cadena de altura del contenido de la página

- **Qué pasa**: `detail-fill` da altura a `.hub-detail-shell--fill`, pero lo que la página pone dentro (avisos,
  cabecera del negocio, la tabla y lo que va debajo) necesita su propia cadena flex para que la tabla se quede
  con el resto sin aplastarse ni empujar la página.
- **Resuelto en `@erplora/ui`** (ui#4, 070e74f; rodeo `frontend/panel-fill.css` retirado en FIX-DATATABLE-SAAS):
  la cadena vive en `packages/ui/src/shell/theme/polish.css` (la carga `createShell`) para `.page-fill` (la pila
  de `AppPage` `content-layout="fill"`, del Hub) y `.panel-fill` (la del panel, con `detail-fill`): pila en
  columna a `height: 100%`; lo que no es la lista conserva su alto; la lista (`.data-table--fill` o una pila
  anidada) se queda el resto, con un suelo de `20rem` en escritorio y tableta (`--panel-list-min`) para que los
  avisos de arriba empujen la página antes que dejar la lista en nada. En el móvil sigue el `fill` propio de
  `DataTable` (crece con sus filas desde la altura de la página, un solo scroll). Guardias: `AppPage.test.ts` de
  ui, `frontend/main.test.ts` (el panel no lleva copia propia), `tests/e2e/panel/viewports.spec.ts` (mide la
  cadena a 390, 834 y 1440 px) y `tests/e2e/panel/fix-datatable.spec.ts` (Facturas: llena la página sin doble
  scroll y, sin la cadena, deja de llenar).

## 5. Estados de una consulta viva: cargando, error, vacío (auditoría 2026-10-14, R-04/R-08)

- **Qué pasa**: `useLive` da `status` del stream (`loading`, `live`, `error`, `reconnecting`), no lo que la
  página puede afirmar: con `/api/live` en 503 o sin red, `data` queda `undefined`, el estado es `reconnecting`
  para siempre y las páginas pintaban «vacío» («Crea tu primer negocio») o un spinner eterno.
- **Rodeo hoy**: `frontend/live-state.ts` (`useLiveState(live)` → `loading | error | empty | ready`, con
  tiempo máximo de 10 s y `retry()`) y `frontend/LoadFailed.vue` (aviso con «Reintentar»). Guardarraíl:
  `frontend/panel-controls.test.ts` (todo componente con `useLive` usa `useLiveState`).
- **Propuesta**: ese estado en el SDK (`useLive(...).view` o un `useLiveState` exportado) para el Hub y el SaaS.

## 6. Descargar un fichero por el SDK (auditoría R-05)

- **Qué pasa**: `api.call` solo lee JSON; un PDF/CSV pedido con un enlace guardaba el JSON de error como
  `pdf.json`.
- **Rodeo hoy**: `billing/frontend/browser.ts` hace un `fetch` con `Accept` (única excepción de
  `no-restricted-globals`, comentada).
- **Propuesta**: `api.download(op, input, { accept })` en `@erplora/ui/sdk` que devuelva el `Blob` y el nombre,
  o el `ApiError` del sobre.

## 7. El marco del shell: «Saltar al contenido», objetivos de 44 px y ☰ con ← (auditoría R-11, R-13, R-20)

- **Qué pasa**: el shell no tiene enlace de salto; botones, segmentos, ☰, ← y ✕ miden 28–40 px a 390; en una
  página de detalle salen ☰ y ← juntos.
- **Rodeo hoy**: `frontend/skip-link.ts` (enlace al principio de `<body>` que lleva el foco al `ion-content` de
  la página visible) y `frontend/panel-chrome.css` (44 px en táctil y ≤640 px; sin ☰ cuando la topbar tiene
  `topbar-back`). Medido en `tests/e2e/panel/chrome.spec.ts`.
- **Propuesta**: enlace de salto en `App.vue`, `min-height: 44px` táctil en el tema y `AppTopbar` sin ☰ cuando
  hay `backHref`.

## 8. `DataTable`: la barra en una fila de 834 a 1180 px (auditoría R-14)

- **Qué pasa**: el buscador pide `flex-basis: 22rem` y una fila que se parte decide por la base, así que la
  barra saltaba a dos filas antes de encoger el buscador.
- **Resuelto en `@erplora/ui`** (ui#4, 070e74f; rodeo `frontend/panel-fill.css` retirado en FIX-DATATABLE-SAAS):
  `packages/ui/src/shell/theme/polish.css`, en escritorio y solo bajo el `.panel-fill` del SaaS: `.panel-fill
  .data-table .data-table__search { flex: 1 1 11rem; min-width: 9rem; max-width: 22rem }`. Guardia:
  `AppPage.test.ts` de ui.

## 9. El cliente de allauth del SDK: la respuesta a «Confiar en este navegador» (APP-ACCOUNTS-2)

- **Qué pasa**: con `MFA_TRUST_ENABLED`, tras un código bueno de la app el login espera la etapa `mfa_trust` de
  allauth.headless (`POST /_allauth/browser/v1/auth/2fa/trust`, `{ trust: boolean }`), y `createAllauthClient` de
  `@erplora/ui/sdk` no tiene esa llamada.
- **Rodeo hoy**: `accounts/frontend/pages/TwoFactorAuthenticatePage.vue` hace su propio `fetch` con la cabecera
  CSRF (con `eslint-disable` de `no-restricted-globals`), probado en `TwoFactorAuthenticatePage.test.ts` y en
  `tests/e2e/panel/accounts-security.spec.ts` (ACCOUNTS-G88).
- **Propuesta**: `auth.mfaTrust(trust: boolean)` en el cliente de allauth del SDK, que devuelva la misma respuesta
  de sesión que `mfaAuthenticate`; con eso la página quita su `fetch`.
