"""Capa web: rutas HTTP, integración perfil-escenario y documentación servida."""
from .documentos import DOCS
from .perfil import con_perfil, normalizar_perfil
from .rutas import Handler

__all__ = ["Handler", "con_perfil", "normalizar_perfil", "DOCS"]
