"""Экспорт модели в векторные и растровые форматы без браузера."""

from __future__ import annotations

import math
from io import BytesIO
from typing import Any

import resvg_py
from PIL import Image

from .constants import RASTER_MAX_PIXELS, RASTER_MAX_SIDE
from .render import to_drawio, to_svg
from .text_utils import rasterScale


def export_model(model: dict[str, Any], format: str) -> tuple[bytes, str]:
    format = format.lower().lstrip('.')
    if format == 'svg':
        return to_svg(model).encode('utf-8'), 'image/svg+xml'
    if format in ('drawio', 'xml'):
        return to_drawio(model).encode('utf-8'), 'application/xml'
    if format not in ('png', 'jpg', 'jpeg'):
        raise ValueError('Поддерживаются SVG, PNG, JPG и Draw.io.')
    # rasterScale совместим с JS API (масштаб не ниже 0.1); жёсткие лимиты
    # серверного экспорта (16Mpx и 16384px по стороне) действуют всегда.
    w, h = float(model['width']), float(model['height'])
    hard_pixel_scale = math.sqrt(RASTER_MAX_PIXELS / max(1.0, w * h))
    hard_side_scale = RASTER_MAX_SIDE / max(1.0, w, h)
    scale = min(rasterScale(w, h), hard_pixel_scale, hard_side_scale)
    try:
        png = resvg_py.svg_to_bytes(
            svg_string=to_svg(model),
            width=max(1, int(w * scale)),
            height=max(1, int(h * scale)),
            background='#ffffff',
        )
    except Exception as e:
        raise ValueError('Не удалось создать растровое изображение.') from e
    if not png:
        raise ValueError('Не удалось создать растровое изображение.')
    if format == 'png':
        return png, 'image/png'
    out = BytesIO()
    with Image.open(BytesIO(png)) as image:
        image.convert('RGB').save(out, format='JPEG', quality=95)
    return out.getvalue(), 'image/jpeg'
