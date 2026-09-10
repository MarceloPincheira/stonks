#!/usr/bin/env python3
"""Pruebas del modelo de proyección. Sin dependencias: unittest de la stdlib.

    make test        o        python3 -m unittest test_stonks -v

Cada prueba apunta a un invariante de MODELO.md §12 o a un hallazgo de AUDITORIA.md,
de modo que una regresión vuelva a fallar exactamente donde se detectó. Las que tocan
la base usan un archivo temporal: ninguna prueba escribe en `stonks.db`.
"""

import os
import sqlite3
import tempfile
import unittest
from datetime import date

import afp
import engine
import inflation

# --- ayudas ---------------------------------------------------------------


def escenario(**kw):
    """Escenario de dividendos con valores por defecto razonables."""
    base = {
        "name": "t",
        "years": 30,
        "currency": "CLP",
        "model": "dividends",
        "appreciation": 5.71,
        "dividend_yield": 3.5,
        "dividend_tax": 0.0,
        "reinvest": True,
        "payout_months": [4, 5, 9, 12],
        "inflation": 3.83,
        "income_goal": 2000000,
        "index_contributions": True,
        "ranges": [{"start_month": 1, "end_month": 360, "amount": 300000}],
    }
    base.update(kw)
    return engine.project(engine.normalize_input(base))


PERFIL = {
    "nacimiento": "1990-05-15",
    "sexo": "hombre",
    "inicio_mes": 1,
    "inicio_anio": 2026,
    "sueldo_imponible": 2500000,
    "no_imponible": 0,
    "afp": "Habitat",
    "comision_afp": 1.27,
    "fondo": "B",
    "saldo_afp": 45000000,
    "salud": "fonasa",
    "salud_extra": 0,
    "contrato_indefinido": True,
    "aporte_empleador": 0.1,
    "uf": 40884.32,
    "utm": 71721,
    "trayectoria": "fijo",
    "destino_salida_a": "B",
}


def perfil(**kw):
    p = dict(PERFIL, **kw)
    p["edad"] = afp.edad_desde(p["nacimiento"])
    return p


# --- conversión de tasas --------------------------------------------------


class TestConversionDeTasas(unittest.TestCase):
    """MODELO.md §3.1 — toda conversión anual→mensual es geométrica, no lineal."""

    def test_tasa_mensual_es_geometrica(self):
        r = escenario(model="simple", annual_return=5.71, dividend_yield=0, payout_months=[12])
        esperado = ((1 + 0.0571) ** (1 / 12) - 1) * 100
        self.assertAlmostEqual(r["monthly_rate_pct"], round(esperado, 6), places=6)
        self.assertNotAlmostEqual(r["monthly_rate_pct"], 5.71 / 12, places=4)

    def test_retorno_real_usa_fisher_no_resta(self):
        r = escenario(model="simple", annual_return=9.5, inflation=3.83)
        fisher = ((1 + 0.095) / (1 + 0.0383) - 1) * 100
        self.assertAlmostEqual(r["real_return_pct"], round(fisher, 3), places=3)
        self.assertNotAlmostEqual(r["real_return_pct"], 9.5 - 3.83, places=2)

    def test_retorno_total_compone_no_suma(self):
        """AUDITORIA #11 — declararlo como g+y quedaba bajo lo que el motor entrega."""
        d = engine.normalize_input(
            {
                "years": 30,
                "model": "dividends",
                "appreciation": 5.71,
                "dividend_yield": 3.5,
                "ranges": [],
            }
        )
        self.assertAlmostEqual(d["annual_return"], ((1.0571 * 1.035) - 1) * 100, places=6)
        self.assertNotAlmostEqual(d["annual_return"], 5.71 + 3.5, places=2)


# --- aportes --------------------------------------------------------------


class TestAportes(unittest.TestCase):

    def test_aporte_indexado_vale_lo_escrito_en_pesos_de_hoy(self):
        """MODELO.md V6 / AUDITORIA #12 — antes se descolgaba 3,4% dentro del año."""
        r = escenario(index_contributions=True)
        for m in (1, 6, 12, 13, 120, 360):
            real = r["months"][m - 1]["contribution"] / (1.0383 ** (m / 12))
            self.assertAlmostEqual(
                real, 300000, delta=1, msg=f"mes {m}: el aporte no vale lo escrito"
            )

    def test_aporte_nominal_no_se_indexa(self):
        r = escenario(index_contributions=False)
        for m in (1, 120, 360):
            self.assertAlmostEqual(r["months"][m - 1]["contribution"], 300000, delta=0.01)

    def test_aporte_extraordinario_ida_y_vuelta(self):
        """El monto se escribe en pesos de hoy y al deflactar vuelve exacto."""
        r = escenario(
            years=30,
            start_year=2026,
            start_month=1,
            lump_sums=[{"year": 2030, "month": 6, "amount": 10_000_000}],
        )
        lump = r["lump_sums"][0]
        self.assertTrue(lump["in_range"])
        self.assertEqual(lump["projection_month"], (2030 - 2026) * 12 + (6 - 1) + 1)
        self.assertAlmostEqual(
            lump["amount_nominal"] / (1.0383 ** (lump["projection_month"] / 12)),
            10_000_000,
            delta=1,
        )
        self.assertAlmostEqual(r["total_invested_real"], 360 * 300000 + 10_000_000, delta=2)

    def test_tramos_solapados_se_rechazan(self):
        with self.assertRaises(engine.ValidationError):
            engine.normalize_input(
                {
                    "years": 10,
                    "ranges": [
                        {"start_month": 1, "end_month": 60, "amount": 100},
                        {"start_month": 50, "end_month": 80, "amount": 200},
                    ],
                }
            )

    def test_tramo_se_recorta_al_horizonte(self):
        tabla = engine.monthly_amount_table(
            [{"start_month": 1, "end_month": 600, "amount": 100}], 12
        )
        self.assertEqual(len(tabla), 12)
        self.assertTrue(all(a == 100 for a in tabla))

    def test_dejar_de_trabajar_corta_los_aportes(self):
        r = escenario(work_until_month=120)
        self.assertEqual(r["months"][119]["contribution"] > 0, True)
        self.assertEqual(r["months"][120]["contribution"], 0)
        self.assertEqual(r["months_trimmed"], 240)


# --- identidades contables ------------------------------------------------


class TestIdentidadesContables(unittest.TestCase):
    """MODELO.md §5.5 y §12 — invariantes que deben cerrar siempre."""

    def _casos(self):
        for reinvest in (True, False):
            for tax in (0.0, 23.0):
                yield escenario(reinvest=reinvest, dividend_tax=tax)

    def test_V1_plusvalia_es_valor_menos_capital_puesto(self):
        for r in self._casos():
            m = r["months"][-1]
            self.assertAlmostEqual(
                m["capital_gain"],
                m["portfolio"] - (m["invested"] + m["reinvested_total"]),
                delta=0.02,
            )

    def test_V2_ganancia_es_repartos_netos_mas_plusvalia(self):
        for r in self._casos():
            self.assertAlmostEqual(
                r["total_gain"], r["total_dividends_net"] + r["total_capital_gain"], delta=0.02
            )

    def test_V3_ganancia_real(self):
        for r in self._casos():
            self.assertAlmostEqual(
                r["total_gain_real"],
                r["final_real_balance"] - r["total_invested_real"],
                delta=0.05,
            )

    def test_V10_neto_mas_impuesto_es_el_bruto(self):
        for r in self._casos():
            self.assertAlmostEqual(
                r["total_dividends_net"] + r["total_dividends_tax"],
                r["total_dividends"],
                delta=0.02,
            )


# --- repartos e impuesto --------------------------------------------------


class TestRepartos(unittest.TestCase):

    def test_impuesto_reduce_lo_reinvertido(self):
        """AUDITORIA #4 — antes se reinvertía el reparto bruto, libre de impuesto."""
        libre = escenario(dividend_tax=0)
        gravado = escenario(dividend_tax=23)
        self.assertLess(gravado["final_balance"], libre["final_balance"])
        self.assertAlmostEqual(
            gravado["total_dividends_tax"], gravado["total_dividends"] * 0.23, delta=1
        )
        self.assertEqual(libre["total_dividends_tax"], 0)

    def test_impuesto_fuera_de_rango_se_rechaza(self):
        for t in (-1, 101):
            with self.assertRaises(engine.ValidationError):
                engine.normalize_input(
                    {
                        "years": 10,
                        "model": "dividends",
                        "appreciation": 3,
                        "dividend_yield": 5,
                        "dividend_tax": t,
                        "ranges": [],
                    }
                )

    def test_el_reparto_se_devenga_por_mes_tenido(self):
        """AUDITORIA #8 — el reparto se devenga yield/12 al mes, no es una fracción del
        valor en la fecha de pago. Un aporte que entra en el mes de pago devenga UN mes,
        no un trimestre completo."""
        un_mes = escenario(
            years=1,
            appreciation=0.0,
            dividend_yield=4.0,
            payout_months=[1],
            inflation=0,
            index_contributions=False,
            ranges=[{"start_month": 1, "end_month": 1, "amount": 1_000_000}],
        )
        self.assertAlmostEqual(un_mes["total_dividends"], 1_000_000 * 0.04 / 12, delta=1)

        dos_meses = escenario(
            years=1,
            appreciation=0.0,
            dividend_yield=4.0,
            payout_months=[2],
            inflation=0,
            index_contributions=False,
            ranges=[{"start_month": 1, "end_month": 1, "amount": 1_000_000}],
        )
        self.assertAlmostEqual(dos_meses["total_dividends"], 2 * 1_000_000 * 0.04 / 12, delta=1)

    def test_el_calendario_de_pagos_no_altera_lo_devengado(self):
        """Con devengo, lo repartido depende del valor del fondo y del yield, no de en
        cuántas fechas se pague. Se compara sin reinversión para aislar el devengo del
        efecto de componer antes (con reinversión, pagar más seguido sí compone más)."""
        com = {
            "years": 10,
            "appreciation": 0.0,
            "dividend_yield": 6.0,
            "inflation": 0,
            "index_contributions": False,
            "reinvest": False,
            "ranges": [{"start_month": 1, "end_month": 12, "amount": 1_000_000}],
        }
        uno = escenario(**com, payout_months=[12])
        doce = escenario(**com, payout_months=list(range(1, 13)))
        self.assertAlmostEqual(uno["total_dividends"], doce["total_dividends"], delta=1)

    def test_reinvertir_mas_seguido_compone_mas(self):
        """La contracara: con reinversión, pagar mensual compone más que pagar una vez."""
        com = {
            "years": 10,
            "appreciation": 0.0,
            "dividend_yield": 6.0,
            "inflation": 0,
            "index_contributions": False,
            "reinvest": True,
            "ranges": [{"start_month": 1, "end_month": 12, "amount": 1_000_000}],
        }
        uno = escenario(**com, payout_months=[12])
        doce = escenario(**com, payout_months=list(range(1, 13)))
        self.assertGreater(doce["final_balance"], uno["final_balance"])

    def test_el_mes_del_reparto_no_altera_el_resultado(self):
        """Invariante fuerte: invertir más tarde nunca rinde más, y el costo marginal de
        atrasarse un mes es uniforme. Antes había un salto de 7x en los meses de pago —
        primero a favor (cobraba el reparto entero) y luego en contra (lo perdía)."""
        com = {
            "years": 20,
            "appreciation": 5.71,
            "dividend_yield": 3.5,
            "payout_months": [4, 5, 9, 12],
            "start_year": 2026,
            "start_month": 1,
            "index_contributions": False,
            "income_goal": 0,
            "ranges": [{"start_month": 1, "end_month": 240, "amount": 150000}],
        }
        finales = [
            escenario(**com, lump_sums=[{"year": 2026, "month": mes, "amount": 50_000_000}])[
                "final_balance"
            ]
            for mes in range(1, 13)
        ]
        for k in range(1, 12):
            self.assertLess(
                finales[k], finales[k - 1], f"invertir en el mes {k + 1} rinde más que en el {k}"
            )
        saltos = [finales[k - 1] - finales[k] for k in range(1, 12)]
        self.assertLess(
            max(saltos) / min(saltos),
            1.15,
            "el mes de pago sigue produciendo un salto en el resultado",
        )


# --- retiro sostenible ----------------------------------------------------


class TestRetiroSostenible(unittest.TestCase):
    """AUDITORIA post-#7 — el retiro sostenible es el retorno REAL en ambos modelos."""

    def test_los_dos_modelos_coinciden_en_el_mismo_instrumento(self):
        com = {
            "years": 40,
            "inflation": 3.83,
            "income_goal": 2000000,
            "index_contributions": True,
            "ranges": [{"start_month": 1, "end_month": 480, "amount": 400000}],
        }
        d = escenario(
            **com,
            appreciation=5.71,
            dividend_yield=3.5,
            dividend_tax=0,
            payout_months=[4, 5, 9, 12],
        )
        s = escenario(**com, model="simple", annual_return=(1.0571 * 1.035 - 1) * 100)
        self.assertAlmostEqual(d["sustainable_rate"], s["sustainable_rate"], places=2)
        self.assertEqual(d["fi_year"], s["fi_year"])

    def test_es_el_retorno_real_del_instrumento(self):
        r = escenario(appreciation=5.71, dividend_yield=3.5, dividend_tax=0, inflation=3.83)
        esperado = ((1.0571 * 1.035) / 1.0383 - 1) * 100
        self.assertAlmostEqual(r["sustainable_rate"], round(esperado, 3), places=2)

    def test_el_impuesto_baja_la_tasa_sostenible(self):
        libre = escenario(dividend_tax=0)
        gravado = escenario(dividend_tax=23)
        self.assertLess(gravado["sustainable_rate"], libre["sustainable_rate"])

    def test_solo_repartos_va_como_cifra_secundaria(self):
        d = escenario(appreciation=5.71, dividend_yield=3.5, dividend_tax=0)
        self.assertAlmostEqual(d["payout_only_rate"], 3.5, places=3)
        self.assertLess(d["payout_only_rate"], d["sustainable_rate"])
        s = escenario(model="simple", annual_return=9.41)
        self.assertIsNone(s["payout_only_rate"])

    def test_el_modelo_simple_ya_no_informa_cero(self):
        """AUDITORIA #8 — la pestaña de poder adquisitivo mostraba $0 todos los años."""
        s = escenario(model="simple", annual_return=9.21, inflation=3.83)
        self.assertGreater(s["sustainable_rate"], 5)
        self.assertGreater(s["yearly"][-1]["sustainable_monthly"], 0)

    def test_consumir_la_tasa_sostenible_mantiene_el_capital_real(self):
        """Simulación directa: retirar la tasa sostenible deja el capital real intacto."""
        g, y, i = 0.03, 0.065, 0.0383
        sost = (1 + g) * (1 + y) / (1 + i) - 1
        V, mr, per = 100.0, (1 + g) ** (1 / 12) - 1, y / 4
        for m in range(1, 361):
            V *= 1 + mr
            if m % 3 == 0:
                V += V * per - V * sost / 4
        self.assertAlmostEqual(V / ((1 + i) ** 30), 100.0, delta=6)


# --- fase de retiro -------------------------------------------------------


class TestFaseDeRetiro(unittest.TestCase):

    def _comun(self, portfolio=120_000_000, tasa=6.0, infl=3.83, pension=0.0):
        return {
            "start_month": 0,
            "portfolio": portfolio,
            "deflator": lambda m: (1 + infl / 100) ** (m / 12),
            "monthly_rate": (1 + tasa / 100) ** (1 / 12) - 1,
            "accrual_rate": 0.0,
            "payout_months": [],
            "pension_today": pension,
            "pension_start": 1 if pension else None,
        }

    def test_max_spend_acota_en_horizonte_corto(self):
        """AUDITORIA #7 — el techo V/12 no acotaba y devolvía un máximo falso."""
        for meses in (3, 6, 12, 24, 60):
            kw = self._comun()
            ms = engine._max_spend(meses, **kw)
            sobra = engine._retirement_path(ms * 1.05, end_month=meses, **kw)[2]
            self.assertLessEqual(
                sobra, 1.0, f"con {meses} meses, gastar 5% más del máximo deja saldo"
            )

    def test_max_spend_agota_justo(self):
        kw = self._comun()
        ms = engine._max_spend(240, **kw)
        self.assertGreater(engine._retirement_path(ms * 0.95, end_month=240, **kw)[2], 1)
        self.assertLessEqual(engine._retirement_path(ms * 1.05, end_month=240, **kw)[2], 1)

    def test_gasto_mayor_agota_antes(self):
        kw = self._comun()
        _, a1, _ = engine._retirement_path(1_000_000, end_month=240, **kw)
        _, a2, _ = engine._retirement_path(3_000_000, end_month=240, **kw)
        self.assertTrue(a2 is not None)
        self.assertTrue(a1 is None or a2 < a1)

    def test_la_edad_de_agotamiento_va_en_anios_enteros(self):
        """AUDITORIA #5 — un decimal prometía precisión que el modelo no tiene."""
        r = escenario(
            years=40,
            income_goal=2500000,
            start_age=36.3,
            life_age=86.6,
            retire_to_age=86.6,
            work_until_age=65,
            work_until_month=344,
            spend_mode="goal",
            pension_monthly=700000,
            pension_start_month=353,
            include_pension=True,
            ranges=[{"start_month": 1, "end_month": 344, "amount": 150000}],
        )
        edad = r["retirement"]["depletion_age"]
        self.assertIsInstance(edad, int)


# --- previsional ----------------------------------------------------------


class TestImpuestoUnico(unittest.TestCase):
    """AUDITORIA #2 — el tramo del 35% llega a 310 UTM, no a 150."""

    UTM = 71721.0

    def test_coincide_con_la_tabla_del_sii(self):
        for utm_base, esperado in (
            (13.5, 0),
            (30, 47336),
            (90, 685653),
            (120, 1339748),
            (150, 2092819),
            (200, 3347936),
            (310, 6109195),
            (600, 14428831),
        ):
            self.assertAlmostEqual(
                afp.impuesto_unico(utm_base * self.UTM, self.UTM),
                esperado,
                delta=1,
                msg=f"{utm_base} UTM",
            )

    def test_la_escala_es_continua_en_cada_corte(self):
        for k in range(len(afp.IUSC) - 1):
            tope = afp.IUSC[k][0]
            izq = afp.IUSC[k][1] * tope - afp.IUSC[k][2]
            der = afp.IUSC[k + 1][1] * tope - afp.IUSC[k + 1][2]
            self.assertAlmostEqual(izq, der, places=9, msg=f"corte en {tope} UTM")

    def test_el_tramo_superior_arranca_en_310_utm(self):
        self.assertEqual(afp.IUSC[-2][0], 310.0)
        self.assertAlmostEqual(afp.IUSC[-1][2], 38.82, places=2)

    def test_bases_no_positivas_no_tributan(self):
        self.assertEqual(afp.impuesto_unico(0, self.UTM), 0.0)
        self.assertEqual(afp.impuesto_unico(-1000, self.UTM), 0.0)
        self.assertEqual(afp.impuesto_unico(1_000_000, 0), 0.0)


class TestCotizaciones(unittest.TestCase):

    def test_la_cesantia_usa_su_propio_tope(self):
        """AUDITORIA #10 — 90 UF es el tope de AFP y salud; la AFC va a 135,2 UF."""
        uf = 40884.32
        a = afp.proyectar(perfil(sueldo_imponible=5_000_000))
        self.assertAlmostEqual(a["descuentos"]["cesantia"], 5_000_000 * 0.006, delta=1)
        b = afp.proyectar(perfil(sueldo_imponible=8_000_000))
        self.assertAlmostEqual(
            b["descuentos"]["cesantia"], afp.TOPE_CESANTIA_UF * uf * 0.006, delta=1
        )
        self.assertGreater(afp.TOPE_CESANTIA_UF, afp.TOPE_IMPONIBLE_UF)

    def test_afp_y_salud_se_topan_en_90_uf(self):
        uf = 40884.32
        a = afp.proyectar(perfil(sueldo_imponible=8_000_000))
        tope = afp.TOPE_IMPONIBLE_UF * uf
        self.assertAlmostEqual(a["descuentos"]["cotizacion"], tope * 0.10, delta=1)
        self.assertAlmostEqual(a["descuentos"]["salud"], tope * 0.07, delta=1)

    def test_la_comision_no_entra_a_la_cuenta_individual(self):
        """Es precio de administración: baja el líquido, no el saldo."""
        cara = afp.proyectar(perfil(comision_afp=1.45))
        barata = afp.proyectar(perfil(comision_afp=0.49))
        self.assertEqual(cara["saldo_al_jubilar"], barata["saldo_al_jubilar"])
        self.assertLess(cara["liquido_aprox"], barata["liquido_aprox"])

    def test_identidad_del_saldo(self):
        a = afp.proyectar(perfil())
        self.assertAlmostEqual(
            a["saldo_al_jubilar"],
            a["saldo_actual"] + a["total_cotizado"] + a["rentabilidad_ganada"],
            delta=1,
        )


class TestFondosYTraspasos(unittest.TestCase):

    def test_V3_los_pesos_de_la_mezcla_suman_uno(self):
        for contrato in ("basico", "ampliado"):
            for sexo in ("hombre", "mujer"):
                for paso in range(0, 401):
                    pesos = afp._mezcla_a_edad(paso / 4, sexo, contrato)
                    self.assertAlmostEqual(sum(pesos.values()), 1.0, places=9)

    def test_el_traspaso_completa_en_cuatro_anios(self):
        pesos = afp._mezcla_a_edad(36, "hombre", "basico")
        self.assertAlmostEqual(pesos.get("C", 0), 0.2, places=9)
        pesos = afp._mezcla_a_edad(40, "hombre", "basico")
        self.assertAlmostEqual(pesos.get("C", 0), 1.0, places=9)

    def test_el_fondo_A_tiene_salida_obligatoria(self):
        self.assertEqual(afp.fondo_vigente(55, "A", "hombre"), "A")
        self.assertEqual(afp.fondo_vigente(56, "A", "hombre"), "B")
        self.assertEqual(afp.fondo_vigente(56, "A", "hombre", "E"), "E")
        self.assertEqual(afp.fondo_vigente(60, "B", "hombre"), "B")

    def test_se_informa_el_fondo_realmente_usado(self):
        """AUDITORIA #9 — con traspaso por edad la elección de fondo no se aplica."""
        a = afp.proyectar(perfil(trayectoria="basico", fondo="E"))
        self.assertTrue(a["fondo_ignorado"])
        self.assertEqual(a["fondo_elegido"], "E")
        self.assertNotEqual(a["fondo_inicial"], "E")
        b = afp.proyectar(perfil(trayectoria="fijo", fondo="E"))
        self.assertFalse(b["fondo_ignorado"])
        self.assertEqual(b["fondo_inicial"], "E")


class TestPension(unittest.TestCase):
    """MODELO.md §7.5 — CNU por renta cierta y su desacumulación."""

    def test_V4_la_desacumulacion_agota_el_saldo(self):
        saldo, sexo = 100_000_000, "hombre"
        p = afp.pension_mensual(saldo, sexo)
        i_m = (1 + afp.TASA_TECNICA / 100) ** (1 / 12) - 1
        n = round(afp.EXPECTATIVA_VIDA[sexo] * 12)
        s = saldo
        for _ in range(n):
            s = s * (1 + i_m) - p
        self.assertAlmostEqual(s, 0.0, delta=0.01)

    def test_V5_identidad_del_cnu(self):
        a = afp.proyectar(perfil())
        self.assertAlmostEqual(
            a["cnu"], a["saldo_al_jubilar"] / (12 * a["pension_mensual"]), delta=0.01
        )

    def test_saldo_cero_no_paga_pension(self):
        self.assertEqual(afp.pension_mensual(0, "hombre"), 0.0)
        self.assertEqual(afp.pension_mensual(-100, "mujer"), 0.0)

    def test_mas_saldo_mas_pension_proporcional(self):
        self.assertAlmostEqual(
            afp.pension_mensual(200e6, "hombre"),
            2 * afp.pension_mensual(100e6, "hombre"),
            delta=0.01,
        )


class TestEdad(unittest.TestCase):

    def test_edad_exacta_con_fraccion(self):
        self.assertAlmostEqual(afp.edad_desde("1990-01-01", date(2026, 1, 1)), 36.0, places=2)
        self.assertAlmostEqual(afp.edad_desde("1990-07-01", date(2026, 1, 1)), 35.5, delta=0.02)

    def test_29_de_febrero_no_revienta(self):
        """El 29 de febrero no existe en años no bisiestos: no debe lanzar."""
        self.assertGreaterEqual(afp.edad_desde("2000-02-29", date(2026, 3, 1)), 26.0)
        self.assertLess(afp.edad_desde("2000-02-29", date(2026, 3, 1)), 27.0)


# --- inflación ------------------------------------------------------------


class TestInflacion(unittest.TestCase):

    def test_media_geometrica(self):
        esperado = ((1.10 * 1.20) ** 0.5 - 1) * 100
        original = dict(inflation.IPC_CL)
        try:
            inflation.IPC_CL.clear()
            inflation.IPC_CL.update({2000: 10.0, 2001: 20.0})
            self.assertAlmostEqual(inflation.geometric_mean([2000, 2001]), esperado, places=9)
        finally:
            inflation.IPC_CL.clear()
            inflation.IPC_CL.update(original)

    def test_la_geometrica_es_menor_que_la_aritmetica(self):
        años = list(inflation.window(26))
        aritmetica = sum(inflation.IPC_CL[y] for y in años) / len(años)
        self.assertLess(inflation.geometric_mean(años), aritmetica)

    def test_los_presets_estan_ordenados_y_completos(self):
        keys = [p["key"] for p in inflation.presets()]
        self.assertEqual(keys[0], "target")
        self.assertTrue(any(p.get("recommended") for p in inflation.presets()))


# --- alineación perfil ↔ escenario ----------------------------------------


class TestAlineacionAFP(unittest.TestCase):
    """AUDITORIA #3 — la serie de la AFP y la proyección tienen orígenes distintos."""

    @staticmethod
    def _alinear(serie, desfase):
        return [
            serie[j] if 0 <= (j := desfase + k) < len(serie) else None
            for k in range(len(serie) - desfase)
        ]

    def test_sin_desfase_el_primer_mes_es_el_saldo_de_hoy(self):
        serie = [100, 101, 102, 103]
        self.assertEqual(self._alinear(serie, 0)[:4], [100, 101, 102, 103])

    def test_con_desfase_negativo_los_meses_previos_son_huecos(self):
        serie = [100, 101, 102, 103]
        al = self._alinear(serie, -3)
        self.assertEqual(al[:3], [None, None, None])
        self.assertEqual(al[3], 100)

    def test_con_desfase_positivo_arranca_mas_adelante(self):
        serie = [100, 101, 102, 103]
        self.assertEqual(self._alinear(serie, 2)[0], 102)

    def test_no_se_pierde_la_cola(self):
        serie = list(range(50))
        self.assertEqual(self._alinear(serie, -8)[-1], 49)

    def test_el_mes_de_jubilacion_lee_el_saldo_al_jubilar(self):
        p = perfil()
        pr = afp.proyectar(p)
        hoy = date.today()
        desfase = (p["inicio_anio"] - hoy.year) * 12 + (p["inicio_mes"] - hoy.month)
        serie = [pr["saldo_actual"]] + pr["serie_mensual"]
        al = self._alinear(serie, desfase)
        y, m = int(p["nacimiento"][:4]), int(p["nacimiento"][5:7])
        desde = (
            (y + afp.EDAD_PENSION[p["sexo"]] - p["inicio_anio"]) * 12 + (m - p["inicio_mes"]) + 1
        )
        self.assertAlmostEqual(al[desde - 1], pr["saldo_al_jubilar"], delta=0.01)


# --- sensibilidad ---------------------------------------------------------


class TestSensibilidad(unittest.TestCase):
    """AUDITORIA #5 — la proyección viaja con su banda."""

    def _escenario(self):
        return engine.normalize_input(
            {
                "name": "s",
                "years": 40,
                "model": "dividends",
                "appreciation": 5.71,
                "dividend_yield": 3.5,
                "dividend_tax": 0,
                "payout_months": [4, 5, 9, 12],
                "inflation": 3.83,
                "income_goal": 2500000,
                "index_contributions": True,
                "start_age": 36.3,
                "life_age": 86.6,
                "retire_to_age": 86.6,
                "work_until_age": 65,
                "work_until_month": 344,
                "spend_mode": "goal",
                "pension_monthly": 700000,
                "pension_start_month": 353,
                "include_pension": True,
                "ranges": [{"start_month": 1, "end_month": 344, "amount": 150000}],
            }
        )

    def test_la_banda_contiene_al_caso_central(self):
        d = self._escenario()
        s = engine.sensitivity(d, engine.project(d))
        for metrica, rango in s["rangos"].items():
            if rango["central"] is None or rango["min"] is None:
                continue
            self.assertLessEqual(rango["min"], rango["central"], metrica)
            self.assertLessEqual(rango["central"], rango["max"], metrica)

    def test_mas_retorno_estira_el_patrimonio(self):
        d = self._escenario()
        s = engine.sensitivity(d, engine.project(d))
        self.assertLess(
            s["casos"]["retorno_baja"]["final_real_balance"],
            s["casos"]["retorno_sube"]["final_real_balance"],
        )

    def test_la_banda_no_es_degenerada(self):
        d = self._escenario()
        s = engine.sensitivity(d, engine.project(d))
        r = s["rangos"]["final_real_balance"]
        self.assertGreater(r["max"], r["min"])


# --- persistencia ---------------------------------------------------------


class TestPersistencia(unittest.TestCase):
    """AUDITORIA #1, #6, #13 — arranque, edad y migraciones."""

    def setUp(self):
        import db

        self.db = db
        self.original = db.DB_PATH
        self.tmp = tempfile.mkdtemp()
        db.DB_PATH = os.path.join(self.tmp, "test.db")

    def tearDown(self):
        self.db.DB_PATH = self.original

    def test_arranca_en_base_nueva_con_los_ejemplos(self):
        self.db.init()
        with sqlite3.connect(self.db.DB_PATH) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM scenario").fetchone()[0], 2)

    def test_arrancar_varias_veces_es_idempotente(self):
        for _ in range(3):
            self.db.init()
        with sqlite3.connect(self.db.DB_PATH) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM scenario").fetchone()[0], 2)

    def test_las_semillas_traen_todas_las_claves_que_exige_values(self):
        need = [c.strip() for c in self.db.SCENARIO_COLUMNS.split(",")]
        for nombre, s in self.db.SEEDS:
            limpio = engine.normalize_input(s)
            faltan = [c for c in need if c not in limpio]
            self.assertEqual(faltan, [], f"{nombre} no produce {faltan}")

    def test_la_edad_se_recalcula_al_leer(self):
        """Un perfil viejo sobrestimaba la pensión: la edad sale de la fecha."""
        self.db.init()
        with sqlite3.connect(self.db.DB_PATH) as c:
            c.execute(
                "INSERT INTO profile (id, edad, nacimiento, sexo, sueldo_imponible, "
                "uf, utm) VALUES (1, 20.0, '1990-05-15', 'hombre', 2500000, "
                "40884.32, 71721)"
            )
        leido = self.db.get_profile()["profile"]
        self.assertAlmostEqual(leido["edad"], afp.edad_desde("1990-05-15"), places=2)

    def test_sueldo_bruto_obsoleto_no_resucita(self):
        self.db.init()
        with sqlite3.connect(self.db.DB_PATH) as c:
            c.execute(
                "INSERT INTO profile (id, nacimiento, sueldo_bruto, sueldo_imponible) "
                "VALUES (1, '1990-05-15', 9999999, 0)"
            )
        self.db.init()
        with sqlite3.connect(self.db.DB_PATH) as c:
            self.assertEqual(
                c.execute("SELECT sueldo_imponible FROM profile WHERE id=1").fetchone()[0], 0
            )

    def test_borrar_un_escenario_borra_sus_tramos(self):
        self.db.init()
        guardado = self.db.save_scenario(
            engine.normalize_input(
                {
                    "name": "x",
                    "years": 10,
                    "model": "simple",
                    "annual_return": 5,
                    "ranges": [{"start_month": 1, "end_month": 12, "amount": 100}],
                }
            )
        )
        self.assertTrue(self.db.delete_scenario(guardado["id"]))
        with sqlite3.connect(self.db.DB_PATH) as c:
            self.assertEqual(
                c.execute(
                    "SELECT count(*) FROM contribution_range WHERE scenario_id = ?",
                    (guardado["id"],),
                ).fetchone()[0],
                0,
            )

    def test_el_escenario_guardado_se_recupera_igual(self):
        self.db.init()
        datos = engine.normalize_input(
            {
                "name": "ida y vuelta",
                "years": 25,
                "model": "dividends",
                "appreciation": 4.2,
                "dividend_yield": 5.5,
                "dividend_tax": 17,
                "inflation": 3.5,
                "income_goal": 1_500_000,
                "payout_months": [3, 9],
                "reinvest": False,
                "index_contributions": True,
                "ranges": [{"start_month": 1, "end_month": 120, "amount": 250000}],
            }
        )
        guardado = self.db.save_scenario(datos)
        leido = self.db.get_scenario(guardado["id"])
        for campo in (
            "name",
            "years",
            "appreciation",
            "dividend_yield",
            "dividend_tax",
            "inflation",
            "income_goal",
            "reinvest",
            "index_contributions",
        ):
            self.assertEqual(leido[campo], datos[campo], campo)
        self.assertEqual(leido["payout_months"], "3,9")
        self.assertEqual(leido["ranges"], datos["ranges"])


# --- validación de entrada ------------------------------------------------


class TestValidacion(unittest.TestCase):

    def test_horizonte_fuera_de_rango(self):
        for years in (0, 101, "abc", None):
            with self.assertRaises(engine.ValidationError):
                engine.normalize_input({"years": years, "ranges": []})

    def test_inflacion_de_menos_cien_se_rechaza(self):
        with self.assertRaises(engine.ValidationError):
            engine.normalize_input({"years": 10, "inflation": -100, "ranges": []})

    def test_inflacion_cero_o_negativa_es_valida(self):
        for infl in (0, -2, -50):
            r = escenario(
                inflation=infl,
                years=5,
                ranges=[{"start_month": 1, "end_month": 60, "amount": 100000}],
            )
            self.assertGreater(r["final_balance"], 0)

    def test_modelo_desconocido(self):
        with self.assertRaises(engine.ValidationError):
            engine.normalize_input({"years": 10, "model": "magia", "ranges": []})

    def test_meta_negativa_se_rechaza(self):
        with self.assertRaises(engine.ValidationError):
            engine.normalize_input({"years": 10, "income_goal": -1, "ranges": []})

    def test_horizonte_extremo_no_revienta(self):
        r = escenario(years=100, ranges=[{"start_month": 1, "end_month": 1200, "amount": 100000}])
        self.assertEqual(r["total_months"], 1200)
        self.assertGreater(r["final_balance"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
