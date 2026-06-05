"""Tests QR recovery v0.2.0."""

from __future__ import annotations

import pytest

from core.shared.crypto import qr_recovery
from core.shared.crypto.qr_recovery import (
    PAYLOAD_PREFIX,
    QRRecoveryError,
    decode_payload,
    encode_payload,
)


MNEMONIC_OK = (
    "abaco abbaglio abbinato abete abisso abolire abrasivo accadere "
    "accenno accusato acetone acido"
)


class TestEncodePayload:
    def test_ok(self):
        payload = encode_payload(MNEMONIC_OK)
        assert payload.startswith(PAYLOAD_PREFIX)
        body = payload[len(PAYLOAD_PREFIX) :]
        assert body == MNEMONIC_OK

    def test_normalizza_lowercase(self):
        upper = " ".join(p.upper() for p in MNEMONIC_OK.split())
        payload = encode_payload(upper)
        assert MNEMONIC_OK in payload

    def test_normalizza_spazi(self):
        with_extra_spaces = "  " + "   ".join(MNEMONIC_OK.split()) + "  "
        payload = encode_payload(with_extra_spaces)
        body = payload[len(PAYLOAD_PREFIX) :]
        assert body == MNEMONIC_OK

    def test_lunghezza_invalida_11(self):
        short = " ".join(MNEMONIC_OK.split()[:11])
        with pytest.raises(QRRecoveryError, match="12 parole"):
            encode_payload(short)

    def test_lunghezza_invalida_13(self):
        long = MNEMONIC_OK + " extra"
        with pytest.raises(QRRecoveryError, match="12 parole"):
            encode_payload(long)

    def test_vuoto(self):
        with pytest.raises(QRRecoveryError, match="12 parole"):
            encode_payload("")


class TestDecodePayload:
    def test_roundtrip(self):
        payload = encode_payload(MNEMONIC_OK)
        out = decode_payload(payload)
        assert out == MNEMONIC_OK

    def test_header_mancante(self):
        with pytest.raises(QRRecoveryError, match="header"):
            decode_payload("not a recovery payload")

    def test_body_corrupt(self):
        bad = PAYLOAD_PREFIX + "solo due parole"
        with pytest.raises(QRRecoveryError, match="12 parole"):
            decode_payload(bad)

    def test_body_parole_extra(self):
        bad = PAYLOAD_PREFIX + MNEMONIC_OK + " tredicesima"
        with pytest.raises(QRRecoveryError):
            decode_payload(bad)

    def test_versione_futura_rifiutata(self):
        bad = "GIVE-RECOVERY-v2\n" + MNEMONIC_OK
        with pytest.raises(QRRecoveryError, match="header"):
            decode_payload(bad)


class TestGeneraQR:
    def test_genera_qr_png_dipendenza_opzionale(self):
        pytest.importorskip("qrcode")
        png = qr_recovery.genera_qr_png(MNEMONIC_OK)
        assert isinstance(png, bytes)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_genera_qr_png_box_size_custom(self):
        pytest.importorskip("qrcode")
        png_small = qr_recovery.genera_qr_png(MNEMONIC_OK, box_size=4)
        png_large = qr_recovery.genera_qr_png(MNEMONIC_OK, box_size=12)
        assert len(png_small) < len(png_large)

    def test_genera_qr_svg(self):
        pytest.importorskip("qrcode")
        svg = qr_recovery.genera_qr_svg(MNEMONIC_OK)
        assert isinstance(svg, str)
        assert "<svg" in svg

    def test_genera_qr_invalid_mnemonic(self):
        pytest.importorskip("qrcode")
        with pytest.raises(QRRecoveryError, match="12 parole"):
            qr_recovery.genera_qr_png("solo tre parole")


class TestDecodeQRImageNoDecoder:
    def test_no_decoder_disponibile(self, monkeypatch):
        monkeypatch.setattr(qr_recovery, "_available_decoders", lambda: [])
        with pytest.raises(QRRecoveryError, match="decoder"):
            qr_recovery.decode_qr_image(b"fake-image-bytes")

    def test_no_qr_in_image(self, monkeypatch):
        def fake_decoders():
            return [("fake", lambda b: None)]

        monkeypatch.setattr(qr_recovery, "_available_decoders", fake_decoders)
        with pytest.raises(QRRecoveryError, match="Nessun QR"):
            qr_recovery.decode_qr_image(b"fake-image-bytes")


class TestDecodeQRWithMockedDecoder:
    def test_decoder_ritorna_payload_valido(self, monkeypatch):
        valid_payload = encode_payload(MNEMONIC_OK)

        def fake_decoders():
            return [("mock", lambda b: valid_payload)]

        monkeypatch.setattr(qr_recovery, "_available_decoders", fake_decoders)
        result = qr_recovery.decode_qr_image(b"image-bytes")
        assert result == MNEMONIC_OK

    def test_decoder_ritorna_payload_invalido(self, monkeypatch):
        def fake_decoders():
            return [("mock", lambda b: "random-non-recovery-payload")]

        monkeypatch.setattr(qr_recovery, "_available_decoders", fake_decoders)
        with pytest.raises(QRRecoveryError, match="header"):
            qr_recovery.decode_qr_image(b"image-bytes")

    def test_decoder_fallback_dopo_eccezione(self, monkeypatch):
        valid_payload = encode_payload(MNEMONIC_OK)

        def fake_decoders():
            def broken(b):
                raise RuntimeError("decoder crashed")

            return [("broken", broken), ("works", lambda b: valid_payload)]

        monkeypatch.setattr(qr_recovery, "_available_decoders", fake_decoders)
        result = qr_recovery.decode_qr_image(b"image-bytes")
        assert result == MNEMONIC_OK


class TestPayloadFormat:
    def test_payload_e_ascii_safe(self):
        payload = encode_payload(MNEMONIC_OK)
        payload.encode("ascii")

    def test_payload_size_realistico(self):
        payload = encode_payload(MNEMONIC_OK)
        assert len(payload) < 200

    def test_prefix_costante(self):
        assert PAYLOAD_PREFIX == "GIVE-RECOVERY-v1\n"
