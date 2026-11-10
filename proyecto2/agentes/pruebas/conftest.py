"""Configuración común de los tests: rutas de importación (agentes y app del kiosco)."""
import sys
from pathlib import Path

AGENTES = Path(__file__).resolve().parent.parent          # proyecto2/agentes
APP_KIOSCO = AGENTES.parent / "app_kiosco"                 # proyecto2/app_kiosco

for ruta in (AGENTES, APP_KIOSCO):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))
