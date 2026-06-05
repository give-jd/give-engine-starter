# Gi.Ve Engine — Starter Kit

> Il motore IA che accelera il tuo business.

Versione **gratuita** e **open-source** di Gi.Ve Engine. Trasforma le tue
idee in software vero, sul tuo computer, in meno di un minuto. Nessun
account, nessun cloud, nessuna telemetria.

## Installazione one-liner

**macOS / Linux**
```bash
curl -fsSL https://engine.givegroup.it/install.sh | bash
```

**Windows (PowerShell)**
```powershell
iwr -useb https://engine.givegroup.it/install.ps1 | iex
```

Dopo l'installazione lancia con:
```bash
givengine start
```

Si apre automaticamente la **Cabina di Regia** sul tuo browser
(`http://localhost:5000`). Da lì scegli una ricetta e parti.

## Cosa include lo Starter

- ✅ **Hardware Checker** — capisce se il tuo PC può far girare l'IA in locale
- ✅ **Caveman Optimizer base** — riduzione del contesto LLM per risparmiare token API
- ✅ **Cabina di Regia** — interfaccia web locale, no terminale, no IDE
- ✅ **1 ricetta inclusa**: *Gestione Spese Familiari* (app web personale con
  database locale, grafici, export Excel)
- ✅ **Supporto community** via GitHub Issues
- ✅ **Codice 100% leggibile**: Python + HTML + Tailwind. Niente magia nera.

## Cosa NON include (riservato al Catalogo)

- 🔒 **Catalogo ricette completo** (Landing SaaS, Domotica, Mini E-commerce, Agenda Clienti…)
- 🔒 **Caveman Optimizer Pro** con compressione kanji (~50% token saved)
- 🔒 **Nuove ricette ogni mese**
- 🔒 **Supporto via email** + **onboarding 1-to-1**
- 🔒 **Ricette premium esclusive** e **early access**

> Sblocca il catalogo da €49/mese o l'All-Access annuale a €490/anno
> (equivalente a €40,80/mese) su **https://engine.givegroup.it/#pricing**

## Architettura veloce

```
~/.givengine/
├── core/
│   ├── orchestrator.py    # FastAPI + WebSocket su :5000
│   ├── checker.py         # Hardware diagnostics
│   ├── caveman_optimizer.py
│   ├── templates/ui.html  # Cabina di Regia (HTML statico)
│   └── recipes/
│       └── spese-casalinghe/   # tier: starter
├── installer/             # gli script che ti hanno portato qui
├── requirements.txt
└── LICENSE                # MIT
```

## Sviluppo locale (per chi vuole contribuire)

```bash
git clone https://github.com/give-jd/give-engine-starter.git
cd give-engine-starter
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m core.orchestrator
```

Le ricette sono in `core/recipes/<id>/`. Schema:

- `recipe.yaml` — metadata + domande human-in-the-loop
- `inject.py` — produce il progetto utente da `templates/`
- `ui_states.json` — sequenza di messaggi WebSocket per la Cabina
- `templates/` — file Jinja
- `caveman_human.md` + `tutorial.md` — briefing agente + guida utente

## Aggiornamento

```bash
givengine update    # git pull --ff-only nel repo locale
```

## Licenza

[MIT License](LICENSE) — usalo, modificalo, ridistribuiscilo. Conserva
l'attribuzione.

## Editore

**GI.VE GROUP S.R.L.**
Via Carlo Fabani 18/B · 23017 Morbegno (SO) · Italia
P.IVA / C.F. **01088150147** · R.E.A. **SO-81817** · PEC **gi.ve@pec.it** · SDI **USAL8PV**

🌍 **https://engine.givegroup.it** — *Costruito in Valtellina*
