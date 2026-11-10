"""Registro de chequeos: herramientas del Agente de Registro y del Sub-agente de Reportes.

Contrato: INSTRUCCIONES_GRUPO.md §4.3 (API de Benjamín).
Dos backends (variable REGISTRO_BACKEND):
- "local": SQLite en proyecto2/agentes/datos_local/registro.db, con los mismos campos que la API.
- "api":   POST/GET {REGISTRO_API_URL}/chequeos con header x-api-key (la key viene de Key Vault).

El veredicto NO lo decide el modelo: lo calcula `veredicto_por_regla` (basta un sello para
NO_APTO, Decreto 13/2015 art. 110 bis). El LLM solo lo explica.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone

import httpx

from .. import config

log = logging.getLogger("kiosco.registro")

SELLOS_VALIDOS = {"AZUCARES", "SODIO", "CALORIAS", "GRASAS_SATURADAS"}
ORIGENES_VALIDOS = {"vision", "chat"}


def veredicto_por_regla(sellos: list[str]) -> str:
    """Regla fija del sistema: con uno o más sellos 'ALTO EN' el producto es NO_APTO."""
    return "NO_APTO" if sellos else "APTO"


def _normalizar_sellos(sellos: list[str]) -> list[str]:
    reemplazos = {"AZÚCARES": "AZUCARES", "CALORÍAS": "CALORIAS", "GRASAS SATURADAS": "GRASAS_SATURADAS"}
    salida = []
    for s in sellos or []:
        s = reemplazos.get(s.strip().upper(), s.strip().upper().replace(" ", "_"))
        if s not in SELLOS_VALIDOS:
            raise ValueError(f"Sello inválido: {s}. Válidos: {sorted(SELLOS_VALIDOS)}")
        if s not in salida:
            salida.append(s)
    return salida


# --- Backend local (SQLite) --------------------------------------------------------

def _conexion() -> sqlite3.Connection:
    config.CARPETA_DATOS_LOCAL.mkdir(exist_ok=True)
    con = sqlite3.connect(config.CARPETA_DATOS_LOCAL / "registro.db")
    con.execute("""CREATE TABLE IF NOT EXISTS chequeos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kiosco_id TEXT NOT NULL, producto TEXT NOT NULL,
        sku TEXT, sellos TEXT NOT NULL, veredicto TEXT NOT NULL, motivo TEXT, origen TEXT NOT NULL,
        fecha TEXT NOT NULL)""")
    return con


def _guardar_local(dato: dict) -> dict:
    fecha = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _conexion() as con:
        cur = con.execute(
            "INSERT INTO chequeos (kiosco_id, producto, sku, sellos, veredicto, motivo, origen, fecha) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (dato["kiosco_id"], dato["producto"], dato["sku"], json.dumps(dato["sellos"]),
             dato["veredicto"], dato["motivo"], dato["origen"], fecha))
        return {"id": cur.lastrowid, "fecha": fecha}


def _listar_local(kiosco_id: str, desde: str) -> list[dict]:
    with _conexion() as con:
        con.row_factory = sqlite3.Row
        filas = con.execute("SELECT * FROM chequeos WHERE kiosco_id = ? AND fecha >= ? ORDER BY fecha",
                            (kiosco_id, desde)).fetchall()
    return [dict(f, sellos=json.loads(f["sellos"])) for f in filas]


# --- Herramientas que ven los agentes ------------------------------------------------

def guardar_chequeo(producto: str, sellos: list[str], motivo: str, origen: str = "chat",
                    kiosco_id: str = "", sku: str = "") -> dict:
    """Guarda en la base de datos el chequeo de un producto. El veredicto (APTO / NO_APTO) lo
    calcula el sistema con la regla fija: con uno o más sellos es NO_APTO.

    Args:
        producto: nombre del producto. Ej: "Galletas X 120 g".
        sellos: lista de sellos 'ALTO EN' detectados, valores entre AZUCARES, SODIO, CALORIAS,
            GRASAS_SATURADAS. Lista vacía si no tiene sellos.
        motivo: explicación breve. Ej: "Art. 110 bis: basta un sello ALTO EN".
        origen: "vision" si viene de la cámara, "chat" si lo informó una persona.
        kiosco_id: identificador del kiosco. Si va vacío se usa el del sistema.
        sku: SKU del catálogo, si se conoce.
    """
    try:
        dato = {
            "kiosco_id": kiosco_id or config.KIOSCO_ID_DEFECTO,
            "producto": producto.strip(),
            "sku": sku.strip(),
            "sellos": _normalizar_sellos(sellos),
            "motivo": motivo.strip(),
            "origen": origen if origen in ORIGENES_VALIDOS else "chat",
        }
        dato["veredicto"] = veredicto_por_regla(dato["sellos"])
        if config.REGISTRO_BACKEND == "api":
            r = httpx.post(f"{config.REGISTRO_API_URL}/chequeos", json=dato,
                           headers={"x-api-key": config.REGISTRO_API_KEY}, timeout=10)
            r.raise_for_status()
            resp = r.json()
        else:
            resp = _guardar_local(dato)
        log.info("chequeo guardado id=%s veredicto=%s", resp.get("id"), dato["veredicto"])
        return {"estado": "guardado", "veredicto": dato["veredicto"], **resp}
    except Exception as e:
        log.error("error al guardar chequeo: %s: %s", type(e).__name__, e)
        return {"estado": "error", "detalle": f"{type(e).__name__}: {e}"}


def listar_chequeos(kiosco_id: str = "", desde: str = "") -> dict:
    """Lista los chequeos guardados de un kiosco desde una fecha, para reportes de auditoría.

    Args:
        kiosco_id: identificador del kiosco. Si va vacío se usa el del sistema.
        desde: fecha de inicio AAAA-MM-DD. Si va vacía, últimos 7 días.
    """
    kiosco_id = kiosco_id or config.KIOSCO_ID_DEFECTO
    desde = desde or (date.today() - timedelta(days=7)).isoformat()
    try:
        if config.REGISTRO_BACKEND == "api":
            r = httpx.get(f"{config.REGISTRO_API_URL}/chequeos", params={"kiosco_id": kiosco_id, "desde": desde},
                          headers={"x-api-key": config.REGISTRO_API_KEY}, timeout=10)
            r.raise_for_status()
            chequeos = r.json()
        else:
            chequeos = _listar_local(kiosco_id, desde)
        return {"estado": "ok", "kiosco_id": kiosco_id, "desde": desde, "total": len(chequeos), "chequeos": chequeos}
    except Exception as e:
        log.error("error al listar chequeos: %s: %s", type(e).__name__, e)
        return {"estado": "error", "detalle": f"{type(e).__name__}: {e}"}
