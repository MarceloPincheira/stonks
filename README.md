# Stonks

Calculadora de proyección de inversión con aportes por tramos de meses.

## Cómo correrla

```bash
make init
```

Prepara la base, arranca el servidor y dice en la consola dónde quedó escuchando
(http://127.0.0.1:8420 por defecto; `make init PORT=9000` para otro). Si el puerto está
ocupado avisa en vez de reventar con un traceback.

| Comando | Qué hace |
|---|---|
| `make init` | Base + servidor, con la URL en pantalla |
| `make stop` | Mata el servidor que esté escuchando en ese puerto |
| `make restart` | Los dos anteriores: necesario al tocar un `.py` |
| `make db` | Sólo crea la base y aplica migraciones |
| `make help` | Lista los comandos |

Si el puerto está ocupado, `make init` toma el primero libre que encuentre y lo dice en pantalla,
en vez de caerse.

La base (`stonks.db`) **no se versiona**: guarda el perfil con sueldo, saldo AFP y fecha de
nacimiento. La que trae el repo es un perfil de demostración —imponible $1.200.000 sin
asignaciones, sin saldo AFP acumulado, aportes de $200.000 al mes— y es el mismo con el que
están calculados los ejemplos de este README. Lo primero al usarla es abrir **Mi perfil** y
reemplazarlo por los datos propios.

También sirve `python3 server.py` a secas, o `PORT=9000 python3 server.py`.

Backend sin dependencias: sólo Python 3 de la stdlib (`http.server` + `sqlite3`).
El frontend usa **Chart.js** (gráfico) y **Grid.js** (tabla), ambas vanilla y **descargadas en
`static/vendor/`**, así que la app funciona sin internet.

> Si tocas un `.py`, reinicia el servidor (`make restart`): Python mantiene los módulos
> cargados en memoria.

La interfaz es **reactiva**: cualquier cambio en los parámetros o en los tramos vuelve a
proyectar solo (debounce de 220 ms), sin botón de calcular. El badge junto a "Resultado"
indica el estado: *calculando…*, *actualizado* o *esperando datos…* cuando hay un campo a
medio escribir. Las respuestas que llegan fuera de orden se descartan, así que el número en
pantalla siempre corresponde a lo último que escribiste.

## Qué hace

- **Dos modelos de retorno**:
  - *Simple*: una sola tasa de retorno total anual (X%), convertida a tasa mensual equivalente `(1+X)^(1/12)-1` y reinvertida siempre.
  - *Con dividendos*: separa la **plusvalía de la cuota** (se capitaliza mes a mes) del **dividend yield** (se paga en los meses que indiques), con un checkbox para **reinvertir los dividendos o cobrarlos en efectivo**. Si no se reinvierten, se acumulan aparte sin rentar.
- **Tramos de aporte**: defines rangos de meses a demanda (`1-60: $100`, `61-120: $200`, ...). Los rangos son inclusivos, se validan contra solapamientos y los meses sin tramo aportan $0.
- **Horizonte Z (años)**: la proyección corre `Z*12` meses. Si un tramo se pasa del horizonte, se recorta; si dejas de aportar antes, el capital sigue capitalizando.
- **Aportes extraordinarios**: montos puntuales amarrados a un mes de calendario y escritos en pesos de hoy — [ver](#aportes-extraordinarios).
- **Sueldo y descuentos reales**: imponible y asignaciones no imponibles, cotizaciones con tope de 90 UF (135,2 UF la cesantía) e impuesto único de segunda categoría — [ver](#sueldo-imponible-y-no-imponible).
- **Tu AFP**: proyección del saldo con las rentabilidades del sistema y los traspasos por edad, y la pensión que financia, que se descuenta de la meta desde que jubilas — [ver](#la-pensión-de-la-afp-dentro-de-la-meta).
- **Fase de retiro**: desde que dejas de aportar, a qué edad el patrimonio llega a cero y cuánto podrías gastar para que dure justo hasta la edad que quieras — [ver](#fase-de-retiro-llevar-el-patrimonio-a-cero).
- Resultado: tarjetas con la cifra nominal y su equivalente en pesos de hoy, gráfico que llega hasta la expectativa de vida —con el saldo AFP y la rama de consumo— y tablas por año, mes a mes y de poder adquisitivo.

Convenciones del modelo:

- El aporte del mes entra al inicio del mes y renta ese mismo mes (anualidad anticipada).
- El dividendo se calcula sobre el valor del portafolio al momento del pago y **no** se descuenta del capital: la plusvalía histórica de un fondo de reparto ya viene neta de los repartos, así que restarla sería contarla dos veces.
- El yield anual se reparte en partes iguales entre los meses de pago. En CFINRENTAS los pagos reales son desiguales (el de abril es el grande), lo que mueve el resultado a 30 años en décimas de punto.

## La tabla de resultados

Las columnas cambian según el modo, para que nunca haya dos que valgan lo mismo (con
reinversión, "en el fondo" y "valor total" son idénticas; sin ella, "aportado + reinvertido"
es igual a "aportado"). En modo dividendos con reinversión:

| Columna | Qué es |
|---|---|
| Aportado por ti | Sólo el dinero de tu bolsillo, sin reinversión |
| Aportado + reinvertido | Tus aportes más los dividendos que volvieron al fondo |
| Dividendos del año | Lo repartido durante ese año |
| Dividendos acum. | Todo lo repartido hasta ese año |
| Plusvalía acum. | Cuánto subieron las cuotas por sobre el capital puesto |
| Valor total | Lo que tendrías ese año |
| Ganancia | **Dividendos acum. + plusvalía acum.**, que es lo mismo que valor total − aportado por ti |

Cada encabezado lleva esa explicación como tooltip. Al hacer clic en una celda se resalta su
fila y su columna completas; un segundo clic lo apaga. Los encabezados ordenan por valor
numérico, no alfabético.

Sin paginación: se renderizan todas las filas (30 en la vista anual, 360 en la mensual) dentro
de un alto fijo de 460 px con scroll interno y encabezado fijo, así el largo de la página no
crece con el horizonte.

## Mi perfil y la AFP

Botón **👤 Mi perfil** en la cabecera; todo se configura en un modal para no cargar la
pantalla principal. Guarda datos personales, sueldo con sus descuentos, AFP, y **el plan de
aporte** —tramos mensuales y aportes extraordinarios—: viven en el perfil y no en cada
escenario, así cambiar de instrumento no obliga a reescribirlos (se guardan solos ~1,5 s
después de editarlos). La UF y la UTM también se editan ahí: mueven el tope imponible y los
tramos del impuesto.

La **edad se deriva de la fecha de nacimiento**, no se ingresa a mano, y con decimales: a los
36,23 años quedan 28,8 años exactos de cotización.

El modal es **reactivo**, igual que la pantalla principal: cada tecla vuelve a proyectar
(debounce de 220 ms, respuestas fuera de orden descartadas) contra `POST /api/afp/preview`,
que calcula **sin guardar**; el botón sigue siendo el que persiste. Cerrar sin guardar
devuelve el banner a lo que estaba en la base.

### Sueldo: imponible y no imponible

El sueldo se ingresa en dos campos porque no todo cotiza:

- **Sueldo imponible**: la parte que paga AFP, salud y cesantía. AFP y salud cotizan hasta
  **90 UF**; el **seguro de cesantía tiene tope propio y mayor, 135,2 UF** (AFC, 2026), así que
  se topa aparte.
- **Asignaciones no imponibles** (colación, movilización): no cotizan ni descuentan, entran
  enteras al líquido.

De esa suma sale el **bruto percibido**, que el modal muestra junto al **líquido aproximado**
y el desglose de descuentos, actualizándose mientras escribes:

```
bruto percibido = imponible + no imponibles
líquido         = bruto percibido − (AFP 10% + comisión + salud + cesantía + impuesto único)
```

Ejemplo, con UF $40.884,32 y UTM $71.721: un imponible de $1.200.000 sin asignaciones tiene
descuentos por $226.653 —AFP $120.000, comisión $15.240, salud $84.000, cesantía $7.200 e
impuesto $213— y líquido **$973.347**. Ese sueldo no alcanza el tope imponible de $3.679.589:
por sobre esa cifra las cotizaciones dejan de subir. El adicional de Isapre, si lo hay, se
descuenta también.

### Impuesto único de segunda categoría

Tabla mensual del art. 52 de la LIR, tal como la publica el SII. Está expresada en UTM, así
que no envejece con la inflación: lo único que hay que actualizar es el valor de la UTM, que
es un campo del perfil junto a la UF.

| Renta afecta (UTM) | Factor | Rebaja (UTM) |
|---|---|---|
| hasta 13,5 | exento | — |
| 13,5 – 30 | 0,04 | 0,54 |
| 30 – 50 | 0,08 | 1,74 |
| 50 – 70 | 0,135 | 4,49 |
| 70 – 90 | 0,23 | 11,14 |
| 90 – 120 | 0,304 | 17,80 |
| 120 – 310 | 0,35 | 23,32 |
| 310 y más | 0,40 | 38,82 |

El impuesto es `base × factor − rebaja × UTM`. Las rebajas empalman los tramos: a 30 UTM
`0,04·30 − 0,54` y `0,08·30 − 1,74` dan ambos 0,66 UTM, y lo mismo en cada corte, así que la
escala es continua y progresiva pese a aplicarse de forma directa.

> Ojo con los dos últimos tramos: el del 35% llega hasta **310 UTM**, no hasta 150, y por eso
> la rebaja del 40% es 38,82 (`0,35·310 − 23,32 = 0,40·310 − 38,82 = 85,18 UTM`). Cortarlo
> antes deja la escala igual de continua, así que el error no se delata solo: hay que
> contrastarlo contra la tabla del SII.

La **base afecta** no es el bruto:

- Parte de la renta **imponible**, no del bruto percibido: las asignaciones no imponibles
  razonables (colación, movilización) no son renta afecta.
- Se le restan las **cotizaciones obligatorias efectivamente pagadas** — AFP, comisión, el 7%
  de salud y la cesantía —, que se calculan sólo hasta sus topes (90 UF; 135,2 UF la
  cesantía). El adicional de
  Isapre **no** rebaja la base: sale del líquido pero no es cotización obligatoria.

En ese mismo ejemplo: base $973.560 (13,6 UTM, segundo tramo) →
`0,04 × 973.560 − 0,54 × 71.721` = **$213** de impuesto. Apenas asoma sobre el tramo exento de
13,5 UTM, que es justamente lo que hace la rebaja: gravar el exceso y no el total.

### Parámetros legales (`afp.py`)

Rentabilidad **real** anualizada del sistema desde el inicio de los multifondos (sep-2002),
según la Superintendencia de Pensiones. Son reales, o sea ya descontada la inflación, que
calza con proyectar en pesos de hoy:

| Fondo | A | B | C | D | E |
|---|---|---|---|---|---|
| Real anual | 5,95% | 5,11% | 4,30% | 3,47% | 2,80% |

Descuentos del sueldo: **10%** a la cuenta individual, **comisión AFP** (0,49% Uno a 1,45%
ProVida; se autocompleta al elegir la AFP), **7%** de salud, **0,6%** de cesantía con contrato
indefinido, todo con tope imponible de **90 UF**. La cotización del empleador de la Ley 21.735
sube gradualmente hasta 8,5% en 2033, pero sólo una fracción llega a la cuenta individual
(hoy 0,1%): ese porcentaje es un campo editable.

### Traspaso automático por edad

El DL 3.500 asigna fondo B hasta los 35, C hasta los 55 (hombres) o 50 (mujeres), y D después,
a quien nunca eligió. El campo **trayectoria de fondos** ofrece tres caminos:

| Trayectoria | Qué modela |
|---|---|
| Me quedo en mi fondo hasta que la ley me obligue | Sigues en el fondo elegido; el único cambio forzoso es la salida del **fondo A** a los 56 (hombres) o 51 (mujeres), y el destino (B, C, D o E) lo eliges tú |
| Traspaso por edad · básico | Hitos a los 36 y 56/51, terminando en D |
| Traspaso por edad · ampliado | Hitos a los 31, 36, 56/51 y 61/56, terminando en E |

Los traspasos no son automáticos: se contratan con la AFP, y tampoco son de golpe. Se mueve
**20% del saldo al cumplir la edad y 20% más cada año** hasta completarse a los cuatro, así
que en el intermedio la rentabilidad es el promedio ponderado de los fondos en que está
repartido el saldo. Fuera del A ningún fondo tiene tope de edad: en B puedes quedarte hasta
jubilar.

> **Abril de 2027**: los multifondos se reemplazan por **diez fondos generacionales** asignados
> por año de nacimiento, sin posibilidad de elegir en el ahorro obligatorio. La proyección
> sigue usando la trayectoria de los multifondos porque los nuevos todavía no tienen
> rentabilidad observada; conceptualmente son lo mismo, una cartera que se vuelve conservadora
> al acercarse la jubilación.

**Valores de referencia** (`afp.py`): UF $40.884,32 (8-sep-2026, Banco Central) y UTM $71.721
(sep-2026, SII). Ambos se editan en el perfil y conviene actualizarlos: la UF mueve el tope
imponible y la UTM mueve todos los tramos del impuesto.

Lo que el líquido todavía no considera: APV, cargas familiares, anticipos, otros descuentos
voluntarios y el ajuste anual de la Operación Renta.

## Aportes extraordinarios

Además de los tramos mensuales hay montos puntuales —vender una propiedad heredada, un bono,
una indemnización— que se ingresan con **mes y año de calendario**, no con número de mes de la
proyección, porque así es como uno los piensa. Viven en el perfil junto al plan de aporte, así
que valen para todos los escenarios.

El monto se escribe en **pesos de hoy** y la app lo lleva al valor nominal del mes en que cae:

```
nominal = monto de hoy × (1 + inflación)^(mes/12)
```

Es el mismo factor con que se deflacta todo lo demás, aplicado al revés. Con 4,12% de
inflación, $20.000.000 de hoy vendidos en marzo de 2032 son **$24.722.042** de ese momento,
que es lo que hay que sumar al fondo para que el poder adquisitivo cuadre. Cada fila muestra
esa equivalencia y el número de mes de la proyección en que entra.

El mes se calcula contra la fecha de inicio de la inversión del perfil (*empiezo a invertir
en*). Si el aporte cae fuera del horizonte la fila lo dice y la proyección lo ignora, en vez
de bloquear el cálculo mientras se escribe. En la vista mes a mes el aporte aparece marcado
con una etiqueta *extra*, y entra al fondo al inicio de ese mes como cualquier otro aporte.

## La pensión de la AFP dentro de la meta

Desde la edad de jubilación parte de la meta la paga la AFP, así que la inversión sólo tiene
que cubrir la diferencia. El checkbox **Contar la pensión de la AFP** lo activa (viene
encendido) y el escenario recuerda la elección; el monto no se guarda en el escenario, sale
del perfil, así que cambiar de fondo o de AFP lo actualiza en todos a la vez.

```
falta cubrir = meta del mes − pensión de la AFP
```

Ambas cifras van en pesos del año que toque. La pensión se toma **constante en pesos de hoy**
porque tanto la renta vitalicia como el retiro programado se pagan en UF: en nominal crece
con la inflación igual que la meta. El año en que la pensión empieza se prorratea por los
meses que alcanza a pagar, y la columna *Cobertura* pasa a medirse contra lo que falta
después de la pensión, no contra la meta completa.

### Cómo la calcula la AFP, y cómo la aproxima esto

La AFP divide el saldo por doce veces el **Capital Necesario Unitario (CNU)**:

```
pensión mensual = saldo / (12 × CNU)
```

El CNU es el capital que financia una unidad anual de pensión: el valor presente de pagar $1
al año mientras el afiliado (y sus beneficiarios) sigan vivos. Cada periodo futuro se pondera
por la probabilidad de seguir vivo según las **tablas de mortalidad** vigentes —CB-H-2020 para
hombres, RV-M-2020 para mujeres, con sus factores de mejoramiento— y se descuenta a la **tasa
de interés técnica**, que la Superintendencia de Pensiones fija cada trimestre ponderando la
tasa implícita de las rentas vitalicias del año anterior con la rentabilidad promedio de los
fondos de los últimos cinco años. Es una tasa real, porque el sistema opera en UF.

`afp.py` aproxima ese CNU con una **renta cierta a lo largo de la expectativa de vida**, sin
arrastrar las tablas completas:

| Parámetro | Valor | Fuente |
|---|---|---|
| Tasa técnica | 3,45% real | TITRP del 3.º trimestre de 2026, Circular N° 2.417 |
| Expectativa a los 65 (hombre) | 21,6 años | tablas de mortalidad 2020 |
| Expectativa a los 60 (mujer) | 30,8 años | ídem |

Dos diferencias que conviene tener claras:

- La aproximación **sobrestima el CNU** y por lo tanto deja la pensión del lado conservador:
  el valor presente es cóncavo en la duración, así que el promedio de los plazos posibles vale
  menos que el plazo promedio.
- El **retiro programado se recalcula todos los años y va decreciendo**; esto se parece más a
  una renta vitalicia, constante en UF. Tampoco modela beneficiarios de sobrevivencia (que
  suben el CNU y bajan la pensión) ni la PGU.

## Fase de retiro: llevar el patrimonio a cero

Hasta aquí todo era acumular. La fase de retiro responde la otra mitad: **desde que dejas de
aportar, ¿cuánto dura lo que juntaste?** Corre desde el último mes con aporte hasta la edad
objetivo, y cada mes junta la meta en pesos de ese año con esta prelación:

1. La **pensión de la AFP**, desde la edad de jubilación.
2. Los **dividendos** del mes, que no se descuentan del capital (misma convención que en la
   acumulación).
3. Lo que falte se **vende del fondo**. Si sobra, vuelve al fondo.

Sirve igual con el modelo simple que con el de dividendos: sin dividendos, todo el gasto sale
de vender capital. De ahí salen las dos respuestas:

- **A qué edad el patrimonio llega a cero** con el gasto que pusiste como meta.
- **Cuánto podrías gastar al mes** para llegar justo a cero en la edad objetivo, que se
  resuelve por bisección: el saldo final es monótono decreciente en el gasto.

La **edad objetivo** viene por defecto en la expectativa de vida que la AFP usa para calcular
la pensión (86,6 años para un hombre, 90,8 para una mujer), y se puede cambiar. El selector
*gasto mensual en el retiro* decide qué simula el gráfico: tu meta, o el máximo que dura hasta
esa edad.

> Entre los 50 y los 65 —o donde caiga tu caso— hay un tramo sin pensión en que todo el gasto
> sale del fondo: es el que más rápido lo consume, y por eso el gráfico ahora llega hasta la
> expectativa de vida en vez de cortarse en el horizonte.

### Trabajo hasta los X

Campo aparte de la edad objetivo: **hasta cuándo trabajas**, por defecto la edad legal de
pensión. Bajarlo corta dos cosas a la vez, porque las dos salen del mismo sueldo:

- Las **cotizaciones a la AFP**. El saldo sigue rentando hasta jubilar, pero sin plata nueva:
  en el ejemplo de arriba, dejar de trabajar a los 55 baja el saldo al jubilar de $90,8 M a
  $71,9 M y la pensión de $495.031 a $392.012.
- Los **aportes al fondo**. Los tramos definidos más allá de esa edad se recortan, y el texto
  dice cuántos meses quedaron fuera para que no se pierda en silencio.

La pensión sigue calculándose a la edad legal aunque dejes de cotizar antes: adelantarla tiene
requisitos propios que esto no modela. Por lo mismo el campo no acepta pasarse de la edad de
pensión, porque postergar cambia la expectativa de vida y con ella el CNU.

### La tabla de hitos

Bajo los campos de la fase de retiro va el resumen de dónde está toda la plata en cada momento
que importa, **en pesos de hoy** —la única unidad en que cifras de años distintos se pueden
comparar— y separada en las dos bolsas que casi nunca se miran juntas:

| Hito | Qué muestra |
|---|---|
| Empiezas a invertir | El fondo con tu primer aporte y la AFP con lo que ya tienes |
| Dejas de trabajar | Lo acumulado en cada una justo antes de que se corte la plata nueva |
| Jubilas | El fondo ya consumido unos años y el saldo AFP que financia la pensión |
| Se acaba el fondo | Sólo si se agota antes: desde ahí vives sólo de la pensión, y dice cuánto falta |
| Edad objetivo | Con qué llegas: la AFP en cero y el fondo con lo que quede |

Siguiendo el ejemplo, aportando $200.000 al mes, trabajando hasta los 55 y con una meta de
$800.000 al mes: llegas a los 55 con $112,3 M en el fondo y $43,7 M en la AFP ($155,9 M en
total), a los 65 la pensión parte en $392.012 y el fondo aguanta justo: a los 86,6 quedarían
$6,9 M en pesos de hoy. El techo sostenible es **$806.952** al mes, así que la meta de $800.000
pasa raspando.

Sobre el gráfico hay un selector de unidad: **pesos nominales** (los de cada año, como las
tarjetas) o **pesos de hoy** (cada punto dividido por `(1+i)^(mes/12)`). Conviene tenerlo a
mano porque el modal del perfil habla siempre en pesos de hoy: en esa unidad el máximo de la
curva de la AFP coincide con el saldo al jubilar del perfil, y en nominales es tres veces más
grande a 30 años. El tooltip muestra siempre la otra unidad entre paréntesis.

El tooltip cierra con el **patrimonio total** del mes: fondo más AFP. Cuando existe la rama
de consumo manda ella y no la de acumulación, porque son el mismo fondo bajo dos supuestos y
sumarlas lo contaría dos veces.

### Dos preguntas distintas que parecían contradecirse

Las tarjetas y los banners de arriba responden *¿los dividendos cubren la meta sin tocar el
capital, dentro del horizonte?*; la fase de retiro responde *¿alcanza la plata hasta la edad
objetivo, consumiéndola y con la pensión?*. Son preguntas distintas y pueden dar respuestas
opuestas —"no alcanzas la meta" junto a "el patrimonio no se agota"— sin que ninguna esté
mal. Por eso los banners del horizonte cierran diciendo qué concluye la fase de retiro, y las
tarjetas dicen en su descripción si tocan o no el capital.

El gráfico suma dos series a las de siempre: el **saldo en la AFP**, que sube mientras cotizas
y baja mientras te paga la pensión hasta agotarse justo en la expectativa de vida, y la rama de
**consumo**, que arranca donde dejas de aportar.

Cuando el horizonte es más largo que los aportes, el fondo queda dibujado dos veces y los
nombres lo dicen: *valor acumulado · sin consumir nada* es lo que tendrías si no sacaras un
peso, y *consumiendo tu meta desde los X* descuenta mes a mes lo que gastas. Es el mismo
dinero bajo supuestos opuestos, y la distancia entre las dos curvas es lo consumido más lo que
ese dinero habría rentado. Por eso el total del tooltip usa la rama de consumo cuando existe:
sumar las dos contaría el fondo dos veces.

## Corrección por inflación

Responde: *¿cuánto tendré que recibir en el año X para vivir como vivo hoy con $2.000.000
al mes?* La app calcula la meta nominal, la compara con los dividendos proyectados y dice
en qué año la alcanzas.

### La serie usada

`inflation.py` lleva la variación anual del IPC chileno (dic-dic) desde el año 2000. Parte
ahí a propósito: Chile adoptó metas de inflación con tipo de cambio flotante en 1999, y los
años previos (30% en 1990, convergiendo desde el ciclo inflacionario del siglo XX)
pertenecen a otro régimen monetario, así que mezclarlos sesgaría la estimación al alza.

| Ventana | Media geométrica | Años de crisis incluidos |
|---|---|---|
| Meta del Banco Central | 3,00% | — |
| Últimos 10 años (2016-2025) | 4,58% | 3 |
| Últimos 20 años (2006-2025) | 4,12% | 6 |
| **2000-2025 (26 años)** | **3,83%** | 6 |

El default es la ventana de 26 años. Una de 10 años puede caer entera dentro de un régimen
benigno o de uno de crisis: la de 2016-2025 da 4,58% porque está dominada por el shock de
2022 (12,8%), mientras que la larga cubre dos ciclos completos — subprime 2008-09 y el shock
2021-22 — que es lo que corresponde para proyectar a 30 años.

### Vivir de la rentabilidad sin descapitalizarse

"Que la inversión no decrezca" en términos reales no significa que el capital nominal no baje
—con dividendos como flujo aparte, nunca baja— sino que **no pierda poder adquisitivo**. Para
eso el capital debe crecer al menos como la inflación. La plusvalía aporta parte; el resto
tiene que salir de reinvertir dividendos:

```
tasa de retiro sostenible = dividend yield − máx(0, inflación − plusvalía)
```

Con yield 6,5%, plusvalía 3% e inflación 4,12%: hay que reinvertir permanentemente el
**17,2%** de los dividendos, y lo que queda para vivir es **5,38% anual** del capital, no el
6,5% nominal. La app calcula el primer año en que ese retiro sostenible cubre tu meta —el
**año de independencia**— y lo distingue del año en que los dividendos brutos la cubren, que
llega antes pero es insostenible: consumir el yield completo con plusvalía bajo la inflación
hace decrecer el poder adquisitivo año a año.

Si `plusvalía ≥ inflación`, la tasa sostenible es el yield completo. Si el yield no alcanza a
cubrir la brecha, la app avisa que no hay punto sostenible con esos supuestos.

### Impuesto sobre los repartos

Campo **Impuesto sobre los repartos (%)** en el modelo de dividendos. Cada reparto se descuenta
esa fracción **antes** de reinvertirse o cobrarse, porque el impuesto no se puede reinvertir.

Viene en **0% por defecto** —la tasa efectiva depende del tramo de cada uno— pero está a la
vista a propósito: dejarlo implícito equivalía a proyectar libre de impuestos sin decirlo, y
eso no es neutro. Reinvertir el reparto bruto de CFINRENTAS a 30 años infla el resultado un
**24%** frente a hacerlo con una tasa efectiva del 23%.

Qué tributa y qué no, para elegir el número:

- **Los repartos sí.** Las distribuciones de un fondo de inversión y los dividendos de
  acciones son renta afecta al global complementario (con crédito por impuesto de primera
  categoría en el caso de las acciones).
- **La ganancia de capital, casi no.** El [art. 107 de la LIR](https://www.sii.cl/normativa_legislacion/circulares/2022/circu39.pdf)
  grava con impuesto único de 10% el mayor valor en la enajenación de instrumentos con
  presencia bursátil hasta el 31-dic-2026, y desde el 1-ene-2027 vuelve a ser ingreso no
  renta. En un horizonte de décadas la venta queda esencialmente exenta, y por eso el modelo
  no la grava.

La cobertura de la meta, el retiro sostenible y el capital necesario se miden todos contra el
reparto **neto**, que es de lo que se vive.

### Esto es un escenario, no un pronóstico

Bajo el resultado va una franja con el rango que producen **±1 punto de retorno y ±1 punto de
inflación** — menos de una desviación estándar histórica (el IPC anual 2000-2025 tiene
desviación estándar de 2,59 puntos). Son cuatro proyecciones extra sobre el mismo escenario:
no es un Monte Carlo, es la banda mínima honesta.

Hace falta porque la sensibilidad es grande y no se ve:

| Plusvalía | Se agota a los |
|---|---|
| 3,71% | 69 años |
| 5,71% | 71 años |
| 7,71% | 76 años |

Casi siete años de rango por mover la plusvalía ±2 puntos. Por lo mismo la **edad de
agotamiento se publica en años enteros**: con un decimal se leía como una medición.

### Nominal vs. pesos de hoy

Cada tarjeta muestra la cifra nominal arriba y su equivalente en pesos de hoy debajo: son el
mismo dinero y separarlas en tarjetas distintas se prestaba para confusión. Los equivalentes
reales **deflactan cada flujo en el momento en que ocurrió** (`Σ flujo_m / (1+i)^(m/12)`), no
la suma total con un único factor: sumar aportes de 30 años distintos y luego dividirlos por
un solo deflactor mezclaría pesos heterogéneos.

Las tarjetas van en orden: lo que pones → lo que genera → lo que resulta → cuándo eres libre.

### Decisiones estadísticas

- **Media geométrica, no aritmética.** Promediar +12,8% y −1,4% aritméticamente no equivale
  al efecto compuesto de haber vivido ambos años; la aritmética sobreestima.
- **Deflactar es dividir por (1+i)^t**, no restar la inflación.
- **Retorno real = (1+r)/(1+i) − 1**, no `r − i`. Con 9,5% nominal y 3,83% de inflación el
  retorno real es 5,46%, no 5,67%.
- **El retorno total compone, no suma.** Con plusvalía `g` y yield `y` reinvertido, el retorno
  anual del modelo es `(1+g)(1+y) − 1`, no `g + y`: el motor capitaliza la plusvalía cada mes
  y reinvierte el dividendo, así que las dos fuentes se componen. Para el IPSA eso es 9,41% y
  no 9,21% — 0,25 puntos por año, un 7% más de capital a 30 años.
- **Aportes indexados** (checkbox): el monto escrito se interpreta como pesos de hoy y sube
  con la inflación **al mismo ritmo con que se deflacta el resto**, así que vale lo mismo en
  poder adquisitivo todos los meses. Con un escalón anual no lo hacía: se descolgaba hasta
  3,4% dentro de cada año, y los aportes extraordinarios —que sí se convierten exacto— decían
  «pesos de hoy» con otro significado. Sin el checkbox es un monto
  nominal fijo cuyo poder adquisitivo se erosiona. Mezclar una meta corregida por inflación
  con aportes nominales fijos compara pesos de años distintos.

> **Ojo con CFINRENTAS y la UF.** Los arriendos inmobiliarios en Chile suelen estar indexados
> a la UF, así que la plusvalía y el dividendo nominales del fondo ya incorporan inflación.
> Poner 3% de plusvalía nominal junto a 3,83% de inflación implica plusvalía real negativa.
> Si quieres razonar en términos reales, ingresa tasas reales y deja la inflación en 0.

## Escenarios precargados

Vienen dos, con los mismos tramos de aporte para que sean comparables. Cada uno se siembra
una sola vez: si lo borras, no vuelve.

## Escenario CFINRENTAS

La app viene con un escenario precargado del **Fondo de Inversión Independencia Rentas Inmobiliarias** (nemotécnico `CFINRENTAS` en la Bolsa de Santiago, ISIN CL0000006669).

Supuestos por defecto, **editables y no son una proyección oficial**:

| Parámetro | Valor | De dónde sale |
|---|---|---|
| Dividend yield | 6,5% | Yield actual ≈ 6,5%; promedio 2022-2026 ≈ 7,3% |
| Plusvalía de la cuota | 2,3% | Promedio 2022-2024, excluyendo el salto atípico de 2025 |
| Meses de pago | 3, 4, 6, 9, 12 | Cinco repartos al año: cuatro provisorios + el definitivo de abril |

Dividendos históricos por cuota (CLP): 2022 $113 · 2023 $124 · 2024 $120 · 2025 $124 · 2026 YTD $119.
Promedio ≈ **$120 al año** repartidos en 5 pagos: cuatro de ~$13-20 y el de abril de ~$43-74.

Ojo con el promedio de rentabilidad total: entre 2022 y 2025 da ~21% anual compuesto, pero está dominado por 2025 (+59,7%), año en que se cerró el descuento sobre valor libro al que se transaba el fondo. No es una tasa proyectable a 30 años.

## Archivos

| Archivo | Rol |
|---|---|
| `Makefile` | Atajos: `make init`, `stop`, `restart`, `db`, `help` |
| `server.py` | Servidor HTTP + rutas API (responde `Cache-Control: no-store`, si no el navegador se queda con el CSS/JS viejo); busca puerto libre si el pedido está ocupado |
| `engine.py` | Validación y motor de proyección |
| `db.py` | Esquema, migraciones y acceso a SQLite (`stonks.db`): escenarios, perfil, plan de aporte y aportes extraordinarios; siembra los escenarios de ejemplo |
| `inflation.py` | Serie del IPC chileno y ventanas de estimación |
| `afp.py` | Parámetros legales previsionales y proyección del saldo AFP |
| — | Los escenarios precargados (CFINRENTAS e IPSA) viven en `db.py` |
| `static/` | Frontend (HTML/CSS/JS vanilla) |
| `static/vendor/` | Chart.js y Grid.js servidos localmente |

## API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/inflation` | Serie del IPC y ventanas disponibles |
| GET/POST | `/api/profile` | Perfil, plan de aporte, aportes extraordinarios y proyección AFP |
| GET | `/api/afp/params` | Constantes legales previsionales |
| POST | `/api/afp/preview` | Proyecta el perfil sin guardarlo (lo que usa el modal reactivo) |
| POST | `/api/calculate` | Proyecta sin guardar; antes le inyecta del perfil la pensión, la fecha de inicio y la serie del saldo AFP |
| GET | `/api/scenarios` | Lista escenarios |
| POST | `/api/scenarios` | Crea escenario |
| GET/POST | `/api/scenarios/<id>` | Lee / actualiza escenario |
| DELETE | `/api/scenarios/<id>` | Elimina escenario |
