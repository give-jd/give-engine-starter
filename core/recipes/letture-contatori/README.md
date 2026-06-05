# Letture Contatori

**Tier**: Starter (MIT) · **Slug**: `letture-contatori` · **Versione**: 0.1.0

**Tagline**: *Auto-letture gas, luce, acqua: prepari le bollette, scopri i conguagli.*

Diario delle auto-letture utenze tenuto sul tuo PC. Sai sempre cosa hai comunicato al fornitore, scopri i conguagli abnormi prima della bolletta, eviti stime gonfiate.

## Buyer persona

Famiglia/cittadino con utenze gas/luce/acqua.

## Cosa fa

- CRUD utenze (gas/luce/acqua) con POD/PDR
- Diario letture con foto opzionale (OCR Tesseract opt-in)
- Finestre auto-lettura configurabili per distributore
- Notifiche OS al inizio/fine finestra
- Vista delta consumo + grafico storico

## Companion strettissimo

**`bollette-watcher`** (Starter): diff fra consumo dichiarato dal fornitore e letture comunicate → alert conguagli.

## Stack

- Python 3.10+ + Streamlit
- SQLite locale
- Tesseract OCR (opt-in)
- `core/shared/notifications/`

## Limiti noti v0.1

- Configurazione finestre manuale (sito distributore)
- No API distributori (non esistono pubbliche stabili)
