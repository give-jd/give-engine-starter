"""QR recovery v0.2.0 — encoding/decoding mnemonic BIP-39 in QR code.

Permette esportazione/importazione recovery phrase via QR (foto su PC offline,
printable backup, hardware wallet transfer).

Specifiche:
- Payload format: "GIVE-RECOVERY-v1\n<12 parole separate da spazio>"
- QR error correction: H (30% redundancy, sopravvive a foto sfocate/sgualcite)
- QR version: auto-selected dal contenuto (tipicamente 4-6 per 12 parole)
- Encoding: byte mode (UTF-8 NFC)

Dipendenza opzionale: `qrcode[pil]` (PIL/Pillow per rendering immagine).
Decoder opzionale: `pyzbar` o `opencv-python` (NON inclusi per default).
"""

from __future__ import annotations

import io
import re
from typing import Any


PAYLOAD_PREFIX = "GIVE-RECOVERY-v1\n"
_RE_MNEMONIC = re.compile(r"^(?:\S+\s+){11}\S+$")


class QRRecoveryError(Exception):
    pass


def encode_payload(mnemonic: str) -> str:
    parole = mnemonic.strip().split()
    if len(parole) != 12:
        raise QRRecoveryError(f"mnemonic deve avere 12 parole, trovate {len(parole)}")
    normalized = " ".join(p.lower().strip() for p in parole)
    return PAYLOAD_PREFIX + normalized


def decode_payload(payload: str) -> str:
    if not payload.startswith(PAYLOAD_PREFIX):
        raise QRRecoveryError(
            "payload non riconosciuto (manca header GIVE-RECOVERY-v1)"
        )
    body = payload[len(PAYLOAD_PREFIX) :].strip()
    if not _RE_MNEMONIC.match(body):
        raise QRRecoveryError("body non e' una mnemonic 12 parole valida")
    return body


def genera_qr_png(mnemonic: str, box_size: int = 8, border: int = 4) -> bytes:
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_H
    except ImportError as e:
        raise QRRecoveryError(
            "Pacchetto qrcode non installato. pip install 'qrcode[pil]'"
        ) from e

    payload = encode_payload(mnemonic)
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=int(box_size),
        border=int(border),
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def genera_qr_svg(mnemonic: str, box_size: int = 8, border: int = 4) -> str:
    try:
        import qrcode
        import qrcode.image.svg
        from qrcode.constants import ERROR_CORRECT_H
    except ImportError as e:
        raise QRRecoveryError(
            "Pacchetto qrcode non installato. pip install 'qrcode[pil]'"
        ) from e

    payload = encode_payload(mnemonic)
    factory = qrcode.image.svg.SvgImage
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=int(box_size),
        border=int(border),
        image_factory=factory,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image()
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


def decode_qr_image(image_bytes: bytes) -> str:
    decoders = _available_decoders()
    if not decoders:
        raise QRRecoveryError(
            "Nessun decoder QR disponibile. pip install pyzbar oppure opencv-python"
        )

    for _decoder_name, decoder_fn in decoders:
        try:
            payload = decoder_fn(image_bytes)
            if payload:
                return decode_payload(payload)
        except QRRecoveryError:
            raise
        except Exception:
            continue

    raise QRRecoveryError("Nessun QR riconosciuto nell'immagine")


def _available_decoders() -> list[tuple[str, Any]]:
    decoders: list[tuple[str, Any]] = []
    try:
        from pyzbar.pyzbar import decode as _pyzbar_decode

        decoders.append(("pyzbar", lambda b: _decode_with_pyzbar(b, _pyzbar_decode)))
    except ImportError:
        pass
    try:
        import cv2
        import numpy as np

        decoders.append(("opencv", lambda b: _decode_with_opencv(b, cv2, np)))
    except ImportError:
        pass
    return decoders


def _decode_with_pyzbar(image_bytes: bytes, pyzbar_decode: Any) -> str | None:
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    results = pyzbar_decode(img)
    if not results:
        return None
    return results[0].data.decode("utf-8")


def _decode_with_opencv(image_bytes: bytes, cv2: Any, np: Any) -> str | None:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(img)
    return data if data else None
