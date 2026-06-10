-- calendario-comunale-rifiuti schema v1.0.0
-- Local-first SQLite. Tutte le child table CASCADE dalla frazione.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS frazioni (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  colore TEXT,
  icona TEXT,
  attiva INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ricorrenze (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  frazione_id INTEGER NOT NULL REFERENCES frazioni(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL CHECK(tipo IN ('settimanale', 'quindicinale', 'mensile', 'lista_date')),
  giorni_settimana TEXT,          -- CSV ISO weekday "1,4" (1=lun .. 7=dom)
  settimane_alterne INTEGER NOT NULL DEFAULT 0,
  giorno_mese INTEGER,            -- per tipo 'mensile'
  date_extra TEXT,               -- CSV date ISO per 'lista_date'
  valido_da DATE,                -- ancora parita' + inizio validita'
  valido_a DATE,
  note TEXT
);

CREATE TABLE IF NOT EXISTS eccezioni (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  data DATE NOT NULL,
  frazione_id INTEGER REFERENCES frazioni(id) ON DELETE CASCADE,
  salta INTEGER NOT NULL DEFAULT 0,
  sposta_a DATE,
  motivo TEXT
);

CREATE TABLE IF NOT EXISTS regolamento (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  materiale TEXT NOT NULL,
  frazione_id INTEGER REFERENCES frazioni(id) ON DELETE CASCADE,
  note TEXT
);

CREATE TABLE IF NOT EXISTS promemoria (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  frazione_id INTEGER NOT NULL REFERENCES frazioni(id) ON DELETE CASCADE,
  anticipo_ore INTEGER NOT NULL DEFAULT 12,
  ora_invio TEXT,                -- "HH:MM" opzionale
  attivo INTEGER NOT NULL DEFAULT 1,
  ultimo_inviato DATE
);

CREATE TABLE IF NOT EXISTS config (
  chiave TEXT PRIMARY KEY,
  valore TEXT
);

CREATE INDEX IF NOT EXISTS idx_ricorrenze_frazione ON ricorrenze(frazione_id);
CREATE INDEX IF NOT EXISTS idx_eccezioni_data ON eccezioni(data);
CREATE INDEX IF NOT EXISTS idx_regolamento_materiale ON regolamento(materiale);
CREATE INDEX IF NOT EXISTS idx_promemoria_frazione ON promemoria(frazione_id);
