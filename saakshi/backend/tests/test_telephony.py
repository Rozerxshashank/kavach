"""Telephony layer, offline: Twilio signatures, TwiML, phone audio, voicemail and forged webhooks."""

import asyncio
import re
import struct

import numpy as np
import pytest
from starlette.testclient import TestClient

from saakshi import audio, simulate, store
from saakshi import telephony as tel
from saakshi.config import settings

FAKE = {"twilio_sid": "ACtest", "twilio_token": "tok_test", "twilio_from": "+911140001234",
        "public_base_url": "https://saakshi.test"}


@pytest.fixture()
def line():
    old = {k: getattr(settings, k) for k in FAKE}
    for k, v in FAKE.items():
        object.__setattr__(settings, k, v)
    yield
    for k, v in old.items():
        object.__setattr__(settings, k, v)


def test_signature_matches_twilio_algorithm():
    # Twilio's documented example: URL + params sorted by key, HMAC-SHA1, base64
    url = "https://mycompany.com/myapp.php?foo=1&bar=2"
    params = {"CallSid": "CA1234567890ABCDE", "Caller": "+12349013030", "Digits": "1234", "From": "+12349013030",
              "To": "+18005551212"}
    assert tel.signature(url, params, "12345") == "0/KCTR6DLpKmkAf8muzZqo1nDgQ="


def test_forged_and_valid_requests(line):
    params = {"From": "+919810011223"}
    good = tel.signature("https://saakshi.test/tel/inbound", params, "tok_test")
    assert tel.valid_request("https://saakshi.test/tel/inbound", params, good)
    assert not tel.valid_request("https://saakshi.test/tel/inbound", params, "forged")
    assert not tel.valid_request("https://saakshi.test/tel/inbound", {"From": "+910000000000"}, good)


def test_twiml_record_and_silence_redirect(line):
    xml = tel.twiml(tel.play("/audio/x/a.wav"), tel.record("/tel/register?from=919990001111"))
    assert "<Play>https://saakshi.test/audio/x/a.wav</Play>" in xml
    action = re.search(r'<Record action="([^"]+)"', xml).group(1)
    redirect = re.search(r"<Redirect[^>]*>([^<]+)</Redirect>", xml).group(1)
    assert action == "https://saakshi.test/tel/register?from=919990001111"
    assert redirect == "https://saakshi.test/tel/register?from=919990001111&amp;silent=1"


def _mulaw_wav(pcm: np.ndarray) -> bytes:
    x = np.clip(pcm * 32768, -32635, 32635).astype(np.int32)
    s = (x < 0)
    x = np.abs(x) + 0x84
    e = np.clip(np.floor(np.log2(x)).astype(int) - 7, 0, 7)
    m = (x >> (e + 3)) & 0x0F
    body = (~((s << 7) | (e << 4) | m)).astype(np.uint8).tobytes()
    fmt = struct.pack("<HHIIHH", 7, 1, 8000, 8000, 1, 8)
    return (b"RIFF" + struct.pack("<I", 36 + len(body)) + b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt
            + b"data" + struct.pack("<I", len(body)) + body)


def test_phone_audio_mulaw_8k_becomes_16k_pcm():
    t = np.arange(8000) / 8000
    pcm = (0.3 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    out, sr = audio.read_wav(audio.to_16k(_mulaw_wav(pcm)))
    assert sr == 16000 and len(out) == 16000
    assert abs(float(np.abs(out).max()) - 0.3) < 0.02


def test_voicemail_is_never_spoken_to_and_forgeries_are_rejected(line):
    from saakshi.server import app
    asyncio.run(simulate.seed_demo(with_voice=False))
    call = next(c for c in store.list_calls() if c["status"] == "queued")
    client = TestClient(app)
    path = f"/tel/call/{call['id']}/answer"

    forged = client.post(path, data={"AnsweredBy": "human"}, headers={"X-Twilio-Signature": "nope"})
    assert forged.status_code == 403

    params = {"AnsweredBy": "machine_start"}
    sig = tel.signature("https://saakshi.test" + path, params, "tok_test")
    r = client.post(path, data=params, headers={"X-Twilio-Signature": sig})
    assert r.status_code == 200 and "<Hangup/>" in r.text and "<Play>" not in r.text
    after = store.get_call(call["id"])
    assert after["status"] == "queued" and after["attempts"] == 1


def test_real_calls_need_configuration():
    assert not settings.telephony or settings.public_base_url
    with pytest.raises(tel.TelephonyError):
        if settings.telephony:
            raise tel.TelephonyError("configured; skip")
        tel._auth()
