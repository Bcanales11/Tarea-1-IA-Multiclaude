"""Permite importar `app` al correr pytest desde proyecto2/api_registro."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
