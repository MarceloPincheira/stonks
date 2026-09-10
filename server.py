#!/usr/bin/env python3
"""Punto de entrada del servidor. La app corre con la stdlib: `http.server` + `sqlite3`.

Las rutas viven en el paquete `web/`; aquí queda sólo cómo se levanta.
"""

from __future__ import annotations

import os
from http.server import HTTPServer

import db
from web import Handler


def puerto_libre(preferido: int) -> int:
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


def main() -> None:
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
