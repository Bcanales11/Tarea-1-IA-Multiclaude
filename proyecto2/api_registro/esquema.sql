-- Esquema de la BD de registro (Azure Database for PostgreSQL – Flexible Server).
-- La API lo crea sola al arrancar (app/bd.py, ESQUEMA_POSTGRES); este archivo es la referencia
-- para el informe. Contrato: INSTRUCCIONES_GRUPO.md §4.3.

CREATE TABLE IF NOT EXISTS chequeos (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kiosco_id  text        NOT NULL,                 -- p. ej. colegio-001
    producto   text        NOT NULL,                 -- p. ej. Galletas X 120 g
    sku        text        NOT NULL DEFAULT '',      -- SKU del catálogo, si se conoce
    sellos     text[]      NOT NULL DEFAULT '{}',    -- sellos ALTO EN detectados (puede ir vacía con NO_APTO)
    veredicto  text        NOT NULL CHECK (veredicto IN ('APTO', 'NO_APTO')),  -- se guarda tal cual llega
    motivo     text        NOT NULL DEFAULT '',
    origen     text        NOT NULL CHECK (origen IN ('vision', 'chat')),
    fecha      timestamptz NOT NULL DEFAULT now(),   -- la pone la API, en UTC
    -- Segunda barrera (la primera es la validación de la API, que responde 422):
    CONSTRAINT chequeos_sellos_validos
        CHECK (sellos <@ ARRAY['AZUCARES', 'SODIO', 'CALORIAS', 'GRASAS_SATURADAS']::text[]),
    CONSTRAINT chequeos_apto_sin_sellos
        CHECK (veredicto = 'NO_APTO' OR cardinality(sellos) = 0)
);

-- GET /chequeos?kiosco_id=...&desde=... filtra por kiosco y rango de fechas
CREATE INDEX IF NOT EXISTS chequeos_kiosco_fecha_idx ON chequeos (kiosco_id, fecha);
