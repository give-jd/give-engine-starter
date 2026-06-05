-- osservaprezzi-carburanti schema v0.1.0
CREATE TABLE IF NOT EXISTS distributori (
  id INTEGER PRIMARY KEY,
  bandiera TEXT,
  tipo_impianto TEXT,
  nome_impianto TEXT,
  indirizzo TEXT,
  comune TEXT,
  provincia TEXT,
  latitudine REAL,
  longitudine REAL,
  ultimo_aggiornamento_anagrafica DATE
);

CREATE TABLE IF NOT EXISTS prezzi (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  distributore_id INTEGER NOT NULL REFERENCES distributori(id) ON DELETE CASCADE,
  carburante TEXT NOT NULL,
  prezzo_self REAL,
  prezzo_servito REAL,
  data_comunicazione TIMESTAMP NOT NULL,
  UNIQUE(distributore_id, carburante, data_comunicazione)
);

CREATE TABLE IF NOT EXISTS preferiti (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  distributore_id INTEGER NOT NULL REFERENCES distributori(id) ON DELETE CASCADE,
  etichetta_utente TEXT,
  ordine INTEGER DEFAULT 0,
  alert_sotto_eur REAL,
  carburante_principale TEXT DEFAULT 'Benzina',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rifornimenti (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  distributore_id INTEGER REFERENCES distributori(id),
  data DATE NOT NULL,
  carburante TEXT NOT NULL,
  litri REAL,
  prezzo_unitario REAL,
  prezzo_totale REAL,
  km_attuali INTEGER,
  note TEXT
);

CREATE TABLE IF NOT EXISTS refresh_mimit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  data_refresh TIMESTAMP NOT NULL,
  esito TEXT NOT NULL,
  righe_anagrafica INTEGER,
  righe_prezzi INTEGER,
  note TEXT
);

CREATE INDEX IF NOT EXISTS idx_distributori_geo ON distributori(latitudine, longitudine);
CREATE INDEX IF NOT EXISTS idx_prezzi_distributore_data ON prezzi(distributore_id, data_comunicazione DESC);
