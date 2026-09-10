"""Lo que las herramientas de formato no pueden comprobar.

El reparto de trabajo es deliberado. **ruff** cubre el estilo estático -- largo de línea,
espacios sobrantes, imports muertos, nombres sin definir, cobertura de anotaciones (ANN) --
y **black** e **isort** lo imponen antes de cada commit. Repetir aquí esas mismas reglas
sería tener dos sistemas discutiendo sobre lo mismo.

Queda una comprobación que ningún analizador estático hace: que las anotaciones
**resuelvan en tiempo de ejecución**. Con `from __future__ import annotations` son sólo
texto, y ruff verifica que el nombre exista pero no que `typing.get_type_hints` logre
evaluarlo -- que es lo que necesita cualquiera que quiera introspeccionar las firmas.
"""

from __future__ import annotations

import importlib
import inspect
import typing
import unittest
from typing import ClassVar


class TestAnotaciones(unittest.TestCase):
    """PEP 484 más allá de la sintaxis: que los tipos se puedan evaluar de verdad."""

    MODULOS: ClassVar[list[str]] = [
        "engine.validacion",
        "engine.acumulacion",
        "engine.retiro",
        "engine.sensibilidad",
        "engine.tipos",
        "afp.edad",
        "afp.tributario",
        "afp.pension",
        "afp.fondos",
        "afp.proyeccion",
        "db",
        "inflation",
        "server",
        "web.perfil",
        "web.rutas",
    ]

    def _invocables(self):
        """Funciones y métodos definidos en los módulos del proyecto, no importados."""
        for nombre in self.MODULOS:
            modulo = importlib.import_module(nombre)
            for atributo, obj in vars(modulo).items():
                if inspect.isfunction(obj) and obj.__module__ == nombre:
                    yield f"{nombre}.{atributo}", obj
                elif inspect.isclass(obj) and obj.__module__ == nombre:
                    for metodo, fn in vars(obj).items():
                        if inspect.isfunction(fn):
                            yield f"{nombre}.{atributo}.{metodo}", fn

    def test_las_anotaciones_resuelven_en_ejecucion(self):
        rotas = []
        for nombre, fn in self._invocables():
            try:
                typing.get_type_hints(fn)
            except Exception as exc:  # interesa cualquier fallo, sea del tipo que sea
                rotas.append(f"{nombre}: {exc}")
        self.assertEqual(rotas, [], "anotaciones que no se pueden evaluar")

    def test_hay_anotaciones_que_evaluar(self):
        """Guarda contra el falso verde: si el recorrido no encuentra nada, no prueba nada."""
        self.assertGreater(len(list(self._invocables())), 40)


if __name__ == "__main__":
    unittest.main(verbosity=2)
