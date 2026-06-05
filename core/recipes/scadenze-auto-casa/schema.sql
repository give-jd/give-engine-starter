-- scadenze-auto-casa schema v0.1.0
CREATE TABLE IF NOT EXISTS scadenze (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  categoria TEXT NOT NULL CHECK(categoria IN ('auto', 'casa', 'persona')),
  tipo TEXT NOT NULL,
  oggetto TEXT,
  prossima_scadenza DATE NOT NULL,
  frequenza_tipo TEXT NOT NULL,
  frequenza_custom_giorni INTEGER,
  importo_previsto_eur REAL,
  note TEXT,
  notifiche_attive INTEGER DEFAULT 1,
  giorni_anticipo_notifica INTEGER DEFAULT 14,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pagamenti_storici (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scadenza_id INTEGER REFERENCES scadenze(id) ON DELETE CASCADE,
  data_pagamento DATE NOT NULL,
  importo_pagato_eur REAL,
  metodo TEXT,
  riferimento TEXT,
  note TEXT
);

CREATE INDEX IF NOT EXISTS idx_scadenze_prossima ON scadenze(prossima_scadenza);
CREATE INDEX IF NOT EXISTS idx_scadenze_categoria ON scadenze(categoria);
