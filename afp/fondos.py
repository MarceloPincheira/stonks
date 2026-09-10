"""En qué fondo está el afiliado a cada edad, y con qué rentabilidad.

El fondo puede ser uno fijo -- salvo la salida obligatoria del A -- o una mezcla, si se
contrató un esquema de traspasos por edad, que avanza 20% al año.
"""
from __future__ import annotations

from .parametros import (EDAD_SALIDA_FONDO_A, HITOS, PASO_ANUAL, RENTABILIDAD_REAL, TRAMOS)


def _mezcla_a_edad(edad: float, sexo: str, contrato: str) -> dict[str, float]:
    """Fracción del saldo en cada fondo a esa edad, según el traspaso gradual.

    Devuelve {fondo: peso}. Antes del primer hito todo está en el fondo inicial;
    en cada hito el traspaso avanza 20% por año hasta completarse en cuatro.
    """
    hitos = HITOS[contrato][sexo]
    pesos = {hitos[0][1]: 1.0}
    for i in range(1, len(hitos)):
        edad_hito, destino = hitos[i]
        if edad < edad_hito:
            break
        avance = min(1.0, PASO_ANUAL * (1 + int(edad - edad_hito)))
        movido = {f: p * avance for f, p in pesos.items()}
        pesos = {f: p * (1 - avance) for f, p in pesos.items()}
        pesos[destino] = pesos.get(destino, 0.0) + sum(movido.values())
        pesos = {f: p for f, p in pesos.items() if p > 1e-9}
    return pesos


def fondo_por_defecto(edad: float, sexo: str) -> str:
    """El fondo que la ley asigna si el afiliado no elige."""
    t = TRAMOS[sexo]
    if edad <= t["b_hasta"]:
        return "B"
    if edad <= t["c_hasta"]:
        return "C"
    return "D"


def fondo_vigente(edad: float, fondo_elegido: str, sexo: str,
                  destino_salida_a: str = "B") -> str:
    """El fondo A no admite el saldo obligatorio desde los 56 (hombres) o 51 (mujeres).

    La ley obliga a salir, pero deja elegir cualquiera de los otros cuatro: el destino
    es decisión del afiliado, no un traspaso automático a un fondo determinado.
    El fondo B, en cambio, no tiene restricción de edad en ningún tramo.
    """
    if fondo_elegido == "A" and edad >= EDAD_SALIDA_FONDO_A[sexo]:
        return destino_salida_a
    return fondo_elegido


def rentabilidad_a_edad(edad: float, fondo_elegido: str, sexo: str,
                        trayectoria: str = "fijo",
                        destino_salida_a: str = "B") -> float:
    """Rentabilidad real esperada a esa edad, según la trayectoria elegida.

    'fijo'    -> te quedas en tu fondo, salvo la salida obligatoria del A.
    'basico'  -> esquema de traspasos por edad, contrato básico (termina en D).
    'ampliado'-> contrato ampliado (termina en E).
    """
    if trayectoria == "fijo":
        return RENTABILIDAD_REAL[fondo_vigente(edad, fondo_elegido, sexo, destino_salida_a)]

    pesos = _mezcla_a_edad(edad, sexo, trayectoria)
    return sum(RENTABILIDAD_REAL[f] * p for f, p in pesos.items())


def fondo_a_edad(edad: float, fondo_elegido: str, sexo: str,
                 trayectoria: str = "fijo",
                 destino_salida_a: str = "B") -> str:
    """Etiqueta legible del fondo (o mezcla) en que estarías a esa edad."""
    if trayectoria == "fijo":
        return fondo_vigente(edad, fondo_elegido, sexo, destino_salida_a)
    pesos = _mezcla_a_edad(edad, sexo, trayectoria)
    orden = sorted(pesos.items(), key=lambda kv: -kv[1])
    if len(orden) == 1 or orden[0][1] > 0.99:
        return orden[0][0]
    return " / ".join(f"{f} {round(p * 100)}%" for f, p in orden)
