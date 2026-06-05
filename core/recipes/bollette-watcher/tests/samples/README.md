# Test samples — PDF bollette

⚠️ **MAI committare bollette reali in repo.** Solo PDF anonimizzati con dati fittizi.

Convenzione naming:
- `enel-luce-2026-q1-anon.pdf` — Enel luce trim 1 anonimized
- `eni-gas-2026-feb-anon.pdf` — Eni gas febbraio anonimized

Generazione test PDF anonimizzato:
1. Apri bolletta reale in editor PDF (es. LibreOffice Draw)
2. Sostituisci tutti dati personali con valori dummy
3. Verifica con `pdfminer.six` extract_text che il layout sia preservato
4. Salva in questa cartella

Test usage:
```python
from pdfminer.high_level import extract_text
from parsers import dispatch
text = extract_text("tests/samples/enel-luce-2026-q1-anon.pdf")
parsed = dispatch(text)
assert parsed.parser_usato == "enel"
assert parsed.tipo == "luce"
```
