"""API de registro de chequeos (contrato §4.3 de INSTRUCCIONES_GRUPO.md).

Endpoints:
- GET  /salud                          sin autenticación; estado de la app y de la BD.
- POST /chequeos                       guarda un chequeo -> 201 {"id", "fecha"}.
- GET  /chequeos?kiosco_id=&desde=     lista los chequeos de un kiosco desde una fecha.

Seguridad:
- Header `x-api-key`, comparado en tiempo constante (hmac.compare_digest). Se revisa en un
  middleware antes de leer el cuerpo: sin clave válida la respuesta es 401, nunca 422.
- Si la API no tiene clave configurada, rechaza todo con 503 (falla cerrada).
- Límite de tamaño del cuerpo (413) y de cada campo (422).
- Logs JSON a stdout; warning en cada 401 y 422.

Correr local:  uvicorn app.main:app --port 8000   (desde proyecto2/api_registro)
"""

from __future__ import annotations

import hmac
import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import date, datetime, time as hora, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .bd import ErrorBD, Repositorio, crear_repositorio, formatear_fecha
from .config import Config, cargar_config
from .logs import configurar_logs, evento
from .modelos import (PATRON_KIOSCO_ID, TIPO_ERROR_APTO_CON_SELLOS, ChequeoCreado, ChequeoEntrada,
                      ChequeoSalida)

RUTAS_PROTEGIDAS = ("/chequeos",)
VERSION = "1.0.0"


def _ip_cliente(request: Request) -> str:
    # Container Apps (Envoy) agrega X-Forwarded-For con la IP real del cliente al principio
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


def _parsear_desde(texto: str | None, zona: ZoneInfo) -> datetime | None:
    """`desde` = AAAA-MM-DD (inicio de ese día en la zona del colegio) o fecha-hora ISO 8601.
    Una fecha-hora sin zona también se interpreta en la zona del colegio."""
    if texto is None or texto.strip() == "":
        return None
    texto = texto.strip()
    try:
        if len(texto) == 10:
            return datetime.combine(date.fromisoformat(texto), hora.min, tzinfo=zona)
        valor = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        return valor if valor.tzinfo else valor.replace(tzinfo=zona)
    except ValueError:
        raise RequestValidationError([{
            "type": "fecha_invalida", "loc": ("query", "desde"), "input": texto[:40],
            "msg": "desde debe ser AAAA-MM-DD o una fecha-hora ISO 8601",
        }])


def crear_app(config: Config | None = None, reloj: Callable[[], datetime] | None = None) -> FastAPI:
    """Arma la app. `config` y `reloj` se inyectan en las pruebas."""
    config = config or cargar_config()
    reloj = reloj or (lambda: datetime.now(timezone.utc))
    log = configurar_logs(config.nivel_log)
    zona = ZoneInfo(config.zona_horaria)
    clave_esperada = config.api_key.encode("utf-8")

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        repo: Repositorio = crear_repositorio(config.database_url)
        app.state.repo = repo
        try:
            repo.inicializar()
            evento(log, logging.INFO, "inicio", "API de registro iniciada", backend=repo.backend,
                   version=VERSION)
        except ErrorBD as e:
            # Se reintenta en la primera petición; /salud lo informa mientras tanto
            evento(log, logging.ERROR, "bd_no_disponible", "no se pudo preparar la tabla al iniciar",
                   backend=repo.backend, error=str(e)[:300])
        if not clave_esperada:
            evento(log, logging.ERROR, "sin_api_key",
                   "REGISTRO_API_KEY no está definida: /chequeos responderá 503")
        yield
        repo.cerrar()

    app = FastAPI(
        title="API de registro — Kiosco Escolar Saludable",
        version=VERSION,
        lifespan=ciclo_de_vida,
        docs_url="/docs" if config.habilitar_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.habilitar_docs else None,
    )

    # --- Middleware: tamaño, autenticación y log de cada petición -------------------------
    @app.middleware("http")
    async def seguridad_y_logs(request: Request, siguiente):
        inicio = time.perf_counter()
        ruta = request.url.path
        ip = _ip_cliente(request)

        def responder(estado: int, detalle: str, **cabeceras) -> JSONResponse:
            return JSONResponse({"detail": detalle}, status_code=estado, headers=cabeceras or None)

        respuesta = None
        if ruta.startswith(RUTAS_PROTEGIDAS):
            # 1) Tamaño del cuerpo (antes de leerlo)
            if request.method in {"POST", "PUT", "PATCH"}:
                largo = request.headers.get("content-length")
                if largo is None:
                    respuesta = responder(411, "Falta Content-Length")
                elif not largo.isdigit() or int(largo) > config.max_bytes_cuerpo:
                    evento(log, logging.WARNING, "rechazo_413", "cuerpo demasiado grande",
                           ruta=ruta, ip=ip, bytes=largo[:20])
                    respuesta = responder(413, f"Cuerpo mayor a {config.max_bytes_cuerpo} bytes")
            # 2) API key en tiempo constante
            if respuesta is None:
                if not clave_esperada:
                    respuesta = responder(503, "API sin clave configurada")
                else:
                    recibida = request.headers.get("x-api-key", "")
                    if not hmac.compare_digest(recibida.encode("utf-8"), clave_esperada):
                        evento(log, logging.WARNING, "rechazo_401", "x-api-key ausente o inválida",
                               ruta=ruta, metodo=request.method, ip=ip,
                               motivo="ausente" if not recibida else "invalida")
                        respuesta = responder(401, "x-api-key ausente o inválida",
                                              **{"WWW-Authenticate": "ApiKey"})
        if respuesta is None:
            respuesta = await siguiente(request)

        if ruta != "/salud":  # las sondas de salud no ensucian los logs
            evento(log, logging.INFO, "peticion", f"{request.method} {ruta} {respuesta.status_code}",
                   metodo=request.method, ruta=ruta, estado=respuesta.status_code, ip=ip,
                   ms=round((time.perf_counter() - inicio) * 1000, 1))
        return respuesta

    # --- Errores -----------------------------------------------------------------
    @app.exception_handler(RequestValidationError)
    async def rechazo_422(request: Request, exc: RequestValidationError):
        errores = exc.errors()
        cuerpo = exc.body if isinstance(getattr(exc, "body", None), dict) else {}
        resumen = [{"loc": list(e.get("loc", ())), "tipo": e.get("type"), "msg": str(e.get("msg"))[:200]}
                   for e in errores]
        if any(e.get("type") == TIPO_ERROR_APTO_CON_SELLOS for e in errores):
            # Evidencia de auditoría: un APTO con sello es un error grave o una llamada manipulada
            evento(log, logging.WARNING, "rechazo_apto_con_sellos",
                   "chequeo APTO con sellos rechazado (no se recalcula el veredicto)",
                   ruta=request.url.path, ip=_ip_cliente(request),
                   kiosco_id=str(cuerpo.get("kiosco_id", ""))[:64],
                   producto=str(cuerpo.get("producto", ""))[:200],
                   sellos=cuerpo.get("sellos") if isinstance(cuerpo.get("sellos"), list) else None)
        else:
            evento(log, logging.WARNING, "rechazo_422", "petición rechazada por validación",
                   ruta=request.url.path, ip=_ip_cliente(request),
                   kiosco_id=str(cuerpo.get("kiosco_id", ""))[:64], errores=resumen)
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(ErrorBD)
    async def error_bd(request: Request, exc: ErrorBD):
        evento(log, logging.ERROR, "error_bd", "falló la base de datos", ruta=request.url.path,
               error=str(exc)[:300])
        return JSONResponse({"detail": "Base de datos no disponible"}, status_code=503)

    # --- Endpoints -----------------------------------------------------------------
    @app.get("/salud")
    def salud():
        repo: Repositorio = app.state.repo
        try:
            repo.ping()
            return {"estado": "ok", "bd": "ok", "backend": repo.backend, "version": VERSION}
        except ErrorBD:
            return JSONResponse({"estado": "degradado", "bd": "error", "backend": repo.backend,
                                 "version": VERSION}, status_code=503)

    @app.post("/chequeos", status_code=201, response_model=ChequeoCreado)
    def crear_chequeo(chequeo: ChequeoEntrada):
        fecha = reloj()
        nuevo_id = app.state.repo.insertar(chequeo.model_dump(), fecha)
        evento(log, logging.INFO, "chequeo_guardado", "chequeo guardado", id=nuevo_id,
               kiosco_id=chequeo.kiosco_id, veredicto=chequeo.veredicto, origen=chequeo.origen,
               n_sellos=len(chequeo.sellos))
        return ChequeoCreado(id=nuevo_id, fecha=formatear_fecha(fecha))

    @app.get("/chequeos", response_model=list[ChequeoSalida])
    def listar_chequeos(
        kiosco_id: str = Query(min_length=1, max_length=64, pattern=PATRON_KIOSCO_ID),
        desde: str | None = Query(default=None, max_length=40,
                                  description="AAAA-MM-DD (día en hora de Chile) o fecha-hora ISO 8601"),
        limite: int = Query(default=1000, ge=1, le=config.max_resultados),
    ):
        filas = app.state.repo.listar(kiosco_id, _parsear_desde(desde, zona), limite)
        return filas

    return app


app = crear_app()
