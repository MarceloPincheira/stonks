# Stonks -- atajos de desarrollo. Sin dependencias: sólo Python 3 de la stdlib.
#
#   make test            pruebas del modelo y de estilo (PEP 8 / PEP 484)
#   make init            levanta todo en el puerto por defecto (o el primero libre)
#   make init PORT=9000  fija otro puerto de partida
#   make stop            mata el servidor que esté escuchando en PORT
#   make restart         stop + init, para tomar cambios en los .py

PORT ?= 8420
URL  := http://127.0.0.1:$(PORT)

.PHONY: init run db stop restart check help test

## init: prepara la base y arranca el servidor
init: check db run

## check: la app corre con la stdlib, pero necesita un Python moderno
check:
	@python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' \
	  || { echo "Necesitas Python 3.9 o superior (tienes $$(python3 -V 2>&1))."; exit 1; }

## test: pruebas del modelo y guardias de estilo (no tocan stonks.db)
test:
	@python3 -m unittest discover -p 'test_*.py' -v

## db: crea la base y aplica las migraciones pendientes
db:
	@python3 -c 'import db; db.init(); print("Base lista:", db.DB_PATH)'

## run: arranca el servidor y dice dónde quedó escuchando
##      si el puerto pedido está ocupado, toma el primero libre que haya
run:
	@puerto=$$(python3 -c 'import server; print(server.puerto_libre($(PORT)))'); \
	echo ""; \
	if [ "$$puerto" != "$(PORT)" ]; then \
	  echo "  El puerto $(PORT) está ocupado (¿un Stonks viejo? make stop)."; \
	  echo "  Uso el $$puerto en su lugar."; \
	  echo ""; \
	fi; \
	echo "  Stonks corriendo en  http://127.0.0.1:$$puerto"; \
	echo "  Ctrl+C para parar."; \
	echo ""; \
	PORT=$$puerto python3 server.py

## stop: mata el servidor que esté escuchando en PORT
stop:
	@pid=$$(lsof -nP -tiTCP:$(PORT) -sTCP:LISTEN 2>/dev/null); \
	if [ -n "$$pid" ]; then kill $$pid && echo "Servidor en $(PORT) detenido."; \
	else echo "No hay nada escuchando en $(PORT)."; fi

## restart: Python mantiene los módulos en memoria, así que tocar un .py pide reinicio
restart: stop
	@sleep 1
	@$(MAKE) --no-print-directory init PORT=$(PORT)

## help: lista los comandos
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  make /'
