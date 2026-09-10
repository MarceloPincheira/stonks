"""Tipos del dominio, compartidos por el motor y por quien lo llama.

Los diccionarios grandes -- el escenario normalizado, el resultado de la proyección --
se anotan como `dict[str, Any]` a propósito: tienen decenas de claves heterogéneas y
un TypedDict de ese tamaño documenta menos de lo que estorba. Los registros chicos y
estables sí valen la pena, y van como TypedDict para que el editor avise si falta una
clave o sobra otra.
"""
from __future__ import annotations

from typing import Any, Callable, TypedDict


class Tramo(TypedDict):
    """Un tramo de aporte mensual: desde el mes `start_month` hasta `end_month`."""

    start_month: int
    end_month: int
    amount: float


class AporteExtraordinario(TypedDict):
    """Aporte puntual amarrado a un mes de calendario, escrito en pesos de hoy."""

    year: int
    month: int
    amount: float


class Rango(TypedDict):
    """Recorrido de una métrica bajo la banda de sensibilidad."""

    min: float | None
    max: float | None
    indefinido: bool


#: Lo que llega del frontend sin validar. Cualquier clave puede faltar o venir en texto.
Payload = dict[str, Any]

#: Escenario ya pasado por `normalize_input`: todas las claves presentes y verificadas.
Escenario = dict[str, Any]

#: Salida de `project`: mes a mes, agregados anuales, métricas y fase de retiro.
Resultado = dict[str, Any]

#: Perfil previsional tal como lo guarda y devuelve `db`.
Perfil = dict[str, Any]

#: Lleva un mes de proyección a su factor de inflación acumulada.
Deflactor = Callable[[int], float]
