"""Guardias de estilo: PEP 8 mecánico y cobertura de anotaciones PEP 484.

Van como pruebas y no como un linter aparte porque el proyecto no tiene dependencias:
así la regla se verifica con `make test` en cualquier máquina, sin instalar nada. Sólo
cubre lo que se puede comprobar sin ambigüedad; el criterio fino queda en la revisión.
"""
from __future__ import annotations

import ast
import configparser
import inspect
import pathlib
import typing
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent
PAQUETES = ("engine", "afp", "web")
SUELTOS = ("db.py", "inflation.py", "server.py", "test_stonks.py", "test_estilo.py")


def fuentes() -> list[pathlib.Path]:
    """Todos los .py del proyecto, sin entrar a directorios generados."""
    archivos = [RAIZ / n for n in SUELTOS]
    for paquete in PAQUETES:
        archivos += sorted((RAIZ / paquete).glob("*.py"))
    return [a for a in archivos if a.exists()]


def limite_de_linea() -> int:
    cfg = configparser.ConfigParser()
    cfg.read(RAIZ / "setup.cfg")
    return cfg.getint("pycodestyle", "max-line-length", fallback=99)


class TestPEP8(unittest.TestCase):
    """Reglas mecánicas: las que no admiten discusión y sí se rompen sin querer."""

    def test_ninguna_linea_pasa_el_limite(self):
        limite = limite_de_linea()
        largas = [f"{a.relative_to(RAIZ)}:{i}"
                  for a in fuentes()
                  for i, linea in enumerate(a.read_text(encoding="utf-8").splitlines(), 1)
                  if len(linea) > limite]
        self.assertEqual(largas, [], f"líneas sobre {limite} columnas")

    def test_sin_espacios_al_final_de_linea(self):
        sucias = [f"{a.relative_to(RAIZ)}:{i}"
                  for a in fuentes()
                  for i, linea in enumerate(a.read_text(encoding="utf-8").splitlines(), 1)
                  if linea != linea.rstrip()]
        self.assertEqual(sucias, [])

    def test_indentacion_con_espacios(self):
        con_tabs = [f"{a.relative_to(RAIZ)}:{i}"
                    for a in fuentes()
                    for i, linea in enumerate(a.read_text(encoding="utf-8").splitlines(), 1)
                    if linea.startswith("\t")]
        self.assertEqual(con_tabs, [])

    def test_archivo_termina_en_un_solo_salto(self):
        malos = [str(a.relative_to(RAIZ)) for a in fuentes()
                 if not a.read_text(encoding="utf-8").endswith("\n")
                 or a.read_text(encoding="utf-8").endswith("\n\n")]
        self.assertEqual(malos, [])

    def test_sin_mas_de_dos_lineas_en_blanco_seguidas(self):
        malos = []
        for a in fuentes():
            blancos = 0
            for i, linea in enumerate(a.read_text(encoding="utf-8").splitlines(), 1):
                blancos = blancos + 1 if not linea.strip() else 0
                if blancos > 2:
                    malos.append(f"{a.relative_to(RAIZ)}:{i}")
        self.assertEqual(malos, [])

    def test_todo_modulo_tiene_docstring(self):
        sin_doc = [str(a.relative_to(RAIZ)) for a in fuentes()
                   if not ast.get_docstring(ast.parse(a.read_text(encoding="utf-8")))]
        self.assertEqual(sin_doc, [])


class TestPEP484(unittest.TestCase):
    """Cobertura de anotaciones: que no se pierda al agregar código nuevo."""

    MODULOS = [
        "engine.validacion", "engine.acumulacion", "engine.retiro", "engine.sensibilidad",
        "afp.edad", "afp.tributario", "afp.pension", "afp.fondos", "afp.proyeccion",
        "db", "inflation", "server", "web.perfil",
    ]

    def _funciones(self):
        import importlib
        for nombre in self.MODULOS:
            mod = importlib.import_module(nombre)
            for atributo, obj in vars(mod).items():
                if inspect.isfunction(obj) and obj.__module__ == nombre:
                    yield f"{nombre}.{atributo}", obj

    def test_toda_funcion_declara_lo_que_devuelve(self):
        sin_retorno = [n for n, f in self._funciones()
                       if "return" not in f.__annotations__]
        self.assertEqual(sin_retorno, [])

    def test_todo_parametro_esta_anotado(self):
        sin_anotar = []
        for nombre, fn in self._funciones():
            firma = inspect.signature(fn)
            for p in firma.parameters.values():
                if p.kind in (p.VAR_KEYWORD, p.VAR_POSITIONAL) and p.annotation is p.empty:
                    continue  # *args/**kwargs de reenvío: anotarlos no aporta
                if p.annotation is p.empty:
                    sin_anotar.append(f"{nombre}({p.name})")
        self.assertEqual(sin_anotar, [])

    def test_las_anotaciones_resuelven(self):
        """`from __future__ import annotations` las deja como texto: hay que evaluarlas."""
        rotas = []
        for nombre, fn in self._funciones():
            try:
                typing.get_type_hints(fn)
            except Exception as exc:                      # noqa: BLE001
                rotas.append(f"{nombre}: {exc}")
        self.assertEqual(rotas, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
