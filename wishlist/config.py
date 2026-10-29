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
class Group:
    """A foldable section of items. The ungrouped items form one with no id or label."""

    id: str | None
    label: Localized | None
    is_folded: bool
    items: tuple[Item, ...]


@dataclass(frozen=True)
class Wishlist:
    """The whole configured wishlist."""

    title: Localized
    subtitle: Localized
    preview_chars: int
    default_language: str | None
    want_min: int
    want_max: int
    groups: tuple[Group, ...]

    @property
    def items(self) -> list[Item]:
        """Every item, in display order."""
        return [item for group in self.groups for item in group.items]

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
    ungrouped = _parse_items(raw.get("items", []), "items", want_min, want_max)
    groups = [
        _parse_group(entry, f"groups[{index}]", want_min, want_max)
        for index, entry in enumerate(raw.get("groups", []))
    ]
    if ungrouped:
        groups.insert(0, Group(id=None, label=None, is_folded=False, items=ungrouped))
    _reject_duplicates([g.id for g in groups if g.id is not None], "group")
    _reject_duplicates([item.id for group in groups for item in group.items], "item")
    preview_chars = raw.get("preview_chars", DEFAULT_PREVIEW_CHARS)
    if not isinstance(preview_chars, int) or preview_chars < 1:
        raise ConfigError("preview_chars must be a positive integer")
    default_language = raw.get("default_language")
    if default_language is not None and default_language not in SUPPORTED_LANGUAGES:
        supported = ", ".join(SUPPORTED_LANGUAGES)
        raise ConfigError(f"default_language must be one of {supported}")
    return Wishlist(
        title=_localized(raw.get("title", "Wishlist"), "title"),
        subtitle=_localized(raw.get("subtitle", ""), "subtitle"),
        preview_chars=preview_chars,
        default_language=default_language,
        want_min=want_min,
        want_max=want_max,
        groups=tuple(groups),
    )


def _reject_duplicates(ids: list[str], kind: str) -> None:
    duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    if duplicates:
        raise ConfigError(f"duplicate {kind} ids: {', '.join(duplicates)}")


def _parse_group(entry: dict, where: str, want_min: int, want_max: int) -> Group:
    group_id = entry.get("id")
    if not isinstance(group_id, str) or not group_id.strip():
        raise ConfigError(f"{where}.id must be a non-empty string")
    is_folded = entry.get("folded", False)
    if not isinstance(is_folded, bool):
        raise ConfigError(f"{where}.folded must be true or false")
    return Group(
        id=group_id.strip(),
        label=_localized(entry.get("label"), f"{where}.label", required=True),
        is_folded=is_folded,
        items=_parse_items(entry.get("items", []), f"{where}.items", want_min, want_max),
    )


def _parse_items(entries: list, where: str, want_min: int, want_max: int) -> tuple[Item, ...]:
    return tuple(
        _parse_item(entry, f"{where}[{index}]", want_min, want_max)
        for index, entry in enumerate(entries)
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


def _parse_item(entry: dict, where: str, want_min: int, want_max: int) -> Item:
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
