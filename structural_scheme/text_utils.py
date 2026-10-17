"""Текстовые утилиты, оценка ширины подписей и типизированные словари модели."""

from __future__ import annotations

import math
import re
from typing import Any, TypedDict
from uuid import uuid4

from .constants import PER_ROW_MAX, RASTER_MAX_PIXELS, RASTER_SCALE


class D(dict[str, Any]):
    """Словарь с доступом через точку, остаётся сериализуемым JSON."""

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(key) from e

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


class RoomModel(TypedDict):
    id: str
    name: str
    fill: str
    x: float
    y: float
    w: float
    h: float


class BlockModel(TypedDict):
    id: str
    item: dict[str, Any]
    kind: str
    level: str
    row: int
    col: int
    w: float
    h: float
    x: float
    y: float
    name: str
    lines: list[str]
    fill: str


class ConnModel(TypedDict):
    src: BlockModel
    tgt: BlockModel
    color: str
    sx: float
    tx: float
    sy: float
    ty: float
    sEdge: str
    tEdge: str
    pts: list[list[float]]


class LegendItemModel(TypedDict):
    name: str
    color: str
    x: float
    y: float


class LegendModel(TypedDict):
    x: float
    y: float
    w: float
    h: float
    itemW: int
    items: list[LegendItemModel]


class NotesModel(TypedDict):
    x: float
    y: float
    lines: list[str]


class SchemeModel(TypedDict):
    width: float
    height: float
    title: str
    subtitle: str
    fileName: str
    rooms: list[RoomModel]
    blocks: list[BlockModel]
    conns: list[ConnModel]
    ext: list[dict[str, Any]]
    signals: list[dict[str, Any]]
    legend: LegendModel
    notes: NotesModel | None
    warnings: list[str]


def uid() -> str:
    return uuid4().hex[:12]


def fit(s: Any, n: int) -> str:
    s = '' if s is None else str(s)
    return s[: n - 1] + '…' if len(s) > n else s


def textWidth(value: Any, size: float, bold: bool = False) -> float:
    """Оценка ширины строки в px без шрифтовых библиотек (Arial / DejaVu Sans).

    Нужна, чтобы подпись не выходила за блок и не наезжала на соседний: точный
    расчёт потребовал бы загрузки шрифта, а для проверки влезания хватает
    таблицы коэффициентов. Оценка намеренно пессимистична (шире реальной).
    """
    text = '' if value is None else str(value)
    narrow = ' .,:;!|\'"()[]/\\-–—iljtI'
    wide = 'МШЩЖЮмшщжюMW@№'
    total = 0.0
    for ch in text:
        if ch in narrow:
            f = 0.30
        elif ch in wide:
            f = 0.82
        else:
            f = 0.60
        if bold and ch.isupper():
            f += 0.07
        total += f * size
    return total


def fitText(value: Any, max_width: float, size: float, bold: bool = False) -> str:
    """Обрезка подписи по ширине блока: 'длинный текст' -> 'длинный те…'."""
    text = '' if value is None else str(value)
    if textWidth(text, size, bold) <= max_width:
        return text
    # Сначала дешёвая граница по числу знаков, затем точная обрезка по ширине.
    text = fit(text, max(4, int(max_width / (0.30 * size))))
    while text and textWidth(text + '…', size, bold) > max_width:
        text = text[:-1]
    return text + '…'


def pad2(n: int) -> str:
    return str(n).zfill(2)


def clampPerRow(value: Any) -> int:
    try:
        return min(PER_ROW_MAX, max(1, math.floor(float(value or 0))))
    except (ValueError, TypeError, OverflowError):
        return 1


def rasterScale(width: float, height: float) -> float:
    return max(0.1, min(RASTER_SCALE, math.sqrt(RASTER_MAX_PIXELS / max(1, width * height))))


def signalLabel(signal: dict[str, Any], showCounts: Any) -> str:
    return f"{signal['k']} ({signal['n']})" if showCounts and signal.get('n') not in (None, '') else str(signal['k'])


def signalsOf(c: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(k=k, **({'n': c.get(n)} if n else {}))
        for f, k, n in [
            ('di', 'DI', 'diN'),
            ('dO', 'DO', 'doN'),
            ('ai', 'AI', 'aiN'),
            ('ao', 'AO', 'aoN'),
            ('rs485', 'RS-485', None),
        ]
        if c.get(f)
    ]


def fileNameOf(project: dict[str, Any]) -> str:
    cleaned = re.sub(r'[^\wа-яА-ЯёЁ-]+', '_', str(project.get('fileName') or 'scheme'), flags=re.ASCII)[:120]
    return cleaned or 'scheme'


clamp_per_row = clampPerRow
raster_scale = rasterScale
fit_text = fitText
text_width = textWidth
