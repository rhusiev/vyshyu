import pytest

from wishlist.config import ConfigError, parse_config

WANT = {"min": 1, "max": 3}


def test_item_defaults_to_lowest_want_and_empty_description() -> None:
    wishlist = parse_config({"want": WANT, "items": [{"id": "a", "label": "A"}]})

    assert wishlist.items[0].want == 1
    assert wishlist.items[0].description == ""


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"want": {"min": 3, "max": 1}}, "greater than"),
        ({"want": {"min": 1}}, "want.max"),
        ({"want": WANT, "items": [{"id": "a", "label": "A", "want": 4}]}, "want"),
        ({"want": WANT, "items": [{"id": "a", "label": " "}]}, "label"),
        ({"want": WANT, "items": [{"id": "a", "label": {"en": "A", "uk": ""}}]}, "label"),
        ({"want": WANT, "items": [{"id": "a", "label": {"ua": "A"}}]}, "unknown language 'ua'"),
        ({"want": WANT, "items": [{"id": "a", "label": 5}]}, "label"),
        ({"want": WANT, "items": [{"label": "A"}]}, "id"),
        (
            {"want": WANT, "items": [{"id": "a", "label": "A"}, {"id": "a", "label": "B"}]},
            "duplicate item ids: a",
        ),
        ({"want": WANT, "preview_chars": 0}, "preview_chars"),
    ],
)
def test_invalid_config_is_rejected(raw: dict, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_config(raw)


def test_text_can_be_given_per_language() -> None:
    wishlist = parse_config(
        {
            "title": {"en": "Wishlist", "uk": "Список бажань"},
            "want": WANT,
            "items": [{"id": "a", "label": {"en": " Pen ", "uk": "Ручка"}, "description": "x"}],
        }
    )

    assert wishlist.title == {"en": "Wishlist", "uk": "Список бажань"}
    assert wishlist.items[0].label == {"en": "Pen", "uk": "Ручка"}
    assert wishlist.items[0].description == "x"
