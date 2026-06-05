-- letture-contatori schema v0.1.0
CREATE TABLE IF NOT EXISTS utenze (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo TEXT NOT NULL CHECK(tipo IN ('gas', 'luce', 'acqua')),
  codice_pod_pdr TEXT,
  fornitore_attuale TEXT,
  distributore TEXT,
  unita_misura TEXT NOT NULL,
  tariffa_riferimento TEXT,
  fasce_orarie_attive INTEGER DEFAULT 0,
  alias_utente TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS letture (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  utenza_id INTEGER NOT NULL REFERENCES utenze(id) ON DELETE CASCADE,
  data_lettura DATE NOT NULL,
  valore REAL NOT NULL,
  valore_f1 REAL,
  valore_f2 REAL,
  valore_f3 REAL,
  tipo_lettura TEXT NOT NULL,
  foto_path TEXT,
  comunicata_al_fornitore INTEGER DEFAULT 0,
  note TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finestre_autolettura (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  utenza_id INTEGER NOT NULL REFERENCES utenze(id) ON DELETE CASCADE,
  mese_anno TEXT NOT NULL,
  giorno_inizio INTEGER NOT NULL,
  giorno_fine INTEGER NOT NULL,
  finestra_chiusa INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_letture_utenza_data ON letture(utenza_id, data_lettura DESC);
