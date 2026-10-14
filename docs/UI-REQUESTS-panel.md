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

## 2. `DataTable`: en el móvil, sin el título cuando hay buscador

- **Qué pasa**: a ≤640 px el buscador ocupa su línea (`flex-basis: 100%`) y el título va en otra: una lista con
  título y buscador gasta tres líneas de barra (título · buscador · resto). En el panel la topbar y la tabbar ya
  nombran la lista y el pie la cuenta.
- **Rodeo hoy**: `frontend/panel-fill.css` (global del panel), en `@media (max-width: 640px)`:
  `.panel-fill .data-table__bar-main:has(> .data-table__search) > .data-table__title-wrap { display: none }`.
  Depende de las clases internas `data-table__*`.
- **Propuesta**: una prop (p. ej. `titleOnPhone: false`) o ese comportamiento por defecto cuando hay buscador.

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
- **Rodeo hoy**: `frontend/panel-fill.css` (`.panel-fill`, cargado por `main.ts`): pila en columna a `height:
  100%`; lo que no es la lista conserva su alto; la lista (`.data-table--fill` o una `.panel-fill` anidada) se
  queda el resto, con un suelo de `20rem` en escritorio y tableta (`--panel-list-min`) para que los avisos de
  arriba empujen la página antes que dejar la lista en nada. En el móvil sigue el `fill` propio de `DataTable`
  (crece con sus filas desde la altura de la página, un solo scroll).
- **Propuesta**: que `AppPage` (o `@erplora/ui`) ofrezca esa pila (`<FillStack>` o una clase del tema) para el
  Hub y el SaaS, en vez de que cada proyecto la escriba.
