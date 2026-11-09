from datetime import date

import pytest

from saakshi.numbers import inr, parse_amount, parse_numbers, parse_period, spoken_amount_hi

TODAY = date(2026, 11, 7)  # a Saturday


@pytest.mark.parametrize("text,expected", [
    ("4000", 4000), ("₹4,500", 4500), ("Rs. 1,42,890", 142890), ("४५००", 4500), ("4.5k", 4500), ("4k", 4000),
    ("chaar hazaar", 4000), ("4 hazaar", 4000), ("35 sau", 3500), ("pachees sau", 2500),
    ("saade chaar hazaar", 4500), ("paune paanch hazaar", 4750), ("sava do hazaar", 2250),
    ("dedh sau", 150), ("dedh hazaar", 1500), ("dhai sau", 250), ("dhai lakh", 250000), ("dedh lakh", 150000),
    ("saade teen sau", 350), ("do sau pachaas", 250), ("4 hazaar 500", 4500), ("do lakh pachaas hazaar", 250000),
    ("चार हज़ार", 4000), ("साढ़े चार हज़ार", 4500), ("डेढ़ हज़ार", 1500), ("ढाई सौ", 250),
    ("four thousand five hundred", 4500), ("bees hazaar rupaye", 20000),
    ("Mehta ji ne teen hazaar diye", 3000),
])
def test_amounts(text, expected):
    assert parse_amount(text) == expected


def test_multiple_quantities_stay_separate():
    assert parse_numbers("chhah din, 700 roz") == [6, 700]
    assert parse_numbers("3000 aur 2500") == [3000, 2500]


def test_amount_picks_money_over_day_count():
    assert parse_amount("6 din kaam kiya, 700 ke hisaab se") == 700


def test_inr_grouping():
    assert inr(142890.5) == "₹1,42,891"
    assert inr(4750) == "₹4,750"
    assert inr(250000) == "₹2,50,000"


def test_spoken_hindi_amount():
    assert spoken_amount_hi(4750) == "4 हज़ार 750 रुपये"
    assert spoken_amount_hi(150000) == "1 लाख 50 हज़ार रुपये"


@pytest.mark.parametrize("text,start,end", [
    ("aaj", "2026-11-07", "2026-11-07"),
    ("kal kaam kiya", "2026-11-06", "2026-11-06"),
    ("parso", "2026-11-05", "2026-11-05"),
    ("pichle hafte", "2026-10-26", "2026-11-01"),
    ("is hafte", "2026-11-02", "2026-11-07"),
    ("pichle mahine", "2026-10-01", "2026-10-31"),
    ("is mahine", "2026-11-01", "2026-11-07"),
    ("October", "2026-10-01", "2026-10-31"),
    ("अक्टूबर में", "2026-10-01", "2026-10-31"),
    ("december", "2025-12-01", "2025-12-31"),          # future month => last year
    ("march 2026", "2026-03-01", "2026-03-31"),
])
def test_periods(text, start, end):
    p = parse_period(text, TODAY)
    assert p is not None and p.start.isoformat() == start and p.end.isoformat() == end


def test_unknown_period():
    assert parse_period("kuch din pehle", TODAY) is None


def test_fractions_on_digits_written_by_speech_to_text():
    # Prisma writes "paune paanch hazaar" as "पौने 5,000"
    assert parse_amount("इस महीने मेहता जी के यहाँ खाना बनाया पौने 5,000 मिले।") == 4750
    assert parse_amount("saade 3,000") == 3500
    assert parse_amount("sava 2000") == 2250
    assert parse_amount("पौने 500") == 475
