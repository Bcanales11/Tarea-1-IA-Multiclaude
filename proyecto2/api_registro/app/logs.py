"""Logs estructurados: una línea JSON por evento a stdout.

Container Apps manda stdout a Log Analytics (tabla `ContainerAppConsoleLogs_CL`), donde se
filtra por `evento`. Nunca se escribe la x-api-key ni la URL de la base de datos.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

NOMBRE_LOGGER = "registro_api"


class FormatoJSON(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        dato = {
            "fecha": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "nivel": record.levelname,
            "logger": record.name,
            "evento": getattr(record, "evento", None),
            "mensaje": record.getMessage(),
        }
        datos = getattr(record, "datos", None)
        if datos:
            dato["datos"] = datos
        if record.exc_info:
            dato["excepcion"] = self.formatException(record.exc_info)
        return json.dumps(dato, ensure_ascii=False, default=str)


def configurar_logs(nivel: str = "INFO") -> logging.Logger:
    log = logging.getLogger(NOMBRE_LOGGER)
    log.setLevel(nivel)
    if not any(getattr(h, "_registro_api", False) for h in log.handlers):
        manejador = logging.StreamHandler(sys.stdout)
        manejador.setFormatter(FormatoJSON())
        manejador._registro_api = True  # type: ignore[attr-defined]
        log.addHandler(manejador)
    return log


def evento(log: logging.Logger, nivel: int, nombre: str, mensaje: str, **datos) -> None:
    log.log(nivel, mensaje, extra={"evento": nombre, "datos": datos})
