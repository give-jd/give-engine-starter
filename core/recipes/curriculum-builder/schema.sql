-- curriculum-builder v1 — dati PROPRI dell'utente, sqlite locale, timestamps ISO 8601
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version (version)
  SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM schema_version);

-- payload JSON unico (schema v1, identico al prototipo: export/import compatibili).
-- Deliberato: documento per-utente, <10 righe attese, nessuna query relazionale ⇒ niente tabelle dominio/FTS5.
CREATE TABLE IF NOT EXISTS cv (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  nome_cv     TEXT NOT NULL,
  payload     TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
