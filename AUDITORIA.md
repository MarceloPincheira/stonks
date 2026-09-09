# Auditoría de Stonks — cálculos, proyecciones y funcionalidades

**Fecha:** 9 de septiembre de 2026 · **Commit auditado:** `5798aec` · **Alcance:** `engine.py`, `afp.py`,
`inflation.py`, `server.py`, `db.py`, `static/app.js`, `README.md`.

Auditoría adversarial. Cada hallazgo se reprodujo **ejecutando los módulos reales** y pasó después por
tres lentes antes de entrar a este documento:

1. **¿Es cierto?** — reproducción numérica, no lectura de código.
2. **¿La corrección propuesta es mejor?** — un parche que empeora otra cosa no es un hallazgo.
3. **¿Cambia alguna decisión del usuario?** — lo que no mueve una decisión va a *Observaciones menores*.

Lo que no sobrevivió a las tres lentes está al final, con el motivo.

> **Estado: los 14 hallazgos están corregidos.** Cada corrección se verificó reejecutando la
> comprobación que había detectado el defecto (17/17 pasan), y las tres identidades que ya
> estaban bien —ganancia contable, ganancia real y pesos del traspaso entre fondos— siguen
> cuadrando. `make init` levanta el proyecto completo desde una instalación limpia.
>
> Al corregir el hallazgo 3 apareció un **desfase adicional de un mes** que la auditoría no
> había aislado: `serie_mensual` de la AFP empieza en el mes *siguiente* a hoy, pero se
> indexaba como si empezara hoy, así que la curva estaba corrida un mes **incluso cuando la
> inversión partía el mes actual**. Está corregido junto con el resto.

---

## Resumen

| # | Sev. | Hallazgo | Cómo quedó |
|---|---|---|---|
| 1 | 🔴 | La app no arranca en una instalación nueva, y al tercer intento arranca sin los escenarios de ejemplo | Las semillas pasan por `normalize_input`; la marca de sembrado va en la **misma transacción** que el insert; una semilla defectuosa ya no puede tumbar el arranque, sólo avisa |
| 2 | 🟠 | La tabla del impuesto único corta el tramo del 35% en 150 UTM en vez de 310 UTM | `(310.0, 0.350, 23.32)` y `(None, 0.400, 38.82)`; README corregido |
| 3 | 🟠 | La curva del saldo AFP se dibuja adelantada cuando la inversión empieza antes de hoy | La serie se construye por índice de destino, con el saldo de hoy en el origen y `None` en los meses sin dato |
| 4 | 🟠 | La proyección reinvierte los repartos **libres de impuesto**, sin declararlo | Campo *Impuesto sobre los repartos (%)*; se descuenta antes de reinvertir o cobrar; cobertura, retiro sostenible y capital necesario se miden en neto |
| 5 | 🟠 | Cifras deterministas con precisión falsa: «se agota a los 71,1 años» sin banda alguna | `engine.sensitivity()` devuelve el rango con ±1 pp de retorno e inflación; franja fija en la UI; edad de agotamiento en años enteros |
| 6 | 🟡 | La edad se congela en la base y nunca se recalcula desde la fecha de nacimiento | `get_profile()` la deriva de `nacimiento` en cada lectura |
| 7 | 🟡 | El techo de la bisección de `_max_spend` no acota: subestima el gasto máximo | El techo se duplica hasta acotar antes de bisecar |
| 8 | 🟡 | En el modelo simple las columnas de retiro sostenible muestran siempre $0 y 0% | La tasa sostenible del modelo simple es el retorno **real** (Fisher); las columnas de dividendo se ocultan en ese modo |
| 9 | 🟡 | Las trayectorias `basico`/`ampliado` descartan en silencio el fondo elegido | El selector se deshabilita con traspaso por edad y se explica; la proyección informa el fondo **realmente usado** |
| 10 | 🟡 | El seguro de cesantía usa el tope de la AFP (90 UF) en vez del suyo (135,2 UF) | `TOPE_CESANTIA_UF = 135.2`, topado aparte; README corregido |
| 11 | 🟡 | El retorno anual declarado (9,21%) no es el que entrega el motor (9,46%) | `annual_return = (1+g)(1+y)−1`, que es lo que la simulación entrega |
| 12 | 🟢 | El aporte indexado etiquetado «pesos de hoy» oscila 3,4% dentro de cada año | El factor de indexación **es** el deflactor del mes: ahora vale exactamente lo escrito, igual que los aportes extraordinarios |
| 13 | 🟢 | Un `sueldo_bruto` obsoleto resucita en cada reinicio | La migración corre una sola vez (marca en `app_meta`) y deja la columna en 0 |
| 14 | 🟢 | CFINRENTAS usa 3,0% de plusvalía donde el propio README justifica 2,3% | Plusvalía a 2,3%, coherente con el criterio aplicado al IPSA |

---

## 1. 🔴 La app no arranca en una instalación nueva

**Archivo:** `db.py:166` (`_values`) y `db.py:266` (`seed_examples`)

Las semillas `CFINRENTAS` e `IPSA` son diccionarios literales que nunca pasan por
`engine.normalize_input()`, así que les faltan las cuatro claves que `_values()` agregó después:
`include_pension`, `retire_to_age`, `spend_mode` y `work_until_age`. `db.init()` las siembra en cada
arranque, de modo que **cualquier base nueva revienta**:

```
$ python3 -c 'import db; db.init()'
  File "db.py", line 172, in _values
    1 if data["include_pension"] else 0, ...
KeyError: 'include_pension'
```

Esto rompe `make init`, `make db` y `python3 server.py` para quien clone el repositorio. El README
promete justo lo contrario: *«Si el puerto está ocupado avisa en vez de reventar con un traceback»*.

**Y hay un segundo daño, permanente.** `seed_examples()` inserta la marca en `app_meta` en una
transacción **distinta** de `save_scenario()`, así que la marca se confirma antes de que el insert
falle. Secuencia real, reproducida cuatro veces:

| Arranque | Resultado | `app_meta` | Escenarios |
|---|---|---|---|
| 1 | `KeyError` | `seeded_cfinrentas` | 0 |
| 2 | `KeyError` | `+ seeded_ipsa` | 0 |
| 3 | **OK** | ambas | **0** |
| 4 | OK | ambas | 0 |

Al tercer intento la app arranca —y los dos escenarios de ejemplo se perdieron para siempre, porque
la marca dice que ya se sembraron. La base que viene en el repositorio funciona sólo porque se creó
antes de que existieran esas columnas.

**Corrección.** Completar las cuatro claves en `CFINRENTAS` e `IPSA` (o mejor: pasarlas por
`engine.normalize_input()`, que es la única fuente que garantiza el contrato de `_values`), y mover
el `INSERT INTO app_meta` a la **misma transacción** que `save_scenario` para que la marca no
sobreviva a un insert fallido.

---

## 2. 🟠 La tabla del impuesto único corta el tramo del 35% en 150 UTM

**Archivo:** `afp.py:50-51` — y el `README.md:129-146` repite el mismo error.

La tabla mensual del art. 52 de la LIR que publica el SII lleva el tramo del 35% **hasta 310 UTM**, y
el tramo del 40% arranca ahí con una rebaja de **38,82 UTM**. Stonks usa 150 UTM y 30,82:

```python
(150.0, 0.350, 23.32),      # el SII dice 310,0
(None,  0.400, 30.82),      # el SII dice 38,82
```

Ambas tablas son internamente continuas —la del código empalma en 150 UTM, la oficial en 310—, así
que el error no se delata solo: hay que contrastarlo contra la fuente. Con UTM $71.721:

| Renta afecta | Base | Impuesto Stonks | Impuesto SII | Sobrecobro |
|---|---|---|---|---|
| 150 UTM | $10.758.150 | $2.092.819 | $2.092.819 | $0 |
| 200 UTM | $14.344.200 | $3.527.239 | $3.347.936 | **$179.302** |
| 250 UTM | $17.930.250 | $4.961.659 | $4.603.054 | **$358.605** |
| 310 UTM | $22.233.510 | $6.682.963 | $6.109.195 | **$573.768** |
| 600 UTM | $43.032.600 | $15.002.599 | $14.428.831 | **$573.768** |

La divergencia empieza en una base afecta de **$10.758.150 mensuales** y se estabiliza en un
sobrecobro **permanente de $573.768 al mes ($6.885.216 al año)** sobre las 310 UTM. Como el impuesto
entra en `liquido_aprox`, la app subestima la capacidad de ahorro de exactamente el segmento de renta
que más usaría una herramienta así.

**Corrección.** `(310.0, 0.350, 23.32)` y `(None, 0.400, 38.82)`, y actualizar la tabla del README.

---

## 3. 🟠 La curva del saldo AFP se dibuja adelantada

**Archivo:** `server.py:168-175` (`con_perfil`)

La serie de la AFP arranca **hoy**; la proyección de la inversión arranca en `inicio_mes`/`inicio_anio`
del perfil. El bucle que las alinea:

```python
for i in range(len(serie)):
    j = desfase + i
    if j < 0:
        continue                     # <-- no inserta placeholder: sólo no agrega
    alineada.append(serie[j] if j < len(serie) else 0.0)
```

Cuando `desfase < 0` —la inversión empezó **antes** de hoy— el `continue` no reserva el hueco: el
primer elemento que sí se agrega cae en el índice 0. Resultado: `alineada[k]` no es el saldo AFP del
mes de proyección `k+1`, sino el de `k+1+|desfase|`. **La curva de la AFP queda adelantada
`|desfase|` meses.**

Esto no es un caso raro: el perfil guarda una fecha de inicio fija, así que **el desfase crece un mes
por cada mes que pasa sin volver a guardar el perfil**. Con el default de la base (`inicio_mes = 1`,
`inicio_anio = 2026`) hoy vale −8.

Perfil de prueba (hombre, nace 1990-05-15, imponible $2.500.000, saldo AFP $45.000.000, fondo B):

| Mes de proyección | Saldo que muestra la app | Saldo correcto | Error |
|---|---|---|---|
| 24 | $56.102.049 | $52.277.753 | **+$3.824.296 (7,3%)** |
| 60 | $74.974.537 | $70.533.509 | +$4.441.029 (6,3%) |
| 120 | $113.431.295 | $107.733.540 | +$5.697.755 (5,3%) |
| 240 | $226.071.937 | $216.693.206 | +$9.378.732 (4,3%) |
| 344 | $381.111.887 | $366.666.614 | **+$14.445.273 (3,9%)** |

Además se pierden los 8 meses de cola de la serie (`len` pasa de 603 a 595).

**El efecto más visible está en la tabla de hitos.** `pension_start_month` se calcula contra el origen
de la *inversión* (mes 353), mientras la serie alineada quedó con origen *hoy* (jubilación en el mes
344). Los dos orígenes difieren en `|desfase|+1 = 9` meses, así que la fila «Jubilas» lee un punto que
**ya lleva 9 meses de desacumulación**:

```
Saldo AFP al jubilar (correcto)               = $381.111.887
Lo que muestra la fila «Jubilas»              = $372.014.653   (−$9.097.234)
```

O sea: la misma raíz sobrestima el patrimonio total en todo el gráfico y subestima el saldo justo en
el hito donde el usuario lo mira.

**Corrección.** Construir la serie por índice de destino y rellenar con `None` los meses anteriores a
hoy (Chart.js ya corta la línea con `spanGaps: false`):

```python
alineada = [serie[j] if 0 <= (j := desfase + k) < len(serie) else None
            for k in range(total_meses)]
```

y calcular `pension_start_month` y la serie AFP contra **el mismo origen**.

---

## 4. 🟠 La proyección reinvierte los repartos libres de impuesto

**Archivo:** `engine.py` — no hay una sola mención a tributación de la inversión en todo el motor.

El motor acumula el 100% de cada reparto y lo reinvierte íntegro. En Chile los repartos de un fondo de
inversión y los dividendos de acciones son renta afecta al Global Complementario; el
[art. 107 de la LIR](https://www.sii.cl/normativa_legislacion/circulares/2022/circu39.pdf) exime el
*mayor valor* en la enajenación —y desde el 1 de enero de 2027 vuelve a ser ingreso no renta—, pero
**no cubre las distribuciones periódicas**, que son justamente el motor del modelo de dividendos.

Sobre el escenario CFINRENTAS a 30 años (aporte $300.000 indexado, 6,5% de yield reinvertido):

| Tasa efectiva sobre el reparto | Patrimonio final | vs. lo que muestra la app |
|---|---|---|
| 0% (lo que hace Stonks) | $864.537.423 | — |
| 8% | $784.350.861 | **−9,3%** |
| 23% | $656.466.861 | **−24,1%** |
| 35% | $571.856.571 | **−33,9%** |

**Es la mayor distorsión cuantificada de toda la app**, y no está declarada en ninguna parte: ni el
README ni la UI advierten que la proyección es libre de impuestos. El README documenta con cuidado el
impuesto único del *sueldo*, lo que refuerza la impresión de que la parte tributaria está cubierta.

**Corrección.** El tratamiento exacto depende del instrumento y del crédito por impuesto de Primera
Categoría, así que modelarlo bien es un proyecto. El mínimo honesto es un campo «tasa efectiva sobre
los repartos» (por defecto 0) que multiplique el dividendo antes de reinvertirlo, y una nota explícita
en la UI y el README mientras no exista.

---

## 5. 🟠 Precisión falsa: cifras deterministas sin banda

**Alcance:** transversal (`engine.py`, `afp.py`, y toda la capa de presentación).

Toda la app proyecta con **un único escenario determinista** y publica los resultados con un decimal:
«se agota a los 71,1 años», «pensión estimada $2.078.157». No hay bandas, escenarios, análisis de
sensibilidad ni riesgo de secuencia de retornos —que es precisamente el riesgo dominante en una fase
de desacumulación, porque el orden de los retornos importa aunque la media no cambie.

La sensibilidad real, medida sobre un escenario que sí se agota (meta $2.500.000, aporte $150.000):

| Plusvalía | Se agota a los |
|---|---|
| 3,71% | **69,0 años** |
| 4,71% | 69,9 años |
| 5,71% (central) | 71,1 años |
| 6,71% | 73,0 años |
| 7,71% | **75,8 años** |

Casi **siete años de rango** por mover la plusvalía ±2 pp — menos de una desviación estándar para una
bolsa. Y no hace falta salirse de la propia app para mover la cifra: los cuatro presets de inflación
que ofrece el selector ya dan un rango de 2,5 años.

| Preset de inflación (los de la app) | Se agota a los |
|---|---|
| Meta del Banco Central, 3,0% | 72,6 años |
| Últimos 26 años, 3,83% ✓ recomendado | 71,1 años |
| Últimos 20 años, 4,12% | 70,7 años |
| Últimos 10 años, 4,58% | 70,1 años |

Para contexto: el IPC anual 2000-2025 tiene desviación estándar de **2,59 pp** (mínimo −1,4%, máximo
12,8%). Publicar un decimal sobre un modelo con esa dispersión de entrada comunica una precisión que
el modelo no tiene.

**Corrección.** Redondear las edades a años enteros; mostrar junto a cada cifra clave el rango que
producen ±1 pp de retorno y ±1 pp de inflación; y una nota fija de que es un escenario, no un
pronóstico. Un Monte Carlo sería mejor, pero el rango de sensibilidad ya se calcula con tres llamadas
más al motor.

**Crédito donde corresponde:** el README es notablemente honesto en sus supuestos —advierte sobre el
outlier de 2025 en CFINRENTAS, sobre la trampa UF/nominal en los fondos inmobiliarios, y dice que los
supuestos «no son una proyección oficial». El problema está en la UI, no en la documentación.

---

## 6. 🟡 La edad se congela en la base

**Archivos:** `db.py` (`get_profile`) y `afp.py:244`

`server.normalizar_perfil()` recalcula la edad desde `nacimiento`, pero **sólo en el POST**.
`db.get_profile()` devuelve la `edad` guardada, y tanto `GET /api/profile` como `con_perfil()` la usan
tal cual. Un perfil que no se vuelve a guardar envejece mal:

```
edad guardada hace 3 años : 33.32      (nacimiento guardado: 1990-05-15)
edad real hoy             : 36.32
  con edad rancia -> 380 meses cotizando, pensión $2.466.870
  con edad real   -> 344 meses cotizando, pensión $2.078.157
  sobrestima la pensión en $388.713/mes (+18,7%)
```

Se autocorrige cada vez que se guarda el perfil o se toca el plan de aporte (`schedulePlanSave`
POSTea el perfil completo), así que sólo afecta a la sesión que se limita a mirar. Pero el error es
silencioso, crece ~6% al año y va en la dirección peligrosa: **una pensión inflada reduce la meta que
la inversión debe cubrir.**

**Corrección.** Recalcular en la lectura, que es donde está el dato bueno:

```python
if profile and profile.get("nacimiento"):
    profile["edad"] = afp.edad_desde(profile["nacimiento"])
```

---

## 7. 🟡 El techo de la bisección de `_max_spend` no acota

**Archivo:** `engine.py:248`

```python
bajo, alto = 0.0, max(1.0, kw["portfolio"]) / 12 + kw["pension_today"] + 1
```

El techo asume implícitamente que gastar un doceavo del patrimonio al mes lo agota. Con horizontes de
retiro **cortos** eso es falso, la bisección converge al propio techo y el «gasto máximo» que se
publica es simplemente el techo:

| Patrimonio | Meses de retiro | `max_spend` reportado | Techo | Saldo gastando 2× el reportado |
|---|---|---|---|---|
| $120.000.000 | 6 | $10.000.001 | $10.000.001 | **$144.799 (aún sobra)** |
| $120.000.000 | 12 | $10.000.001 | $10.000.001 | $0 |
| $10.000.000 + pensión $1.500.000 | 6 | $2.333.334 | $2.333.334 | $0 |
| $120.000.000 (deflación −5%) | 12 | $10.000.001 | $10.000.001 | $0 |

Con 24 meses o más el techo ya acota y el resultado es correcto, así que el defecto vive sólo en el
régimen de edad objetivo ≈ edad de término de aportes. Ahí la app subestima el gasto máximo hasta
2× y puede emitir el veredicto falso *«Con $X al mes no alcanza»*
(`renderRetirement` compara `ret.max_spend_today < r.income_goal`).

**Corrección.** Duplicar `alto` hasta que deje de sobrar saldo, antes de bisecar:

```python
alto = max(1.0, kw["portfolio"]) / 12 + kw["pension_today"] + 1
while _retirement_path(alto, end_month=objetivo_mes, **kw)[2] > 1:
    alto *= 2
```

---

## 8. 🟡 En el modelo simple, el retiro sostenible es siempre $0

**Archivo:** `engine.py:424`

```python
sustainable_rate = data["dividend_yield"] - growth_gap if dividends_on else 0.0
```

En el modelo `simple` no hay `dividend_yield`, así que la tasa sostenible queda en 0 — pero la pestaña
**«poder adquisitivo»** (`purchasingColumns` en `static/app.js`) renderiza siempre las columnas
*Retiro sostenible* y *Cobertura sostenible*. Un escenario simple al 9,21% con 5,18% de retorno real:

```
sustainable_rate = None
último año: sustainable_monthly = 0.0   sustainable_coverage = 0.0
            coverage = 0.0              dividend_monthly = 0.0
patrimonio final real = $173.397.808
```

La tabla afirma, año tras año, que de $173 millones reales que rinden 5,18% real no se puede retirar
nada. Las columnas *Dividendo mensual*, *Cobertura* y *Dividendos del año* muestran $0 por la misma
razón.

**Corrección.** Para el modelo simple la tasa sostenible es el retorno **real** —Fisher, no resta—:
`((1 + annual_return/100) / (1 + inflación/100) − 1) × 100`. Alternativa mínima: ocultar esas cinco
columnas cuando `model == "simple"`, igual que ya se hace con las columnas de reinversión.

---

## 9. 🟡 Las trayectorias descartan el fondo elegido

**Archivo:** `afp.py:213-226`

Con `trayectoria` distinta de `fijo`, `rentabilidad_a_edad()` y `fondo_a_edad()` ignoran por completo
`fondo_elegido` y arrancan desde el fondo fijo de `HITOS`:

```
usuario elige fondo A + trayectoria 'basico' -> proyecta fondo B, 5.11%
usuario elige fondo B + trayectoria 'basico' -> proyecta fondo B, 5.11%
usuario elige fondo C + trayectoria 'basico' -> proyecta fondo B, 5.11%
usuario elige fondo D + trayectoria 'basico' -> proyecta fondo B, 5.11%
usuario elige fondo E + trayectoria 'basico' -> proyecta fondo B, 5.11%
```

El modal del perfil deja el selector de fondo activo y visible en los tres modos, así que el usuario
elige algo que no tiene efecto y no se le avisa. Que el esquema de traspasos parta de un fondo
canónico es defendible; que el selector siga habilitado y mudo, no.

**Corrección.** Deshabilitar el selector de fondo cuando la trayectoria no es `fijo` y explicar por qué,
o hacer que la mezcla parta del fondo elegido en vez del primer hito.

---

## 10. 🟡 El seguro de cesantía usa el tope de la AFP

**Archivo:** `afp.py:266`

```python
cesantia = imponible * CESANTIA_INDEFINIDO / 100 if perfil["contrato_indefinido"] else 0.0
```

`imponible` viene topado en `TOPE_IMPONIBLE_UF = 90.0`, pero el seguro de cesantía tiene **tope propio
y mayor**: [135,2 UF para 2026](https://www.afc.cl/afc-informa/noticias/empleador-conozca-el-nuevo-tope-imponible-para-2026/),
según la [Superintendencia de Pensiones](https://www.spensiones.cl/portal/institucional/594/w3-article-16885.html).
El tope de 90 UF para AFP y salud sí está correcto.

| Sueldo imponible | Cesantía en Stonks | Cesantía real | Diferencia |
|---|---|---|---|
| $3.000.000 | $18.000 | $18.000 | $0 |
| $4.000.000 | $22.078 | $24.000 | −$1.922 |
| $5.527.560 y más | $22.078 | $33.165 | **−$11.088** |

Sobrestima el líquido hasta $11.088 al mes y, como la cesantía rebaja la base tributable, arrastra un
pequeño error de signo contrario en el impuesto. El README también documenta un único tope de 90 UF
para todo.

**Corrección.** Constante propia `TOPE_CESANTIA_UF = 135.2` y un `min()` separado para ese descuento.

---

## 11. 🟡 El retorno anual declarado no es el que entrega el motor

**Archivo:** `engine.py:69`

```python
annual_return = appreciation + dividend_yield        # suma simple
```

Pero la simulación capitaliza la plusvalía todos los meses y reinvierte el dividendo cuando toca, o
sea que compone las dos fuentes en vez de sumarlas. Con los supuestos del escenario IPSA:

```
annual_return declarado          = 9.2100 %
CAGR efectivo de la simulación   = 9.4587 %     (medido a 1 y a 10 años)
(1+g)(1+y)−1                     = 9.4098 %
brecha: 0,249 pp por año -> factor 1,0706× a 30 años
```

El comportamiento del motor es el financieramente correcto (reinvertir dividendos compone); **el
número mal puesto es la etiqueta**. Y esa etiqueta se propaga: se guarda en la columna
`annual_return`, se muestra en la lista de escenarios («9,21% anual») y alimenta `real_return_pct`
(5,182%), que por lo tanto también queda bajo. Sobre el resultado de $588.920.154 del escenario IPSA
la brecha vale unos $41 millones.

**Corrección.** Declarar `annual_return = ((1 + g/100) * (1 + y/100) − 1) * 100`, o calcular
`real_return_pct` desde el retorno efectivo del motor en vez de desde la suma.

---

## 12. 🟢 El aporte «en pesos de hoy» oscila 3,4% dentro de cada año

**Archivo:** `engine.py:311`

`contribution_factor` sube en **escalón anual**, `deflator` baja de forma **continua**, así que el
aporte etiquetado «pesos de hoy» nunca vale lo escrito:

| Mes | Aporte nominal | En pesos de hoy | Escrito |
|---|---|---|---|
| 1 | $300.000 | $299.062 | $300.000 |
| 12 | $300.000 | $288.934 | $300.000 |
| 13 | $311.490 | $299.062 | $300.000 |
| 360 | $892.245 | $288.934 | $300.000 |

Diente de sierra de 3,4% que se repite cada año, con inflación 3,83%; con la del 2022 (12,8%) sería
del 11%. La UI promete otra cosa: `syncIndexUI()` pone la etiqueta *«pesos de hoy»* y el texto *«el
monto sube con la inflación cada año, como un reajuste de sueldo»*.

Es **inconsistente con los aportes extraordinarios**, que sí se convierten exactamente
(`nominal = amount * deflator(m)`) y recuperan el valor escrito al deflactar.

**Corrección.** Usar `(1 + i) ** ((m - 1) / 12)` si se quiere fidelidad a la etiqueta, o dejar el
escalón anual —que imita mejor un reajuste real— y cambiar la etiqueta a «pesos de hoy, reajustado
una vez al año».

---

## 13. 🟢 Un `sueldo_bruto` obsoleto resucita en cada reinicio

**Archivo:** `db.py:127`

La migración `UPDATE profile SET sueldo_imponible = sueldo_bruto WHERE sueldo_imponible = 0 AND
sueldo_bruto > 0` corre en **cada** `db.init()`, y `save_profile()` nunca escribe `sueldo_bruto`, así
que la columna obsoleta queda congelada para siempre y vuelve a pisar:

```
usuario pone imponible en 0 -> guardado: 0
tras reiniciar el servidor  -> 9,999,999   <- resucitó sueldo_bruto
```

**Corrección.** Correr la migración una sola vez (marca en `app_meta`, como las semillas) y poner
`sueldo_bruto` a 0 al migrarlo.

---

## 14. 🟢 CFINRENTAS usa una plusvalía mayor que la que su propia nota justifica

**Archivos:** `db.py` (`CFINRENTAS`) y `README.md`

El README documenta: *«Plusvalía de la cuota | 3,0% | Promedio 2022-2024 ≈ 2,3%, excluyendo el salto
atípico de 2025»*. El valor usado (3,0%) es **superior** al promedio que se cita como fundamento
(2,3%), sin explicar el redondeo al alza.

Vale la pena contrastarlo con el criterio del escenario IPSA, donde excluir el outlier de 2025 (+56%)
baja la plusvalía de 9,52% a 5,71% —una corrección conservadora y bien argumentada—. Aplicar el mismo
criterio aquí daría 2,3%, no 3,0%. La asimetría entre ambos casos es lo que conviene resolver.

**Corrección.** Usar 2,3% o documentar por qué el ajuste al alza está justificado.

---

## Lo que verifiqué y está correcto

Para que el reporte sea útil hay que decir también qué resistió el escrutinio:

- **Identidades contables del motor.** `ganancia = dividendos acumulados + plusvalía` se cumple al
  centavo con y sin reinversión (diferencia $0,00), y `total_gain_real = final_real_balance −
  total_invested_real` cuadra con error de redondeo ($0,01).
- **Conversión de tasas.** `(1+g)^(1/12)−1` es la conversión geométrica correcta; la deflactación
  `(1+i)^(m/12)` se aplica con el mismo exponente en el backend y en las cuatro rutas del frontend.
- **Retorno real por Fisher.** `((1+nominal)/(1+inflación)−1)` es la fórmula correcta, no la resta.
- **Traspaso gradual entre fondos.** `_mezcla_a_edad` reparte bien: los pesos suman exactamente 1 en
  una malla de edades de 0 a 100 en pasos de 0,25 años, el avance 20%/año completa en cuatro años, y
  mover saldo a un fondo que ya tiene no duplica ni pierde.
- **La anualidad de la pensión.** `factor = (1−(1+i)^−n)/i` es la anualidad vencida correcta, y la
  desacumulación mes a mes (`saldo·(1+i) − pensión`) la agota exactamente en `n` meses. La identidad
  `cnu = saldo/pensión/12` que muestra la UI es consistente.
- **El argumento de Jensen del docstring de `pension_mensual`.** Es correcto: el valor presente es
  cóncavo en la duración, así que la renta cierta a la expectativa de vida sobrestima el CNU y deja la
  pensión del lado conservador. (Con una salvedad, abajo.)
- **Validación de tramos solapados.** El barrido tras ordenar por `start_month` detecta cualquier
  solapamiento; no encontré contraejemplo.
- **Media geométrica del IPC.** Correcta, y el default de la base (3,83%) coincide exactamente con la
  ventana recomendada de 26 años (3,8260%).
- **Tope imponible de AFP y salud.** 90 UF para 2026 es correcto.
- **Comisión de la AFP.** Bien tratada: se descuenta del sueldo y **no** entra a la cuenta individual.

---

## Observaciones menores (no sobrevivieron las tres lentes)

- **Ganancia de capital sin impuesto.** Mi hipótesis inicial era que faltaba tributar también el mayor
  valor. Verificado contra la Circular N° 39 de 2022 del SII: el art. 107 de la LIR grava con impuesto
  único de 10% hasta el 31-dic-2026 y **vuelve a ser ingreso no renta desde el 1-ene-2027**, así que
  para un horizonte de 30 años la omisión es casi inocua. El hallazgo real quedó acotado a los
  repartos (#4). *Refutado por la lente 1.*
- **Base del dividendo en la fase de retiro.** `_retirement_path` calcula el dividendo sobre el saldo
  **antes** del crecimiento del mes, mientras la acumulación lo calcula **después**. Es una
  inconsistencia real, pero vale 0,46% por reparto y no mueve ninguna conclusión. *Refutado por la
  lente 3.*
- **Grupo familiar en el CNU.** El CNU real pondera beneficiarios de sobrevivencia, lo que lo **sube**
  y por tanto **baja** la pensión — es decir, empuja en dirección contraria al sesgo conservador de la
  aproximación por renta cierta. No lo cuantifiqué lo suficiente como para afirmar cuál de los dos
  domina, así que lo dejo como incertidumbre declarada, no como hallazgo.
- **Déficit no acumulado.** En `_retirement_path` el `shortfall` se reporta por mes pero no se arrastra:
  el mes siguiente parte como si nada hubiese faltado. Dado que `agotado` ya marca el primer mes de
  quiebre y la UI corta ahí la lectura, no cambia ninguna decisión.
- **Moneda sin conversión.** Cambiar la moneda sólo cambia el símbolo y los decimales, sin convertir
  montos. Está documentado en el código como decisión deliberada, aunque un cartel en la UI ayudaría.

---

## Cobertura: lo que no alcancé a auditar

En honor a no dar por barrido lo que no se barrió:

- **`static/app.js` a fondo.** Revisé los cálculos duplicados en el cliente y las rutas de render
  citadas, pero no hice una pasada completa sobre las 1.645 líneas: quedan sin auditar el parseo de
  montos en formato chileno (`parseAmount` / `reformatAmountInput`), las carreras de `calcSeq` /
  `previewSeq`, y la ruta de `loadScenario` que no pisa los tramos cuando el perfil ya tiene plan
  propio (sospecho que carga un escenario guardado y lo proyecta con otros aportes, sin avisar).
- **Verificación de la serie IPC dato por dato** contra el INE. Comprobé la aritmética de las medias y
  las ventanas, no cada uno de los 26 valores.
- **`RENTABILIDAD_REAL` y `COMISIONES`** contra las publicaciones vigentes de la Superintendencia de
  Pensiones. No están fechadas en el código, lo que conviene arreglar aunque los valores sean correctos.
- **`APORTE_EMPLEADOR_CUENTA = 0.1`** bajo la Ley 21.735: el código lo fija constante durante toda la
  proyección, sin modelar la gradualidad hasta 2033. Merece verificación específica y probablemente
  sea un hallazgo por derecho propio.
- **Aportes extraordinarios y el recorte por dejar de trabajar.** Los lump sums se suman *después* del
  recorte de `work_until_month`, así que sobreviven a dejar de trabajar. Puede ser deliberado (una
  herencia no depende del sueldo), pero no está documentado.

---

*Auditoría de sólo lectura: no se modificó ni se versionó ningún archivo del proyecto.*
