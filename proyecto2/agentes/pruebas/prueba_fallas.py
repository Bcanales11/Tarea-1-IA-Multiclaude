"""Prueba de fallas con evidencia (requisitos: logs de agente/modelo que no responde, reintento y
respaldo [Magíster], herramienta que falla).

No toca el código de producción: cada escenario corre en un proceso hijo con variables de entorno
distintas (config.py las lee al importarse; python-dotenv NO pisa las que ya existen) y se
captura el log JSON que emiten los agentes. El resultado queda en pruebas/evidencia/escenario_N.log
(una línea JSON por evento). Antes de guardar se verifica que no aparezca ninguna clave.

    python pruebas/prueba_fallas.py              # los 4 escenarios
    python pruebas/prueba_fallas.py 1 3          # solo algunos

Escenarios (1 consulta corta cada uno):
  1. El modelo principal no responde (servidor que acepta la conexión y nunca contesta) ->
     timeout -> reintento -> respaldo a Gemini.
  2. Principal Y respaldo caídos (endpoint inexistente + clave de Gemini inválida) ->
     respuesta controlada (modelo_error), el proceso no se cae.
  3. La herramienta de registro falla (API de registro inexistente) -> herramienta_error y el
     agente no afirma que guardó.
  4. Igual que el 1, pero con un respaldo SIMULADO (servidor local compatible con OpenAI que
     responde) -> demuestra la cadena completa: timeout, reintento, modelo_respaldo y respuesta
     del respaldo. Existe porque el plan gratuito de Gemini (20 consultas/día) puede estar sin
     cupo y el escenario 1 entonces termina en modelo_error: ese es un resultado real y queda
     documentado tal cual en su log.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
AGENTES = AQUI.parent
EVIDENCIA = AQUI / "evidencia"

# Variables que contienen claves: nunca se imprimen ni se guardan.
VARIABLES_SECRETAS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "AZURE_API_KEY", "FOUNDRY_SEARCH_API_KEY", "REGISTRO_API_KEY",
                      "AGENTES_API_KEY")
PATRONES_CLAVE = [re.compile(p) for p in (r"AIza[0-9A-Za-z_\-]{20,}", r"[?&]key=[^\s&\"']+",
                                          r"sk-[A-Za-z0-9]{20,}", r"api[-_]key['\"]?\s*[:=]\s*['\"][^'\"]{12,}")]

# El orquestador solo, sin delegar: una llamada al modelo y poco gasto.
PREGUNTA_CORTA = "Hola, ¿qué puedes hacer? Responde en una sola frase."
PREGUNTA_REGISTRO = ("Registra este chequeo con origen chat: producto 'Galletas de prueba 100 g', "
                     "sellos: SODIO. Dime el id del registro si se guardó.")


def escenarios(puerto_agujero: int, puerto_respaldo: int) -> dict[int, dict]:
    return {
        1: {
            "titulo": "Modelo principal no responde: timeout, reintento y respaldo a Gemini",
            "pregunta": PREGUNTA_CORTA,
            # Un servidor local que acepta la conexión y nunca contesta simula un modelo colgado.
            # Todos los agentes usan el principal (MODELO_ESPECIALISTAS vacío); el respaldo es el
            # Gemini real del .env.
            "env": {"MODELO_PRINCIPAL": "azure/modelo-que-no-responde",
                    "MODELO_ESPECIALISTAS": "",
                    "AZURE_API_BASE": f"http://127.0.0.1:{puerto_agujero}",
                    "AZURE_API_KEY": "clave-falsa-de-prueba", "AZURE_API_VERSION": "v1",
                    "TIMEOUT_MODELO_S": "3", "REINTENTOS_MODELO": "1"},
        },
        2: {
            "titulo": "Principal y respaldo caídos: respuesta controlada sin que el proceso se caiga",
            "pregunta": PREGUNTA_CORTA,
            # Principal: puerto 9 (nadie escucha, conexión rechazada). Respaldo: Gemini con una
            # clave inválida (responde error de autenticación, sin gastar tokens).
            "env": {"MODELO_PRINCIPAL": "azure/modelo-caido", "MODELO_ESPECIALISTAS": "",
                    "AZURE_API_BASE": "http://127.0.0.1:9",
                    "AZURE_API_KEY": "clave-falsa-de-prueba", "AZURE_API_VERSION": "v1",
                    "GEMINI_API_KEY": "clave-invalida-de-prueba", "GOOGLE_API_KEY": "clave-invalida-de-prueba",
                    "TIMEOUT_MODELO_S": "5", "REINTENTOS_MODELO": "1"},
        },
        3: {
            "titulo": "Herramienta de registro falla: herramienta_error y el agente no dice que guardó",
            "pregunta": PREGUNTA_REGISTRO,
            # Modelo real según el .env; solo se rompe el backend de registro (API inexistente).
            "env": {"REGISTRO_BACKEND": "api", "REGISTRO_API_URL": "http://127.0.0.1:9",
                    "REGISTRO_API_KEY": "clave-falsa-de-prueba"},
        },
        4: {
            "titulo": "Principal no responde y el respaldo (simulado) sí: timeout, reintento y modelo_respaldo",
            "pregunta": PREGUNTA_CORTA,
            "env": {"MODELO_PRINCIPAL": "azure/modelo-que-no-responde", "MODELO_ESPECIALISTAS": "",
                    "AZURE_API_BASE": f"http://127.0.0.1:{puerto_agujero}",
                    "AZURE_API_KEY": "clave-falsa-de-prueba", "AZURE_API_VERSION": "v1",
                    "MODELO_RESPALDO": "openai/respaldo-simulado",
                    "OPENAI_API_BASE": f"http://127.0.0.1:{puerto_respaldo}", "OPENAI_API_KEY": "clave-falsa-de-prueba",
                    "TIMEOUT_MODELO_S": "3", "REINTENTOS_MODELO": "1"},
        },
    }


# --- Proceso hijo: corre UNA consulta con los agentes reales ---------------------------------

async def _hijo(pregunta: str) -> None:
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from kiosco_agentes.agent import root_agent  # importa DESPUÉS de que el entorno ya está fijado

    runner = InMemoryRunner(agent=root_agent, app_name="kiosco_agentes")
    sesion = await runner.session_service.create_session(app_name="kiosco_agentes", user_id="prueba")
    mensaje = types.Content(role="user", parts=[types.Part(text=pregunta)])
    inicio, respuesta, error = time.perf_counter(), "", None
    try:
        async for ev in runner.run_async(user_id="prueba", session_id=sesion.id, new_message=mensaje):
            if ev.is_final_response() and ev.content and ev.content.parts:
                respuesta = "".join(p.text or "" for p in ev.content.parts)
    except Exception as e:  # noqa: BLE001 - lo que escape de los agentes se documenta, no se oculta
        error = f"{type(e).__name__}: {str(e)[:300]}"
    print(json.dumps({"evento": "prueba_respuesta_final", "ms": int((time.perf_counter() - inicio) * 1000),
                      "respuesta": respuesta, "excepcion_escapada": error}, ensure_ascii=False), flush=True)


# --- Proceso padre -----------------------------------------------------------------------------

def _agujero_negro() -> tuple[socket.socket, int]:
    """Servidor TCP que acepta conexiones y nunca responde (simula un modelo colgado)."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(16)
    conexiones: list[socket.socket] = []

    def aceptar() -> None:
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            conexiones.append(c)  # se queda abierta, sin leer ni responder

    threading.Thread(target=aceptar, daemon=True).start()
    return srv, srv.getsockname()[1]


def _respaldo_simulado() -> tuple[object, int]:
    """Servidor local compatible con la API de OpenAI que responde siempre lo mismo (respaldo simulado)."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Manejador(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            largo = int(self.headers.get("content-length") or 0)
            self.rfile.read(largo)
            cuerpo = json.dumps({
                "id": "sim-1", "object": "chat.completion", "created": int(time.time()), "model": "respaldo-simulado",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {
                    "role": "assistant",
                    "content": "[respaldo simulado] Puedo ayudarte con la normativa, el catálogo y el registro de chequeos."}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, *args):  # sin ruido en consola
            pass

    srv = HTTPServer(("127.0.0.1", 0), Manejador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _claves_conocidas() -> list[str]:
    """Valores de las claves reales (del .env y del entorno) para verificar que no se filtren."""
    valores: set[str] = set()
    try:
        from dotenv import dotenv_values
        for k, v in dotenv_values(AGENTES / ".env").items():
            if k in VARIABLES_SECRETAS and v and len(v) >= 8:
                valores.add(v)
    except Exception:  # noqa: BLE001
        pass
    for k in VARIABLES_SECRETAS:
        v = os.environ.get(k, "")
        if len(v) >= 8:
            valores.add(v)
    return sorted(valores)


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _correr(numero: int, esc: dict, claves: list[str]) -> bool:
    ts_inicio = _ahora()
    print(f"\n=== Escenario {numero}: {esc['titulo']} ===", flush=True)
    env = dict(os.environ, **esc["env"], PYTHONIOENCODING="utf-8", PYTHONPATH=str(AGENTES))
    inicio = time.perf_counter()
    try:
        p = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--hijo", esc["pregunta"]],
                           cwd=AGENTES, env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=300)
        salida, cod = p.stdout, p.returncode
    except subprocess.TimeoutExpired as e:
        salida, cod = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), -1

    # Solo se guardan las líneas JSON de nuestros logs (se descartan avisos de librerías).
    lineas = []
    for l in salida.splitlines():
        l = l.strip()
        if not l.startswith("{"):
            continue
        try:
            d = json.loads(l)
        except json.JSONDecodeError:
            continue
        if str(d.get("logger", "")).startswith("kiosco") or d.get("evento") == "prueba_respuesta_final":
            lineas.append(l)

    # Variables de entorno sobrescritas (solo nombres y valores no secretos).
    sobrescritas = {k: ("<oculta>" if k in VARIABLES_SECRETAS else v) for k, v in esc["env"].items()}
    cabecera = json.dumps({"ts": ts_inicio, "evento": "prueba_inicio", "escenario": numero,
                           "titulo": esc["titulo"], "pregunta": esc["pregunta"],
                           "entorno_sobrescrito": sobrescritas}, ensure_ascii=False)
    cierre = json.dumps({"ts": _ahora(), "evento": "prueba_fin", "escenario": numero,
                         "codigo_salida_proceso": cod, "segundos": round(time.perf_counter() - inicio, 1),
                         "eventos_registrados": len(lineas)}, ensure_ascii=False)
    texto = "\n".join([cabecera, *lineas, cierre]) + "\n"

    # Verificación de claves antes de guardar.
    for c in claves:
        if c in texto:
            print("ABORTADO: apareció una clave en el log; no se guarda.")
            return False
    for pat in PATRONES_CLAVE:
        if pat.search(texto):
            print(f"ABORTADO: el patrón {pat.pattern!r} coincide en el log; no se guarda.")
            return False

    EVIDENCIA.mkdir(exist_ok=True)
    ruta = EVIDENCIA / f"escenario_{numero}.log"
    ruta.write_text(texto, encoding="utf-8")

    eventos: dict[str, int] = {}
    final = {}
    for l in lineas:
        d = json.loads(l)
        eventos[d.get("evento", d.get("logger", "?"))] = eventos.get(d.get("evento", d.get("logger", "?")), 0) + 1
        if d.get("evento") == "prueba_respuesta_final":
            final = d
    print(f"Guardado: {ruta}")
    print("Eventos:", json.dumps(eventos, ensure_ascii=False))
    print("Respuesta final:", (final.get("respuesta") or "<vacía>")[:300].replace("\n", " "))
    print("Excepción escapada de los agentes:", final.get("excepcion_escapada") or "ninguna")
    return True


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--hijo":
        sys.stdout.reconfigure(encoding="utf-8")
        asyncio.run(_hijo(sys.argv[2]))
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("numeros", nargs="*", type=int, help="escenarios a correr (por defecto 1 2 3 4)")
    a = ap.parse_args()

    srv, puerto = _agujero_negro()
    srv_respaldo, puerto_respaldo = _respaldo_simulado()
    todos = escenarios(puerto, puerto_respaldo)
    claves = _claves_conocidas()
    ok = True
    try:
        for n in a.numeros or sorted(todos):
            ok = _correr(n, todos[n], claves) and ok
    finally:
        srv.close()
        srv_respaldo.shutdown()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
