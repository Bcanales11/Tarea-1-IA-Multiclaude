"""Corre el golden set varias veces contra el sistema multi-agente y arma la evidencia del informe.

    python correr_golden_set.py --limite 3 --corridas 2 --modo local --golden preguntas_v1.jsonl   # prueba corta
    python correr_golden_set.py                                                                  # 3 corridas completas

Por cada corrida n deja en la carpeta de salida:
    respuestas_corrida{n}.jsonl   id, query, ground_truth, kb, categoria, dificultad, respuesta, latencia_s, modelos, error
    juez_corrida{n}.json          lo anterior + correcta (true/false) + motivo del juez
    eventos_corrida{n}.jsonl      avisos y errores de los agentes (reintentos, respaldo, fallos): evidencia de logs
y al final resumen.md y resumen.json.

Notas:
- Cada pregunta va en una sesión nueva (sin memoria entre preguntas).
- La variación entre corridas viene solo de la no determinación del modelo; no se agrega aleatoriedad.
- Juez: prompt en prompt_juez.md, mismo modelo de Foundry (MODELO_PRINCIPAL), temperatura 0.
- Un caso con error o que excede --timeout cuenta como incorrecto y queda registrado con el motivo.
- Con --reanudar no se repiten los casos ya respondidos (ni ya calificados) de la carpeta de salida.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import statistics
import subprocess
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
AGENTES = AQUI.parent / "agentes"
sys.path.insert(0, str(AGENTES))
sys.stdout.reconfigure(encoding="utf-8")

APP = "kiosco_agentes"
MENSAJE_FALLO_MODELO = "El servicio de IA no respondió a tiempo"  # texto de logs.error_modelo
MAX_PORCENTAJE = 95.0


# --------------------------------------------------------------------------- utilidades
def leer_jsonl(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    out = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            try:
                out.append(json.loads(linea))
            except json.JSONDecodeError:
                pass  # línea cortada por una interrupción
    return out


def agregar_jsonl(ruta: Path, dato: dict) -> None:
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(json.dumps(dato, ensure_ascii=False) + "\n")


def ultimo_por_id(registros: list[dict]) -> dict[str, dict]:
    return {r["id"]: r for r in registros}  # si un id se repitió (reintento), vale el último


def percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    v = sorted(valores)
    k = (len(v) - 1) * p
    i = int(k)
    return v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * (k - i)


def pct(a: int, b: int) -> float:
    return round(100 * a / b, 1) if b else 0.0


# --------------------------------------------------------------------------- clientes del sistema
class ClienteLocal:
    """Agentes en proceso (misma lógica que servidor.py /consulta, sin HTTP)."""

    def __init__(self, archivo_eventos_ref: dict) -> None:
        from google.adk.runners import InMemoryRunner
        from google.genai import types

        from kiosco_agentes import config, logs
        from kiosco_agentes.agent import root_agent

        self.types, self.config = types, config
        self.runner = InMemoryRunner(agent=root_agent, app_name=APP)
        logs.configurar()
        log = logging.getLogger("kiosco")
        for h in list(log.handlers):  # la consola queda limpia; los avisos se guardan en eventos_corridaN.jsonl
            log.removeHandler(h)
        log.addHandler(_ManejadorEventos(archivo_eventos_ref))
        base = lambda m: str(m).split("/", 1)[-1]  # noqa: E731
        self.propios = {base(config.MODELO_PRINCIPAL), base(config.MODELO_ESPECIALISTAS or config.MODELO_PRINCIPAL)}
        self.respaldo = base(config.MODELO_RESPALDO)

    async def consultar(self, pregunta: str) -> dict:
        usuario = self.config.KIOSCO_ID_DEFECTO
        sesion = await self.runner.session_service.create_session(app_name=APP, user_id=usuario)  # sesión nueva
        texto = f"[kiosco_id: {usuario}]\n{pregunta}"
        mensaje = self.types.Content(role="user", parts=[self.types.Part(text=texto)])
        respuesta, modelos = "", Counter()
        async for ev in self.runner.run_async(user_id=usuario, session_id=sesion.id, new_message=mensaje):
            mv = getattr(ev, "model_version", None)
            if mv:
                modelos[str(mv)] += 1
            if ev.is_final_response() and ev.content and ev.content.parts:
                respuesta = "".join(p.text or "" for p in ev.content.parts)
        base = lambda m: str(m).split("/", 1)[-1]  # noqa: E731
        usa_respaldo = any(base(m).startswith(self.respaldo) and self.respaldo not in self.propios for m in modelos)
        return {"respuesta": respuesta, "modelos": dict(modelos), "usa_respaldo": usa_respaldo}

    def respaldo_global(self) -> int:
        return _ManejadorEventos.conteo["modelo_respaldo"]


class _ManejadorEventos(logging.Handler):
    """Guarda en la carpeta de la corrida los eventos de nivel WARNING o superior (reintentos, respaldo, errores)."""

    conteo: Counter = Counter()

    def __init__(self, ref: dict) -> None:
        super().__init__(level=logging.WARNING)
        self.ref = ref

    def emit(self, r: logging.LogRecord) -> None:
        datos = getattr(r, "datos", None) or {"mensaje": r.getMessage()}
        _ManejadorEventos.conteo[datos.get("evento", "")] += 1
        ruta = self.ref.get("ruta")
        if ruta:
            agregar_jsonl(ruta, {"ts": datetime.now().isoformat(timespec="seconds"), "severity": r.levelname, **datos})


class ClienteHttp:
    """Servicio desplegado (Cloud Run): POST /consulta con x-api-key y, si es privado, ID token de Google."""

    def __init__(self) -> None:
        import httpx

        self.url = os.getenv("AGENTES_URL", "").rstrip("/")
        self.clave = os.getenv("AGENTES_API_KEY", "")
        if not self.url or not self.clave:
            sys.exit("Falta AGENTES_URL o AGENTES_API_KEY (en proyecto2/agentes/.env o en el entorno).")
        self.http = httpx.AsyncClient(timeout=None)
        self._token, self._token_hasta = "", 0.0

    def _id_token(self) -> str:
        if self._token and time.time() < self._token_hasta:
            return self._token
        token = ""
        try:
            import google.auth.transport.requests as gr
            from google.oauth2 import id_token

            token = id_token.fetch_id_token(gr.Request(), self.url)
        except Exception:
            try:
                token = subprocess.run("gcloud auth print-identity-token", capture_output=True, text=True,
                                       shell=True, timeout=60).stdout.strip()
            except Exception:
                token = ""
        self._token, self._token_hasta = token, time.time() + 2400  # los ID token duran 1 h
        return token

    async def consultar(self, pregunta: str) -> dict:
        cab = {"x-api-key": self.clave}
        token = await asyncio.to_thread(self._id_token)
        if token:
            cab["Authorization"] = f"Bearer {token}"
        # sin sesion_id: el servidor crea una sesión nueva por consulta
        r = await self.http.post(f"{self.url}/consulta", json={"mensaje": pregunta}, headers=cab)
        if r.status_code in (401, 403) and not token:
            raise RuntimeError(f"HTTP {r.status_code}: revisa AGENTES_API_KEY o el acceso al servicio (token de Google).")
        r.raise_for_status()
        d = r.json()
        return {"respuesta": d.get("respuesta", ""), "modelos": {}, "usa_respaldo": False}

    def respaldo_global(self) -> int:
        return 0


# --------------------------------------------------------------------------- juez
def cargar_prompt_juez() -> tuple[str, str]:
    txt = (AQUI / "prompt_juez.md").read_text(encoding="utf-8")
    m = re.search(r"### SISTEMA\s*\n(.*?)\n### USUARIO\s*\n(.*)\Z", txt, re.S)
    if not m:
        sys.exit("prompt_juez.md no tiene los bloques '### SISTEMA' y '### USUARIO'.")
    return m.group(1).strip(), m.group(2).strip()


async def juzgar(caso: dict, respuesta: str, sistema: str, plantilla: str, config) -> tuple[bool | None, str]:
    import litellm

    usuario = (plantilla.replace("{kb}", str(caso.get("kb", "")))
               .replace("{query}", caso["query"])
               .replace("{ground_truth}", caso["ground_truth"])
               .replace("{respuesta}", respuesta))
    ultimo = ""
    for intento in range(3):
        try:
            r = await litellm.acompletion(
                model=config.MODELO_PRINCIPAL, temperature=0, drop_params=True, timeout=config.TIMEOUT_MODELO_S * 3,
                messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
            )
            texto = r.choices[0].message.content or ""
            m = re.search(r"\{.*\}", texto, re.S)
            d = json.loads(m.group(0)) if m else {}
            if isinstance(d.get("correcta"), bool):
                return d["correcta"], str(d.get("motivo", ""))[:400]
            ultimo = f"respuesta del juez sin formato: {texto[:120]}"
        except Exception as e:  # noqa: BLE001
            ultimo = f"{type(e).__name__}: {str(e)[:150]}"
        await asyncio.sleep(2 * (intento + 1))
    return None, f"el juez no pudo calificar ({ultimo})"


# --------------------------------------------------------------------------- una corrida
async def correr_corrida(n: int, casos: list[dict], cliente, a, salida: Path, sistema: str, plantilla: str, config,
                         ref_eventos: dict) -> list[dict]:
    f_resp = salida / f"respuestas_corrida{n}.jsonl"
    f_juez = salida / f"juez_corrida{n}.jsonl"  # avance; al final se escribe juez_corrida{n}.json
    ref_eventos["ruta"] = salida / f"eventos_corrida{n}.jsonl"
    if not a.reanudar:
        for f in (f_resp, f_juez, ref_eventos["ruta"]):
            f.unlink(missing_ok=True)

    respondidos = {i: r for i, r in ultimo_por_id(leer_jsonl(f_resp)).items() if not r.get("error")}
    juzgados = ultimo_por_id(leer_jsonl(f_juez))
    sem = asyncio.Semaphore(a.concurrencia)
    hechos = [0]
    t0 = time.perf_counter()
    respaldo_antes = cliente.respaldo_global()

    async def uno(caso: dict) -> None:
        cid = caso["id"]
        if cid in respondidos:
            reg = respondidos[cid]
        else:
            async with sem:
                ini = time.perf_counter()
                error, datos = None, {"respuesta": "", "modelos": {}, "usa_respaldo": False}
                try:
                    datos = await asyncio.wait_for(cliente.consultar(caso["query"]), timeout=a.timeout)
                except asyncio.TimeoutError:
                    error = f"timeout: más de {a.timeout:.0f} s sin respuesta"
                except Exception as e:  # noqa: BLE001
                    error = f"{type(e).__name__}: {str(e)[:250]}"
                lat = round(time.perf_counter() - ini, 2)
            if not error and not datos["respuesta"].strip():
                error = "respuesta vacía"
            if not error and MENSAJE_FALLO_MODELO in datos["respuesta"]:
                error = "falló el modelo principal y el de respaldo (mensaje controlado del sistema)"
            reg = {k: caso.get(k) for k in ("id", "query", "ground_truth", "kb", "categoria", "dificultad", "origen") if k in caso}
            reg.update(respuesta=datos["respuesta"], latencia_s=lat, modelos=datos["modelos"],
                       usa_respaldo=datos["usa_respaldo"], error=error)
            agregar_jsonl(f_resp, reg)
            respondidos[cid] = reg

        if cid not in juzgados:
            if reg.get("error"):
                correcta, motivo = False, f"incorrecta por error del sistema: {reg['error']}"
            else:
                correcta, motivo = await juzgar(caso, reg["respuesta"], sistema, plantilla, config)
                if correcta is None:  # el juez falló: queda sin calificar para poder reanudar
                    hechos[0] += 1
                    print(f"  corrida {n}: [{hechos[0]}/{len(casos)}] {cid} SIN CALIFICAR ({motivo})")
                    return
            juzgados[cid] = {**reg, "correcta": correcta, "motivo": motivo}
            agregar_jsonl(f_juez, juzgados[cid])
        hechos[0] += 1
        estado = "OK " if juzgados[cid]["correcta"] else "MAL"
        print(f"  corrida {n}: [{hechos[0]}/{len(casos)}] {cid} {estado} {reg['latencia_s']} s"
              + (f"  ERROR: {reg['error']}" if reg.get("error") else ""))

    await asyncio.gather(*(uno(c) for c in casos))
    final = [juzgados[c["id"]] for c in casos if c["id"] in juzgados]
    (salida / f"juez_corrida{n}.json").write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
    dur = time.perf_counter() - t0
    ok = sum(1 for r in final if r["correcta"])
    print(f"Corrida {n}: {ok}/{len(casos)} correctas ({pct(ok, len(casos))} %), {dur / 60:.1f} min")
    ref_eventos["respaldo_" + str(n)] = cliente.respaldo_global() - respaldo_antes
    return final


# --------------------------------------------------------------------------- resumen
def desglose(corridas: list[list[dict]], campo: str) -> dict[str, list[tuple[int, int]]]:
    claves = sorted({r.get(campo) or "(sin dato)" for c in corridas for r in c})
    out = {}
    for k in claves:
        out[k] = [(sum(1 for r in c if (r.get(campo) or "(sin dato)") == k and r["correcta"]),
                   sum(1 for r in c if (r.get(campo) or "(sin dato)") == k)) for c in corridas]
    return out


def armar_resumen(corridas: list[list[dict]], total: int, ref_eventos: dict, args, modo: str, golden: Path) -> dict:
    por_corrida = []
    for i, c in enumerate(corridas, 1):
        lat = [r["latencia_s"] for r in c if r.get("latencia_s") is not None and not r.get("error")]
        ok = sum(1 for r in c if r["correcta"])
        por_corrida.append({
            "corrida": i, "correctas": ok, "total": total, "calificados": len(c), "porcentaje": pct(ok, total),
            "latencia_media_s": round(statistics.mean(lat), 2) if lat else 0,
            "latencia_p95_s": round(percentil(lat, 0.95), 2),
            "errores": sum(1 for r in c if r.get("error") and not str(r["error"]).startswith("timeout")),
            "timeouts": sum(1 for r in c if str(r.get("error") or "").startswith("timeout")),
            "casos_con_modelo_respaldo": sum(1 for r in c if r.get("usa_respaldo")),
            "eventos_modelo_respaldo": ref_eventos.get(f"respaldo_{i}", 0),
            "modelos_vistos": dict(sum((Counter(r.get("modelos") or {}) for r in c), Counter())),
        })
    pcts = [p["porcentaje"] for p in por_corrida]
    distintos = len(set(pcts))
    req_max = all(p <= MAX_PORCENTAJE for p in pcts)
    req_dist = distintos >= 2
    fallaron_todas = []
    if corridas:
        ids = [set(r["id"] for r in c if not r["correcta"]) for c in corridas]
        fallaron_todas = sorted(set.intersection(*ids)) if all(len(c) == total for c in corridas) else []
    return {
        "fecha": datetime.now().isoformat(timespec="seconds"), "golden": golden.name, "casos": total, "modo": modo,
        "concurrencia": args.concurrencia, "timeout_s": args.timeout, "corridas": por_corrida,
        "por_kb": {k: v for k, v in desglose(corridas, "kb").items()},
        "por_dificultad": {k: v for k, v in desglose(corridas, "dificultad").items()},
        "requisitos": {
            "golden_set_al_menos_300": total >= 300, "todas_las_corridas_hasta_95": req_max,
            "porcentajes_distintos": distintos, "al_menos_2_porcentajes_distintos": req_dist,
        },
        "ids_fallaron_en_todas": fallaron_todas,
    }


def resumen_md(s: dict) -> str:
    n = len(s["corridas"])
    L = [f"# Resumen de {n} corridas del golden set", "",
         f"- Fecha: {s['fecha']}  |  Golden set: `{s['golden']}` ({s['casos']} casos)  |  Modo: {s['modo']}  |  "
         f"Concurrencia: {s['concurrencia']}  |  Timeout por caso: {s['timeout_s']:.0f} s",
         "- Cada caso va en una sesión nueva. La variación entre corridas viene de la no determinación del modelo "
         "(no se agregó aleatoriedad). Calificación: juez LLM con temperatura 0 (`prompt_juez.md`).", "",
         "## Resultado por corrida", "",
         "| Corrida | Correctas | Accuracy | Latencia media (s) | Latencia p95 (s) | Errores | Timeouts | Casos con respaldo |",
         "|---|---|---|---|---|---|---|---|"]
    for c in s["corridas"]:
        L.append(f"| {c['corrida']} | {c['correctas']}/{c['total']} | {c['porcentaje']:.1f} % | {c['latencia_media_s']} | "
                 f"{c['latencia_p95_s']} | {c['errores']} | {c['timeouts']} | {c['casos_con_modelo_respaldo']} |")
    L.append("")
    for titulo, clave in (("Desglose por fuente (kb)", "por_kb"), ("Desglose por dificultad", "por_dificultad")):
        L += [f"## {titulo}", "", "| Grupo | " + " | ".join(f"Corrida {i}" for i in range(1, n + 1)) + " |",
              "|---|" + "---|" * n]
        for k, v in s[clave].items():
            L.append(f"| {k} | " + " | ".join(f"{a}/{b} ({pct(a, b):.1f} %)" for a, b in v) + " |")
        L.append("")
    resp = sum(c["casos_con_modelo_respaldo"] for c in s["corridas"])
    ev = sum(c["eventos_modelo_respaldo"] for c in s["corridas"])
    L += ["## Modelo de respaldo y modelos usados", "",
          f"- Casos que usaron el modelo de respaldo (Gemini): {resp}; avisos `modelo_respaldo` en los logs: {ev}"
          + (" (en modo http no se puede saber desde aquí: revisar Cloud Logging, evento `modelo_respaldo`)." if s["modo"] == "http" else "."),
          *[f"- Corrida {c['corrida']}: modelos vistos {c['modelos_vistos'] or 'sin dato'}" for c in s["corridas"]], "",
          "## Verificación de requisitos del enunciado", ""]
    r = s["requisitos"]
    L += [f"- Golden set de al menos 300 casos: **{'CUMPLE' if r['golden_set_al_menos_300'] else 'NO CUMPLE'}** ({s['casos']} casos).",
          f"- Accuracy de 95 % o menos en todas las corridas: **{'CUMPLE' if r['todas_las_corridas_hasta_95'] else 'NO CUMPLE'}** "
          f"({', '.join(f'{c['porcentaje']:.1f} %' for c in s['corridas'])}).",
          f"- Al menos 2 porcentajes distintos entre las corridas: **{'CUMPLE' if r['al_menos_2_porcentajes_distintos'] else 'NO CUMPLE'}** "
          f"({r['porcentajes_distintos']} distintos).", "",
          "## Ids que fallaron en todas las corridas", ""]
    L.append(", ".join(s["ids_fallaron_en_todas"]) if s["ids_fallaron_en_todas"] else "Ninguno.")
    L += ["", "Los errores y timeouts quedan en `respuestas_corridaN.jsonl` (campo `error`) y los avisos de los agentes "
          "(reintentos, respaldo, fallos) en `eventos_corridaN.jsonl`.", ""]
    return "\n".join(L)


# --------------------------------------------------------------------------- main
async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--golden", default="golden_set.jsonl", help="JSONL del golden set (relativo a evaluacion/ si no existe tal cual)")
    p.add_argument("--corridas", type=int, default=3)
    p.add_argument("--modo", choices=["local", "http"], default="local")
    p.add_argument("--limite", type=int, default=0, help="solo los primeros N casos (para pruebas)")
    p.add_argument("--concurrencia", type=int, default=4)
    p.add_argument("--timeout", type=float, default=180, help="segundos máximos por caso")
    p.add_argument("--salida", default="", help="carpeta de salida (defecto: corridas/<fecha-hora>/)")
    p.add_argument("--reanudar", action="store_true", help="no repetir casos ya respondidos en --salida")
    a = p.parse_args()

    golden = Path(a.golden)
    if not golden.exists():
        golden = AQUI / a.golden
    casos = leer_jsonl(golden)
    if not casos:
        sys.exit(f"No encuentro casos en {a.golden}")
    for c in casos:
        faltan = [k for k in ("id", "query", "ground_truth") if k not in c]
        if faltan:
            sys.exit(f"El caso {c.get('id', '?')} no tiene los campos {faltan}")
    if a.limite:
        casos = casos[: a.limite]
    if a.reanudar and not a.salida:
        sys.exit("--reanudar necesita --salida con la carpeta de la corrida cortada.")
    salida = Path(a.salida) if a.salida else AQUI / "corridas" / datetime.now().strftime("%Y-%m-%d_%H%M")
    salida.mkdir(parents=True, exist_ok=True)

    from kiosco_agentes import config  # carga proyecto2/agentes/.env (y Key Vault si está configurado)

    sistema, plantilla = cargar_prompt_juez()
    ref_eventos: dict = {}
    cliente = ClienteLocal(ref_eventos) if a.modo == "local" else ClienteHttp()
    print(f"Golden: {golden.name} ({len(casos)} casos) | {a.corridas} corridas | modo {a.modo} | "
          f"concurrencia {a.concurrencia} | salida {salida}")
    print(f"Modelo de agentes y juez: {config.MODELO_PRINCIPAL} (respaldo {config.MODELO_RESPALDO}, KB {config.KB_BACKEND})")

    corridas = []
    for n in range(1, a.corridas + 1):
        corridas.append(await correr_corrida(n, casos, cliente, a, salida, sistema, plantilla, config, ref_eventos))

    s = armar_resumen(corridas, len(casos), ref_eventos, a, a.modo, golden)
    s["modelo_agentes_y_juez"] = config.MODELO_PRINCIPAL
    s["modelo_respaldo"] = config.MODELO_RESPALDO
    (salida / "resumen.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    (salida / "resumen.md").write_text(resumen_md(s), encoding="utf-8")
    print(f"\nListo. Resumen en {salida / 'resumen.md'}")
    print(" | ".join(f"corrida {c['corrida']}: {c['correctas']}/{c['total']} ({c['porcentaje']:.1f} %)" for c in s["corridas"]))


if __name__ == "__main__":
    asyncio.run(main())
