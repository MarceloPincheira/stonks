#!/usr/bin/env python3
"""Servidor HTTP mínimo (stdlib) para la calculadora de inversión."""
import json
import os
import re
import sys
from datetime import date
from http.server import HTTPServer, SimpleHTTPRequestHandler

import db
import engine
import inflation
import afp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
SCENARIO_RE = re.compile(r"^/api/scenarios/(\d+)$")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def end_headers(self):
        # Sin esta cabecera el navegador aplica caché heurística y se queda
        # con el CSS/JS viejo sin revalidar.
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    # --- helpers -----------------------------------------------------
    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    # --- routing -----------------------------------------------------
    def do_GET(self):
        if self.path == "/api/scenarios":
            return self._json(db.list_scenarios())
        if self.path == "/api/profile":
            data = db.get_profile()
            if data["profile"]:
                try:
                    data["afp"] = afp.proyectar({**data["profile"], "fondo": data["profile"]["fondo"]})
                except (KeyError, ValueError):
                    data["afp"] = None
            return self._json(data)
        if self.path == "/api/afp/params":
            return self._json({
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
            })
        if self.path == "/api/inflation":
            return self._json({"presets": inflation.presets(), "series": inflation.IPC_CL,
                               "crises": inflation.CRISES})
        m = SCENARIO_RE.match(self.path)
        if m:
            scenario = db.get_scenario(int(m.group(1)))
            if scenario is None:
                return self._json({"error": "Escenario no encontrado."}, 404)
            return self._json(scenario)
        if self.path.startswith("/api/"):
            return self._json({"error": "Ruta no encontrada."}, 404)
        return super().do_GET()

    def do_POST(self):
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
                        {"years": 1, "ranges": ranges or [], "lump_sums": lumps or []})
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
                return self._json({"input": data, "result": engine.project(data)})
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

    def do_PUT(self):
        return self.do_POST()

    def do_DELETE(self):
        m = SCENARIO_RE.match(self.path)
        if m:
            if db.delete_scenario(int(m.group(1))):
                return self._json({"ok": True})
            return self._json({"error": "Escenario no encontrado."}, 404)
        return self._json({"error": "Ruta no encontrada."}, 404)


def con_perfil(payload):
    """Agrega al payload lo que sale del perfil: cuándo parte la inversión y la pensión.

    La fecha de inicio hace falta para ubicar los aportes extraordinarios, que se
    escriben como mes de calendario y no como número de mes de la proyección.

    La pensión no se guarda en el escenario: sale del perfil, así que cambiar de AFP o
    de fondo la actualiza en todos los escenarios a la vez. El escenario sólo recuerda
    si hay que considerarla.
    """
    datos = db.get_profile()
    perfil = datos.get("profile")
    if not perfil:
        return payload
    payload = {**payload,
               "start_year": perfil["inicio_anio"], "start_month": perfil["inicio_mes"]}
    try:
        proyeccion = afp.proyectar(perfil, trabajo_hasta=payload.get("work_until_age") or None)
    except (KeyError, ValueError):
        return payload

    # La serie de la AFP arranca hoy y la inversión en inicio_mes/inicio_anio: hay que
    # alinearlas antes de mandarlas al motor, que sólo entiende meses de proyección.
    hoy = date.today()
    desfase = (perfil["inicio_anio"] - hoy.year) * 12 + (perfil["inicio_mes"] - hoy.month)
    serie = proyeccion["serie_mensual"]
    alineada = []
    for i in range(len(serie)):
        j = desfase + i
        if j < 0:
            continue
        alineada.append(serie[j] if j < len(serie) else 0.0)
    edad_inicio = perfil["edad"] + max(0, desfase) / 12

    # Mes de la proyección en que se cumple la edad de pensión. La inversión parte en
    # inicio_mes/inicio_anio, que no tiene por qué coincidir con el cumpleaños.
    y, m, _ = (int(x) for x in str(perfil["nacimiento"]).split("-")[:3])
    anio_pension = y + afp.EDAD_PENSION[perfil["sexo"]]
    desde = ((anio_pension - perfil["inicio_anio"]) * 12
             + (m - perfil["inicio_mes"]) + 1)
    # Mes de la proyección en que se deja de trabajar: ahí se cortan las cotizaciones
    # y también los aportes al fondo, que salen del mismo sueldo.
    fin_trabajo = proyeccion["trabajo_hasta"]
    hasta_mes = int(round((fin_trabajo - edad_inicio) * 12))

    return {**payload,
            "pension_monthly": proyeccion["pension_mensual"],
            "pension_start_month": max(1, desde),
            "start_age": round(edad_inicio, 2),
            "life_age": proyeccion["edad_final"],
            "work_until_age": fin_trabajo,
            "work_until_month": max(0, hasta_mes),
            "afp_monthly": alineada,
            "afp_summary": {k: proyeccion[k] for k in (
                "saldo_actual", "saldo_al_jubilar", "pension_mensual", "edad_pension",
                "fondo_inicial", "fondo_final", "topado", "tope_imponible", "descuentos",
                "trabajo_hasta", "meses_cotizando", "cnu", "expectativa_vida")}}


def normalizar_perfil(payload):
    """Valida el perfil; los campos numéricos llegan como texto desde el formulario."""
    def num(key, default=0.0, minimo=None, maximo=None):
        try:
            v = float(payload.get(key, default) or default)
        except (TypeError, ValueError):
            raise engine.ValidationError(f"El campo '{key}' debe ser numérico.")
        if minimo is not None and v < minimo:
            raise engine.ValidationError(f"El campo '{key}' no puede ser menor que {minimo}.")
        if maximo is not None and v > maximo:
            raise engine.ValidationError(f"El campo '{key}' no puede ser mayor que {maximo}.")
        return v

    sexo = payload.get("sexo") or "hombre"
    if sexo not in afp.EDAD_PENSION:
        raise engine.ValidationError("Sexo no reconocido para los tramos legales.")
    fondo = (payload.get("fondo") or "B").upper()
    if fondo not in afp.RENTABILIDAD_REAL:
        raise engine.ValidationError("El fondo debe ser A, B, C, D o E.")
    trayectoria = payload.get("trayectoria") or "fijo"
    if trayectoria not in ("fijo", "basico", "ampliado"):
        raise engine.ValidationError("Trayectoria de fondos no reconocida.")
    destino_salida_a = (payload.get("destino_salida_a") or "B").upper()
    if destino_salida_a not in ("B", "C", "D", "E"):
        raise engine.ValidationError("Al salir del fondo A el destino debe ser B, C, D o E.")

    nacimiento = (payload.get("nacimiento") or "").strip()
    try:
        edad = afp.edad_desde(nacimiento)
    except (ValueError, IndexError, AttributeError):
        raise engine.ValidationError("Ingresa una fecha de nacimiento válida.")
    if not 15 <= edad <= 100:
        raise engine.ValidationError("La edad derivada de esa fecha está fuera de rango (15 a 100).")
    if edad >= afp.EDAD_PENSION[sexo]:
        raise engine.ValidationError(
            f"La edad ya alcanzó la de pensión ({afp.EDAD_PENSION[sexo]}): no hay años por proyectar."
        )
    return {
        "edad": edad,
        "nacimiento": nacimiento,
        "sexo": sexo,
        "inicio_mes": int(num("inicio_mes", 1, 1, 12)),
        "inicio_anio": int(num("inicio_anio", 2026, 1900, 2200)),
        "sueldo_imponible": num("sueldo_imponible", num("sueldo_bruto", 0, 0), 0),
        "no_imponible": num("no_imponible", 0, 0),
        "afp": (payload.get("afp") or "Habitat")[:40],
        "comision_afp": num("comision_afp", 1.27, 0, 10),
        "fondo": fondo,
        "saldo_afp": num("saldo_afp", 0, 0),
        "salud": (payload.get("salud") or "fonasa")[:20],
        "salud_extra": num("salud_extra", 0, 0),
        "contrato_indefinido": bool(payload.get("contrato_indefinido", True)),
        "aporte_empleador": num("aporte_empleador", afp.APORTE_EMPLEADOR_CUENTA, 0, 20),
        "uf": num("uf", afp.UF_REFERENCIA, 1),
        "utm": num("utm", afp.UTM_REFERENCIA, 1),
        "trayectoria": trayectoria,
        "destino_salida_a": destino_salida_a,
    }


def puerto_libre(preferido):
    """El puerto pedido si está libre; si no, cualquiera que el sistema tenga a mano.

    Sondear y después enlazar deja una carrera teórica entre medio, pero en desarrollo
    local no compite nadie por el puerto. Sirve para que `make init` no se caiga cuando
    quedó un servidor viejo escuchando.
    """
    import socket

    for candidato in (preferido, 0):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", candidato))
                return probe.getsockname()[1]
            except OSError:
                continue
    raise SystemExit("No hay puertos disponibles.")


def main():
    port = int(os.environ.get("PORT", 8420))
    db.init()
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Stonks corriendo en http://127.0.0.1:{port}  (base: {db.DB_PATH})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nChao.")


if __name__ == "__main__":
    main()
