# Briefing agente — Ricetta: spese-casalinghe

Versione leggibile (italiano piano) stessa 情 
`caveman.md` codifica kanji LLM background.

## Obiettivo ricetta

Generare applicazione web personale Streamlit gestione 
spese familiari. Funziona offline sul computer 用者. Nessun
account, nessun cloud, nessuna telemetria.

## Componenti progetto 用者

- `DB.py` — 作 DB SQLite `spese.db` 表 `spese`
 (id integer primary key, 日 text ISO-8601, 種 text, 額
 real, descrizione text).
- `seed.py` — 充 DB dieci spese esempio realistiche
 italiane (Esselunga, Eni, Telepass, ENEL, MM Milano, dentista, cinema).
- `app.py` — Applicazione Streamlit 暗皮, sidebar 帳 
 aggiungere spesa, 表 ultime 20 spese, 図 torta
 種, totale mese corrente, esportazione xlsx.
- `requirements.txt` — streamlit, pandas, plotly, openpyxl.

## Vincoli funzionali

- 入検: 日 futura, 額 positivo, 種 enum.
- 保存 spesa DB singolo INSERT prepared.
- Aggiornare 表図 immediatamente dopo INSERT.
- Esportare Excel `openpyxl`. Nome 件: `spese_<YYYY-MM-DD>.xlsx`.
- Tema Streamlit scuro `.streamlit/config.toml`.

## Vincoli funzionali

- label, messaggi errori italiano.
- Codice commentato 小 indispensabile ( nomi parlano).
- 無 dipendenze cloud, 無 chiamate internet.

## Esecuzione

```
pip install -r requirements.txt
python DB.py # 作 spese.db esiste
python seed.py # opzionale: 充 esempio
streamlit run app.py # apre http://localhost:8501
```

 用者 ha risposto "Sì, accesso telefono" domanda q1,
Streamlit deve essere avviato `--鯖.address 0.0.0.0` così 
telefono stessa 網 può raggiungerlo.

## Stato consegna atteso

用者 vede solo Cabina Regia. Quando build completa,
 Cabina apre automaticamente Streamlit nuova tab browser.
用者 vede mai terminale né comandi.
