"""Геометрические инварианты helpers.js + границы всех объектов. Shapely 2/STRtree."""
from shapely.geometry import LineString, box
from shapely.strtree import STRtree


def layoutProblems(model):
    problems, segments, owners = [], [], []
    blocks = model['blocks']
    rects = [box(b['x']+.5, b['y']+.5, b['x']+b['w']-.5, b['y']+b['h']-.5) for b in blocks]
    tree = STRtree(rects)
    def hit_blocks(line, excluded):
        for i in tree.query(line, predicate='intersects'):
            if blocks[i]['id'] not in excluded:
                problems.append(f'Линия проходит сквозь блок {blocks[i]["id"]}')
    for ci, c in enumerate(model['conns']):
        for x, y in c['pts']:
            if not 0 <= x <= model['width'] or not 0 <= y <= model['height']:
                problems.append(f'Связь {ci} выходит за лист')
        for a, b in zip(c['pts'], c['pts'][1:]):
            line = LineString([a,b])
            if line.length < .01:
                problems.append(f'Пустой отрезок {ci}')
            elif abs(a[0]-b[0]) > .01 and abs(a[1]-b[1]) > .01:
                problems.append(f'Неортогональный отрезок {ci}')
            hit_blocks(line, {c['src']['id'], c['tgt']['id']})
            segments.append(line)
            owners.append(ci)
    st = STRtree(segments)
    for i, a in enumerate(segments):
        for j in st.query(a.buffer(.05, cap_style=3)):
            if j <= i or owners[i] == owners[j]:
                continue
            b = segments[j]
            (ax, ay), (az, aw) = a.coords
            (bx, by), (bz, bw) = b.coords
            ah, bh = abs(ay-aw) < .01, abs(by-bw) < .01
            if ah != bh:
                continue
            if ah:
                overlap = min(max(ax,az), max(bx,bz))-max(min(ax,az), min(bx,bz)) if abs(ay-by) < .05 else 0
            else:
                overlap = min(max(ay,aw), max(by,bw))-max(min(ay,aw), min(by,bw)) if abs(ax-bx) < .05 else 0
            if overlap > 1.5:
                problems.append(f'Наложение связей {owners[i]} и {owners[j]}: {overlap:.2f}px')
    for s in model['signals']:
        line = LineString([(s['x'], s['y1']), (s['x'], s['y2'])])
        hit_blocks(line, {b['id'] for b in blocks if b['id'] == s['block']['id'] or b['y'] < s['block']['y']})
    for e in model['ext']:
        if e['x2'] > model['width']:
            problems.append('Внешняя связь выходит за лист')
        line = LineString([(e['x1'],e['y']), (e['x2'],e['y'])])
        for b in blocks:
            if b['id'] != e['b']['id'] and line.intersects(box(b['x'], b['y'], b['x']+b['w'], b['y']+b['h'])):
                problems.append('Внешняя связь проходит сквозь блок')
    for b in blocks + model['rooms'] + [model['legend']]:
        if b['x'] < 0 or b['y'] < 0 or b['x']+b['w'] > model['width'] or b['y']+b['h'] > model['height']:
            problems.append('Объект выходит за лист')
    lg = model['legend']
    for it in lg['items']:
        if it['x']+100 > lg['x']+lg['w']:
            problems.append('Элемент легенды выходит за рамку')
    n = model['notes']
    if n and n['y']+20+16*len(n['lines']) > model['height']:
        problems.append('Примечания выходят за лист')
    return problems


layout_problems = layoutProblems
