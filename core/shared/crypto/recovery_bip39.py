"""BIP-39 12-word recovery phrase (wordlist italiana 2048 termini).

Skeleton interface v0.1.0-dev. Implementazione Q3 W28 (8-14 lug 2026).
KAT vectors: vedi `tests/kat/kat_recovery_bip39.py` (10 BIP-39 official).

Riferimenti standard:
- BIP-39 Mnemonic code for generating deterministic keys
- Bitcoin Wiki BIP-39 Italian wordlist (2048 termini canonical)

Wordlist source: `data/bip39-it-2048.txt` (UTF-8 NFC, 1 parola per riga).
"""

from __future__ import annotations

from pathlib import Path


# Path wordlist canonical
WORDLIST_PATH: Path = Path(__file__).parent / "data" / "bip39-it-2048.txt"

# SHA-256 hash atteso wordlist (integrity check al load).
# Computato Pre-Q3 W2 retrofit (29 mag 2026) su wordlist canonical
# bitcoin/bips master/bip-0039/italian.txt (2048 termini UTF-8 NFC).
# Verifica integrity all'import: assertion in test_wordlist.py.
WORDLIST_IT_SHA256: str = (
    "d392c49fdb700a24cd1fceb237c1f65dcc128f6b34a8aacb58b59384b5c648c2"
)

# Wordlist canonical source URL (per audit reproducibility)
WORDLIST_SOURCE_URL: str = (
    "https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/italian.txt"
)

# Numero parole standard BIP-39 12-word phrase
PHRASE_LEN: int = 12

# Entropia BIP-39 12-word = 128 bit + 4 bit checksum
ENTROPY_BITS: int = 128
ENTROPY_BYTES: int = ENTROPY_BITS // 8  # 16 byte


import functools  # noqa: E402
import hashlib  # noqa: E402
import secrets  # noqa: E402
import unicodedata  # noqa: E402

from core.shared.crypto.exceptions import InvalidRecovery  # noqa: E402

# BIP-39 standard PBKDF2 params
_PBKDF2_ITERATIONS: int = 2048
_PBKDF2_HASH: str = "sha512"
_SEED_LEN_BYTES: int = 64


@functools.lru_cache(maxsize=1)
def _load_wordlist() -> tuple[list[str], dict[str, int]]:
    """Carica wordlist BIP-39 IT. Cached + integrity check SHA-256."""
    raw = WORDLIST_PATH.read_bytes()
    actual_hash = hashlib.sha256(raw).hexdigest()
    if actual_hash != WORDLIST_IT_SHA256:
        raise InvalidRecovery(
            f"Wordlist SHA-256 mismatch: expected {WORDLIST_IT_SHA256}, "
            f"got {actual_hash}"
        )
    words = [
        unicodedata.normalize("NFC", line.strip())
        for line in raw.decode("utf-8").splitlines()
        if line.strip()
    ]
    if len(words) != 2048:
        raise InvalidRecovery(f"Wordlist length != 2048: {len(words)}")
    index = {w: i for i, w in enumerate(words)}
    return words, index


def generate_recovery_phrase() -> list[str]:
    """Genera 12 parole BIP-39 italiane.

    Process:
    1. Random 128 bit entropy via secrets.token_bytes(16)
    2. Compute SHA-256 checksum 4 bit
    3. Split 132 bit in 12 gruppi da 11 bit
    4. Map ogni gruppo a parola wordlist italiana

    Returns:
        12 parole BIP-39 italiane (lowercase, no accent).
    """
    entropy = secrets.token_bytes(ENTROPY_BYTES)
    return entropy_to_phrase(entropy)


def entropy_to_phrase(entropy: bytes) -> list[str]:
    """Converte 16 byte entropy → 12 parole BIP-39 italiane.

    Pure function determinista. BIP-39 spec:
    - Entropy bits + SHA-256 checksum first 4 bit (= ENT/32)
    - Split bit stream in 11-bit indices
    - Map ogni indice a wordlist[idx]
    """
    if len(entropy) != ENTROPY_BYTES:
        raise InvalidRecovery(
            f"Entropy must be {ENTROPY_BYTES} byte, got {len(entropy)}"
        )
    words, _ = _load_wordlist()

    # Compute checksum: first ENT/32 = 128/32 = 4 bit of SHA-256(entropy)
    checksum_byte = hashlib.sha256(entropy).digest()[0]
    checksum_bits = checksum_byte >> 4  # high 4 bit

    # Combine entropy (128 bit) + checksum (4 bit) = 132 bit
    bit_stream = int.from_bytes(entropy, "big") << 4 | checksum_bits

    # Extract 12 indici 11-bit (high-to-low)
    indices: list[int] = []
    for i in range(PHRASE_LEN):
        shift = (PHRASE_LEN - 1 - i) * 11
        idx = (bit_stream >> shift) & 0x7FF  # 0x7FF = 2047 (11-bit mask)
        indices.append(idx)

    return [words[i] for i in indices]


def verify_phrase(phrase: list[str]) -> bool:
    """Valida 12 parole BIP-39 + checksum.

    Returns:
        True se phrase valida + checksum OK, False altrimenti.
    """
    if not isinstance(phrase, list) or len(phrase) != PHRASE_LEN:
        return False
    try:
        _, index = _load_wordlist()
    except InvalidRecovery:
        return False

    # Lookup indici
    indices: list[int] = []
    for w in phrase:
        if not isinstance(w, str):
            return False
        norm = unicodedata.normalize("NFC", w.lower().strip())
        if norm not in index:
            return False
        indices.append(index[norm])

    # Ricostruisci bit stream 132 bit
    bit_stream = 0
    for idx in indices:
        bit_stream = (bit_stream << 11) | idx

    # Estrai entropy 128 bit + checksum 4 bit
    checksum_bits = bit_stream & 0xF
    entropy_int = bit_stream >> 4
    entropy = entropy_int.to_bytes(ENTROPY_BYTES, "big")

    # Recompute checksum
    expected_checksum = hashlib.sha256(entropy).digest()[0] >> 4
    return checksum_bits == expected_checksum


def phrase_to_seed(phrase: list[str], passphrase: str = "") -> bytes:
    """Deriva seed 64 byte da phrase BIP-39.

    Algoritmo standard BIP-39: PBKDF2-HMAC-SHA512 2048 iterazioni.
    Mnemonic input = " ".join(phrase) normalizzato NFKD.
    Salt = "mnemonic" + passphrase NFKD.
    """
    mnemonic_str = unicodedata.normalize("NFKD", " ".join(phrase))
    salt_str = unicodedata.normalize("NFKD", "mnemonic" + passphrase)
    # NOTA SICUREZZA: 2048 iterazioni NON sono un parametro di password-hashing
    # da rafforzare, ma il valore IMPOSTO dallo standard BIP-39 (sez. "From
    # mnemonic to seed") per PBKDF2-HMAC-SHA512. Cambiarlo romperebbe
    # l'interoperabilità con qualsiasi wallet/strumento BIP-39. La robustezza
    # qui deriva dall'entropia del mnemonic (128/256 bit), non dalle iterazioni.
    # Avviso "use >= 100000 iterations" (es. SonarQube): falso positivo nel
    # contesto BIP-39.
    return hashlib.pbkdf2_hmac(  # NOSONAR S5344 - BIP-39 mandates 2048 iterations
        hash_name=_PBKDF2_HASH,
        password=mnemonic_str.encode("utf-8"),
        salt=salt_str.encode("utf-8"),
        iterations=_PBKDF2_ITERATIONS,
        dklen=_SEED_LEN_BYTES,
    )
