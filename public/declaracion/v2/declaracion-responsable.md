# Declaración responsable del sistema informático de facturación «ERPlora Hub» — v2

**Artículo 13 del Reglamento (RD 1007/2023, texto consolidado a 03/12/2025)** — declaración
responsable de la persona o entidad **productora** del sistema informático de facturación.

> Sustituye a la versión **v1** (firmada el 2026-08-08), que **no se retira**: sigue amparando las
> versiones del producto anteriores a la **1.1.13** y se conserva en el archivo (art. 13.3). Lo que
> cambia es la **composición** del sistema, descrita en el apartado 4: la remisión delegada dejó de
> hacerse repartiendo el certificado de la productora a cada instalación y pasa a hacerse desde un
> componente propio de transmisión, la **celda fiscal**.

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
| `Version` | La declara cada instalación: es la versión del binario que ejecuta. Esta declaración responsable ampara las versiones indicadas en el apartado 9. |

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
   identidad fiscal del obligado, la custodia del certificado electrónico del obligado y el
   despachador de operaciones. Es el componente que ejecuta el **motor fiscal**.
2. **Motor fiscal** VERI\*FACTU — componente propio del productor, integrado en el núcleo, que
   genera el registro de facturación, calcula la **huella SHA-256 encadenada**, compone el XML
   completo según los esquemas publicados por la AEAT y gestiona la cola de reenvío ante
   incidencias. **Es el único componente que construye registros de facturación.**
3. **Módulos funcionales** — facturación, ventas, punto de venta, impuestos y catálogo, entre
   otros. Se instalan por obligado tributario según sus necesidades y **no** intervienen en el
   cálculo de la huella ni en la remisión.
4. **Interfaz de usuario** — aplicación web y aplicación instalable de escritorio y móvil, que son
   presentación del mismo sistema.
5. **Plano de control** — servicio del productor que sirve a cada instalación los datos
   identificativos del fabricante que figuran en el apartado 2, la referencia de la declaración
   responsable que la ampara y la autorización de uso de la celda fiscal cuando procede. **No
   construye, no valida y no conserva registros de facturación**, y **no entrega material
   criptográfico a ninguna instalación**.
6. **Celda fiscal** (`verifactu-gateway`) — componente de **transmisión** del productor, explotado
   por él en su propia infraestructura y separado de las instalaciones. Interviene **únicamente**
   en la vía delegada del apartado 7.2: recibe de la instalación el XML ya construido y lo entrega
   a la AEAT **sin modificarlo**, firmando el canal con el certificado de sello de entidad del
   productor. **No genera registros, no los altera y no los conserva**, y **no entrega certificados
   ni claves privadas a ninguna instalación**.

## 5. Funcionalidades relevantes a efectos del artículo 29.2.j) de la Ley 58/2003

- **Registro de facturación por cada factura**, generado automáticamente en el momento de su
  expedición, sin que su generación quede a decisión del usuario.
- **Encadenamiento**: cada registro incorpora la huella del registro anterior de la misma
  instalación y obligado, de modo que cualquier alteración u omisión posterior es detectable.
- **Integridad e inalterabilidad**: los registros no se modifican ni se borran; las correcciones se
  practican mediante registros de subsanación y facturas rectificativas, que quedan encadenados.
- **Trazabilidad y conservación**: se conservan los registros y el XML efectivamente remitido, con
  su huella SHA-256 y el identificador de la transmisión con que salió.
- **Remisión automática a la AEAT** de todos los registros, por la vía que corresponda según el
  apartado 7, con **cola de reenvío** ante falta de conexión o incidencia, hasta su remisión
  efectiva. No es posible que un registro generado quede sin remitir.
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
- **Conservación**: los registros de facturación se conservan durante los plazos legalmente
  exigibles, con copias de seguridad periódicas y verificadas.

## 7. Vías de remisión a la AEAT

El registro de facturación —su contenido, su huella y su encadenamiento— lo genera **siempre** el
motor fiscal de la instalación del obligado, y **es el mismo por las dos vías**. Lo que cambia entre
ellas es únicamente **con qué certificado se firma el canal** por el que se entrega a la AEAT. La
vía la determina el sistema, sin intervención del usuario: **si el obligado tiene certificado
propio, se usa el propio**; si no lo tiene, se usa la celda fiscal.

### 7.1 Vía propia — el obligado aporta su certificado

El obligado incorpora su certificado electrónico en su instalación, donde queda **cifrado en
reposo**. La instalación establece con la AEAT una conexión **TLS mutua** presentando ese
certificado y le entrega el registro directamente. **El certificado no sale de la instalación del
obligado**: ni el plano de control ni la celda fiscal acceden a él.

### 7.2 Vía delegada — la celda fiscal transmite por cuenta del obligado

Cuando el obligado no aporta certificado propio, su instalación construye el registro y el XML
completos exactamente igual y los entrega a la **celda fiscal**, que actúa como componente de
transmisión:

- La instalación envía el XML acompañado de su **huella SHA-256** y de un identificador de
  transmisión. La celda vuelve a calcular esa huella sobre lo que recibe, comprueba que el NIF del
  obligado que consta en el XML es aquel para el que está autorizada, y entrega a la AEAT **los
  mismos bytes**. **No recompone el XML, no lo reserializa y no altera el registro**; la
  instalación comprueba a su vez que la huella que la celda le devuelve es la de los bytes que
  envió, y si no coincide el registro vuelve a la cola en lugar de darse por remitido.
- La celda firma el canal con el **certificado cualificado de sello de entidad** de **ERPLORA
  CLOUD SL**, en su condición de **colaborador social** de la Administración tributaria: acuerdo de
  colaboración social de tipo 017 suscrito con la AEAT el **7 de septiembre de 2026** y alta en el
  censo de colaboradores sociales con efectos desde el **9 de septiembre de 2026**.
- La transmisión de registros reales por esta vía requiere el **otorgamiento de representación**
  del obligado tributario, otorgado sobre el modelo oficial, conservado por el productor y
  **revocable** por el obligado en cualquier momento. Revocado el otorgamiento, la vía delegada deja
  de estar disponible para esa instalación.
- Cuando quien presenta el registro y el obligado tributario son personas distintas, el registro
  incorpora el bloque `Representante` construido con la identidad del certificado que efectivamente
  firma el canal.
- **La celda no conserva registros de facturación.** El XML exacto, su huella, el identificador de
  transmisión, los intentos y la respuesta de la AEAT los conserva **la instalación del obligado**,
  que es también quien reintenta hasta obtener respuesta.
- La comunicación entre la instalación y la celda se establece por **TLS mutuo** con certificados
  de una autoridad de certificación interna del productor; la clave privada de cada instalación se
  genera **en la propia instalación** y no sale de ella.

## 8. Declaración

**ERPLORA CLOUD SL**, con NIF **B27593136**, en su condición de **productora** del sistema
informático de facturación **ERPlora Hub**, **DECLARA BAJO SU RESPONSABILIDAD** que dicho sistema,
en la modalidad **SOLO VERI\*FACTU**, en la composición descrita en el apartado 4 y en las versiones
amparadas por esta declaración, **cumple** lo dispuesto en el artículo 29.2.j) de la Ley 58/2003, de
17 de diciembre, General Tributaria, y en su desarrollo reglamentario (RD 1007/2023 y Orden
HAC/1177/2024).

## 9. Versiones amparadas y vigencia

Esta declaración ampara las versiones del producto **iguales o posteriores a la 1.1.13** —la primera
que incorpora la composición del apartado 4— y las instalaciones que las ejecutan. Las versiones
**anteriores a la 1.1.13** están amparadas por la declaración **v1**, que se conserva y no se
retira.

La versión que ejecuta cada instalación es la que consta como `Version` en cada uno de sus registros
de facturación, de modo que el registro remitido a la AEAT y la declaración que lo ampara son
comprobables entre sí. Cada nueva versión del sistema que altere lo declarado lleva su propia
declaración responsable, y **todas se conservan** (art. 13.3). El archivo completo, con esta y las
anteriores, está disponible en el propio sistema y se entrega al cliente y al comercializador en el
momento de la adquisición (art. 13.2).

## 10. Fecha y lugar de la firma (art. 13.4)

**Coslada (Madrid), España** — **2026-09-09**.

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
- AEAT — «Colaboración social en la aplicación de los tributos»: remisión por un tercero con
  certificado cualificado propio, acuerdo de tipo 017 y otorgamiento del obligado.
