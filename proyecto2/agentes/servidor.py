"""Servidor HTTP de los agentes (lo que corre en Google Cloud Run).

Endpoints:
- GET  /salud      chequeo para Cloud Run (sin clave)
- POST /consulta   lo usa la app Flask del kiosco. Header `x-api-key: <AGENTES_API_KEY>`.
    entrada:  {"mensaje": "...", "kiosco_id": "colegio-001", "sesion_id": "opcional"}
    salida:   {"respuesta": "...", "sesion_id": "...", "ms": 1234}
- Además, los endpoints estándar de ADK (/run, /run_sse, /apps/...) de get_fast_api_app.

Local:      uvicorn servidor:app --port 8080
Cloud Run:  ver README.md (Dockerfile).
"""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel

from kiosco_agentes import config, logs
from kiosco_agentes.agent import root_agent

APP = "kiosco_agentes"
CLAVE = os.getenv("AGENTES_API_KEY", "")

app = get_fast_api_app(agents_dir=str(Path(__file__).parent), web=False)
_runner = InMemoryRunner(agent=root_agent, app_name=APP)

_RUTAS_LIBRES = {"/salud"}


@app.middleware("http")
async def exigir_clave(request: Request, call_next):
    """Toda ruta salvo /salud exige x-api-key, incluidas las que agrega ADK (/run, /run_sse,
    /apps/...). Sin esto, si el servicio se abre al público cualquiera podría usar los agentes
    y gastar tokens (detectado el 10 nov)."""
    if request.url.path not in _RUTAS_LIBRES:
        clave = request.headers.get("x-api-key", "")
        if not CLAVE or not secrets.compare_digest(clave, CLAVE):
            logs.evento("acceso_rechazado", ruta=request.url.path)
            return JSONResponse(status_code=401, content={"detail": "clave inválida"})
    return await call_next(request)


class Consulta(BaseModel):
    mensaje: str
    kiosco_id: str = ""
    sesion_id: str | None = None


@app.get("/salud")
def salud():
    return {"estado": "ok", "modelo_principal": config.MODELO_PRINCIPAL, "kb": config.KB_BACKEND,
            "registro": config.REGISTRO_BACKEND}


@app.post("/consulta")
async def consulta(c: Consulta, x_api_key: str = Header(default="")):
    if not CLAVE or not secrets.compare_digest(x_api_key, CLAVE):
        raise HTTPException(status_code=401, detail="clave inválida")
    usuario = c.kiosco_id or config.KIOSCO_ID_DEFECTO
    sesion = None
    if c.sesion_id:
        sesion = await _runner.session_service.get_session(app_name=APP, user_id=usuario, session_id=c.sesion_id)
    if sesion is None:
        sesion = await _runner.session_service.create_session(app_name=APP, user_id=usuario)

    texto = f"[kiosco_id: {usuario}]\n{c.mensaje}"
    mensaje = types.Content(role="user", parts=[types.Part(text=texto)])
    inicio, respuesta = time.perf_counter(), ""
    async for ev in _runner.run_async(user_id=usuario, session_id=sesion.id, new_message=mensaje):
        if ev.is_final_response() and ev.content and ev.content.parts:
            respuesta = "".join(p.text or "" for p in ev.content.parts)
    ms = int((time.perf_counter() - inicio) * 1000)
    logs.evento("consulta", kiosco_id=usuario, sesion=sesion.id, ms=ms)
    return {"respuesta": respuesta, "sesion_id": sesion.id, "ms": ms}
