"""Import di un CV esistente (PDF/DOCX/ODT) -> estrazione testo + popolamento campi.

Estrazione testo: locale, import lazy delle librerie (se manca, ImportError gestito dall'app).
Parsing strutturato: euristica deterministica (sempre) + AI BYOK opzionale (chiave utente,
chiamata dalla macchina dell'utente — Punto 14: Gi.Ve resta fuori dal flusso).
"""

import io
import re
from copy import deepcopy

SUPPORTED = (".pdf", ".docx", ".odt")


def _ext(filename: str) -> str:
    return ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""


def extract_text(filename: str, data: bytes) -> str:
    ext = _ext(filename)
    if ext == ".pdf":
        from pdfminer.high_level import extract_text as _pdf
        return _pdf(io.BytesIO(data)) or ""
    if ext == ".docx":
        import docx
        doc = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    if ext == ".odt":
        from odf.opendocument import load
        from odf import teletype
        from odf.text import P
        d = load(io.BytesIO(data))
        return "\n".join(teletype.extractText(p) for p in d.getElementsByType(P))
    raise ValueError(f"Formato non supportato: {ext or filename}")


# ---------- euristica locale ----------

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s.-]?)?(?:\d[\s.-]?){8,13}\d")
_LINKEDIN = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/\S+", re.I)

# header di sezione -> chiave interna (match su riga maiuscola/keyword)
_SECTIONS = [
    ("profilo", ("PROFILO", "PROFILE", "SUMMARY", "SOMMARIO", "ABOUT", "CHI SONO", "OBIETTIVO")),
    ("esperienze", ("ESPERIENZ", "WORK EXPERIENCE", "EMPLOYMENT", "ESPERIENZA PROFESSIONALE", "WORK HISTORY")),
    ("istruzione", ("ISTRUZIONE", "EDUCATION", "FORMAZIONE", "STUDI", "TITOLI DI STUDIO")),
    ("competenze", ("COMPETENZ", "SKILLS", "LINGUE", "LANGUAGES", "ABILIT")),
]


def _section_key(line: str):
    up = line.strip().upper()
    if not up or len(up) > 40:
        return None
    for key, kws in _SECTIONS:
        if any(up.startswith(k) or up == k for k in kws):
            return key
    return None


def _looks_like_name(line: str) -> bool:
    words = line.split()
    return (1 < len(words) <= 4
            and all(w[:1].isupper() for w in words)
            and not _EMAIL.search(line) and not any(ch.isdigit() for ch in line))


def _blocks_to_items(section_lines, role_field, org_field):
    """Spezza per righe vuote; ogni blocco -> item con descrizione = testo del blocco.

    L'euristica NON separa ruolo/azienda in modo affidabile: lascia quei campi vuoti
    (l'utente li compila) e conserva tutto il testo in descrizione. Onestà-prima.
    """
    items, block = [], []
    for ln in list(section_lines) + [""]:
        if ln.strip():
            block.append(ln.strip())
        elif block:
            item = {role_field: "", org_field: "", "luogo": "", "dal": "", "al": "",
                    "descrizione": "\n".join(block)}
            if role_field == "ruolo":
                item["corrente"] = False
            items.append(item)
            block = []
    return items


def parse_heuristic(text: str) -> dict:
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    nonempty = [ln for ln in lines if ln.strip()]
    personal = {}

    blob = "\n".join(lines)
    m = _EMAIL.search(blob)
    if m:
        personal["email"] = m.group(0)
    m = _LINKEDIN.search(blob)
    if m:
        personal["linkedin"] = m.group(0)
    # telefono: rimuovi prima l'email dalla riga (spesso email e tel convivono)
    for ln in nonempty[:15]:
        candidate = _EMAIL.sub(" ", ln)
        mp = _PHONE.search(candidate)
        if mp and sum(ch.isdigit() for ch in mp.group(0)) >= 8:
            personal["tel"] = mp.group(0).strip()
            break
    # nome: prima riga "da nome" nelle prime 5
    for ln in nonempty[:5]:
        if _looks_like_name(ln):
            parts = ln.split()
            personal["nome"] = parts[0]
            personal["cognome"] = " ".join(parts[1:])
            break

    # sezioni: raccogli righe sotto ogni header fino al prossimo header
    buckets = {k: [] for k, _ in _SECTIONS}
    cur = None
    for ln in lines:
        key = _section_key(ln)
        if key:
            cur = key
            continue
        if cur:
            buckets[cur].append(ln)

    out = {"personal": personal}
    prof = "\n".join(buckets["profilo"]).strip()
    if prof:
        out["profilo"] = prof
    exp = _blocks_to_items(buckets["esperienze"], "ruolo", "azienda")
    if exp:
        out["esperienze"] = exp
    edu = _blocks_to_items(buckets["istruzione"], "titolo", "istituto")
    if edu:
        out["istruzione"] = edu
    skills_raw = "\n".join(buckets["competenze"]).strip()
    if skills_raw:
        items = [s.strip() for s in re.split(r"[\n,;•·|]", skills_raw) if s.strip()]
        if items:
            out["competenze"] = {"digitali": items}
    return out


# ---------- applicazione al CV ----------

_FILLABLE_PERSONAL = ("nome", "cognome", "email", "tel", "indirizzo",
                      "dataNascita", "nazionalita", "linkedin", "sito")


def apply_import(base: dict, extracted: dict) -> dict:
    out = deepcopy(base)
    ep = extracted.get("personal", {})
    for k in _FILLABLE_PERSONAL:
        if ep.get(k) and not out["personal"].get(k):
            out["personal"][k] = ep[k]
    if extracted.get("profilo") and not out.get("profilo", "").strip():
        out["profilo"] = extracted["profilo"]
    for key in ("esperienze", "istruzione"):
        if extracted.get(key) and not out.get(key):
            out[key] = extracted[key]
    dig = extracted.get("competenze", {}).get("digitali")
    if dig and not out["competenze"]["digitali"]:
        out["competenze"]["digitali"] = dig
    return out


# ---------- AI BYOK (opzionale) ----------

def ai_available() -> bool:
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


_AI_PROMPT = (
    "Estrai i dati del seguente CV in JSON con questo schema esatto (campi vuoti se assenti): "
    '{"personal":{"nome":"","cognome":"","email":"","tel":"","indirizzo":"","dataNascita":"",'
    '"nazionalita":"","linkedin":"","sito":""},"profilo":"",'
    '"esperienze":[{"ruolo":"","azienda":"","luogo":"","dal":"YYYY-MM","al":"YYYY-MM",'
    '"corrente":false,"descrizione":""}],'
    '"istruzione":[{"titolo":"","istituto":"","luogo":"","dal":"YYYY-MM","al":"YYYY-MM","descrizione":""}],'
    '"competenze":{"digitali":[],"soft":[],"lingue":[{"lingua":"","livello":"B2"}]}}'
    " Rispondi SOLO con il JSON, nessun altro testo.\n\nCV:\n"
)


def parse_ai(text: str, api_key):
    """Estrazione AI BYOK. None se chiave/SDK assenti o qualunque errore. Mai solleva."""
    if not api_key or not ai_available():
        return None
    try:
        import json

        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-3-5-haiku-latest", max_tokens=2000,
            messages=[{"role": "user", "content": _AI_PROMPT + text[:12000]}])
        raw = msg.content[0].text.strip()
        raw = raw[raw.find("{"): raw.rfind("}") + 1]
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None
