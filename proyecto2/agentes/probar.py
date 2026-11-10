"""Prueba los agentes desde la terminal, sin servidor.

    python probar.py "¿Puedo vender el Chocolate de Leche Milka 125 g en el kiosco?"
    python probar.py --lote ../evaluacion/preguntas_v1.jsonl --n 5 --salida respuestas.jsonl

El modo --lote deja, por cada pregunta, la respuesta del sistema junto a la esperada
(formato útil para la evaluación de Foundry: query, response, ground_truth).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid

from google.adk.runners import InMemoryRunner
from google.genai import types

from kiosco_agentes.agent import root_agent

APP = "kiosco_agentes"
sys.stdout.reconfigure(encoding="utf-8")


async def preguntar(runner: InMemoryRunner, texto: str) -> tuple[str, int]:
    sesion = await runner.session_service.create_session(app_name=APP, user_id="prueba")
    mensaje = types.Content(role="user", parts=[types.Part(text=texto)])
    inicio, respuesta = time.perf_counter(), ""
    async for ev in runner.run_async(user_id="prueba", session_id=sesion.id, new_message=mensaje):
        if ev.is_final_response() and ev.content and ev.content.parts:
            respuesta = "".join(p.text or "" for p in ev.content.parts)
    return respuesta, int((time.perf_counter() - inicio) * 1000)


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("pregunta", nargs="?")
    p.add_argument("--lote", help="JSONL con query / ground_truth")
    p.add_argument("--n", type=int, default=0, help="solo las primeras N del lote")
    p.add_argument("--salida", default="respuestas.jsonl")
    p.add_argument("--pausa", type=float, default=0, help="segundos de espera entre preguntas (cupo por minuto)")
    a = p.parse_args()

    runner = InMemoryRunner(agent=root_agent, app_name=APP)
    if a.pregunta:
        r, ms = await preguntar(runner, a.pregunta)
        print(f"\n=== Respuesta ({ms} ms) ===\n{r}")
        return

    casos = [json.loads(l) for l in open(a.lote, encoding="utf-8")]
    casos = casos[: a.n] if a.n else casos
    corrida = uuid.uuid4().hex[:8]
    with open(a.salida, "w", encoding="utf-8") as f:
        for i, c in enumerate(casos, 1):
            r, ms = await preguntar(runner, c["query"])
            f.write(json.dumps({**c, "response": r, "ms": ms, "corrida": corrida}, ensure_ascii=False) + "\n")
            print(f"[{i}/{len(casos)}] {c['id']} {ms} ms")
            if a.pausa and i < len(casos):
                await asyncio.sleep(a.pausa)
    print(f"Listo: {a.salida} (corrida {corrida})")


if __name__ == "__main__":
    asyncio.run(main())
