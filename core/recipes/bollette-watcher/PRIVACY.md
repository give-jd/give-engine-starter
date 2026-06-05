# Bollette Watcher — Privacy

**Mostrata al primo lancio della ricetta. Checkbox "Ho letto e capito" → flag in preferences.json.**

## Come tratta i tuoi dati questa ricetta

I PDF delle tue bollette restano sul tuo PC. Vengono letti in locale da Gi.Ve Engine per estrarre consumi e importi. **Niente viene inviato a Gi.Ve Group, ai fornitori delle utenze o a terzi.**

I dati estratti sono salvati in un database SQLite locale (`~/.givengine/data/bollette-watcher.db`). Puoi cancellare tutto in qualsiasi momento dalla dashboard, oppure eliminando direttamente il file.

## Inquadramento GDPR

### Bollette intestate a te (uso personale)

L'art. 2 par. 2 lett. c GDPR esclude dall'ambito applicativo del Regolamento i trattamenti effettuati da una persona fisica per attività **a carattere esclusivamente personale o domestico** ("esenzione domestica"). Importare e analizzare le proprie bollette per scopi privati rientra in questa esenzione.

### Bollette intestate a terzi (uso professionale)

⚠️ Se importi bollette intestate ad **altri soggetti** (es. consulente energetico che gestisce utenze di clienti), l'esenzione domestica **decade**. Diventi **Titolare del trattamento** ai sensi del GDPR e assumi i relativi obblighi:

- Base giuridica per il trattamento (contratto, consenso, legittimo interesse)
- Informativa privacy verso i tuoi clienti
- Registro dei trattamenti (se sei tenuto a tenerlo)
- Risposta a richieste di accesso/cancellazione/portabilità dei tuoi clienti
- Eventuale DPIA se trattamento "su larga scala"

**Gi.Ve Group S.R.L. NON è né titolare né responsabile** del trattamento dei dati nella ricetta. Fornisce esclusivamente il software che gira sul tuo dispositivo.

## Cosa NON facciamo

- Non riceviamo i tuoi PDF
- Non riceviamo i dati estratti
- Non ti tracciamo nell'uso della ricetta
- Non vendiamo né analizziamo aggregati di consumi
- Non sappiamo nemmeno se la ricetta è installata sul tuo PC

## Diritto all'oblio immediato

Dashboard → menu → **Cancella tutto** → conferma → DB rimosso + cartella eliminata. Verifica filesystem se vuoi essere certo:

```bash
ls ~/.givengine/data/bollette-watcher.db
# nessun output = file cancellato
```

## Riferimenti

- GDPR art. 2 par. 2 lett. c — esenzione domestica
- GDPR art. 24 — Titolare del trattamento
- Garante Privacy https://www.garanteprivacy.it/

---

**Ultimo aggiornamento**: 24 maggio 2026 · versione 1.0
