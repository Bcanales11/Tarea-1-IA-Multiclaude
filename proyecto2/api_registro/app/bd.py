"""Acceso a la base de datos: SQLite (local y pruebas) o PostgreSQL (Azure), según DATABASE_URL.

- `sqlite:///ruta/registro.db`  -> SQLite, `sellos` como texto JSON.
- `postgresql://usuario:clave@host:5432/registro?sslmode=require` -> PostgreSQL (psycopg 3 + pool),
  `sellos` como `text[]`. En Azure la URL completa vive en Key Vault (secreto
  `registro-database-url`) y llega a la app como variable de entorno.

La tabla se crea sola al arrancar (CREATE TABLE IF NOT EXISTS): la BD tiene acceso privado y
no se puede administrar desde fuera de la VNet. El esquema queda también en `esquema.sql`.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

COLUMNAS = ("id", "kiosco_id", "producto", "sku", "sellos", "veredicto", "motivo", "origen", "fecha")

ESQUEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS chequeos (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kiosco_id  text        NOT NULL,
    producto   text        NOT NULL,
    sku        text        NOT NULL DEFAULT '',
    sellos     text[]      NOT NULL DEFAULT '{}',
    veredicto  text        NOT NULL CHECK (veredicto IN ('APTO', 'NO_APTO')),
    motivo     text        NOT NULL DEFAULT '',
    origen     text        NOT NULL CHECK (origen IN ('vision', 'chat')),
    fecha      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chequeos_sellos_validos
        CHECK (sellos <@ ARRAY['AZUCARES', 'SODIO', 'CALORIAS', 'GRASAS_SATURADAS']::text[]),
    CONSTRAINT chequeos_apto_sin_sellos
        CHECK (veredicto = 'NO_APTO' OR cardinality(sellos) = 0)
);
CREATE INDEX IF NOT EXISTS chequeos_kiosco_fecha_idx ON chequeos (kiosco_id, fecha);
"""

ESQUEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS chequeos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kiosco_id  TEXT NOT NULL,
    producto   TEXT NOT NULL,
    sku        TEXT NOT NULL DEFAULT '',
    sellos     TEXT NOT NULL DEFAULT '[]',
    veredicto  TEXT NOT NULL CHECK (veredicto IN ('APTO', 'NO_APTO')),
    motivo     TEXT NOT NULL DEFAULT '',
    origen     TEXT NOT NULL CHECK (origen IN ('vision', 'chat')),
    fecha      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chequeos_kiosco_fecha_idx ON chequeos (kiosco_id, fecha);
"""


class ErrorBD(Exception):
    """La base de datos no respondió o falló la consulta."""


def formatear_fecha(fecha: datetime) -> str:
    """ISO 8601 en UTC con segundos, igual que el backend local de los agentes."""
    return fecha.astimezone(timezone.utc).isoformat(timespec="seconds")


class Repositorio(Protocol):
    backend: str

    def inicializar(self) -> None: ...
    def insertar(self, dato: dict, fecha: datetime) -> int: ...
    def listar(self, kiosco_id: str, desde: datetime | None, limite: int) -> list[dict]: ...
    def ping(self) -> None: ...
    def cerrar(self) -> None: ...


# --- SQLite -------------------------------------------------------------------------

def _fecha_sqlite(fecha: datetime) -> str:
    # Formato fijo con microsegundos: así la comparación de texto ordena igual que el tiempo
    return fecha.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


class RepositorioSqlite:
    backend = "sqlite"

    def __init__(self, ruta: str):
        self.ruta = ruta
        if ruta != ":memory:":
            Path(ruta).parent.mkdir(parents=True, exist_ok=True)

    def _conectar(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.ruta, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def inicializar(self) -> None:
        with self._conectar() as con:
            con.executescript(ESQUEMA_SQLITE)

    def insertar(self, dato: dict, fecha: datetime) -> int:
        try:
            with self._conectar() as con:
                cur = con.execute(
                    "INSERT INTO chequeos (kiosco_id, producto, sku, sellos, veredicto, motivo, origen, fecha) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (dato["kiosco_id"], dato["producto"], dato["sku"], json.dumps(dato["sellos"]),
                     dato["veredicto"], dato["motivo"], dato["origen"], _fecha_sqlite(fecha)),
                )
                return int(cur.lastrowid)
        except sqlite3.Error as e:
            raise ErrorBD(str(e)) from e

    def listar(self, kiosco_id: str, desde: datetime | None, limite: int) -> list[dict]:
        sql = f"SELECT {', '.join(COLUMNAS)} FROM chequeos WHERE kiosco_id = ?"
        parametros: list = [kiosco_id]
        if desde is not None:
            sql += " AND fecha >= ?"
            parametros.append(_fecha_sqlite(desde))
        sql += " ORDER BY fecha, id LIMIT ?"
        parametros.append(limite)
        try:
            with self._conectar() as con:
                filas = con.execute(sql, parametros).fetchall()
        except sqlite3.Error as e:
            raise ErrorBD(str(e)) from e
        return [
            {**dict(f), "sellos": json.loads(f["sellos"]),
             "fecha": formatear_fecha(datetime.fromisoformat(f["fecha"]))}
            for f in filas
        ]

    def ping(self) -> None:
        try:
            with self._conectar() as con:
                con.execute("SELECT 1")
        except sqlite3.Error as e:
            raise ErrorBD(str(e)) from e

    def cerrar(self) -> None:
        pass


# --- PostgreSQL ---------------------------------------------------------------------

class RepositorioPostgres:
    backend = "postgres"

    def __init__(self, url: str):
        # Import diferido: en local y en las pruebas no hace falta tener psycopg instalado
        from psycopg_pool import ConnectionPool

        # open=True sin esperar: si la BD todavía no responde, la app arranca igual y /salud lo informa
        self._pool = ConnectionPool(
            url, min_size=1, max_size=5, open=True, timeout=10,
            kwargs={"connect_timeout": 10, "application_name": "registro-api"},
        )
        self._tabla_lista = False
        self._candado = threading.Lock()

    def _asegurar_tabla(self) -> None:
        if self._tabla_lista:
            return
        with self._candado:
            if not self._tabla_lista:
                with self._pool.connection() as con:
                    con.execute(ESQUEMA_POSTGRES)
                self._tabla_lista = True

    def inicializar(self) -> None:
        try:
            self._asegurar_tabla()
        except Exception as e:
            raise ErrorBD(f"{type(e).__name__}: {e}") from e

    def insertar(self, dato: dict, fecha: datetime) -> int:
        try:
            self._asegurar_tabla()
            with self._pool.connection() as con:
                fila = con.execute(
                    "INSERT INTO chequeos (kiosco_id, producto, sku, sellos, veredicto, motivo, origen, fecha) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (dato["kiosco_id"], dato["producto"], dato["sku"], list(dato["sellos"]),
                     dato["veredicto"], dato["motivo"], dato["origen"], fecha),
                ).fetchone()
                return int(fila[0])
        except Exception as e:
            raise ErrorBD(f"{type(e).__name__}: {e}") from e

    def listar(self, kiosco_id: str, desde: datetime | None, limite: int) -> list[dict]:
        sql = f"SELECT {', '.join(COLUMNAS)} FROM chequeos WHERE kiosco_id = %s"
        parametros: list = [kiosco_id]
        if desde is not None:
            sql += " AND fecha >= %s"
            parametros.append(desde)
        sql += " ORDER BY fecha, id LIMIT %s"
        parametros.append(limite)
        try:
            self._asegurar_tabla()
            with self._pool.connection() as con:
                filas = con.execute(sql, parametros).fetchall()
        except Exception as e:
            raise ErrorBD(f"{type(e).__name__}: {e}") from e
        salida = []
        for f in filas:
            d = dict(zip(COLUMNAS, f))
            d["sellos"] = list(d["sellos"] or [])
            d["fecha"] = formatear_fecha(d["fecha"])
            salida.append(d)
        return salida

    def ping(self) -> None:
        try:
            with self._pool.connection(timeout=5) as con:
                con.execute("SELECT 1")
        except Exception as e:
            raise ErrorBD(f"{type(e).__name__}: {e}") from e

    def cerrar(self) -> None:
        self._pool.close()


def crear_repositorio(database_url: str) -> Repositorio:
    if database_url.startswith("sqlite:///"):
        return RepositorioSqlite(database_url.removeprefix("sqlite:///"))
    if database_url.startswith(("postgresql://", "postgres://")):
        return RepositorioPostgres(database_url)
    # No se muestra la URL: podría traer la contraseña
    raise ValueError("DATABASE_URL debe empezar con sqlite:/// o postgresql://")
