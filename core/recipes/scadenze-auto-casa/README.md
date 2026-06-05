# Scadenze Auto/Casa

**Tier**: Starter (MIT) · **Slug**: `scadenze-auto-casa` · **Versione**: 0.1.0

**Tagline**: *Bollo, revisione, caldaia, assicurazione: non ti scordi più nulla.*

Tracker e promemoria delle scadenze ricorrenti italiane: bollo regionale, revisione 4+2+2, RCA, caldaia annuale DPR 74/2013, antincendio, ascensore. Notifiche sul tuo computer, non nel cloud di qualcuno.

## Buyer persona

Cittadino italiano con auto + casa: gestisce scadenze ricorrenti che oggi tiene su Calendar/post-it/memoria.

## Cosa fa

- CRUD scadenze categorizzate (auto / casa / persona)
- Template italiani precaricati (opt-in selettivo)
- Notifiche OS native multi-piattaforma
- Storico pagamenti per detrazioni fiscali
- Export CSV annuale

## Stack

- Python 3.10+ + Streamlit
- SQLite locale (no cifratura — dati personali utente)
- `core/shared/notifications/` per OS native

## Sinergie

- `spese-casalinghe`: prompt opt-in mark-paid → registra spesa
- `osservaprezzi-carburanti`: cross-card pieno conveniente prima del bollo

## Installazione

```bash
givengine recipes install scadenze-auto-casa
```

## Limiti noti v0.1

- Importi bollo non auto-aggiornati (manutenzione tabelle ACI insostenibile)
- Detection auto da foto libretto: differita v0.4

## Riferimenti

- DPR 74/2013 (controlli caldaia)
- D.Lgs 285/1992 (Codice della Strada — revisione)
- Codice Assicurazioni Private 209/2005 (RCA)
