"""Рендеры только читают модель; не выполняют раскладку или трассировку."""
from html import escape
from xml.etree.ElementTree import Element, SubElement, tostring


def _xml(root):
    return tostring(root, encoding='unicode')


def _el(parent, tag, **attrs):
    return SubElement(parent, tag, {k.replace('_', '-'): str(v) for k, v in attrs.items() if v is not None})


def to_svg(m):
    root = Element('svg', xmlns='http://www.w3.org/2000/svg', width=str(m['width']), height=str(m['height']),
                   viewBox=f"0 0 {m['width']} {m['height']}", attrib={'font-family': 'Arial, DejaVu Sans, sans-serif'})
    def rect(r, fill=None, **kw):
        return _el(root, 'rect', x=r['x'], y=r['y'], width=r['w'], height=r['h'], fill=fill or r['fill'], **kw)
    def text(x, y, value, size=10, color='#374151', bold=False, anchor=None):
        e = _el(root, 'text', x=x, y=y, font_size=size, fill=color,
                font_weight='bold' if bold else None, text_anchor=anchor)
        e.text = str(value)
    def line(x1, y1, x2, y2, color, **kw):
        return _el(root, 'line', x1=x1, y1=y1, x2=x2, y2=y2, stroke=color, stroke_width=1.7, **kw)
    _el(root, 'rect', x=0, y=0, width=m['width'], height=m['height'], fill='#ffffff')
    text(m['width']/2, 30, m['title'], 18, '#111827', True, 'middle')
    if m['subtitle']:
        text(m['width']/2, 52, m['subtitle'], 12, '#6b7280', anchor='middle')
    for r in m['rooms']:
        rect(r, rx=8, stroke='#94a3b8', stroke_dasharray='6 4')
    for c in m['conns']:
        _el(root, 'path', d=' '.join(f'{"M" if i == 0 else "L"} {x} {y}' for i, (x, y) in enumerate(c['pts'])),
            stroke=c['color'], stroke_width=1.7, fill='none', stroke_linejoin='round')
    for e in m['ext']:
        color = '#f97316'
        line(e['x1'], e['y'], e['x2'], e['y'], color, stroke_dasharray='7 4')
        x, y = e['x2'], e['y']
        _el(root, 'polygon', points=f'{x},{y} {x-8},{y-4} {x-8},{y+4}', fill=color)
        if e['label']:
            text(x-4, y-7, 'Внешняя связь', 9, color, anchor='end')
    for b in m['blocks']:
        rect(b, rx=6, stroke='#334155', stroke_width=1.3)
        text(b['x']+b['w']/2, b['y']+16, b['name'], 11, '#111827', True, 'middle')
        line(b['x']+8, b['y']+24, b['x']+b['w']-8, b['y']+24, '#cbd5e1')
        for i, s in enumerate(b['lines']):
            text(b['x']+12, b['y']+40+i*16, '• '+s)
    for r in m['rooms']:
        _el(root, 'rect', x=r['x']+8, y=r['y']+7, width=len(r['name'])*7.2+12, height=19, rx=4, fill=r['fill'])
        text(r['x']+14, r['y']+21, r['name'], 12, '#475569', True)
    for s in m['signals']:
        x, y = s['x'], s['y2']
        line(x, s['y1'], x, y-6, s['color'])
        _el(root, 'polygon', points=f'{x},{y} {x-4},{y-7} {x+4},{y-7}', fill=s['color'])
        text(x, y+13, s['label'], 9, s['color'], True, 'middle')
    lg = m['legend']
    rect(lg, '#ffffff', rx=6, stroke='#94a3b8')
    text(lg['x']+14, lg['y']+18, 'Условные обозначения:', 11, bold=True)
    for it in lg['items']:
        line(it['x'], it['y'], it['x']+30, it['y'], it['color'])
        text(it['x']+38, it['y']+4, it['name'])
    if m['notes']:
        n = m['notes']
        text(n['x'], n['y']+12, 'Примечания:', 11, bold=True)
        for i, s in enumerate(n['lines']):
            text(n['x'], n['y']+30+i*16, s)
    return _xml(root)


def to_drawio(m):
    root = Element('mxfile', host='app.diagrams.net', agent='scheme-generator-python')
    diagram = SubElement(root, 'diagram', id='d1', name='Схема')
    graph = SubElement(diagram, 'mxGraphModel', grid='0', page='1', pageScale='1',
                       pageWidth=str(m['width']), pageHeight=str(m['height']))
    cells = SubElement(graph, 'root')
    SubElement(cells, 'mxCell', {'id': '0'})
    SubElement(cells, 'mxCell', {'id': '1', 'parent': '0'})
    def vertex(id, value, x, y, w, h, style):
        # Атрибуты передаются словарём: 'parent' — служебное имя SubElement, и ключ
        # работает как атрибут XML только благодаря позиционности аргумента в CPython.
        c = SubElement(cells, 'mxCell', {'id': id, 'value': value, 'style': style, 'vertex': '1', 'parent': '1'})
        SubElement(c, 'mxGeometry', x=str(x), y=str(y), width=str(w), height=str(h), attrib={'as': 'geometry'})
    def text(id, value, x, y, w, h, size=10):
        vertex(id, escape(value), x, y, w, h, f'text;html=1;align=left;verticalAlign=top;fontSize={size};')
    text('title', m['title'], 18, 8, m['width']-36, 26, 18)
    if m['subtitle']:
        text('subtitle', m['subtitle'], 18, 38, m['width']-36, 18, 12)
    for r in m['rooms']:
        vertex(r['id'], escape(r['name']), r['x'], r['y'], r['w'], r['h'],
               f"rounded=1;dashed=1;html=1;fillColor={r['fill']};strokeColor=#94a3b8;verticalAlign=top;align=left;spacingLeft=10;")
    for b in m['blocks']:
        value = '<b>'+escape(b['name'])+'</b><hr/>'+''.join('<div>• '+escape(s)+'</div>' for s in b['lines'])
        vertex('b_'+b['id'], value, b['x'], b['y'], b['w'], b['h'],
               f"rounded=1;whiteSpace=wrap;html=1;fillColor={b['fill']};strokeColor=#334155;verticalAlign=top;fontSize=10;")
    eid = 0
    def edge(value, color, pts, source=None, target=None, style=''):
        nonlocal eid
        attrs = dict(id=f'e{eid}', value=value, style=f'html=1;endArrow=none;strokeWidth=2;strokeColor={color};'+style,
                     edge='1', parent='1')
        eid += 1
        if source:
            attrs['source'] = 'b_'+source
        if target:
            attrs['target'] = 'b_'+target
        c = SubElement(cells, 'mxCell', **attrs)
        g = SubElement(c, 'mxGeometry', relative='1', attrib={'as': 'geometry'})
        for point, name in [(pts[0], 'sourcePoint'), (pts[-1], 'targetPoint')]:
            SubElement(g, 'mxPoint', x=str(point[0]), y=str(point[1]), attrib={'as': name})
        a = SubElement(g, 'Array', attrib={'as': 'points'})
        for x, y in pts[1:-1]:
            SubElement(a, 'mxPoint', x=str(x), y=str(y))
    for c in m['conns']:
        s, t = c['src'], c['tgt']
        style = (f"exitX={(c['sx']-s['x'])/s['w']};exitY={int(c['sEdge']=='bottom')};exitPerimeter=0;"
                 f"entryX={(c['tx']-t['x'])/t['w']};entryY={int(c['tEdge']=='bottom')};entryPerimeter=0;")
        # Без автоматического роутера Draw.io: сохраняем рассчитанные точки точно.
        edge('', c['color'], c['pts'], s['id'], t['id'], style)
    for e in m['ext']:
        b = e['b']
        edge('Внешняя связь' if e['label'] else '', '#f97316', [(e['x1'], e['y']), (e['x2'], e['y'])], b['id'],
             style=f"endArrow=block;dashed=1;exitX=1;exitY={(e['y']-b['y'])/b['h']};exitPerimeter=0;")
    for s in m['signals']:
        edge(s['label'], s['color'], [(s['x'], s['y1']), (s['x'], s['y2'])], s['block']['id'],
             style=f"endArrow=block;exitX={s['exitX']};exitY=1;exitPerimeter=0;")
    lg = m['legend']
    vertex('legend', 'Условные обозначения:', lg['x'], lg['y'], lg['w'], lg['h'],
           'rounded=1;fillColor=#ffffff;strokeColor=#94a3b8;verticalAlign=top;align=left;')
    for i, it in enumerate(lg['items']):
        edge('', it['color'], [(it['x'], it['y']), (it['x']+30, it['y'])])
        text(f'legend_{i}', it['name'], it['x']+38, it['y']-10, lg['itemW']-50, 20)
    if m['notes']:
        n = m['notes']
        text('notes', 'Примечания:\n'+'\n'.join(n['lines']), n['x'], n['y'], lg['w'], 20+len(n['lines'])*16)
    return _xml(root)
