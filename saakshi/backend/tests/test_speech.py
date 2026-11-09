import asyncio

from saakshi import speech


def test_roman_names_are_spoken_in_devanagari(monkeypatch):
    async def no_llm(*a, **k):
        raise AssertionError("seeded names must not need the model")
    monkeypatch.setattr(speech.llm, "chat_json", no_llm)
    out = asyncio.run(speech.for_speech("नमस्ते Khanna जी, Lakshmi जी का OTP कभी नहीं माँगा जाता।", "hi-IN"))
    assert out == "नमस्ते खन्ना जी, लक्ष्मी जी का OTP कभी नहीं माँगा जाता।"


def test_english_and_unknown_languages_are_untouched():
    assert asyncio.run(speech.for_speech("Hello Khanna ji", "en-IN")) == "Hello Khanna ji"
    assert asyncio.run(speech.for_speech("Namaste Khanna", "xx-IN")) == "Namaste Khanna"


def test_a_failing_model_never_blocks_speech(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("quota")
    monkeypatch.setattr(speech.llm, "chat_json", boom)
    monkeypatch.setattr(speech, "_save", lambda: None)
    assert asyncio.run(speech.for_speech("नमस्ते Zorawarpreet जी", "hi-IN")) == "नमस्ते Zorawarpreet जी"
