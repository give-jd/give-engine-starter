# Gi.Ve Engine — Icon Design Brief

Brief tecnico per il/la designer che produrrà l'icona finale dell'app
multi-piattaforma. Sostituisce il placeholder generato proceduralmente
in `installer/resources/`.

## Identità del prodotto

- **Nome**: Gi.Ve Engine
- **Tagline**: *Il motore IA che accelera il tuo business*
- **Editore**: Gi.Ve Group S.R.L. (Valtellina, Italia)
- **Personalità**: tecnico-italiano, pulito, dark-mode-native, gradient
  multi-tonali ma sobri. Non-cartoonish.
- **Mercato target**: micro-imprese italiane non-tecniche + sviluppatori
  che cercano scaffolding rapido.

## Palette ufficiale

| Token | Hex | Uso |
|---|---|---|
| `--brand-violet`   | `#7C3AED` | gradient start, accenti primari |
| `--brand-cyan`     | `#06B6D4` | gradient end, link, highlight |
| `--brand-ink`      | `#020A12` | sfondo dark, testo su chiaro |
| `--brand-cyan-soft` | `#22D3EE` | secondario / hover |

Gradient principale: **diagonale top-left → bottom-right**,
`#7C3AED → #06B6D4`. È lo stesso usato nel logo testuale,
nei bottoni CTA, nei toggle attivi.

## File da produrre

Il/la designer consegna **una sorgente vettoriale singola** (Figma o
`.svg` editabile) da cui esportiamo:

| File | Risoluzione | Note |
|---|---|---|
| `icon.svg`      | vector master | sorgente, conservata nel repo |
| `icon.icns`     | macOS (ic09 512 + ic10 1024) | usare `iconutil` |
| `icon.ico`      | Windows multi-res 16/24/32/48/64/128/256 | hinted small sizes |
| `icon.png`      | 512×512 | Linux .desktop, generico web |
| `icon-1024.png` | 1024×1024 | App Store, social, marketing |

Per macOS rispettare la safe area Apple: il glifo principale resta
nell'80% centrale; ai bordi sono OK ombre/gradient ma il segno deve
respirare.

## Forma del segno

- **Base**: rounded square Apple-style, raggio = **22% del lato**
  (esempio 1024 → r ≈ 225). Stesso radius del macOS Big Sur+ standard.
- **Bevel/inner highlight**: lieve highlight bianco al 15-18% alfa nel
  terzo superiore della tile. Non drammatico, solo per "stacco" su
  fondi chiari.
- **Glifo centrale**: lettera **"G"** maiuscola, white solid `#FFFFFF`.
  Font Inter ExtraBold o Space Grotesk Bold. Peso visivo 60-65% del lato
  della tile. Centrata otticamente (≈ 1-2 % più alta del centro
  geometrico).
- **Glow soft white** (~ stdDev 20px su 1024) dietro il glifo per
  staccare dal gradient.
- **Drop shadow** del glifo: dy ≈ 1.5% del lato, blur ≈ 1.2% del lato,
  alfa 35-55%.
- **Accent dot bianco** in basso-destra (≈ 38px su 1024) — rappresenta
  la "." nel marchio Gi.Ve. Posizione X≈80%, Y≈78%. Bianco al 92% alfa.
  Mantiene la lettura "Gi.Ve" anche nei contesti molto piccoli (16px
  diventerà solo G + dot).

## Riferimento procedurale (interim)

Il file `installer/resources/icon.svg` contiene il vector di
riferimento attuale (DejaVu Sans Bold come glifo, tutto il resto come
specificato sopra). Lo si può aprire in qualsiasi editor vettoriale e
sostituire il `<text>` con un path custom della G. I file binari
PNG/ICO/ICNS sono raster output dello script Pillow (vedi commit
`81d3baf` per la build attuale).

## Cosa NON fare

- ❌ Niente emoji o disegni illustrativi.
- ❌ Niente faccine, robot, ingranaggi: il "motore" è metaforico, non
  letterale.
- ❌ No outline / "outlined" style. Solid fills.
- ❌ No texture rumorosa / noise / grain.
- ❌ No più di tre colori (gradient = 2 stop max). Bianco è il quarto.

## Approvazione

Il segno definitivo deve mantenere le seguenti garanzie:

1. **Leggibilità a 16×16**: la G deve restare riconoscibile come tale,
   o sostituibile con il solo dot accent quando G non scala.
2. **Coerenza con la landing**: il gradient deve essere lo stesso visto
   in hero CTA pricing di `engine.givegroup.it` (nei colori).
3. **Apple HIG compliance**: superare il check automatico
   `iconutil -c icns` senza warning sulle dimensioni.

## Asset di riferimento

- Landing live: https://engine.givegroup.it
- Repo: https://github.com/give-jd/GiveEngine
- Vector master interim: `installer/resources/icon.svg`
- Raster current: `installer/resources/icon.png` (512), `icon-1024.png`

---

© Gi.Ve Group S.R.L. — engine@givegroup.it
