# Stonks — especificación técnica del modelo de proyección

**Versión del documento:** 1.0 · **Fecha:** 9 de septiembre de 2026 · **Código descrito:** `engine.py`,
`afp.py`, `inflation.py`, `server.py` en el estado posterior a las correcciones de `AUDITORIA.md`.

## Cómo leer este documento

Está escrito para que alguien con formación en finanzas cuantitativas, actuariado o tributación
chilena pueda **verificar o refutar** cada cálculo sin leer el código. Cada módulo declara:

1. la **recursión o fórmula exacta** tal como está implementada (no una versión idealizada),
2. el **supuesto** que la sostiene,
3. el **sesgo conocido** que introduce, cuantificado cuando se pudo medir.

La §11 concentra las **decisiones discutibles**: es la lista corta de cosas que un revisor
debería mirar primero. Cuando el modelo se aparta de la práctica correcta y lo sabemos, está
dicho ahí, no escondido en una nota al pie.

---

## 1. Alcance del modelo

Stonks proyecta, en paralelo y bajo un mismo conjunto de supuestos, dos patrimonios de una
persona natural en Chile:

- **Inversión voluntaria**: aportes mensuales por tramos, aportes extraordinarios, capitalización
  compuesta, repartos periódicos opcionales, y una fase de desacumulación.
- **Ahorro previsional obligatorio (AFP)**: cotizaciones sobre renta imponible topada,
  rentabilidad por fondo, y conversión del saldo en pensión.

**No es** una herramienta de optimización de cartera, no modela riesgo de mercado ni de secuencia,
y no es asesoría tributaria. Es un modelo **determinista de escenario único**, con una banda de
sensibilidad de primer orden (§9).

---

## 2. Notación y convenciones

| Símbolo | Significado | Unidad |
|---|---|---|
| `m` | mes de proyección, `m = 1..M` | entero |
| `M` | horizonte, `M = 12·Z` con `Z` años | meses |
| `i` | inflación anual esperada | decimal |
| `g` | plusvalía anual (modelo dividendos) o retorno total anual (modelo simple) | decimal |
| `y` | dividend yield anual | decimal |
| `τ` | tasa efectiva de impuesto sobre los repartos | decimal |
| `P` | conjunto de meses calendario de pago, `P ⊆ {1..12}`, `n = |P|` | — |
| `r` | tasa mensual equivalente a `g` | decimal |
| `D(m)` | deflactor del mes `m` | — |
| `V_m` | valor de mercado del fondo al cierre del mes `m` | \$ nominales |
| `C_m` | efectivo cobrado acumulado (repartos no reinvertidos) | \$ nominales |
| `c_m` | aporte del mes `m` | \$ nominales |

**Convención de índices.** El mes `m = 1` es el primer mes de la proyección. El mes calendario
asociado es `inicio_mes/inicio_anio + (m−1)` meses. La correspondencia con la serie de la AFP
—que tiene otro origen— se trata en §8.

**Convención de unidades.** Conviven tres sistemas y confundirlos es la fuente de error más
probable en un modelo de este tipo:

1. **Pesos nominales**: pesos del año en que ocurre el flujo. Es la unidad interna del motor de
   inversión.
2. **Pesos de hoy (reales)**: nominales divididos por `D(m)`. Es la unidad de la meta de ingreso,
   de los aportes indexados, de los aportes extraordinarios y de todo el módulo AFP.
3. **Tasas reales**: las rentabilidades de los fondos de pensiones y la tasa técnica se publican
   ya descontada la inflación, de modo que proyectar el saldo AFP en pesos de hoy no requiere
   sumarles inflación.

La regla que ordena todo: **el módulo AFP opera íntegramente en pesos de hoy con tasas reales; el
motor de inversión opera en nominales y deflacta al presentar.** El puente está en §8.

---

## 3. Discretización temporal y convención de flujos

El modelo es de **tiempo discreto mensual**, sin sub-períodos. La convención de flujos es
**anualidad anticipada** (*annuity-due*): el aporte entra al inicio del mes y devenga el retorno
completo de ese mes.

```
V_m = (V_{m−1} + c_m) · (1 + r)
```

Con `V_0 = 0`. El módulo AFP usa la **misma** convención (§7.4), lo que hace que ambas curvas sean
comparables punto a punto:

```
S_m = (S_{m−1} + a) · (1 + ρ_m)
```

> **Supuesto.** Un aporte devenga un mes completo de retorno el mes en que se hace. Frente a una
> convención vencida (*annuity-immediate*) esto sobrestima el resultado en aproximadamente un mes
> de retorno sobre el total aportado. Con `g = 5,71%` son ~0,46% sobre los aportes; es una
> convención, no un error, pero conviene tenerla presente al comparar con otra calculadora.

### 3.1 Conversión de tasas

Toda conversión anual → mensual es **geométrica**:

```
r = (1 + g)^(1/12) − 1
```

No `g/12`. Para `g = 5,71%`: `r = 0,463737%` mensual, contra `0,475833%` de la conversión lineal,
que a 30 años acumularía un error de ~4,4%.

---

## 4. Aportes

### 4.1 Tramos

Los aportes se definen por tramos `[inicio, fin, monto]` disjuntos. `monthly_amount_table`
proyecta los tramos sobre un vector de largo `M`:

```
a_m = monto del tramo que contiene a m, o 0
```

Los tramos se recortan al horizonte (`fin ← min(fin, M)`). La validación exige `inicio ≥ 1`,
`fin ≥ inicio`, `monto ≥ 0`, y **no solapamiento**: tras ordenar por `inicio`, se verifica
`inicio_{k+1} > fin_k` para todo `k`. Esa condición sobre pares adyacentes es suficiente —si los
inicios están ordenados y ningún par adyacente se solapa, ningún par se solapa, porque
`inicio_j ≥ inicio_{k+1} > fin_k` para todo `j > k`.

### 4.2 Indexación

Con `index_contributions = true`, el monto escrito se interpreta como **pesos de hoy** y se lleva
a nominales con el mismo factor con que se deflacta:

```
φ(m) = (1 + i)^(m/12)          (indexado)
φ(m) = 1                        (nominal fijo)
```

Como `φ(m) ≡ D(m)`, el valor real de cada aporte es **exactamente** el monto escrito:
`a_m·φ(m)/D(m) = a_m`. Verificado: con 360 aportes de \$300.000 y un extraordinario de
\$10.000.000, `total_invested_real = $118.000.000` exacto.

### 4.3 Aportes extraordinarios

Van amarrados a un mes calendario `(año, mes)` y el monto se escribe en pesos de hoy. El mes de
proyección es:

```
m* = (año − inicio_anio)·12 + (mes − inicio_mes) + 1
L_{m*} = monto · D(m*)
```

Los que caen fuera de `[1, M]` se informan como fuera de rango y no se suman.

### 4.4 Corte por término de la vida laboral

Los aportes salen del sueldo, de modo que se anulan desde el mes `h = work_until_month`:

```
a_m ← 0   para todo m > h
```

Se informa cuántos meses de tramo quedaron recortados. **Los aportes extraordinarios se suman
después del recorte**, es decir sobreviven al término del trabajo: el supuesto es que una herencia
o la venta de un activo no dependen del sueldo. Es una decisión, no un descuido, pero no está
expuesta en la interfaz.

### 4.5 Aporte total del mes

```
c_m = a_m · φ(m) + L_m
```

---

## 5. Motor de acumulación

### 5.1 Recursión

Para `m = 1..M`:

```
c_m       = a_m·φ(m) + L_m
invested += c_m
invested_real += c_m / D(m)
growth    = (V_{m−1} + c_m) · r
V_m       = V_{m−1} + c_m + growth
```

En el **modelo simple** eso es todo: `g` es el retorno total y no hay repartos.

### 5.2 Repartos (modelo dividendos)

El reparto se **devenga todos los meses** sobre el valor del fondo y se **paga acumulado** en
los meses de `P`:

```
devengo  ← devengo + V_m · (y/12)             todos los meses

si ((m−1) mod 12) + 1 ∈ P:
    d_m      = devengo;   devengo ← 0        (bruto)
    t_m      = d_m · τ
    d_m^net  = d_m − t_m
    si reinvierte:   V_m ← V_m + d_m^net
    si no:           C_m ← C_{m−1} + d_m^net
```

> **Por qué devengo y no fracción del valor en la fecha.** Repartir `y/n · V_m` en cada fecha de
> pago hace que el dinero que entra ese mes cobre un trimestre completo de dividendo por un mes de
> tenencia; y si se lo excluye, llegar un mes tarde cuesta el reparto entero. Cualquier regla
> atada a la fecha crea una discontinuidad, porque `y/n` representa una acumulación de `12/n`
> meses. El devengo la elimina: lo repartido en el año es siempre ≈ valor medio × `y`,
> independiente del calendario de pagos.

> **Supuesto central.** El reparto **no se descuenta** del valor del fondo. La justificación es
> que la plusvalía histórica de un fondo de reparto (o el retorno de precio de un índice) ya viene
> **neta** de las distribuciones: descontar el dividendo del capital lo contaría dos veces. Es la
> convención correcta si `g` se estimó sobre una serie de precios ex-dividendo. **Si el usuario
> ingresa en `g` una rentabilidad total (que ya incluya los repartos), el modelo la duplica.** El
> README advierte de esto para CFINRENTAS; es la trampa de uso más fácil de pisar.

### 5.3 Retorno anual efectivamente entregado

Con reinversión, en un año el fondo se multiplica por `(1+g)·(1 + p(1−τ))^n`. Con `τ = 0`:

```
R_efectivo = (1 + g)·(1 + y/n)^n − 1
```

mientras que el campo `annual_return` que se guarda y se muestra declara:

```
R_declarado = (1 + g)·(1 + y) − 1
```

**Estas dos cifras no coinciden.** Para `g = 5,71%`, `y = 3,5%`, `n = 4`:

| | valor |
|---|---|
| `R_declarado` | 9,409850% |
| `R_efectivo` medido con `n = 4` | 9,434140% |
| `R_efectivo` medido con `n = 12` | 9,469783% |
| residuo con `n = 4` | **+0,024290 pp/año** |

El residuo es la capitalización intra-anual de lo repartido: reinvertir cuatro veces al año compone
más que hacerlo una. Crece con `n` y con `y`. A 30 años acumula **+0,67%** de patrimonio final.

> **Sesgo conocido, no corregido.** La etiqueta subestima lo que el motor entrega. Una corrección
> exacta haría que `annual_return` dependiera de `payout_months` y de `reinvest`, lo que es
> discutible porque ese campo pretende describir el *instrumento*, no la convención de simulación.
> Queda declarado para que el revisor decida. (Una versión anterior declaraba `g + y = 9,21%`, con
> un residuo cinco veces mayor.)

### 5.4 Neutralidad frente al calendario de pagos

La propiedad que el devengo garantiza, y que sirve de prueba: **invertir más tarde nunca puede
rendir más, y el costo de atrasarse un mes no depende de si ese mes es de pago.**

Patrimonio final a 20 años según el mes en que cae un aporte extraordinario de \$50.000.000
(`g = 5,71%`, `y = 3,5%`, `P = {4,5,9,12}`):

| ubicación del aporte | costo de atrasarlo un mes |
|---|---|
| meses sin pago | \$1,27 M – \$1,32 M |
| meses de pago (4, 5, 9, 12) | \$1,32 M – \$1,32 M |
| **dispersión máx/mín** | **1,04×** |

Con la regla anterior esa dispersión era de **~7×**, y el signo dependía de la variante: repartir
sobre el valor con el aporte dentro **regalaba** \$13,4 M (+1,33%) por poner el aporte en un mes de
pago; excluir el aporte lo **penalizaba** en 0,76% por llegar un mes tarde. El devengo deja el
resultado esencialmente insensible a la fecha, que es lo correcto.

### 5.5 Identidades contables

El motor mantiene invariantes verificables, que sirven de prueba de regresión:

```
(I1)  capital_gain_m = V_m − (invested_m + reinvested_m)
(I2)  total_gain     = total_dividends_net + total_capital_gain
(I3)  total_gain_real = final_real_balance − total_invested_real
```

Verificadas numéricamente con y sin reinversión y con `τ ∈ {0, 23%}`: (I2) cierra a \$0,00 y (I3) a
\$0,01 de redondeo. **(I2) usa el reparto neto**: el impuesto no es ganancia del inversionista.

Nótese que `reinvested` **no** es dinero del bolsillo, de modo que la ganancia se mide siempre
contra `invested`, nunca contra `cost_basis = invested + reinvested`.

### 5.6 Agregación anual

Sólo se agregan meses con `m mod 12 = 0`. El reparto del año se obtiene por diferencia de
acumulados, no re-sumando:

```
dividends_year_k     = dividends_total_{12k} − dividends_total_{12(k−1)}
dividends_year_net_k = dividends_net_total_{12k} − dividends_net_total_{12(k−1)}
```

**Toda métrica de cobertura usa la versión neta**, que es de lo que se vive.

---

## 6. Fase de desacumulación

### 6.1 Punto de partida

La fase arranca en el último mes con aporte (`last_contribution`, extraordinarios incluidos) y
termina en el mes correspondiente a la edad objetivo:

```
fin    = round((retire_to_age − start_age)·12)
inicio = min(last_contribution, fin)
V      = V_inicio + C_inicio
```

El efectivo no reinvertido `C` se incorpora al saldo y **desde ahí devenga `r`**, a diferencia de
la fase de acumulación donde no rentaba. Es una inconsistencia menor de tratamiento del efectivo.

### 6.2 Recursión mensual

Para `m = inicio+1 .. fin`:

```
necesita = spend_today · D(m)
pension  = pension_today · D(m)   si pension_start ≠ null y m ≥ pension_start, si no 0
devengo  += V·(1+r) · (y/12)·(1−τ)                                   ← se devenga todos los meses
dividendo = devengo (y se pone en 0)  si ((m−1) mod 12)+1 ∈ P, si no 0
ingreso  = pension + dividendo
del_fondo = max(0, necesita − ingreso)
sobra     = max(0, ingreso − necesita)
vendido   = min(del_fondo, V)
V ← max(0, V − vendido + sobra) · (1 + r)
```

Orden de prelación del gasto: **primero la pensión, después el reparto, y sólo lo que falte se
vende del fondo.** El excedente vuelve al fondo y capitaliza.

El devengo pendiente al momento de dejar de aportar **se traspasa** a la fase de retiro
(`accrual0`), de modo que no se pierde una fracción de reparto en la transición. Ambas fases usan
ahora la misma regla de devengo sobre el valor capitalizado del mes.

### 6.3 Detección de agotamiento

```
si del_fondo > V + 1e−6 y agotado = null:  agotado ← m
```

Se registra el **primer** mes en que el fondo no alcanza a cubrir lo que le toca. Además, llegar a
la edad objetivo con menos de un mes de gasto también cuenta como agotamiento:

```
si agotado = null y V_fin < spend_today · D(fin):  agotado ← fin
```

Esto último evita el mensaje contradictorio «no se agota» junto a «quedarían \$0».

> **Limitación.** El déficit (`del_fondo − vendido`) se **informa por mes pero no se arrastra**: el
> mes siguiente parte como si nada hubiera faltado. Como la lectura de la interfaz se corta en
> `agotado`, no distorsiona la conclusión, pero las filas posteriores a `agotado` no representan un
> plan financiable.

### 6.4 Gasto máximo sostenible hasta la edad objetivo

`_max_spend` resuelve por bisección el mayor `s` tal que el saldo final sea ≈ 0. El saldo final es
monótono decreciente en `s` (y satura en 0 por el `max(0, ·)`), así que la bisección es válida.

**Acotamiento previo.** El techo inicial `V/12 + pensión + 1` sólo acota si quedan doce meses o
más; con horizontes cortos la bisección convergía al propio techo y devolvía un máximo falso. Se
duplica hasta acotar:

```
alto ← V/12 + pension_today + 1
mientras saldo_final(alto) > 1 y menos de 64 iteraciones:   bajo ← alto;  alto ← 2·alto
después: 80 iteraciones de bisección sobre [bajo, alto]
```

80 iteraciones dan precisión muy por debajo del peso para cualquier magnitud representable. El
criterio de parada es `saldo_final > 1` peso, umbral absoluto: para saldos de miles de millones es
efectivamente cero.

---

## 7. Módulo previsional (AFP)

Todo este módulo opera en **pesos de hoy** con **tasas reales**.

### 7.1 Base imponible y topes

```
imponible          = min(sueldo_imponible, 90 UF)
imponible_cesantía = min(sueldo_imponible, 135,2 UF)
```

Los dos topes son **distintos** y se aplican por separado: AFP y salud cotizan hasta 90 UF; el
seguro de cesantía tiene tope propio y mayor (AFC, 2026). Las asignaciones no imponibles no cotizan
y entran enteras al líquido.

```
cotización        = imponible · 10%
comisión          = imponible · comisión_AFP%
aporte_empleador  = imponible · aporte_empleador%
salud_legal       = imponible · 7%
cesantía          = imponible_cesantía · 0,6%     (sólo contrato indefinido)
```

> **Supuesto.** El aporte del empleador que llega a la cuenta individual se toma **constante** en
> todo el horizonte (0,1% por defecto). La Ley 21.735 lo incrementa gradualmente hasta 2033, con
> sólo una fracción destinada a capitalización individual. **El modelo no representa esa
> gradualidad y por lo tanto subestima el saldo final.** Es el supuesto previsional más débil del
> módulo.

### 7.2 Impuesto único de segunda categoría

Base afecta, según art. 42 N°1 de la LIR:

```
base = sueldo_imponible − cotización − comisión − salud_legal − cesantía
```

Nótese el cruce deliberado: las cotizaciones se calculan sobre la base **topada**, pero se restan
del sueldo imponible **sin topar**. Es el tratamiento del SII: por sobre el tope las cotizaciones
dejan de crecer pero la renta sigue siendo afecta. El adicional de Isapre **no** rebaja la base.

Tabla mensual del art. 52 en UTM, aplicada en forma directa:

```
impuesto = max(0, base · factor − rebaja · UTM)
```

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

Las rebajas empalman la escala: en cada corte `t`, `factor_k·t − rebaja_k = factor_{k+1}·t −
rebaja_{k+1}`. En 310 UTM: `0,35·310 − 23,32 = 0,40·310 − 38,82 = 85,18 UTM`.

> **Advertencia de verificación.** La continuidad se cumple para *cualquier* par (tope, rebaja)
> construido consistentemente, de modo que **una tabla con el corte equivocado sigue siendo
> continua**. Verificar la continuidad no valida la tabla; hay que contrastar los topes contra el
> SII. Comprobación: 200 UTM → \$3.347.936 y 600 UTM → \$14.428.831 con UTM \$71.721.

> **Punto para el revisor.** Se asume que la **comisión de la AFP** rebaja la base afecta, junto
> con la cotización obligatoria. Es la interpretación habitual, pero conviene que un tributarista
> la confirme: si no fuera rebajable, el modelo subestima el impuesto.

Como la escala está en UTM y la UTM se reajusta con el IPC, la tabla **no envejece** al proyectar
en pesos de hoy: mantener el impuesto constante en términos reales es correcto bajo el supuesto de
que la escala se sigue reajustando.

### 7.3 Rentabilidad por fondo y trayectorias

`RENTABILIDAD_REAL` contiene la rentabilidad real anualizada del sistema por fondo desde el inicio
de los multifondos (sep-2002). Tres modos:

- **`fijo`**: el afiliado permanece en su fondo, salvo la salida obligatoria del Fondo A a los 56
  (hombres) / 51 (mujeres), en que pasa al fondo de destino que él elija.
- **`basico` / `ampliado`**: esquema de traspasos por edad. La mezcla a la edad `e` se obtiene
  recorriendo los hitos y aplicando un avance gradual de 20% anual hasta completar en cuatro años:

```
avance = min(1, 0,20 · (1 + ⌊e − e_hito⌋))
pesos ← pesos·(1 − avance);   pesos[destino] += avance · Σ pesos_previos
ρ(e) = Σ_f  RENTABILIDAD_REAL[f] · pesos[f]
```

  La construcción es correcta cuando el destino ya tiene saldo: queda
  `p_destino·(1−avance) + p_destino·avance + otros·avance`. Verificado que los pesos suman 1 en una
  malla de edades de 0 a 100 en pasos de 0,25.

> **Los esquemas por edad ignoran el fondo elegido**, porque asignan por edad desde un fondo
> canónico. Es correcto en el dominio, pero la proyección informa ahora el fondo **realmente
> usado** (`fondo_inicial`, `fondo_ignorado`) para que la interfaz no calle la diferencia.

> **Supuesto fuerte.** Se usa una rentabilidad histórica de ~24 años como **estimador puntual
> forward** a 30–40 años, sin dispersión. Además, la Ley 21.735 reemplaza los multifondos por
> fondos generacionales desde abril de 2027; la proyección sigue usando la trayectoria de los
> multifondos porque los nuevos no tienen rentabilidad observada.

### 7.4 Acumulación del saldo

```
meses = round((edad_pensión − edad)·12)
para m = 1..meses:
    e   = edad + (m−1)/12
    ρ_m = (1 + ρ(e))^(1/12) − 1
    a   = cotización + aporte_empleador   si e < fin_trabajo, si no 0
    S_m = (S_{m−1} + a) · (1 + ρ_m)
```

La **comisión no se descuenta del fondo**: es precio de administración sobre el sueldo y no entra a
la cuenta individual. Correcto. Su efecto aparece sólo en el líquido.

La cotización se mantiene **constante en poder adquisitivo** durante todo el horizonte: se supone
que el sueldo se reajusta exactamente con la inflación, sin crecimiento real de carrera. Como el
tope imponible también está fijado en UF, ambos se mueven juntos.

Identidad de cierre: `S_final = S_0 + Σ aportes + rentabilidad_ganada`.

### 7.5 Pensión: Capital Necesario Unitario

La AFP divide el saldo por doce veces el **CNU**. El CNU real es el valor presente de una renta
unitaria ponderando cada período por la probabilidad de supervivencia del afiliado **y de su grupo
familiar**, descontada a la tasa técnica. Aquí se aproxima con una **renta cierta** a lo largo de
la expectativa de vida:

```
i_m    = (1 + tasa_técnica)^(1/12) − 1
n      = round(expectativa_vida · 12)
factor = (1 − (1 + i_m)^(−n)) / i_m          (anualidad vencida)
pensión = saldo / factor
CNU     = saldo / (12 · pensión) = factor/12
```

Verificado: con saldo \$100.000.000 y hombre de 65 (n = 259), la pensión es \$545.287,85 y la
desacumulación `S ← S(1+i_m) − pensión` deja **\$0,000001** tras `n` meses. La anualidad es vencida
y la desacumulación paga a fin de mes: las dos convenciones calzan.

**Sobre el sesgo de la aproximación.** Hay dos efectos de signo contrario y el neto no está
determinado:

1. *A favor de subestimar la pensión (conservador).* El valor presente es **cóncavo** en la
   duración, de modo que por Jensen `ä_{E[T]} ≥ E[ä_T]`: la renta cierta a la esperanza sobrestima
   el CNU vitalicio y por lo tanto **baja** la pensión. El argumento es correcto.
2. *En contra.* El CNU legal pondera además **beneficiarios de pensión de sobrevivencia**
   (cónyuge, hijos), lo que **aumenta** el CNU y **baja** la pensión respecto de lo que calcula
   este modelo. Es decir, empuja en dirección opuesta al punto 1.

> **No se cuantificó cuál domina.** Afirmar sin más que la aproximación «queda del lado
> conservador» sólo es defendible mirando el efecto 1. Un revisor con las tablas RV-2020/CB-2020 y
> una composición de grupo familiar puede resolverlo; hasta entonces, el signo del sesgo neto es
> **desconocido**.

Además, lo calculado se parece a una **renta vitalicia** (constante en UF). El **retiro programado**
real se recalcula cada año y **decrece**. El modelo no distingue las dos modalidades.

### 7.6 Desacumulación del saldo AFP

```
para k = 1..meses_retiro:   S ← max(0, S·(1 + i_m) − pensión)
```

Por construcción de §7.5 el saldo se agota justo en la expectativa de vida. Es la contracara del
CNU, vista mes a mes.

---

## 8. Integración: alineación temporal de las dos series

Este es el punto de costura más delicado del sistema y el que concentró más defectos.

La serie de la AFP tiene origen **hoy**; la proyección de inversión tiene origen
**`inicio_mes/inicio_anio`**. Se define:

```
desfase = (inicio_anio − hoy.año)·12 + (inicio_mes − hoy.mes)
```

La serie AFP se completa con el saldo actual en el origen, de modo que el índice `t` signifique
«meses transcurridos desde hoy», con `t = 0` el saldo de hoy:

```
serie = [saldo_actual] + serie_mensual
alineada[k] = serie[desfase + k]   si 0 ≤ desfase + k < len(serie),   si no  null
```

**Dos correcciones que esto incorpora.** `serie_mensual[0]` es el saldo del mes **siguiente** a
hoy, no el de hoy: sin anteponer `saldo_actual` la curva queda corrida un mes incluso con
`desfase = 0`. Y cuando `desfase < 0` (la inversión empezó antes de hoy) los meses sin dato deben
ser **huecos explícitos** (`null`), no elementos omitidos: omitirlos desplazaba la curva completa
`|desfase|` meses, con un error creciente porque el desfase aumenta un mes cada mes que pasa sin
volver a guardar el perfil.

Consistentemente, la edad al inicio de la proyección admite desfase negativo:

```
edad_inicio = edad_hoy + desfase/12
```

y el mes de proyección en que se jubila se mide contra el **mismo** origen que la serie:

```
pension_start_month = max(1, (año_pensión − inicio_anio)·12 + (mes_nacimiento − inicio_mes) + 1)
```

Comprobación de cierre: con perfil de prueba, `alineada[pension_start_month − 1]` coincide
**exactamente** con `saldo_al_jubilar` calculado por `afp.proyectar`.

### 8.1 Paso a nominales

El motor recibe la serie AFP en pesos de hoy y la lleva a nominales con el deflactor del escenario:

```
afp_series[m].balance = alineada[m−1] · D(m)
```

> **Supuesto.** Se mezcla una tasa **real** (la del fondo de pensiones) con la inflación **del
> escenario de inversión**, que son supuestos independientes. Es consistente en el sentido de que
> el saldo real no depende de `i`, pero implica que la curva nominal de la AFP se mueve al cambiar
> un parámetro que no la afecta económicamente.

### 8.2 Pensión dentro del motor

La pensión se toma **constante en pesos de hoy** y se infla con `D(m)`, lo que es correcto para una
renta vitalicia en UF (§7.5) y no para retiro programado.

En la agregación anual se prorratea el año de entrada:

```
meses_con_pensión = max(0, min(12k, M) − max(12k − 11, pension_start) + 1)
pensión_anual_k   = pensión_hoy · D(12k) · min(1, meses_con_pensión/12)
```

> **Mezcla de unidades declarada.** Esto produce el **promedio mensual** de pensión del año, que
> luego se compara contra una meta **mensual puntual**. En el año de transición la cobertura queda
> subestimada respecto del régimen permanente. Es una simplificación de presentación, no del
> cálculo de la fase de retiro (§6), que sí trabaja mes a mes.

---

## 9. Métricas derivadas

### 9.1 Retorno real

Fisher, no resta:

```
retorno_real = (1 + R_declarado)/(1 + i) − 1
```

Hereda el residuo de §5.3, porque se construye sobre `R_declarado` y no sobre `R_efectivo`.

### 9.2 Retiro sostenible

El **retiro sostenible es el retorno real del instrumento**, en ambos modelos. Consumirlo entero
deja el capital constante en pesos de hoy:

```
retorno_neto    = (1+g)·(1 + y·(1−τ)) − 1          (dividendos)
retorno_neto    = g                                 (simple)
tasa_sostenible = (1 + retorno_neto)/(1 + i) − 1
```

Como cifra **secundaria** se informa cuánto de eso llega sólo por reparto, sin vender una cuota:

```
payout_only = y·(1−τ) − max(0, i − g)
```

**Por qué el retorno real y no sólo el reparto.** La regla anterior (`payout_only` como cifra
principal) topaba en el yield y se negaba a contar como consumible la plusvalía por sobre la
inflación. Con `g > i` eso deja el capital creciendo mientras la app declara la meta inalcanzable.
Medido sobre el mismo instrumento (`g = 5,71%`, `y = 3,5%`, `i = 3,83%`, horizonte 40 años):

| | sólo reparto | retorno real |
|---|---|---|
| tasa sostenible | 3,50% | **5,374%** |
| año de independencia | nunca | **34** |
| capital necesario | \$3.084 M | **\$1.603 M** |

Casi el doble de capital exigido por una restricción —«no vender jamás una cuota»— que nadie se
impone en la práctica. Con la regla unificada, el mismo instrumento modelado como `simple` o como
`dividends` entrega **la misma** tasa sostenible y el **mismo** año de independencia, que es la
prueba de consistencia que antes fallaba.

Verificación por simulación directa a 30 años (devengar `y/12` al mes, pagar trimestral, retirar
la tasa sostenible y medir el capital real final, partiendo de 100): con `g = 3%`, `y = 6,5%`,
`i = 3,83%` la tasa sostenible es **5,65%** y el capital real termina en **101,0** — se mantiene,
como debe ser. El residuo de 1,0 en 30 años (0,03%/año) es la capitalización intra-trimestral del
devengo, no una deriva de la regla.

> **Lo que sí exige.** Consumir el retorno real completo requiere **vender** cada año la parte que
> no llegó como reparto. Quien no quiera vender debe mirar la cifra secundaria `payout_only`, que
> la interfaz muestra al lado. Es una restricción legítima, pero es del usuario, no del modelo.

### 9.3 Independencia financiera y capital necesario

```
sustainable_monthly_k = V_k · tasa_sostenible / 12
fi_year = primer k con sustainable_monthly_k ≥ meta_neta_de_pensión_k
capital_needed_sustainable = meta_neta·12 / tasa_sostenible
capital_needed_at_target   = meta_neta·12 / yield_neto
```

`capital_needed_*` divide una meta **nominal** del año de referencia por una tasa **real**, de modo
que el resultado es un capital nominal de ese año. Es internamente consistente pero se presenta
junto a cifras en pesos de hoy.

### 9.4 Cobertura

```
cobertura_k = reparto_neto_mensual_k / (meta_k − pensión_k) · 100
```

Se mide contra lo que falta **después** de la pensión. Si la pensión sola cubre la meta, la
cobertura es 100% por definición y no 0/0.

---

## 10. Inflación y sensibilidad

### 10.1 Serie y estimador

`IPC_CL` contiene la variación anual dic-dic 2000–2025. El estimador es la **media geométrica**:

```
ḡ = (Π (1 + r_t))^(1/N) − 1
```

correcta para tasas que se componen; la aritmética sobrestima. Ventanas ofrecidas: 10 años
(4,58%), 20 años (4,12%), 26 años (3,83%, recomendada) y la meta del Banco Central (3,0%).

> **Sesgo de muestra declarado.** La serie parte en 2000 porque Chile adoptó metas de inflación con
> flotación en 1999, y mezclar regímenes monetarios sesgaría al alza. El argumento es sólido, pero
> tiene una contrapartida: la muestra **excluye el único régimen de inflación alta**, de modo que
> subestima la cola derecha. La desviación estándar de la serie es 2,59 pp (mín −1,4%, máx 12,8%).

### 10.2 Banda de sensibilidad

El modelo es determinista. Para no publicar cifras con precisión inexistente, cada resultado viaja
con el rango que producen **±1 pp de retorno y ±1 pp de inflación** (cuatro proyecciones extra):

```
casos = { retorno ±1pp, inflación ±1pp }
rango(métrica) = [min, max] sobre {central} ∪ casos
```

Se reportan `depletion_age`, `max_spend_today`, `final_real_balance` y `fi_year`. La edad de
agotamiento se publica **en años enteros** por la misma razón.

Magnitud típica: mover la plusvalía ±2 pp desplaza la edad de agotamiento de 69 a 76 años.

> **Lo que esta banda NO es.** No es un intervalo de confianza. No hay distribución, ni
> correlaciones, ni **riesgo de secuencia de retornos** —que es el riesgo dominante en
> desacumulación, porque una caída temprana es irrecuperable aunque la media se cumpla. Un Monte
> Carlo con bootstrap por bloques sobre retornos históricos sería la mejora natural, y cambiaría
> las conclusiones sobre probabilidad de ruina, que este modelo **no estima**.

---

## 11. Resumen de decisiones discutibles

Ordenadas por impacto potencial. Es la lista que un revisor debería atacar primero.

| # | Decisión / limitación | Dirección del sesgo | Magnitud |
|---|---|---|---|
| 1 | Determinismo: sin riesgo de secuencia ni probabilidad de ruina | indeterminada | edad de agotamiento ±3,5 años con ±2 pp |
| 2 | `g` debe ser **ex-dividendo**; si el usuario pone retorno total, se duplica | sobrestima | hasta `+y` por año |
| 3 | Aporte del empleador constante, sin la gradualidad de la Ley 21.735 | subestima saldo AFP | no cuantificada |
| 4 | CNU por renta cierta, sin tablas de mortalidad ni grupo familiar | **signo neto desconocido** (§7.5) | no cuantificada |
| 5 | Rentabilidad histórica de fondos como estimador puntual forward | indeterminada | no cuantificada |
| 6 | `R_declarado` ≠ `R_efectivo` por capitalización intra-anual de lo repartido | subestima la etiqueta | +0,0243 pp/año con `n = 4` |
| 7 | Consumir el retorno real exige **vender**, no sólo cobrar reparto | es una restricción del usuario, no un sesgo | `payout_only` se informa al lado |
| 8 | Convención de anualidad anticipada en ambos módulos | sobrestima | ~1 mes de retorno sobre lo aportado |
| 9 | Deducibilidad de la comisión AFP de la base afecta | subestima el impuesto si no aplica | a verificar |
| 10 | Pensión anual prorrateada vs meta mensual puntual | subestima cobertura en el año de transición | sólo un año |
| 11 | Serie IPC desde 2000: excluye el régimen de inflación alta | subestima la cola | — |
| 12 | Efectivo no reinvertido: no renta en acumulación, sí en retiro | menor | — |
| 13 | Déficit mensual no se arrastra tras el agotamiento | filas post-agotamiento no financiables | — |
| 14 | Sin impuesto a la ganancia de capital | despreciable por art. 107 LIR desde 2027 | ~0 |

---

## 12. Invariantes de verificación

Comprobaciones reproducibles que deberían mantenerse ante cualquier cambio:

```
(V1)  total_gain == total_dividends_net + total_capital_gain            (± $0,01)
(V2)  total_gain_real == final_real_balance − total_invested_real       (± $0,05)
(V3)  Σ pesos de _mezcla_a_edad(e) == 1   ∀ e ∈ [0,100] paso 0,25       (± 1e−9)
(V4)  desacumulación AFP deja saldo ≈ 0 tras n meses                    (± $0,01)
(V5)  CNU == factor/12 == saldo/(12·pensión)
(V6)  aporte indexado: c_m/D(m) == monto escrito  ∀ m                   (± $1)
(V7)  alineada[pension_start_month−1] == saldo_al_jubilar               (± $0,01)
(V8)  impuesto_unico(200 UTM) == $3.347.936 ; (600 UTM) == $14.428.831
(V9)  saldo_final(_max_spend·1,01) ≤ 1                                  (bisección acota)
(V10) total_dividends_net + total_dividends_tax == total_dividends      (± $0,01)
(V11) el patrimonio final es monótono decreciente en el mes del aporte
      extraordinario, y el costo marginal de atrasarlo un mes no varía
      más de 1,15× entre meses de pago y meses sin pago
(V12) el mismo instrumento como 'simple' y como 'dividends' entrega la
      misma tasa sostenible y el mismo año de independencia
(V13) sin reinversión, lo repartido no depende del calendario de pagos
```

Están **implementadas** en `test_stonks.py` — 71 pruebas, `make test` —, junto con una regresión
por cada hallazgo de `AUDITORIA.md`, de modo que un retroceso vuelva a fallar donde se detectó.

---

## 13. Referencias normativas

- **Impuesto único de segunda categoría** — art. 42 N°1 y art. 52, DL 824 (Ley sobre Impuesto a la
  Renta); tabla mensual publicada por el SII.
- **Ganancia de capital en instrumentos con presencia bursátil** — art. 107 LIR;
  [Circular N° 39 de 2022 del SII](https://www.sii.cl/normativa_legislacion/circulares/2022/circu39.pdf).
  Impuesto único de 10% hasta el 31-dic-2026; ingreso no renta desde el 1-ene-2027.
- **Multifondos, asignación por defecto y salida obligatoria del Fondo A** — DL 3.500, art. 23;
  Compendio de Normas del Sistema de Pensiones, cap. II.
- **Reforma previsional** — Ley 21.735 (2025): aporte del empleador y fondos generacionales.
- **Topes imponibles 2026** — [Superintendencia de Pensiones](https://www.spensiones.cl/portal/institucional/594/w3-article-16885.html)
  (90 UF, AFP y salud); [AFC](https://www.afc.cl/afc-informa/noticias/empleador-conozca-el-nuevo-tope-imponible-para-2026/)
  (135,2 UF, seguro de cesantía).
- **Tasa de interés técnica del retiro programado** — fijada trimestralmente por la SP.
- **Tablas de mortalidad** — RV-2020 / CB-2020 con factores de mejoramiento, SP / CMF.
- **Serie de IPC** — INE / Banco Central de Chile, variación anual diciembre-diciembre.

---

*Documento generado a partir del código en su estado posterior a `AUDITORIA.md`. Las cifras de
verificación citadas se obtuvieron ejecutando los módulos reales; los invariantes de §12 son
reproducibles.*
