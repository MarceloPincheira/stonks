"""Capa web: rutas HTTP, integración perfil-escenario y documentación servida."""
from .rutas import Handler
from .perfil import con_perfil, normalizar_perfil
from .documentos import DOCS

__all__ = ["Handler", "con_perfil", "normalizar_perfil", "DOCS"]
