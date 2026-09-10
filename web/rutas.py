"""Rutas HTTP: API JSON sobre `http.server`, más los archivos de `static/`."""

from __future__ import annotations

import json
import os
import re
import sys
from http.server import SimpleHTTPRequestHandler
from typing import Any

import afp
import db
import engine
import inflation

from .documentos import BASE_DIR, DOC_RE, DOCS
from .perfil import con_perfil, normalizar_perfil

STATIC_DIR = os.path.join(BASE_DIR, "static")
SCENARIO_RE = re.compile(r"^/api/scenarios/(\d+)$")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

    def end_headers(self) -> None:
        # Sin esta cabecera el navegador aplica caché heurística y se queda
        # con el CSS/JS viejo sin revalidar.
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    # --- helpers -----------------------------------------------------
    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    # --- routing -----------------------------------------------------
    def do_GET(self) -> None:
        if self.path == "/api/scenarios":
            return self._json(db.list_scenarios())
        if self.path == "/api/profile":
            data = db.get_profile()
            if data["profile"]:
                try:
                    perfil = data["profile"]
                    data["afp"] = afp.proyectar({**perfil, "fondo": perfil["fondo"]})
                except (KeyError, ValueError):
                    data["afp"] = None
            return self._json(data)
        if self.path == "/api/afp/params":
            return self._json(
                {
                    "rentabilidad_real": afp.RENTABILIDAD_REAL,
                    "comisiones": afp.COMISIONES,
                    "cotizacion": afp.COTIZACION_OBLIGATORIA,
                    "salud": afp.SALUD,
                    "cesantia": afp.CESANTIA_INDEFINIDO,
                    "tope_uf": afp.TOPE_IMPONIBLE_UF,
                    "aporte_empleador_cuenta": afp.APORTE_EMPLEADOR_CUENTA,
                    "edad_pension": afp.EDAD_PENSION,
                    "tramos": afp.TRAMOS,
                    "generacionales_desde": afp.FONDOS_GENERACIONALES_DESDE,
                    "iusc": afp.IUSC,
                    "utm_referencia": afp.UTM_REFERENCIA,
                    "uf_referencia": afp.UF_REFERENCIA,
                }
            )
        if self.path == "/api/inflation":
            return self._json(
                {
                    "presets": inflation.presets(),
                    "series": inflation.IPC_CL,
                    "crises": inflation.CRISES,
                }
            )
        if self.path == "/api/docs":
            return self._json(
                [{"slug": k, "titulo": t, "detalle": d} for k, (_, t, d) in DOCS.items()]
            )
        m = DOC_RE.match(self.path)
        if m:
            entrada = DOCS.get(m.group(1))
            if entrada is None:
                return self._json({"error": "Documento no encontrado."}, 404)
            try:
                with open(os.path.join(BASE_DIR, entrada[0]), encoding="utf-8") as fh:
                    cuerpo = fh.read().encode("utf-8")
            except OSError:
                return self._json({"error": "El documento no está en el disco."}, 404)
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            return self.wfile.write(cuerpo)
        m = SCENARIO_RE.match(self.path)
        if m:
            scenario = db.get_scenario(int(m.group(1)))
            if scenario is None:
                return self._json({"error": "Escenario no encontrado."}, 404)
            return self._json(scenario)
        if self.path.startswith("/api/"):
            return self._json({"error": "Ruta no encontrada."}, 404)
        return super().do_GET()

    def do_POST(self) -> None:
        try:
            payload = self._body()
        except (ValueError, json.JSONDecodeError):
            return self._json({"error": "JSON inválido."}, 400)

        try:
            if self.path == "/api/profile":
                perfil = normalizar_perfil(payload)
                ranges = payload.get("ranges")
                lumps = payload.get("lumps")
                if ranges is not None or lumps is not None:
                    limpio = engine.normalize_input(
                        {"years": 1, "ranges": ranges or [], "lump_sums": lumps or []}
                    )
                    ranges = limpio["ranges"] if ranges is not None else None
                    lumps = limpio["lump_sums"] if lumps is not None else None
                data = db.save_profile(perfil, ranges, lumps)
                data["afp"] = afp.proyectar(data["profile"])
                return self._json(data)
            if self.path == "/api/afp/preview":
                # Proyecta el perfil SIN guardarlo, para que el modal se actualice
                # mientras se escribe (mismo rol que /api/calculate para escenarios).
                perfil = normalizar_perfil(payload)
                return self._json({"profile": perfil, "afp": afp.proyectar(perfil)})
            if self.path == "/api/calculate":
                data = engine.normalize_input(con_perfil(payload))
                result = engine.project(data)
                # La proyección es un escenario, no un pronóstico: viaja con el rango
                # que producen ±1 pp de retorno y ±1 pp de inflación para que la UI
                # no publique "se agota a los 71" como si fuera una medición.
                return self._json(
                    {
                        "input": data,
                        "result": result,
                        "sensitivity": engine.sensitivity(data, result),
                    }
                )
            if self.path == "/api/scenarios":
                data = engine.normalize_input(payload)
                return self._json(db.save_scenario(data), 201)
            m = SCENARIO_RE.match(self.path)
            if m:
                data = engine.normalize_input(payload)
                saved = db.save_scenario(data, int(m.group(1)))
                if saved is None:
                    return self._json({"error": "Escenario no encontrado."}, 404)
                return self._json(saved)
        except engine.ValidationError as exc:
            return self._json({"error": str(exc)}, 400)

        return self._json({"error": "Ruta no encontrada."}, 404)

    def do_PUT(self) -> None:
        return self.do_POST()

    def do_DELETE(self) -> None:
        m = SCENARIO_RE.match(self.path)
        if m:
            if db.delete_scenario(int(m.group(1))):
                return self._json({"ok": True})
            return self._json({"error": "Escenario no encontrado."}, 404)
        return self._json({"error": "Ruta no encontrada."}, 404)
