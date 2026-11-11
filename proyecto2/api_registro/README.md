# API de registro de chequeos — Kiosco Escolar Saludable (Grupo 19)

Responsable: Benjamín (infraestructura Azure). Contrato: `../INSTRUCCIONES_GRUPO.md` §4.3 y las reglas acordadas en `../ESTADO.md` ("Cambios de contrato").

Guarda cada chequeo que hace el kiosco (producto, sellos, veredicto) en una base de datos propia y los devuelve para los reportes de auditoría. La usa el **Agente de Registro** de Max (`../agentes/kiosco_agentes/herramientas/registro.py`): `guardar_chequeo` hace `POST /chequeos` y el Sub-agente de Reportes, con `listar_chequeos`, hace `GET /chequeos`.

| Pieza | Dónde |
|---|---|
| API | Python 3.12 + FastAPI, en **Azure Container Apps** (plan de consumo, entorno en la VNet) |
| Base de datos | **Azure Database for PostgreSQL – Flexible Server** B1ms, acceso privado, sin IP pública |
| `x-api-key` y URL de la BD | **Azure Key Vault**, leídas con identidad administrada (nunca en la imagen ni en el repo) |
| Infraestructura | `../infra/` (scripts `az` y guía paso a paso) |

## Contrato

Todas las rutas de `/chequeos` exigen el header `x-api-key`. La clave se compara en tiempo constante y se revisa **antes** de leer el cuerpo: sin clave válida la respuesta es siempre `401`, nunca `422`.

### `POST /chequeos` → `201 {"id": 42, "fecha": "2026-11-10T22:15:03+00:00"}`

```json
{
  "kiosco_id": "colegio-001",
  "producto": "Galletas X 120 g",
  "sku": "612696",
  "sellos": ["AZUCARES", "GRASAS_SATURADAS"],
  "veredicto": "NO_APTO",
  "motivo": "Art. 110 bis: basta un sello ALTO EN",
  "origen": "vision"
}
```

| Campo | Regla | Si no se cumple |
|---|---|---|
| `kiosco_id` | obligatorio, 1-64 caracteres, letras, números, `-`, `_` o `.` | 422 |
| `producto` | obligatorio, 1-200 caracteres | 422 |
| `sku` | opcional (por defecto `""`), máx. 40 | 422 |
| `sellos` | obligatoria, lista (puede ir **vacía**); cada valor ∈ `AZUCARES`, `SODIO`, `CALORIAS`, `GRASAS_SATURADAS`; los repetidos se guardan una vez | 422 |
| `veredicto` | `APTO` o `NO_APTO`. **Se guarda tal cual: la API nunca lo recalcula** desde los sellos | 422 |
| `veredicto` + `sellos` | **`APTO` con sellos se rechaza** y deja un warning `rechazo_apto_con_sellos` en los logs (sería un producto con sello marcado como apto). `NO_APTO` con `sellos: []` es válido: sello visto por la cámara pero ilegible | 422 |
| `motivo` | opcional, máx. 500 | 422 |
| `origen` | `vision` o `chat` | 422 |
| campos extra | no se aceptan | 422 |
| cuerpo | máx. 16 KB (`MAX_BYTES_CUERPO`) | 413 |

Fecha: la pone la API en UTC (ISO 8601, con segundos).

### `GET /chequeos?kiosco_id=colegio-001&desde=2026-11-10[&limite=1000]` → `200 [ ... ]`

Lista ordenada por fecha, con los mismos campos del POST más `id` y `fecha`; `sellos` siempre es una lista.

- `kiosco_id`: obligatorio.
- `desde`: opcional. `AAAA-MM-DD` se interpreta como **el inicio de ese día en hora de Chile** (`ZONA_HORARIA`, por defecto `America/Santiago`), no en UTC; también acepta fecha-hora ISO 8601 (`2026-11-10T14:00:00Z`). Formato inválido → 422.
- `limite`: 1 a 5.000, por defecto 1.000.

### `GET /salud` (sin autenticación)

`200 {"estado": "ok", "bd": "ok", "backend": "postgres", "version": "1.0.0"}`, o `503` con `"bd": "error"` si la base no responde.

### Códigos

| Código | Cuándo |
|---|---|
| 201 / 200 | OK |
| 401 | `x-api-key` ausente o inválida (warning `rechazo_401` en logs, sin la clave) |
| 413 / 411 | cuerpo mayor al límite / POST sin `Content-Length` |
| 422 | validación (warning `rechazo_422` o `rechazo_apto_con_sellos`) |
| 503 | BD caída, o la API arrancó sin `REGISTRO_API_KEY` (falla cerrada: no acepta nada) |

`/docs` y `/openapi.json` están apagados por defecto (`HABILITAR_DOCS=true` para verlos en local).

## Logs

Una línea JSON por evento a stdout (Container Apps la manda a Log Analytics, tabla `ContainerAppConsoleLogs_CL`). Campos: `fecha`, `nivel`, `logger`, `evento`, `mensaje`, `datos`. Eventos: `inicio`, `peticion` (método, ruta, estado, IP, ms), `chequeo_guardado`, `rechazo_401`, `rechazo_422`, `rechazo_apto_con_sellos`, `rechazo_413`, `error_bd`, `bd_no_disponible`, `sin_api_key`. Nunca se escribe la clave ni la URL de la BD.

## Base de datos

Tabla `chequeos` (`esquema.sql`): `id bigint identity`, `kiosco_id`, `producto`, `sku`, `sellos text[]`, `veredicto`, `motivo`, `origen`, `fecha timestamptz`, índice `(kiosco_id, fecha)`. Además de la validación de la API, la tabla tiene `CHECK` de sellos válidos y de "APTO sin sellos" como segunda barrera. La API crea la tabla sola al arrancar, porque la BD es privada y no se puede administrar desde fuera de la VNet.

Backend según `DATABASE_URL`: `sqlite:///ruta.db` (local y pruebas; por defecto `datos_local/registro.db`) o `postgresql://...?sslmode=require` (Azure, psycopg 3 con pool de 1 a 5 conexiones).

## Correr en local

```bash
cd proyecto2/api_registro
python -m venv .venv
.venv/Scripts/activate              # Windows   (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                # y pon una REGISTRO_API_KEY de prueba (inventada)
uvicorn app.main:app --port 8000
```

Prueba rápida:

```bash
curl http://127.0.0.1:8000/salud
curl -X POST http://127.0.0.1:8000/chequeos -H "x-api-key: <tu clave de prueba>" -H "content-type: application/json" \
  -d '{"kiosco_id":"colegio-001","producto":"Galletas X 120 g","sku":"612696","sellos":["AZUCARES"],"veredicto":"NO_APTO","motivo":"Art. 110 bis","origen":"vision"}'
```

Con los agentes de Max contra esta API local: en `../agentes/.env`, `REGISTRO_BACKEND=api`, `REGISTRO_API_URL=http://127.0.0.1:8000` y `REGISTRO_API_KEY=<la misma clave de prueba>`.

## Pruebas

```bash
.venv/Scripts/python -m pytest pruebas -q
```

51 pruebas (10 nov 2026, todas pasan): 401 sin key, con key errónea y en GET; 401 antes que 422; 503 sin clave configurada; 201 con id y fecha UTC; NO_APTO con sellos vacía; APTO sin sellos; repetidos; 422 por APTO con sellos (con su warning en logs y sin guardar nada), sello inválido (`AZÚCARES`, minúsculas, con espacio…), veredicto inválido, origen, largos máximos, campos extra y obligatorios; 413; GET por `kiosco_id`, `desde` (incluido el borde del día en hora de Chile), fecha-hora ISO, límite y parámetros inválidos; logs JSON.

**Integración con el cliente real** (10 nov 2026): con la API local en SQLite y `REGISTRO_BACKEND=api`, `guardar_chequeo` de los agentes guardó un NO_APTO con sellos (normalizó `AZÚCARES` → `AZUCARES`), un NO_APTO con sello ilegible (`sellos: []`) y un APTO, y `listar_chequeos` devolvió los 3 con los mismos campos; con una clave errónea, `guardar_chequeo` devolvió `estado: error` con el 401. El backend PostgreSQL se probó solo en su manejo de fallas (BD inalcanzable → 503 controlado); la primera prueba real contra PostgreSQL es `../infra/verificar.sh`.

## Despliegue

Lo hace `../infra/desplegar_azure.sh` (guía completa en `../infra/README.md`): construye la imagen con `az acr build` en un ACR Basic y la publica en Container Apps con `REGISTRO_API_KEY` y `DATABASE_URL` como referencias a Key Vault (secretos `registro-api-key` y `registro-database-url`), 0,25 vCPU, 0,5 GiB, 1 a 3 réplicas (escala con 20 peticiones simultáneas por réplica) e ingress HTTPS restringido a la IP fija de Cloud Run. `../infra/verificar.sh` prueba la API desplegada.

| Variable | Qué es | En Azure |
|---|---|---|
| `REGISTRO_API_KEY` | clave que se exige en `x-api-key` | Key Vault `registro-api-key` |
| `DATABASE_URL` | URL de la BD | Key Vault `registro-database-url` |
| `ZONA_HORARIA` | zona de `desde=AAAA-MM-DD` | `America/Santiago` |
| `NIVEL_LOG`, `HABILITAR_DOCS`, `MAX_BYTES_CUERPO`, `MAX_RESULTADOS` | opcionales | valores por defecto |

## Limitaciones

- **Una sola clave para todos los kioscos.** La API no distingue quién escribe: cualquiera con la clave puede registrar o leer cualquier `kiosco_id`. Para varios colegios convendría una clave por kiosco o tokens de Entra ID.
- **Sin límite de peticiones por cliente** (rate limiting). Lo mitigan la restricción de IP del ingress y del NSG (solo Cloud Run llega).
- La app se conecta a PostgreSQL con el **usuario administrador** del servidor. Lo correcto es un rol con permisos solo sobre `chequeos`, o autenticación de Entra ID con la identidad administrada (sin contraseña); se dejó así porque la BD es privada y crear roles exige conectarse desde dentro de la VNet.
- No hay borrado ni edición de chequeos (es un registro de auditoría): corregir un error exige hacerlo en la BD.
- `GET /chequeos` devuelve como máximo 5.000 filas y no pagina.
- Rotar la clave exige reiniciar la API y Cloud Run (ver `../infra/README.md`).
