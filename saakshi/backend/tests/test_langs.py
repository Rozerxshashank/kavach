"""Languages: number words, number-preserving translation checks, and line fallbacks."""

from saakshi import langs, lines


def test_english_digits_groups_pairs_and_digits():
    assert langs.english_digits("ninety-eight thousand seven hundred sixty-five, forty three thousand two hundred ten") == "9876543210"
    assert langs.english_digits("ninety eight seventy six fifty four thirty two ten") == "9876543210"
    assert langs.english_digits("nine eight double seven six five four three two one") == "9877654321"
    assert langs.english_digits("nine eight seven six five four three two one zero") == "9876543210"
    assert langs.english_digits("call me maybe") is None


def test_numbers_in_reads_every_indian_script():
    assert langs.numbers_in("₹3,500 और 26 दिन") == [26, 3500]
    assert langs.numbers_in("৩৫০০ টাকা") == [3500]
    assert langs.numbers_in("௩௫௦௦") == [3500]


def test_other_languages_get_their_own_lines_not_english():
    assert lines.REASK["kn-IN"] != lines.REASK["en-IN"] and len(lines.REASK["kn-IN"]) == 3
    assert lines.ASK["employer_phone"]["bn-IN"] != lines.ASK["employer_phone"]["en-IN"]
    assert "{who}" in lines.ASK["employer_phone"]["bn-IN"]
    assert not lines.WELCOME["mr-IN"].startswith("Hello") and "{name}" in lines.WELCOME["mr-IN"]


def test_readback_says_a_new_employers_number():
    d = {"employer_name": "Raman sir", "employer_phone": "+919876543210", "employer_id": None,
         "period": {"start": "2026-11-01", "end": "2026-11-07", "label": ""}, "amount": 3000, "paid": "yes"}
    assert "98765 43210" in lines.readback([d], "en-IN")
    assert "98765 43210" not in lines.readback([{**d, "employer_id": "e_1"}], "en-IN")


def test_localize_passes_hindi_english_and_native_text_through():
    import asyncio
    assert asyncio.run(langs.localize("Hello", "en-IN")) == "Hello"
    assert asyncio.run(langs.localize("नमस्ते", "hi-IN")) == "नमस्ते"
    assert asyncio.run(langs.localize("வணக்கம் லக்ஷ்மி", "ta-IN")) == "வணக்கம் லக்ஷ்மி"


def test_every_spoken_template_is_translated():
    from saakshi import links, passport, server  # noqa: F401  (register their templates)
    assert all(n == 0 for n in lines.missing_translations().values()), lines.missing_translations()


def test_templates_fill_numbers_after_translation():
    d = {"employer_name": "Raman", "period": {"start": "2026-11-01", "end": "2026-11-08", "label": ""},
         "amount": 4750, "paid": "yes"}
    for lang in ("ta-IN", "kn-IN", "bn-IN", "gu-IN"):
        text = lines.readback([d], lang)
        assert "4,750" in text and "I have noted" not in text


def test_translations_stay_in_their_own_script():
    """Every stored translation passes the build checks: same placeholders and numbers, and only the
    language's own script (the model once slipped Korean words into Kannada lines)."""
    import importlib.util
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("build_i18n", root / "scripts" / "build_i18n.py")
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    for path in (b.LINES_OUT, b.UI_OUT):
        for lang, table in json.loads(path.read_text()).items():
            bad = [v for k, v in table.items() if not b.ok(k, v, lang)]
            assert not bad, f"{path.name} {lang}: {bad[:3]}"
