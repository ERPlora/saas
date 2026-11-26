"""Names put in alphabetical order whatever their language: accents and capitals do not move them."""

from base.collation import collation_key


def test_an_accented_initial_sorts_with_its_letter():
    names = ["Peluquería", "Óptica", "Bar", "Gestoría"]

    assert sorted(names, key=collation_key) == ["Bar", "Gestoría", "Óptica", "Peluquería"]


def test_capitals_do_not_come_first():
    assert sorted(["Café", "bar", "Árbol"], key=collation_key) == ["Árbol", "bar", "Café"]


def test_a_letter_with_its_mark_sits_next_to_the_plain_one():
    assert sorted(["Oman", "Österreich", "Panamá", "Estonia", "España"], key=collation_key) == [
        "España",
        "Estonia",
        "Oman",
        "Österreich",
        "Panamá",
    ]
