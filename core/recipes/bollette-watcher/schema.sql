-- Bollette Watcher — schema SQLite locale
-- Path: ~/.givengine/data/bollette-watcher.db
-- Versione: 0.1.0

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS utenze (
  id           INTEGER PRIMARY KEY,
  alias        TEXT NOT NULL,
  tipo         TEXT NOT NULL CHECK (tipo IN ('luce','gas','acqua','telefono','internet')),
  fornitore    TEXT,
  pod_pdr      TEXT,
  intestatario TEXT,
  created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_utenze_tipo ON utenze(tipo);

CREATE TABLE IF NOT EXISTS bollette (
  id                INTEGER PRIMARY KEY,
  utenza_id         INTEGER NOT NULL REFERENCES utenze(id) ON DELETE CASCADE,
  file_originale    TEXT,
  file_hash         TEXT,   -- SHA-256 hex (dedup: same PDF re-import skip)
  periodo_inizio    TEXT,
  periodo_fine      TEXT,
  consumo_qta       REAL,
  consumo_unita     TEXT,
  lettura_prec      REAL,   -- lettura contatore assoluta inizio periodo
  lettura_prec_data TEXT,   -- ISO YYYY-MM-DD
  lettura_att       REAL,   -- lettura contatore assoluta fine periodo
  lettura_att_data  TEXT,   -- ISO YYYY-MM-DD
  importo_totale    REAL,
  importo_imponibile REAL,
  iva               REAL,
  scadenza          TEXT,
  parser_usato      TEXT,
  confidence        REAL CHECK (confidence BETWEEN 0 AND 1),
  raw_text          TEXT,
  imported_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_bollette_file_hash
  ON bollette(file_hash) WHERE file_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bollette_utenza ON bollette(utenza_id);
CREATE INDEX IF NOT EXISTS idx_bollette_scadenza ON bollette(scadenza);
CREATE INDEX IF NOT EXISTS idx_bollette_periodo ON bollette(periodo_inizio);

CREATE TABLE IF NOT EXISTS alert (
  id           INTEGER PRIMARY KEY,
  utenza_id    INTEGER REFERENCES utenze(id) ON DELETE CASCADE,
  bolletta_id  INTEGER REFERENCES bollette(id) ON DELETE SET NULL,
  tipo         TEXT NOT NULL CHECK (tipo IN ('anomalia-consumi','anomalia-costo','scadenza')),
  messaggio    TEXT NOT NULL,
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  dismissed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_alert_active ON alert(utenza_id) WHERE dismissed_at IS NULL;

CREATE VIEW IF NOT EXISTS v_utenze_riepilogo AS
SELECT
  u.id, u.alias, u.tipo, u.fornitore,
  COUNT(b.id)            AS num_bollette,
  SUM(b.importo_totale)  AS totale_speso,
  MAX(b.scadenza)        AS ultima_scadenza,
  MAX(b.imported_at)     AS ultimo_import
FROM utenze u
LEFT JOIN bollette b ON b.utenza_id = u.id
GROUP BY u.id;
