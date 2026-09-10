"""Capa de acceso a SQLite para los escenarios de inversión."""
from __future__ import annotations

from typing import Any, Iterable
import os
import sqlite3

from engine.tipos import AporteExtraordinario, Escenario, Perfil, Tramo
import afp
import engine

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stonks.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS scenario (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    annual_return REAL    NOT NULL,   -- retorno total anual %, usado por el modelo 'simple'
    years         INTEGER NOT NULL,   -- horizonte Z en años
    currency      TEXT    NOT NULL DEFAULT 'CLP',
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contribution_range (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id INTEGER NOT NULL REFERENCES scenario(id) ON DELETE CASCADE,
    start_month INTEGER NOT NULL,
    end_month   INTEGER NOT NULL,
    amount      REAL    NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_range_scenario ON contribution_range(scenario_id);

CREATE TABLE IF NOT EXISTS profile (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    edad                REAL    NOT NULL DEFAULT 30,
    nacimiento          TEXT    NOT NULL DEFAULT '1990-01-01',
    sexo                TEXT    NOT NULL DEFAULT 'hombre',
    inicio_mes          INTEGER NOT NULL DEFAULT 1,
    inicio_anio         INTEGER NOT NULL DEFAULT 2026,
    sueldo_bruto        REAL    NOT NULL DEFAULT 0,
    afp                 TEXT    NOT NULL DEFAULT 'Habitat',
    comision_afp        REAL    NOT NULL DEFAULT 1.27,
    fondo               TEXT    NOT NULL DEFAULT 'B',
    saldo_afp           REAL    NOT NULL DEFAULT 0,
    salud               TEXT    NOT NULL DEFAULT 'fonasa',
    salud_extra         REAL    NOT NULL DEFAULT 0,
    contrato_indefinido INTEGER NOT NULL DEFAULT 1,
    aporte_empleador    REAL    NOT NULL DEFAULT 0.1,
    uf                  REAL    NOT NULL DEFAULT 39500,
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- El plan de aporte vive en el perfil, no en el escenario: es el mismo plan de
-- ahorro sin importar en qué instrumento se invierta.
CREATE TABLE IF NOT EXISTS profile_range (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    start_month INTEGER NOT NULL,
    end_month   INTEGER NOT NULL,
    amount      REAL    NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

-- Aportes extraordinarios: van amarrados a un mes de calendario (heredar y vender algo,
-- un bono, una indemnización) y el monto se guarda en pesos de hoy.
CREATE TABLE IF NOT EXISTS profile_lump (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    year     INTEGER NOT NULL,
    month    INTEGER NOT NULL,
    amount   REAL    NOT NULL,
    label    TEXT    NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# Columnas agregadas después de la v1; se aplican con ALTER TABLE idempotente.
MIGRATIONS = [
    ("model", "TEXT NOT NULL DEFAULT 'simple'"),       # 'simple' | 'dividends'
    ("dividend_yield", "REAL NOT NULL DEFAULT 0"),      # % anual sobre el valor del portafolio
    ("appreciation", "REAL NOT NULL DEFAULT 0"),        # % anual de plusvalía de la cuota
    ("reinvest", "INTEGER NOT NULL DEFAULT 1"),         # 1 = reinvierte dividendos
    ("payout_months", "TEXT NOT NULL DEFAULT '3,6,9,12'"),
    ("inflation", "REAL NOT NULL DEFAULT 3.83"),      # media geométrica 2000-2025
    ("income_goal", "REAL NOT NULL DEFAULT 0"),        # meta mensual en pesos de hoy
    ("index_contributions", "INTEGER NOT NULL DEFAULT 0"),
    ("include_pension", "INTEGER NOT NULL DEFAULT 1"),   # descontar la pensión AFP de la meta
    ("retire_to_age", "REAL NOT NULL DEFAULT 0"),        # 0 = usar la expectativa de vida
    ("spend_mode", "TEXT NOT NULL DEFAULT 'goal'"),      # 'goal' | 'target_age'
    ("work_until_age", "REAL NOT NULL DEFAULT 0"),       # 0 = hasta la edad de pensión
    # % efectivo que se lleva el impuesto de cada reparto antes de reinvertirlo. 0 por
    # defecto porque depende del tramo de cada uno, pero se declara: reinvertir el
    # bruto sin decirlo inflaba el resultado a 30 años en decenas de puntos.
    ("dividend_tax", "REAL NOT NULL DEFAULT 0"),
]

# Igual que en scenario: columnas agregadas después de crear la tabla.
PROFILE_MIGRATIONS = [
    ("nacimiento", "TEXT NOT NULL DEFAULT '1990-01-01'"),
    # 'sueldo_bruto' quedó obsoleto: el sueldo se ingresa separado en su parte
    # imponible (la que cotiza) y las asignaciones no imponibles.
    ("sueldo_imponible", "REAL NOT NULL DEFAULT 0"),
    ("no_imponible", "REAL NOT NULL DEFAULT 0"),
    ("utm", "REAL NOT NULL DEFAULT 71721"),        # septiembre 2026; se edita en el perfil
    ("trayectoria", "TEXT NOT NULL DEFAULT 'fijo'"),
    ("destino_salida_a", "TEXT NOT NULL DEFAULT 'B'"),
]

SCENARIO_COLUMNS = (
    "name, annual_return, years, currency, model, dividend_yield, "
    "appreciation, reinvest, payout_months, inflation, income_goal, index_contributions, "
    "include_pension, retire_to_age, spend_mode, work_until_age, dividend_tax"
)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        for tabla, migraciones in (("scenario", MIGRATIONS), ("profile", PROFILE_MIGRATIONS)):
            existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({tabla})")}
            for column, ddl in migraciones:
                if column not in existing:
                    conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {column} {ddl}")
        # Lo que antes se guardaba como bruto era en la práctica el imponible. Corre
        # UNA sola vez y deja `sueldo_bruto` en 0: si no, la columna obsoleta quedaba
        # viva para siempre (save_profile no la escribe) y resucitaba en cada arranque
        # pisando un imponible que el usuario había puesto en 0 a propósito.
        migrada = conn.execute(
            "SELECT value FROM app_meta WHERE key = 'migrado_sueldo_bruto'").fetchone()
        if not migrada:
            conn.execute("UPDATE profile SET sueldo_imponible = sueldo_bruto "
                         "WHERE sueldo_imponible = 0 AND sueldo_bruto > 0")
            conn.execute("UPDATE profile SET sueldo_bruto = 0")
            conn.execute("INSERT INTO app_meta (key, value) VALUES "
                         "('migrado_sueldo_bruto', '1')")
    seed_examples()


def _row_to_scenario(row: sqlite3.Row) -> Escenario:
    scenario = dict(row)
    scenario["reinvest"] = bool(scenario["reinvest"])
    scenario["index_contributions"] = bool(scenario.get("index_contributions", 0))
    scenario["include_pension"] = bool(scenario.get("include_pension", 1))
    return scenario


def list_scenarios() -> list[Escenario]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, annual_return, years, currency, model, dividend_yield, "
            "appreciation, reinvest, payout_months, inflation, income_goal, "
            "index_contributions, updated_at "
            "FROM scenario ORDER BY updated_at DESC"
        ).fetchall()
        return [_row_to_scenario(r) for r in rows]


def get_scenario(scenario_id: int) -> Escenario | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM scenario WHERE id = ?", (scenario_id,)).fetchone()
        if row is None:
            return None
        scenario = _row_to_scenario(row)
        ranges = conn.execute(
            "SELECT start_month, end_month, amount FROM contribution_range "
            "WHERE scenario_id = ? ORDER BY position, start_month",
            (scenario_id,),
        ).fetchall()
        scenario["ranges"] = [dict(r) for r in ranges]
        return scenario


def _values(data: Escenario) -> tuple[Any, ...]:
    return (
        data["name"], data["annual_return"], data["years"], data["currency"],
        data["model"], data["dividend_yield"], data["appreciation"],
        1 if data["reinvest"] else 0, ",".join(str(m) for m in data["payout_months"]),
        data["inflation"], data["income_goal"], 1 if data["index_contributions"] else 0,
        1 if data["include_pension"] else 0, data["retire_to_age"], data["spend_mode"],
        data["work_until_age"], data["dividend_tax"],
    )


def _save_scenario(conn: sqlite3.Connection, data: Escenario,
                   scenario_id: int | None = None) -> int | None:
    """Inserta o actualiza dentro de una transacción ya abierta. Devuelve el id."""
    if scenario_id is None:
        placeholders = ", ".join("?" * len(SCENARIO_COLUMNS.split(",")))
        cur = conn.execute(
            f"INSERT INTO scenario ({SCENARIO_COLUMNS}) VALUES ({placeholders})",
            _values(data),
        )
        scenario_id = cur.lastrowid
    else:
        assignments = ", ".join(f"{c.strip()} = ?" for c in SCENARIO_COLUMNS.split(","))
        cur = conn.execute(
            f"UPDATE scenario SET {assignments}, updated_at = datetime('now') WHERE id = ?",
            _values(data) + (scenario_id,),
        )
        if cur.rowcount == 0:
            return None
        conn.execute("DELETE FROM contribution_range WHERE scenario_id = ?", (scenario_id,))

    conn.executemany(
        "INSERT INTO contribution_range (scenario_id, start_month, end_month, amount, position) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (scenario_id, r["start_month"], r["end_month"], r["amount"], i)
            for i, r in enumerate(data["ranges"])
        ],
    )
    return scenario_id


def save_scenario(data: Escenario, scenario_id: int | None = None) -> Escenario | None:
    """Inserta o actualiza un escenario junto con sus rangos."""
    with connect() as conn:
        scenario_id = _save_scenario(conn, data, scenario_id)
    return get_scenario(scenario_id) if scenario_id is not None else None


def delete_scenario(scenario_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM scenario WHERE id = ?", (scenario_id,))
        return cur.rowcount > 0


# --- escenarios de ejemplo ------------------------------------------------

CFINRENTAS = {
    "name": "CFINRENTAS · Independencia Rentas Inmobiliarias",
    "annual_return": 8.95,       # (1+2,3%)(1+6,5%)-1, recalculado por el motor
    "years": 30,
    "currency": "CLP",
    "model": "dividends",
    "dividend_yield": 6.5,
    # 2,3% es el promedio 2022-2024 que documenta el README, excluyendo el salto
    # atípico de 2025. Antes decía 3,0%: por encima de su propia justificación, y en
    # sentido contrario al criterio conservador que se aplicó al IPSA.
    "appreciation": 2.3,
    "reinvest": True,
    "payout_months": [3, 4, 6, 9, 12],
    "inflation": 3.83,
    "income_goal": 2000000,
    "index_contributions": True,
    "ranges": [
        {"start_month": 1, "end_month": 60, "amount": 100000},
        {"start_month": 61, "end_month": 120, "amount": 200000},
        {"start_month": 121, "end_month": 360, "amount": 300000},
    ],
}

# Plusvalía: media geométrica del S&P IPSA 2015-2024 (5,71%), según los cierres
# anuales de la Bolsa de Santiago. Se deja fuera 2025 (+56%, el mejor año en 32)
# porque un outlier de esa magnitud en una serie de once años distorsiona la media:
# incluyéndolo la plusvalía sube a 9,52% y el retorno total pasa de 9,2% a 13%.
# Yield: 3,5%, el piso del rango histórico de 3,5%-4,5% del índice (hoy ~3,2%).
# Dividendos concentrados en abril-mayo (definitivos tras las juntas) más
# provisorios en septiembre y diciembre, que es el calendario típico chileno.
IPSA = {
    "name": "IPSA · Bolsa de Santiago",
    "annual_return": 9.21,       # 3,5% dividendos + 5,71% plusvalía
    "years": 30,
    "currency": "CLP",
    "model": "dividends",
    "dividend_yield": 3.5,
    "appreciation": 5.71,
    "reinvest": True,
    "payout_months": [4, 5, 9, 12],
    "inflation": 3.83,
    "income_goal": 2000000,
    "index_contributions": True,
    "ranges": [
        {"start_month": 1, "end_month": 60, "amount": 100000},
        {"start_month": 61, "end_month": 120, "amount": 200000},
        {"start_month": 121, "end_month": 360, "amount": 300000},
    ],
}

SEEDS = [("seeded_cfinrentas", CFINRENTAS), ("seeded_ipsa", IPSA)]


def seed_examples() -> None:
    """Carga cada escenario de ejemplo una sola vez; si el usuario lo borra, no vuelve.

    Las semillas pasan por `engine.normalize_input` en vez de ir crudas: es la única
    fuente que garantiza todas las claves que espera `_values`, así que agregar una
    columna nueva al escenario no vuelve a romper el arranque.

    La marca y el escenario entran en la MISMA transacción. Antes la marca se
    confirmaba primero: si el insert fallaba, el ejemplo quedaba marcado como sembrado
    y se perdía para siempre.
    """
    for key, scenario in SEEDS:
        try:
            with connect() as conn:
                done = conn.execute(
                    "SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
                if done:
                    continue
                _save_scenario(conn, engine.normalize_input(scenario))
                conn.execute("INSERT INTO app_meta (key, value) VALUES (?, '1')", (key,))
        except Exception as exc:                      # noqa: BLE001
            # Un ejemplo malo no puede impedir que la app arranque: se avisa y se
            # sigue. Como la marca va en la misma transacción, el intento se
            # reintenta en el próximo arranque en vez de perderse en silencio.
            import sys
            print(f"  Aviso: no pude sembrar el escenario de ejemplo '{key}': {exc}",
                  file=sys.stderr)


# --- perfil ---------------------------------------------------------------

PROFILE_COLUMNS = (
    "edad, nacimiento, sexo, inicio_mes, inicio_anio, sueldo_imponible, no_imponible, "
    "afp, comision_afp, fondo, "
    "saldo_afp, salud, salud_extra, contrato_indefinido, aporte_empleador, uf, utm, "
    "trayectoria, destino_salida_a"
)


def get_profile() -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
        profile = dict(row) if row else None
        if profile:
            profile["contrato_indefinido"] = bool(profile["contrato_indefinido"])
            # La edad guardada envejece mal: un perfil de hace tres años sobrestimaba
            # la pensión en 18%. La fecha de nacimiento sí es un dato estable, así que
            # la edad se deriva de ella cada vez que se lee.
            if profile.get("nacimiento"):
                try:
                    profile["edad"] = afp.edad_desde(profile["nacimiento"])
                except (ValueError, IndexError, AttributeError):
                    pass
        ranges = conn.execute(
            "SELECT start_month, end_month, amount FROM profile_range "
            "ORDER BY position, start_month"
        ).fetchall()
        lumps = conn.execute(
            "SELECT year, month, amount, label FROM profile_lump ORDER BY year, month, position"
        ).fetchall()
    return {"profile": profile, "ranges": [dict(r) for r in ranges],
            "lumps": [dict(l) for l in lumps]}


def save_profile(data: Perfil, ranges: list[Tramo] | None = None,
                 lumps: list[AporteExtraordinario] | None = None) -> dict[str, Any]:
    cols = [c.strip() for c in PROFILE_COLUMNS.split(",")]
    values = [data[c] if c != "contrato_indefinido" else (1 if data[c] else 0) for c in cols]
    with connect() as conn:
        conn.execute(
            f"INSERT INTO profile (id, {PROFILE_COLUMNS}) "
            f"VALUES (1, {', '.join('?' * len(cols))}) "
            f"ON CONFLICT(id) DO UPDATE SET "
            + ", ".join(f"{c} = excluded.{c}" for c in cols)
            + ", updated_at = datetime('now')",
            values,
        )
        if ranges is not None:
            conn.execute("DELETE FROM profile_range")
            conn.executemany(
                "INSERT INTO profile_range (start_month, end_month, amount, position) "
                "VALUES (?, ?, ?, ?)",
                [(r["start_month"], r["end_month"], r["amount"], i) for i, r in enumerate(ranges)],
            )
        if lumps is not None:
            conn.execute("DELETE FROM profile_lump")
            conn.executemany(
                "INSERT INTO profile_lump (year, month, amount, label, position) "
                "VALUES (?, ?, ?, ?, ?)",
                [(l["year"], l["month"], l["amount"], l.get("label", ""), i)
                 for i, l in enumerate(lumps)],
            )
    return get_profile()
