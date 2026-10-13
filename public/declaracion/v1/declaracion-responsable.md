# Declaración responsable del sistema informático de facturación «ERPlora Hub» — v1

**Artículo 13 del Reglamento (RD 1007/2023, texto consolidado a 03/12/2025)** — declaración
responsable de la persona o entidad **productora** del sistema informático de facturación.

---

## 1. Declarante (productor del sistema)

| Dato | Valor |
|---|---|
| Razón social | **ERPLORA CLOUD SL** |
| NIF | **B27593136** |
| Domicilio | Avda. de Lisboa, 17, 2º C — 28822 Coslada (Madrid), España |
| Condición | **Productora** del sistema informático de facturación descrito en el apartado 2 |

## 2. Identificación del sistema informático

| Campo | Valor |
|---|---|
| Denominación comercial | **ERPlora Hub** |
| `NombreSistemaInformatico` (registro de facturación) | **ERPlora Hub** |
| `IdSistemaInformatico` (registro de facturación) | **EC** |
| `NombreRazon` / `NIF` del productor en el registro | **ERPLORA CLOUD SL** / **B27593136** |
| `NumeroInstalacion` | El identificador único de cada instalación (`hub_id`, UUID v4). Cada instalación es un sistema informático distinto, con su propia cadena de registros. |
| `Version` | La declara cada instalación: es la versión del binario que ejecuta. Esta declaración responsable ampara la versión del producto indicada en el apartado 8. |

> El `IdSistemaInformatico` es un código de dos posiciones que **asigna el propio fabricante** a su
> producto (FAQ de desarrolladores de la AEAT, §4). No lo otorga ni lo registra la Administración.

## 3. Modalidad declarada

| Campo | Valor |
|---|---|
| Modalidad | `SOLO VERI*FACTU` |

El sistema **solo** puede utilizarse como sistema de emisión de facturas verificables: remite a la
Agencia Estatal de Administración Tributaria, de forma automática y sin intervención del usuario,
todos los registros de facturación que genera. En consecuencia:

- `TipoUsoPosibleSoloVerifactu` = **S** en todos los registros de facturación.
- `TipoUsoPosibleMultiOT` = **S**: el sistema puede dar servicio a varios obligados tributarios,
  cada uno con su instalación y su cadena independientes.
- El sistema **no** dispone de modalidad «no VERI\*FACTU», por lo que **no** genera registros de
  evento (art. 16 del Reglamento; FAQ de desarrolladores §15, nota 1), que solo son exigibles a los
  sistemas que admiten ambas modalidades.

## 4. Tipología y composición

**Tipología:** sistema informático de facturación **multiusuario y multiobligado**, explotado en la
modalidad de **software como servicio (SaaS)** por el productor, con una **instalación
independiente por obligado tributario**.

**Composición:**

1. **Núcleo de ejecución (runtime)** — programa que integra el registro de usuarios y permisos, la
   identidad fiscal del obligado, la custodia del certificado electrónico y el despachador de
   operaciones. Es el componente que ejecuta el **motor fiscal**.
2. **Motor fiscal VERI\*FACTU** — componente propio del productor, integrado en el núcleo, que
   genera el registro de facturación, calcula la **huella SHA-256 encadenada**, compone el XML según
   los esquemas publicados por la AEAT, lo remite mediante **TLS mutuo** y gestiona la cola de
   reenvío ante incidencias.
3. **Módulos funcionales** — facturación, ventas, punto de venta, impuestos y catálogo, entre
   otros. Se instalan por obligado tributario según sus necesidades y **no** intervienen en el
   cálculo de la huella ni en la remisión.
4. **Interfaz de usuario** — aplicación web y aplicación instalable de escritorio y móvil, que son
   presentación del mismo sistema.
5. **Plano de control** — servicio del productor que distribuye el certificado electrónico de
   remisión delegada y los datos identificativos del fabricante a las instalaciones.

## 5. Funcionalidades relevantes a efectos del artículo 29.2.j) de la Ley 58/2003

- **Registro de facturación por cada factura**, generado automáticamente en el momento de su
  expedición, sin que su generación quede a decisión del usuario.
- **Encadenamiento**: cada registro incorpora la huella del registro anterior de la misma
  instalación y obligado, de modo que cualquier alteración u omisión posterior es detectable.
- **Integridad e inalterabilidad**: los registros no se modifican ni se borran; las correcciones se
  practican mediante registros de subsanación y facturas rectificativas, que quedan encadenados.
- **Trazabilidad y conservación**: se conservan los registros y el XML efectivamente remitido.
- **Remisión automática a la AEAT** de todos los registros, con **cola de reenvío** ante falta de
  conexión o incidencia, hasta su remisión efectiva. No es posible que un registro generado quede
  sin remitir.
- **Legibilidad y accesibilidad** de los registros conservados.
- **Código «QR» tributario** y mención «VERI\*FACTU» en las facturas expedidas.
- **Separación de entornos**: los registros de prueba y los reales pertenecen a cadenas distintas y
  se remiten a sistemas distintos; el paso a producción es de un solo sentido.
- **Accesos identificados**: toda operación queda atribuida a un usuario identificado del sistema.

## 6. Características de la instalación

- **Instalación por obligado tributario**, con base de datos propia y aislada; cada instalación
  posee un `NumeroInstalacion` único e irrepetible, que no se reutiliza ni siquiera reinstalando.
- **Explotación**: en la infraestructura del productor, en la Unión Europea. El obligado no precisa
  instalar componentes en sus equipos; la aplicación instalable es únicamente acceso al sistema y a
  los periféricos del punto de venta.
- **Actualización**: la realiza el productor; el obligado no puede alterar los componentes del
  sistema ni ejecutar versiones no publicadas por aquel.
- **Certificado electrónico**: la remisión se firma con el certificado del propio obligado
  tributario cuando este lo aporta y, en su defecto, con el del productor en su condición de
  colaborador social de la Administración tributaria, previo otorgamiento suscrito por el obligado.
- **Conservación**: los registros de facturación se conservan durante los plazos legalmente
  exigibles, con copias de seguridad periódicas y verificadas.

## 7. Declaración

**ERPLORA CLOUD SL**, con NIF **B27593136**, en su condición de **productora** del sistema
informático de facturación **ERPlora Hub**, **DECLARA BAJO SU RESPONSABILIDAD** que dicho sistema,
en la modalidad **SOLO VERI\*FACTU** y en la versión amparada por esta declaración, **cumple** lo
dispuesto en el artículo 29.2.j) de la Ley 58/2003, de 17 de diciembre, General Tributaria, y en su
desarrollo reglamentario (RD 1007/2023 y Orden HAC/1177/2024).

## 8. Versión amparada y vigencia

Esta declaración ampara la versión **v1** del producto y las instalaciones que la ejecutan. Cada
nueva versión del sistema lleva su propia declaración responsable, y **todas se conservan**
(art. 13.3). El archivo completo, con esta y las anteriores, está disponible en el propio sistema y
se entrega al cliente y al comercializador en el momento de la adquisición (art. 13.2).

## 9. Fecha y lugar de la firma (art. 13.4)

**Coslada (Madrid), España** — **2026-08-08**.

Firmado por el representante legal de ERPLORA CLOUD SL.

---

### Fuentes normativas

- RD 1007/2023, de 5 de diciembre, **art. 13** (texto consolidado a 03/12/2025).
- Ley 58/2003, General Tributaria, **art. 29.2.j)**.
- Orden HAC/1177/2024, de 17 de octubre (especificaciones técnicas).
- AEAT — «Certificación de los sistemas informáticos: declaración responsable» (act. 22/07/2026):
  *no se requiere certificación por terceros ni registro previo del producto SIF*.
- AEAT — FAQ de desarrolladores v1.3, de 04/12/2025: §4 (`IdSistemaInformatico` lo asigna el
  fabricante) y §15 nota 1 (el registro de eventos solo es exigible en modalidad dual).
