"""Historial local de escaneos (SQLite embebido, ver informe/arquitectura_costos.html §02).
Guarda cada veredicto para poder generar el resumen del día (ver api_resumen en server.py) —
le da al LLM una segunda utilidad real: redactar en lenguaje natural sobre datos propios de la
app, no solo responder preguntas sobre la ley."""
import sqlite3
from datetime import date, datetime
from pathlib import Path

RUTA_DB = Path(__file__).parent / "historial.db"


def _conectar():
    conn = sqlite3.connect(RUTA_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS escaneos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            apto INTEGER NOT NULL,
            nutrientes TEXT NOT NULL,
            motivo TEXT NOT NULL
        )
    """)
    return conn


def registrar_escaneo(apto, nutrientes, motivo):
    conn = _conectar()
    with conn:
        conn.execute(
            "INSERT INTO escaneos (fecha_hora, apto, nutrientes, motivo) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), int(apto), ",".join(nutrientes), motivo),
        )
    conn.close()


def resumen_de_hoy():
    hoy = date.today().isoformat()
    conn = _conectar()
    filas = conn.execute(
        "SELECT apto, nutrientes FROM escaneos WHERE fecha_hora LIKE ?", (hoy + "%",)
    ).fetchall()
    conn.close()

    total = len(filas)
    no_aptos = sum(1 for apto, _ in filas if not apto)
    conteo_nutrientes = {}
    for apto, nutrientes in filas:
        if apto:
            continue
        for n in (nutrientes or "").split(","):
            n = n.strip()
            if n:
                conteo_nutrientes[n] = conteo_nutrientes.get(n, 0) + 1

    return {
        "total": total,
        "aptos": total - no_aptos,
        "no_aptos": no_aptos,
        "por_nutriente": conteo_nutrientes,
    }
