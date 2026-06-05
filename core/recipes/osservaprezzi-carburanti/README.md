# Osservaprezzi Carburanti

**Tier**: Starter (MIT) · **Slug**: `osservaprezzi-carburanti` · **Versione**: 0.1.0

**Tagline**: *I prezzi del tuo distributore preferito, freschi dal MIMIT, prima di partire.*

Consultazione locale dei prezzi carburanti aggiornati dal registro pubblico MIMIT. **Niente API key, nessun dato tuo esce dal PC** — è solo download di CSV pubblici aggiornati ogni giorno.

## Pattern `external_calls: optional-public-source`

Nuovo enum manifest (round 2). Indica chiamate HTTP a fonti pubbliche governative senza autenticazione e senza dati utente trasmessi. Cabina di Regia mostra badge **"Solo lettura da fonte pubblica MIMIT"**.

## Fonte dati MIMIT

- `https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv`
- `https://www.mimit.gov.it/images/exportCSV/prezzo_alle_8.csv`
- Encoding ISO-8859-1, separatore `;`, aggiornati giornalmente
- D.M. 17.01.2013

## Cosa fa

- Ricerca distributori per CAP + raggio km
- Preferiti con alert "sotto soglia"
- Storico prezzi 30 giorni
- Tracking rifornimenti personali (€/100 km, l/100km)
- Geocoding CAP→lat/lng locale (dataset ISTAT precaricato)

## Stack

- Python 3.10+ + Streamlit
- SQLite locale
- HTTPX per download CSV (timeout 30s)
- Pandas per parsing CSV

## Sinergie

- `scadenze-auto-casa`: cross-card bollo + pieno conveniente
- `spese-casalinghe`: prompt opt-in registra rifornimento

## Limiti noti v0.1

- Stabilità URL MIMIT: feature flag per cambio rapido
- Carburanti CSV: nessuna normalizzazione
