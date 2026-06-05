# Bollette Watcher

**Tier**: Starter (free, MIT) · **Slug**: `bollette-watcher` · **Versione**: 0.1.0

Carichi i PDF delle bollette di luce, gas, telefono e internet → l'app legge consumi e importi, ti mostra trend mensili e ti avvisa di anomalie. Tutto sul tuo PC.

## Cosa fa

- Importa PDF bollette (singolo file o cartella intera)
- Parser per fornitori comuni italiani (Enel, Eni, A2A, Iren, Vodafone, TIM, Fastweb) + fallback euristico
- Dashboard locale con grafici mese-su-mese
- Alert anomalie consumo ≥25% vs media trailing 6 mesi
- Export CSV "spese deducibili" per anno fiscale

## Local-first by design

**Niente esce dal tuo PC.** I PDF e i dati estratti sono salvati esclusivamente sul tuo dispositivo (`~/.givengine/data/bollette-watcher.db`). Gi.Ve Group NON riceve nessun dato.

Vedi [PRIVACY.md](./PRIVACY.md) per dettagli sull'inquadramento GDPR (esenzione domestica ex art. 2 par. 2 lett. c GDPR).

## Stack

- Python 3.10+ + Streamlit per UI
- SQLite locale (no server DB)
- pdfminer.six per estrazione testo
- pandas + plotly per dashboard

## Limiti noti v0.1

- Parser Enel + fallback funzionanti. Altri 6 fornitori → scaffold con `NotImplementedError` raise → fallback automatico
- PDF protetti da password: messaggio esplicito, no bypass
- Bollette multi-pagina con dettaglio consumi orari: estrazione del solo totale (V2 per dettaglio)
- Approccio parser regex vs LLM: V1 regex-only per zero costi/dipendenze esterne

## Installazione

```bash
givengine recipes install bollette-watcher
```

Cabina di Regia poi avvia automaticamente Streamlit su `http://localhost:8511`.

## Disinstallazione totale (diritto all'oblio)

Dashboard → menu → "Cancella tutto" → conferma → DB rimosso + cartella `~/.givengine/data/bollette-watcher.db` eliminata.

## Roadmap

| Step | Stato |
|---|---|
| Parser Enel | scaffold v0.1 |
| Parser fallback euristico | scaffold v0.1 |
| Schema SQLite | ✅ v0.1 |
| Dashboard UI | scaffold v0.1 |
| Informativa privacy intra-app | ✅ v0.1 (PRIVACY.md) |
| Alert anomalie | scaffold v0.1 |
| Parser Eni/A2A/Iren | v0.1.1 |
| Parser Vodafone/TIM/Fastweb | v0.1.2 |
| Export CSV deducibili | v0.1.1 |
| Tutorial primo import | v0.2 |

## Riferimenti

- [GDPR art. 2 par. 2 lett. c](https://gdpr-info.eu/art-2-gdpr/) — esenzione domestica
- [README repo Gi.Ve Engine](https://github.com/give-jd/GiveEngine)
