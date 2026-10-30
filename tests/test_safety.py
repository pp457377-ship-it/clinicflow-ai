import pytest

from app.safety import detect_red_flags


@pytest.mark.parametrize(
    "text,expected",
    [
        ("I have crushing chest pain", "Chest pain / possible heart attack"),
        ("I can't breathe properly", "Breathing difficulty"),
        ("my dad's face is drooping and slurred speech", "Possible stroke"),
        ("I want to kill myself", "Mental health crisis"),
        ("her throat is swelling after a bee sting", "Severe allergic reaction"),
    ],
)
def test_red_flags_detected(text, expected):
    assert expected in detect_red_flags(text)


def test_no_red_flags_for_mild_symptoms():
    assert detect_red_flags("sore throat and runny nose for 2 days") == []
