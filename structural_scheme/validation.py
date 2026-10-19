"""Геометрические инварианты helpers.js + границы всех объектов. Shapely 2/STRtree."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise
from typing import Any

from shapely.geometry import LineString, box
from shapely.strtree import STRtree

from .constants import (
    LINE_SIZE,
    NAME_SIZE,
    PORT_MIN_STEP,
    ROOM_LABEL_SIZE,
    SIGNAL_LABEL_SIZE,
    SUBTITLE_SIZE,
    TITLE_SIZE,
)
from .text_utils import textWidth

TOL: float = 0.05


def _has_box(block: dict[str, Any]) -> bool:
    return all(k in block for k in ('x', 'y', 'w', 'h'))


def _on_border(point: Sequence[float], block: dict[str, Any], tol: float = TOL) -> bool:
    """Точка лежит на границе блока: внутри расширенного прямоугольника и у края."""
    x, y = point
    x1, y1 = float(block['x']), float(block['y'])
    x2, y2 = x1 + float(block['w']), y1 + float(block['h'])
    if not (x1 - tol <= x <= x2 + tol and y1 - tol <= y <= y2 + tol):
        return False
    return abs(x - x1) <= tol or abs(x - x2) <= tol or abs(y - y1) <= tol or abs(y - y2) <= tol


def layoutProblems(model: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    segments: list[LineString] = []
    owners: list[int] = []
    blocks = model['blocks']
    rects = [box(b['x'] + 0.5, b['y'] + 0.5, b['x'] + b['w'] - 0.5, b['y'] + b['h'] - 0.5) for b in blocks]
    tree = STRtree(rects)

    def hit_blocks(line: LineString, excluded: set[str]) -> None:
        for i in tree.query(line, predicate='intersects'):
            if blocks[i]['id'] not in excluded:
                problems.append(f'Линия проходит сквозь блок {blocks[i]["id"]}')

    for ci, c in enumerate(model['conns']):
        for x, y in c['pts']:
            if not 0 <= x <= model['width'] or not 0 <= y <= model['height']:
                problems.append(f'Связь {ci} выходит за лист')
        # Концы обязаны лежать на границе своих блоков, иначе связь нарисована
        # «в воздухе» и обрыв не виден ни пользователю, ни остальным проверкам.
        for point, block, role in (
            (c['pts'][0], c.get('src'), 'источника'),
            (c['pts'][-1], c.get('tgt'), 'цели'),
        ):
            if block and _has_box(block) and not _on_border(point, block):
                problems.append(f'Связь {ci} не касается блока {role} {block["id"]}')
        for a, b in pairwise(c['pts']):
            line = LineString([a, b])
            if line.length < 0.01:
                problems.append(f'Пустой отрезок {ci}')
            elif abs(a[0] - b[0]) > 0.01 and abs(a[1] - b[1]) > 0.01:
                problems.append(f'Неортогональный отрезок {ci}')
            hit_blocks(line, {c['src']['id'], c['tgt']['id']})
            segments.append(line)
            owners.append(ci)
    st = STRtree(segments)
    for i, a in enumerate(segments):
        for j in st.query(a.buffer(0.05, cap_style=3)):
            if j <= i or owners[i] == owners[j]:
                continue
            b = segments[j]
            (ax, ay), (az, aw) = a.coords
            (bx, by), (bz, bw) = b.coords
            ah, bh = abs(ay - aw) < 0.01, abs(by - bw) < 0.01
            if ah != bh:
                continue
            if ah:
                overlap = min(max(ax, az), max(bx, bz)) - max(min(ax, az), min(bx, bz)) if abs(ay - by) < 0.05 else 0
            else:
                overlap = min(max(ay, aw), max(by, bw)) - max(min(ay, aw), min(by, bw)) if abs(ax - bx) < 0.05 else 0
            if overlap > 1.5:
                problems.append(f'Наложение связей {owners[i]} и {owners[j]}: {overlap:.2f}px')
    # Порты одной грани не должны сливаться в одну вертикаль: вплоть до
    # подписей шаг ограничен шириной блока, но совпадение — уже ошибка.
    ports: dict[tuple[str, str], list[float]] = {}
    for c in model['conns']:
        for block, edge, field in ((c.get('src'), c.get('sEdge'), 'sx'), (c.get('tgt'), c.get('tEdge'), 'tx')):
            if block and _has_box(block) and edge in ('top', 'bottom') and field in c:
                ports.setdefault((block['id'], edge), []).append(float(c[field]))
    for (bid, edge), xs in ports.items():
        xs.sort()
        for a, b in pairwise(xs):
            if b - a < PORT_MIN_STEP:
                problems.append(f'Порты блока {bid} ({edge}) почти совпадают: шаг {b - a:.3f}px < {PORT_MIN_STEP}')
    for s in model['signals']:
        line = LineString([(s['x'], s['y1']), (s['x'], s['y2'])])
        hit_blocks(line, {b['id'] for b in blocks if b['id'] == s['block']['id'] or b['y'] < s['block']['y']})
    for e in model['ext']:
        if e['x2'] > model['width']:
            problems.append('Внешняя связь выходит за лист')
        line = LineString([(e['x1'], e['y']), (e['x2'], e['y'])])
        for b in blocks:
            if b['id'] != e['b']['id'] and line.intersects(box(b['x'], b['y'], b['x'] + b['w'], b['y'] + b['h'])):
                problems.append('Внешняя связь проходит сквозь блок')
    for b in blocks + model['rooms'] + [model['legend']]:
        if b['x'] < 0 or b['y'] < 0 or b['x'] + b['w'] > model['width'] or b['y'] + b['h'] > model['height']:
            problems.append('Объект выходит за лист')
    # Подписи обрезаются по ширине блока: проверяем, что обрезка не потерялась.
    for b in blocks:
        name, lines = b.get('name'), b.get('lines') or []
        if name and textWidth(name, NAME_SIZE, True) > b['w'] - 8:
            problems.append(f'Название блока {b["id"]} шире блока')
        for s in lines:
            if textWidth(s, LINE_SIZE) > b['w'] - 16:
                problems.append(f'Строка подписи блока {b["id"]} шире блока')
    # Подписи вне блоков обрезаются по ширине листа: заголовки по центру,
    # названия помещений — по рамке, подписи сигналов — вокруг своей стрелки.
    title = model.get('title')
    if title and textWidth(title, TITLE_SIZE, True) > model['width']:
        problems.append('Заголовок схемы шире листа')
    subtitle = model.get('subtitle')
    if subtitle and textWidth(subtitle, SUBTITLE_SIZE) > model['width']:
        problems.append('Подзаголовок схемы шире листа')
    for r in model['rooms']:
        name = r.get('name')
        if name and textWidth(name, ROOM_LABEL_SIZE, True) > r['w'] - 28:
            problems.append(f'Название помещения {r.get("id", "")} шире рамки помещения')
    for s in model['signals']:
        label = s.get('label')
        if label:
            half = textWidth(label, SIGNAL_LABEL_SIZE, True) / 2
            if s['x'] - half < 0 or s['x'] + half > model['width']:
                problems.append('Подпись сигнала выходит за лист')
    lg = model['legend']
    for it in lg['items']:
        if it['x'] + 100 > lg['x'] + lg['w']:
            problems.append('Элемент легенды выходит за рамку')
    n = model['notes']
    if n and n['y'] + 20 + 16 * len(n['lines']) > model['height']:
        problems.append('Примечания выходят за лист')
    if n:
        for s in n['lines']:
            if textWidth(s, LINE_SIZE) > model['width'] - n['x']:
                problems.append('Строка примечаний шире листа')
    return problems


layout_problems = layoutProblems
