"""Load and validate the wishlist configuration file."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PREVIEW_CHARS = 120
SUPPORTED_LANGUAGES = ("en", "uk")

# Text shown to visitors: one string for every language, or one per language code
Localized = str | dict[str, str]


class ConfigError(ValueError):
    """The configuration file is missing a field or holds an invalid value."""


@dataclass(frozen=True)
class Item:
    """One thing on the wishlist."""

    id: str
    label: Localized
    description: Localized
    want: int


@dataclass(frozen=True)
class Wishlist:
    """The whole configured wishlist."""

    title: Localized
    subtitle: Localized
    preview_chars: int
    want_min: int
    want_max: int
    items: tuple[Item, ...]

    def has_item(self, item_id: str) -> bool:
        """Return whether an item with this id is configured."""
        return any(item.id == item_id for item in self.items)


def parse_config(raw: dict) -> Wishlist:
    """Build a Wishlist from parsed TOML, raising ConfigError when it is invalid."""
    want = raw.get("want", {})
    want_min = _int(want, "min", "want")
    want_max = _int(want, "max", "want")
    if want_min > want_max:
        raise ConfigError(f"want.min ({want_min}) is greater than want.max ({want_max})")
    items = tuple(
        _parse_item(entry, index, want_min, want_max)
        for index, entry in enumerate(raw.get("items", []))
    )
    ids = [item.id for item in items]
    duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    if duplicates:
        raise ConfigError(f"duplicate item ids: {', '.join(duplicates)}")
    preview_chars = raw.get("preview_chars", DEFAULT_PREVIEW_CHARS)
    if not isinstance(preview_chars, int) or preview_chars < 1:
        raise ConfigError("preview_chars must be a positive integer")
    return Wishlist(
        title=_localized(raw.get("title", "Wishlist"), "title"),
        subtitle=_localized(raw.get("subtitle", ""), "subtitle"),
        preview_chars=preview_chars,
        want_min=want_min,
        want_max=want_max,
        items=items,
    )


def _int(table: dict, key: str, where: str) -> int:
    value = table.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"{where}.{key} must be an integer")
    return value


def _localized(value: object, where: str, *, required: bool = False) -> Localized:
    if isinstance(value, str):
        texts = {"": value.strip()}
    elif isinstance(value, dict) and all(isinstance(v, str) for v in value.values()):
        unknown = sorted(set(value) - set(SUPPORTED_LANGUAGES))
        if unknown:
            supported = ", ".join(SUPPORTED_LANGUAGES)
            raise ConfigError(f"{where}: unknown language {unknown[0]!r}, use {supported}")
        texts = {lang: text.strip() for lang, text in value.items()}
    else:
        raise ConfigError(f"{where} must be a string or a table of strings per language")
    if required and (not texts or not all(texts.values())):
        raise ConfigError(f"{where} must not be empty")
    return texts[""] if "" in texts else texts


def _parse_item(entry: dict, index: int, want_min: int, want_max: int) -> Item:
    where = f"items[{index}]"
    item_id = entry.get("id")
    if not isinstance(item_id, str) or not item_id.strip():
        raise ConfigError(f"{where}.id must be a non-empty string")
    label = _localized(entry.get("label"), f"{where}.label", required=True)
    want = entry.get("want", want_min)
    if not isinstance(want, int) or not want_min <= want <= want_max:
        raise ConfigError(f"{where}.want must be an integer in {want_min}..{want_max}")
    return Item(
        id=item_id.strip(),
        label=label,
        description=_localized(entry.get("description", ""), f"{where}.description"),
        want=want,
    )


class ConfigSource:
    """Reads the config file, re-parsing it only when its mtime changes."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._mtime_ns: int | None = None
        self._wishlist: Wishlist | None = None

    def load(self) -> Wishlist:
        """Return the current wishlist, re-reading the file if it was edited."""
        mtime_ns = self._path.stat().st_mtime_ns
        if self._wishlist is None or mtime_ns != self._mtime_ns:
            with self._path.open("rb") as file:
                try:
                    raw = tomllib.load(file)
                except tomllib.TOMLDecodeError as exc:
                    raise ConfigError(f"{self._path}: {exc}") from exc
            self._wishlist = parse_config(raw)
            self._mtime_ns = mtime_ns
        return self._wishlist
