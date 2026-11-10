"""Mide el consumo real de una consulta: latencia, tokens y llamadas al modelo y a las KB.

Se corre desde proyecto2/agentes (el .env se carga solo, no se imprime):

    PYTHONIOENCODING=utf-8 PYTHONPATH=. .venv/Scripts/python.exe pruebas/medir_tokens.py
    ... pruebas/medir_tokens.py --repeticiones 2 --salida pruebas/medicion_tokens.json
    ... pruebas/medir_tokens.py --concurrentes 10      # consultas en paralelo (prueba de carga chica)
    ... pruebas/medir_tokens.py --concurrentes 10 --herramientas-en-hilo   # mismo, con la mejora

Cómo cuenta:
- Tokens y llamadas al modelo: un CustomLogger de LiteLLM suma el campo `usage` de cada
  respuesta (así entran también los reintentos y el respaldo, si los hubo).
- Llamadas a las KB: se envuelve el POST /retrieve de `_buscar_foundry` (una llamada HTTP por
  búsqueda) y se guarda la `activity` que devuelve Foundry IQ (tokens de la planificación).
- Llamadas por agente: los eventos de ADK (`author` + `function_call`).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import Counter
from contextvars import ContextVar

import litellm
from google.adk.runners import InMemoryRunner
from google.genai import types
from litellm.integrations.custom_logger import CustomLogger

from kiosco_agentes import config
from kiosco_agentes.agent import root_agent
from kiosco_agentes.herramientas import kb

APP = "kiosco_agentes"
sys.stdout.reconfigure(encoding="utf-8")

CONSULTAS = [
    ("normativa-1", "normativa", "¿Cuál es el límite de sodio en un alimento sólido para no llevar sello ALTO EN?"),
    ("normativa-2", "normativa", "¿Se pueden publicitar productos con sello ALTO EN dentro de un kiosco escolar? ¿Qué dice la ley?"),
    ("catalogo", "catalogo", "¿Puedo vender el Chocolate Milka 125 g?"),
    ("alternativas", "alternativas", "Tengo unas galletas con sello ALTO EN en el kiosco. ¿Qué alternativas sin sello me sugieres?"),
    ("registro-camara", "registro", "La cámara del kiosco detectó un producto NO APTO. Sellos: AZUCARES. Regístralo con origen vision y explícalo en 2 frases."),
    ("resumen", "resumen", "Dame un resumen de los chequeos registrados del kiosco colegio-001."),
]

# Acumulador de la consulta en curso (ContextVar: sirve también con consultas en paralelo)
_acum: ContextVar[dict | None] = ContextVar("acum", default=None)


def _nuevo() -> dict:
    return {"llamadas_modelo": 0, "tokens_in": 0, "tokens_out": 0, "tokens_cache": 0,
            "kb": Counter(), "kb_ms": [], "kb_tokens_in": 0, "kb_tokens_out": 0, "kb_razonamiento": 0,
            "por_agente": Counter(), "herramientas": Counter(), "modelos": Counter()}


class MedidorUso(CustomLogger):
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        a = _acum.get()
        if a is None:
            return
        uso = getattr(response_obj, "usage", None)
        if uso is None and isinstance(response_obj, dict):
            uso = response_obj.get("usage")

        def g(k):
            return (uso.get(k) if isinstance(uso, dict) else getattr(uso, k, None)) or 0

        a["llamadas_modelo"] += 1
        a["tokens_in"] += g("prompt_tokens")
        a["tokens_out"] += g("completion_tokens")
        det = getattr(uso, "prompt_tokens_details", None)
        a["tokens_cache"] += (getattr(det, "cached_tokens", 0) or 0) if det else 0
        a["modelos"][str(kwargs.get("model"))] += 1


class _HttpxConMedicion:
    """Reemplaza `httpx` dentro de kb.py para leer la `activity` de Foundry IQ."""

    def __getattr__(self, nombre):
        import httpx
        return getattr(httpx, nombre)

    def post(self, url, *args, **kw):
        import httpx
        t0 = time.perf_counter()
        r = httpx.post(url, *args, **kw)
        a = _acum.get()
        if a is not None and "/retrieve" in url:
            nombre = url.split("/knowledgebases/")[1].split("/")[0]
            a["kb"][nombre] += 1
            a["kb_ms"].append(int((time.perf_counter() - t0) * 1000))
            try:
                for act in r.json().get("activity", []):
                    # modelQueryPlanning: tokens del modelo (se cobran en Azure OpenAI)
                    a["kb_tokens_in"] += act.get("inputTokens") or 0
                    a["kb_tokens_out"] += act.get("outputTokens") or 0
                    # agenticReasoning: tokens de razonamiento de Azure AI Search (otro medidor)
                    a["kb_razonamiento"] += act.get("reasoningTokens") or 0
            except Exception:
                pass
        return r


def herramientas_en_hilo() -> None:
    """Prueba de la mejora: ejecuta las herramientas síncronas (KB, registro) en un hilo para no
    bloquear el event loop. No toca el código de los agentes: solo reemplaza las funciones en memoria."""
    import functools
    import inspect

    def envolver(fn):
        @functools.wraps(fn)
        async def _en_hilo(*args, **kw):
            return await asyncio.to_thread(fn, *args, **kw)
        return _en_hilo

    def recorrer(agente):
        nuevas = []
        for t in agente.tools:
            if inspect.isfunction(t):
                nuevas.append(envolver(t))
            else:
                nuevas.append(t)
                sub = getattr(t, "agent", None)
                if sub is not None:
                    recorrer(sub)
        agente.tools = nuevas
    recorrer(root_agent)


async def medir(runner: InMemoryRunner, id_: str, tipo: str, texto: str) -> dict:
    a = _nuevo()
    _acum.set(a)
    sesion = await runner.session_service.create_session(app_name=APP, user_id="medicion")
    msg = types.Content(role="user", parts=[types.Part(text=f"[kiosco_id: colegio-001]\n{texto}")])
    inicio, respuesta, error = time.perf_counter(), "", None
    try:
        async for ev in runner.run_async(user_id="medicion", session_id=sesion.id, new_message=msg):
            if ev.content and ev.content.parts:
                for p in ev.content.parts:
                    if p.function_call:
                        a["herramientas"][p.function_call.name] += 1
                        a["por_agente"][ev.author] += 1
            if ev.is_final_response() and ev.content and ev.content.parts and ev.author == root_agent.name:
                respuesta = "".join(p.text or "" for p in ev.content.parts)
    except Exception as e:  # la medición no debe caerse por un fallo del modelo
        error = f"{type(e).__name__}: {str(e)[:200]}"
    ms = int((time.perf_counter() - inicio) * 1000)
    return {"id": id_, "tipo": tipo, "ms": ms, "llamadas_modelo": a["llamadas_modelo"],
            "tokens_in": a["tokens_in"], "tokens_out": a["tokens_out"], "tokens_cache": a["tokens_cache"],
            "llamadas_kb": dict(a["kb"]), "kb_ms": a["kb_ms"],
            "kb_tokens_in": a["kb_tokens_in"], "kb_tokens_out": a["kb_tokens_out"],
            "kb_razonamiento": a["kb_razonamiento"],
            "herramientas": dict(a["herramientas"]), "modelos": dict(a["modelos"]),
            "error": error, "respuesta": respuesta[:300]}


def tabla(filas: list[dict]) -> None:
    print(f"\n{'consulta':<18}{'ms':>8}{'llam.mod':>9}{'tok_in':>8}{'tok_out':>8}{'KBnorm':>7}{'KBcat':>6}{'KBtok':>7}{'KBrazon':>9}  herramientas")
    for f in filas:
        kbn = f["llamadas_kb"].get(config.KB_NORMATIVA, 0)
        kbc = f["llamadas_kb"].get(config.KB_CATALOGO, 0)
        print(f"{f['id']:<18}{f['ms']:>8}{f['llamadas_modelo']:>9}{f['tokens_in']:>8}{f['tokens_out']:>8}"
              f"{kbn:>7}{kbc:>6}{f['kb_tokens_in'] + f['kb_tokens_out']:>7}{f['kb_razonamiento']:>9}  {f['herramientas']}"
              + (f"  ERROR {f['error']}" if f["error"] else ""))
    ok = [f for f in filas if not f["error"]]
    if ok:
        print(f"\nPromedio: {statistics.mean(f['ms'] for f in ok):.0f} ms | "
              f"{statistics.mean(f['llamadas_modelo'] for f in ok):.1f} llamadas | "
              f"{statistics.mean(f['tokens_in'] for f in ok):.0f} tok in | "
              f"{statistics.mean(f['tokens_out'] for f in ok):.0f} tok out")


def memoria_pico_mib() -> float | None:
    """Pico de memoria (working set) de este proceso en MiB; solo Windows (sin psutil)."""
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        kernel32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return pmc.PeakWorkingSetSize / 1024 / 1024
    except Exception:
        return None


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--repeticiones", type=int, default=1)
    p.add_argument("--concurrentes", type=int, default=0, help="lanza N consultas a la vez (mezcla de los 6 tipos)")
    p.add_argument("--salida", default="pruebas/medicion_tokens.json")
    p.add_argument("--pausa", type=float, default=0)
    p.add_argument("--herramientas-en-hilo", action="store_true",
                   help="ejecuta las herramientas síncronas en un hilo (prueba de la mejora de concurrencia)")
    a = p.parse_args()

    litellm.callbacks = list(litellm.callbacks or []) + [MedidorUso()]
    kb.httpx = _HttpxConMedicion()
    if a.herramientas_en_hilo:
        herramientas_en_hilo()
    runner = InMemoryRunner(agent=root_agent, app_name=APP)
    print(f"Modelo principal: {config.MODELO_PRINCIPAL} | KB: {config.KB_BACKEND} | registro: {config.REGISTRO_BACKEND}")

    filas: list[dict] = []
    if a.concurrentes:
        lote = [CONSULTAS[i % len(CONSULTAS)] for i in range(a.concurrentes)]
        t0 = time.perf_counter()
        filas = list(await asyncio.gather(*(medir(runner, f"{c[0]}#{i}", c[1], c[2]) for i, c in enumerate(lote))))
        print(f"Pared total de {a.concurrentes} consultas simultáneas: {int((time.perf_counter() - t0) * 1000)} ms")
    else:
        for r in range(a.repeticiones):
            for c in CONSULTAS:
                fila = await medir(runner, c[0], c[1], c[2])
                fila["repeticion"] = r + 1
                filas.append(fila)
                print(f"  {c[0]} (rep {r + 1}): {fila['ms']} ms", flush=True)
                if a.pausa:
                    await asyncio.sleep(a.pausa)
    tabla(filas)
    mem = memoria_pico_mib()
    if mem:
        print(f"Memoria pico del proceso: {mem:.0f} MiB")
    with open(a.salida, "w", encoding="utf-8") as f:
        json.dump(filas, f, ensure_ascii=False, indent=2)
    print(f"\nGuardado en {a.salida}")


if __name__ == "__main__":
    asyncio.run(main())
