# Briefing agente — Ricetta: spese-casalinghe

Versione leggibile (italiano piano) della stessa informazione che
`caveman.md` codifica in kanji per gli LLM in background.

## Obiettivo della ricetta

Generare un'applicazione web personale Streamlit per la gestione delle
spese familiari. Funziona offline sul computer dell'utente. Nessun
account, nessun cloud, nessuna telemetria.

## Componenti del progetto utente

- `database.py` — Crea il database SQLite `spese.db` con tabella `spese`
  (id integer primary key, data text ISO-8601, categoria text, importo
  real, descrizione text).
- `seed.py` — Popola il database con dieci spese di esempio realistiche
  italiane (Esselunga, Eni, Telepass, ENEL, MM Milano, dentista, cinema).
- `app.py` — Applicazione Streamlit con tema scuro, sidebar form per
  aggiungere una spesa, tabella delle ultime 20 spese, grafico a torta
  per categoria, totale del mese corrente, esportazione xlsx.
- `requirements.txt` — streamlit, pandas, plotly, openpyxl.

## Vincoli funzionali

- Validare input: data non futura, importo positivo, categoria nell'enum.
- Salvare la spesa nel database con un singolo INSERT prepared.
- Aggiornare la tabella e il grafico immediatamente dopo l'INSERT.
- Esportare in Excel con `openpyxl`. Nome file: `spese_<YYYY-MM-DD>.xlsx`.
- Tema Streamlit scuro via `.streamlit/config.toml`.

## Vincoli non funzionali

- Tutte le label, i messaggi e gli errori sono in italiano.
- Codice commentato il minimo indispensabile (i nomi parlano).
- Niente dipendenze cloud, niente chiamate a internet.

## Esecuzione

```
pip install -r requirements.txt
python database.py     # crea spese.db se non esiste
python seed.py         # opzionale: popola di esempio
streamlit run app.py   # apre http://localhost:8501
```

Se l'utente ha risposto "Sì, accesso da telefono" alla domanda q1,
Streamlit deve essere avviato con `--server.address 0.0.0.0` così il
telefono nella stessa rete può raggiungerlo.

## Stato di consegna atteso

L'utente vede solo la Cabina di Regia. Quando la build è completa,
la Cabina apre automaticamente Streamlit in una nuova tab del browser.
L'utente non vede mai il terminale né i comandi.
