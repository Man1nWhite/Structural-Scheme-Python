"""Экспорт модели в векторные и растровые форматы без браузера."""
from io import BytesIO
from PIL import Image
import resvg_py
from .scheme_core import rasterScale, RASTER_MAX_PIXELS, to_svg, to_drawio


def export_model(model, format):
    format = format.lower().lstrip('.')
    if format == 'svg':
        return to_svg(model).encode('utf-8'), 'image/svg+xml'
    if format in ('drawio', 'xml'):
        return to_drawio(model).encode('utf-8'), 'application/xml'
    if format not in ('png', 'jpg', 'jpeg'):
        raise ValueError('Поддерживаются SVG, PNG, JPG и Draw.io.')
    # rasterScale совместим с JS API; жёсткие лимиты серверного экспорта
    # действуют даже когда совместимый масштаб упирается в минимум 0.1.
    w, h = model['width'], model['height']
    scale = min(rasterScale(w, h), (RASTER_MAX_PIXELS/max(1,w*h))**.5, 16384/max(w,h))
    png = resvg_py.svg_to_bytes(svg_string=to_svg(model), width=max(1,int(w*scale)),
                                height=max(1,int(h*scale)), background='#ffffff')
    if not png:
        raise ValueError('Не удалось создать растровое изображение.')
    if format == 'png':
        return png, 'image/png'
    out = BytesIO()
    with Image.open(BytesIO(png)) as image:
        image.convert('RGB').save(out, format='JPEG', quality=95)
    return out.getvalue(), 'image/jpeg'
