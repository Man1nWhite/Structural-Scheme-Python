"""Чистое ядро АСУ ТП. Модель совместима с JS v1; геометрия общая для экспортов."""
from __future__ import annotations

import heapq
import json
import math
import re
from collections import defaultdict
from copy import deepcopy
from uuid import uuid4

BW, GAP_MIN, SLOT, SLOT_M, LSTEP, EXIT_STEP = 190, 30, 7, 8, 8, 20
OP_H, RACK_H, NET_H, AUTO_H, SIG_H, MARGIN = 86, 110, 128, 88, 64, 18
SIG_LEN, HEAD, LEGEND_ITEM_W = 44, 32, 170
CONSTS = {k: v for k, v in list(globals().items()) if k in (
    'BW GAP_MIN SLOT SLOT_M LSTEP EXIT_STEP OP_H RACK_H NET_H AUTO_H SIG_H MARGIN').split()}
COLORS = {'Витая пара': '#2563eb', 'Оптика': '#f97316', 'KVM': '#6b7280',
          'RS-485': '#16a34a', 'DI': '#0891b2', 'DO': '#7c3aed', 'AI': '#db2777', 'AO': '#a16207'}
NAME_BY_COLOR = {v: k for k, v in COLORS.items()}
LEVEL_FILL = {'op': '#eff6ff', 'srv': '#f0fdf4', 'auto': '#fefce8'}
OP_TYPES = ['АРМ', 'Принтер', 'Панель управления']
OP_LINKS = ['Витая пара', 'Оптика', 'KVM']
AUTO_UPLINKS = ['Витая пара', 'Оптика']
KVM_PANEL_ID = 'kvmpanel'
PER_ROW_MAX, RASTER_SCALE, RASTER_MAX_PIXELS = 12, 2, 16_000_000
FORMAT, FORMAT_VERSION, STORAGE_KEY = 'structural-scheme', 1, 'structural-scheme:project'
PROJECT_DEFAULTS = dict(title='Структурная схема комплекса', subtitle='АСУ ТП установки',
    fileName='structural_scheme', operatorName='Операторная', serverName='Серверная',
    autoName='Помещение шкафов автоматики', blocksPerRow=4, showNotes=True,
    showSignalCounts=False, kvmPanel=False, kvmPanelName='Щит КВМ-удлинителей', notesText='')
ITEM_DEFAULTS = {
    'opItems': dict(id='', name='АРМ оператора', type='АРМ', link='Витая пара', target=None, kvmToPanel=False),
    'racks': dict(id='', name='Серверная стойка', servers=2, kvm=False, ntp=False, ups=True, netTarget=None),
    'netCabs': dict(id='', name='Шкаф сетевой', switches=2, fw=0, cross=1, external=False, ups=True),
    'autoCabs': dict(id='', name='Шкаф ША', ctrls=1, uplink='Витая пара', netTarget=None,
        di=True, dO=True, ai=True, ao=False, rs485=False, rs485Cab=False, rs485Target=None,
        diN=16, doN=8, aiN=8, aoN=0)}


class D(dict):
    """Словарь с доступом через точку, остаётся сериализуемым JSON."""
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(key) from e

    __setattr__ = dict.__setitem__


def uid():
    return uuid4().hex[:12]


def fit(s, n):
    s = '' if s is None else str(s)
    return s[:n-1] + '…' if len(s) > n else s


def pad2(n):
    return str(n).zfill(2)


def clampPerRow(value):
    try:
        return min(PER_ROW_MAX, max(1, math.floor(float(value or 0))))
    except (ValueError, TypeError, OverflowError):
        return 1


def rasterScale(width, height):
    return max(.1, min(RASTER_SCALE, math.sqrt(RASTER_MAX_PIXELS / max(1, width * height))))


def signalLabel(signal, showCounts):
    return f"{signal['k']} ({signal['n']})" if showCounts and signal.get('n') not in (None, '') else signal['k']


def signalsOf(c):
    return [dict(k=k, **({'n': c.get(n)} if n else {})) for f, k, n in
            [('di', 'DI', 'diN'), ('dO', 'DO', 'doN'), ('ai', 'AI', 'aiN'),
             ('ao', 'AO', 'aoN'), ('rs485', 'RS-485', None)] if c.get(f)]


def fileNameOf(project):
    return re.sub(r'[^\wа-яА-ЯёЁ-]+', '_', project.get('fileName') or 'scheme', flags=re.ASCII)


def _new(state, key, name):
    return {**ITEM_DEFAULTS[key], 'id': uid(), 'name': name}


def newNetCab(state):
    return _new(state, 'netCabs', 'Шкаф сетевой ШС-' + pad2(len(state['netCabs']) + 1))


def _net(state):
    return state['netCabs'][0]['id'] if state['netCabs'] else None


def newOpItem(state):
    return {**_new(state, 'opItems', 'АРМ оператора №' + str(len(state['opItems']) + 1)), 'target': _net(state)}


def newRack(state):
    return {**_new(state, 'racks', 'Серверная стойка №' + str(len(state['racks']) + 1)), 'netTarget': _net(state)}


def newAutoCab(state):
    return {**_new(state, 'autoCabs', 'Шкаф ША-' + pad2(len(state['autoCabs']) + 1)),
            'netTarget': _net(state), 'rs485Target': state['autoCabs'][0]['id'] if state['autoCabs'] else None}


def createDefaultState():
    s = {'project': deepcopy(PROJECT_DEFAULTS), **{k: [] for k in ITEM_DEFAULTS}}
    s['netCabs'] = [{**newNetCab(s), 'fw': 1, 'cross': 2, 'external': True}]
    for name, kind, kvm in [('АРМ оператора №1', 'АРМ', True), ('АРМ оператора №2', 'АРМ', True),
                             ('Принтер сетевой', 'Принтер', False), ('Панель управления', 'Панель управления', False)]:
        s['opItems'].append({**newOpItem(s), 'name': name, 'type': kind, 'kvmToPanel': kvm})
    s['racks'] = [{**newRack(s), 'servers': 3, 'kvm': True, 'ntp': True}]
    for n in [2, 1, 1]:
        s['autoCabs'].append({**newAutoCab(s), 'ctrls': n, 'ao': True, 'rs485': True,
                              'diN': 32, 'doN': 32, 'aiN': 16, 'aoN': 2, 'rs485Target': None})
    return s


def _pick(src, defaults):
    out = deepcopy(defaults)
    if not isinstance(src, dict):
        return out
    for k, d in defaults.items():
        if k not in src:
            continue
        v = src[k]
        ok = ((v is None or isinstance(v, str)) if d is None else
              type(v) is bool if type(d) is bool else
              (isinstance(v, str) or type(v) in (int, float) and math.isfinite(v)) if type(d) in (int, float) else
              isinstance(v, str))
        if ok:
            out[k] = v
    return out


def normalizeState(raw):
    if not isinstance(raw, dict):
        raise ValueError('Файл не содержит проект структурной схемы.')
    if raw.get('format', FORMAT) != FORMAT:
        raise ValueError('Файл не является проектом структурной схемы.')
    if type(raw.get('version')) in (int, float) and raw['version'] > FORMAT_VERSION:
        raise ValueError('Проект сохранён в более новом формате, обновите приложение.')
    s = {'project': _pick(raw.get('project'), PROJECT_DEFAULTS)}
    v = s['project']['blocksPerRow']
    n = clampPerRow(v)
    try:
        string_number = isinstance(v, str) and bool(v.strip()) and math.isfinite(float(v))
    except ValueError:
        string_number = False
    s['project']['blocksPerRow'] = str(n) if string_number else n
    seen = {KVM_PANEL_ID}
    for k, defaults in ITEM_DEFAULTS.items():
        s[k] = []
        for item in raw.get(k, []) if isinstance(raw.get(k), list) else []:
            if not isinstance(item, dict):
                continue
            it = _pick(item, defaults)
            if not it['id'] or it['id'] in seen:
                it['id'] = uid()
            seen.add(it['id'])
            s[k].append(it)
    return s


def serializeState(state):
    return json.dumps(dict(format=FORMAT, version=FORMAT_VERSION, **{k: state[k] for k in ['project', *ITEM_DEFAULTS]}),
                      ensure_ascii=False, indent=2, allow_nan=False)


def parseState(text):
    try:
        raw = json.loads(text, parse_constant=lambda _: None)
    except (ValueError, TypeError) as e:
        raise ValueError('Файл повреждён или не является JSON.') from e
    return normalizeState(raw)


def makeResolvers(state):
    nets, racks, autos = state['netCabs'], state['racks'], state['autoCabs']
    ids = {i['id'] for i in nets + racks}
    def effTarget(id, allowPanel=False):
        if allowPanel and id == KVM_PANEL_ID and state['project']['kvmPanel']:
            return id
        return id if id in ids else (nets + racks)[0]['id'] if nets + racks else None
    def effNet(id):
        return id if any(c['id'] == id for c in nets) else _net(state)
    def effAutoTarget(id, sourceId):
        if id != sourceId and any(c['id'] == id for c in autos):
            return id
        return next((c['id'] for c in autos if c['id'] != sourceId), None)
    return D(effTarget=effTarget, effNet=effNet, effAutoTarget=effAutoTarget)


def routeBand(hs):
    """Граф «выше» и назначение горизонтальных каналов из backup."""
    for h in hs:
        h['track'] = -1
    above = [set() for _ in hs]
    for i, a in enumerate(hs):
        for j, b in enumerate(hs):
            if i == j:
                continue
            if any(a['x1'] < x < a['x2'] for x in b['top']):
                above[i].add(j)
            if any(a['x1'] < x < a['x2'] for x in b['bot']):
                above[j].add(i)
    left = set(range(len(hs)))
    tracks = 0
    while left:
        i = min(left, key=lambda i: (len(above[i] & left), hs[i]['x2'] - hs[i]['x1'], i))
        left.remove(i)
        h = hs[i]
        t = max([0] + [hs[j]['track'] + 1 for j in above[i] if hs[j]['track'] >= 0])
        while any(k != i and b['track'] == t and not (b['x2'] + 4 < h['x1'] or b['x1'] > h['x2'] + 4)
                  for k, b in enumerate(hs)):
            t += 1
        h['track'] = t
        tracks = max(tracks, t + 1)
    return tracks


def assign_gap_slots(runs):
    """Точное раскрашивание интервального графа (оптимум = макс. глубина).

    Интервалы замкнуты: касающиеся интервалы получают разные слоты.
    Сортировка по началу + очередь окончаний, не эвристика по длине.
    """
    active, free, count = [], [], 0
    for i, r in sorted(enumerate(runs), key=lambda pair: (pair[1]['lo'], pair[1]['hi'], pair[0])):
        while active and active[0][0] < r['lo']:
            _, slot = heapq.heappop(active)
            heapq.heappush(free, slot)
        if free:
            slot = heapq.heappop(free)
        else:
            slot = count
            count += 1
        r['slot'] = slot
        heapq.heappush(active, (r['hi'], slot))
    return count


def _band(id, kind='inner', reserved=0, last=False):
    return D(id=id, kind=kind, reserved=reserved, last=last, hs=[], tracks=0, y=0, height=0,
             pad=22 if kind == 'corridor' else 12)


def layout(state, GAPX=GAP_MIN):
    p = state['project']
    resolve = makeResolvers(state)
    per = clampPerRow(p['blocksPerRow'])
    colStep = BW + GAPX
    def level(key, items):
        raw = [items[i:i+per] for i in range(0, len(items), per)]
        cols = max([1] + [len(r) for r in raw])
        rows, blocks = [], []
        for r, row in enumerate(raw):
            off = (cols - len(row)) // 2
            bs = [D(id=it['id'], item=it, kind=it['kind'], level=key, row=r, col=off+c,
                    w=BW, h={'item': OP_H, 'panel': OP_H, 'rack': RACK_H, 'net': NET_H, 'auto': AUTO_H}[it['kind']],
                    x=0, y=0) for c, it in enumerate(row)]
            rows.append(bs)
            blocks.extend(bs)
        return D(key=key, rows=rows, blocks=blocks, cols=cols, nRows=len(rows),
                 rowH=[max(b.h for b in row) for row in rows],
                 bands=[_band(f'{key}:{r}', reserved=SIG_H if key == 'auto' else 0, last=r == len(rows)-1)
                        for r in range(len(rows))], gapRuns={}, startX=0, y=0, height=0)
    op = [{**i, 'kind': 'item'} for i in state['opItems']]
    if p['kvmPanel']:
        op.append(dict(id=KVM_PANEL_ID, kind='panel', name=p['kvmPanelName']))
    LV = D(op=level('op', op), srv=level('srv', [{**i, 'kind': k} for key, k in [('racks', 'rack'), ('netCabs', 'net')]
                                              for i in state[key]]),
           auto=level('auto', [{**i, 'kind': 'auto'} for i in state['autoCabs']]))
    levels = list(LV.values())
    C1, C2 = _band('C1', 'corridor'), _band('C2', 'corridor')
    side = max(GAPX, 84 if any(c['external'] for c in state['netCabs']) else 0)
    width = max(880, 2 * (MARGIN + side) + max(l.cols for l in levels) * colStep - GAPX)
    for l in levels:
        l.startX = (width - (l.cols * colStep - GAPX)) / 2
        for b in l.blocks:
            b.x = l.startX + b.col * colStep
    blk = {b.id: b for l in levels for b in l.blocks}
    conns = []
    def add(b, id, kind):
        if id in blk and id != b.id:
            conns.append(D(src=b, tgt=blk[id], color=COLORS.get(kind, COLORS['Витая пара'])))
    panel = blk.get(KVM_PANEL_ID)
    for b in LV.op.blocks:
        if b.kind != 'item':
            continue
        t = resolve.effTarget(b.item['target'], True)
        add(b, t, 'KVM' if t == KVM_PANEL_ID else b.item['link'])
        if panel and b.item['kvmToPanel'] and t != KVM_PANEL_ID:
            add(b, KVM_PANEL_ID, 'KVM')
    for b in LV.srv.blocks:
        if b.kind == 'rack':
            if panel and b.item['kvm']:
                add(b, KVM_PANEL_ID, 'KVM')
            add(b, resolve.effNet(b.item['netTarget']), 'Витая пара')
    rs = set()
    for b in LV.auto.blocks:
        add(b, resolve.effNet(b.item['netTarget']), b.item['uplink'])
        if b.item['rs485Cab']:
            t = resolve.effAutoTarget(b.item['rs485Target'], b.id)
            key = tuple(sorted([b.id, t])) if t else None
            if key and key not in rs:
                rs.add(key)
                add(b, t, 'RS-485')
    order = dict(op=0, srv=1, auto=2)
    cx = lambda b: b.x + b.w / 2
    for c in conns:
        s, t = c.src, c.tgt
        c.u = False
        if s.level == t.level:
            l = LV[s.level]
            if s.row < t.row:
                c.sEdge, c.tEdge, c.band = 'bottom', 'top', l.bands[t.row-1]
            elif s.row > t.row:
                c.sEdge, c.tEdge, c.band = 'top', 'bottom', l.bands[t.row]
            else:
                c.u, c.sEdge, c.tEdge, c.band = True, 'bottom', 'bottom', l.bands[s.row]
        else:
            down = order[s.level] < order[t.level]
            c.sEdge, c.tEdge = ('bottom', 'top') if down else ('top', 'bottom')
            c.band = C1 if 'op' in (s.level, t.level) else C2

    # Символическая вертикальная ось не зависит от числа горизонтальных
    # каналов: целый ряд и каждая полоса имеют отдельные порядковые позиции.
    base = 0
    for i, l in enumerate(levels):
        l.base = base
        for r, band in enumerate(l.bands):
            band.pos = base + 4*r + 4
        base += 4*(l.nRows+1) + 4
        if i < 2:
            [C1, C2][i].pos = base-2

    def approach_info(c, source):
        b, o = (c.src, c.tgt) if source else (c.tgt, c.src)
        edge = c.sEdge if source else c.tEdge
        l = LV[b.level]
        if b.level == o.level:
            r0, r1 = (min(b.row, o.row)+1, max(b.row, o.row)-1) if source else (1, 0)
        else:
            r0, r1 = (b.row+1, l.nRows-1) if edge == 'bottom' else (0, b.row-1)
        blocked = any(any(bb.col == b.col for bb in l.rows[r]) for r in range(r0, r1+1))
        jog = l.bands[b.row if edge == 'bottom' else b.row-1] if blocked else None
        port_pos = l.base + 4*b.row + (3 if edge == 'bottom' else 1)
        end = jog.pos if jog else c.band.pos
        return b, o, edge, l, jog, min(port_pos, end)-.4, max(port_pos, end)+.4

    # Совместный реестр вертикальных интервалов, а не глобально занятых X.
    # Непересекающиеся по Y линии переиспользуют координаты без сдвигов.
    occupied = []
    def seat(x, lo, hi, lower, upper=None, spacing=SLOT):
        candidate = max(lower, x)
        if upper is not None:
            candidate = min(upper, candidate)
        # Ближайшая допустимая граница одного из запрещённых интервалов X.
        conflicts = [(px, min(spacing, sep)) for px, a, b, sep in occupied if not (hi < a or lo > b)]
        candidates = [candidate, lower]
        if upper is not None:
            candidates.append(upper)
        for px, sep in conflicts:
            candidates.extend([px-sep, px+sep])
        for cx_ in sorted(candidates, key=lambda v: (abs(v-x), v)):
            if cx_ < lower-1e-8 or (upper is not None and cx_ > upper+1e-8):
                continue
            if all(abs(cx_-px) >= sep-1e-8 for px, sep in conflicts):
                occupied.append((cx_, lo, hi, spacing))
                return cx_
        # Очень высокий fan-in: физически невозможно выдержать шаг 7 px
        # на грани 190 px. Уменьшаем шаг, но никогда не совмещаем линии.
        if upper is not None and spacing > .1:
            return seat(x, lo, hi, lower, upper, spacing/2)
        raise ValueError('Недостаточно места для портов блока')

    ports = defaultdict(list)
    for c in conns:
        ports[(c.src.id, c.sEdge)].append((c, 'sx', cx(c.tgt), approach_info(c, True)[-2:]))
        ports[(c.tgt.id, c.tEdge)].append((c, 'tx', cx(c.src), approach_info(c, False)[-2:]))
    signalPorts = {}
    for b in LV.auto.blocks:
        sigs = signalsOf(b.item)
        for i, sig in enumerate(sigs):
            port = D()
            signalPorts[(b.id, i)] = port
            pos = LV.auto.base + 4*b.row + 3
            ports[(b.id, 'bottom')].append((port, 'x', b.x+b.w*(i+1)/(len(sigs)+1), (pos-.4,pos+.6)))
    for (bid, edge), ps in ports.items():
        b = blk[bid]
        ps.sort(key=lambda q: q[2])
        step = BW/(len(ps)+1) if any(field == 'x' for _, field, _, _ in ps) else min(EXIT_STEP, (BW-24)/(len(ps)+1))
        # Отдельные непересекающиеся ячейки сохраняют порядок целей даже
        # при очень большом числе портов. Шаг адаптируется к fan-in.
        for i, (c, field, _, (lo, hi)) in enumerate(ps):
            x = cx(b) + (i-(len(ps)-1)/2)*step
            c[field] = seat(x, lo, hi, x-step*.4, x+step*.4, min(SLOT, step*.8))

    def approach(c, source):
        b, o, edge, l, jog, _, _ = approach_info(c, source)
        px = c.sx if source else c.tx
        if jog is None:
            return D(x=px, run=None, jog=None)
        g = b.col+1 if cx(o) >= cx(b) else b.col
        run = D(g=g, lo=min(jog.pos,c.band.pos)-.4, hi=max(jog.pos,c.band.pos)+.4,
                px=px, ax=cx(b))
        l.gapRuns.setdefault(g, []).append(run)
        return D(x=px, run=run, jog=jog)
    for c in conns:
        c.sApp, c.tApp = approach(c, True), approach(c, False)
    needGap = GAP_MIN
    physical_gaps = defaultdict(list)
    for l in levels:
        for g, runs in l.gapRuns.items():
            gl = l.startX + g*colStep - GAPX
            physical_gaps[gl].extend(runs)
    for gl, runs in physical_gaps.items():
        count = assign_gap_slots(runs)
        needGap = max(needGap, 2*SLOT_M + (count-1)*SLOT)
        for run in sorted(runs, key=lambda r: (r.lo,r.hi)):
            run.ax = seat(gl+SLOT_M+run.slot*SLOT, run.lo, run.hi, gl+SLOT_M)
            needGap = max(needGap, math.ceil(run.ax-gl+SLOT_M))
    proxy = lambda a: a.run.ax if a.run else a.x
    def horizontal(a, b):
        return D(x1=min(a,b), x2=max(a,b), top=[], bot=[], track=0)
    for c in conns:
        sx, tx = proxy(c.sApp), proxy(c.tApp)
        c.main = horizontal(sx, tx)
        c.main['top' if c.sEdge == 'bottom' else 'bot'].append(sx)
        c.main['bot' if c.tEdge == 'top' else 'top'].append(tx)
        c.band.hs.append(c.main)
        for prefix, a, px, edge in [('s', c.sApp, c.sx, c.sEdge), ('t', c.tApp, c.tx, c.tEdge)]:
            if a.run:
                h = horizontal(px, proxy(a))
                h['top' if edge == 'bottom' else 'bot'].append(px)
                h['bot' if edge == 'bottom' else 'top'].append(proxy(a))
                c[prefix+'Jog'] = h
                a.jog.hs.append(h)
    for b in [C1, C2] + [b for l in levels for b in l.bands]:
        b.tracks = routeBand(b.hs)
    def bandH(b):
        lines = 2*b.pad + (b.tracks-1)*LSTEP if b.tracks else 0
        return max(44, lines) if b.kind == 'corridor' else b.reserved + max(8 if b.last else 18, lines)
    y = 82 if p['subtitle'] else 58
    for i, l in enumerate(levels):
        l.y = y
        cy = y + HEAD
        for r, row in enumerate(l.rows):
            for b in row:
                b.y = cy
            cy += l.rowH[r]
            band = l.bands[r]
            band.y, band.height = cy, bandH(band)
            cy += band.height
        if not l.nRows:
            cy += 12
        l.height = cy+6-y
        y += l.height
        if i < 2:
            b = [C1, C2][i]
            b.y, b.height = y, bandH(b)
            y += b.height
    trackY = lambda b, t: b.y + b.reserved + b.pad + t*LSTEP
    for c in conns:
        c.sy = c.src.y + (c.src.h if c.sEdge == 'bottom' else 0)
        c.ty = c.tgt.y + (c.tgt.h if c.tEdge == 'bottom' else 0)
        sx, tx = proxy(c.sApp), proxy(c.tApp)
        pts = [[c.sx, c.sy]]
        if c.sApp.run:
            jy = trackY(c.sApp.jog, c.sJog.track)
            pts += [[c.sx, jy], [sx, jy]]
        my = trackY(c.band, c.main.track)
        pts += [[sx, my], [tx, my]]
        if c.tApp.run:
            jy = trackY(c.tApp.jog, c.tJog.track)
            pts += [[tx, jy], [c.tx, jy]]
        pts += [[c.tx, c.ty]]
        c.pts = [pt for i, pt in enumerate(pts) if not i or pt != pts[i-1]]
    ext = []
    for b in LV.srv.blocks:
        if b.kind == 'net' and b.item['external']:
            rightmost = LV.srv.rows[b.row][-1] is b
            ext.append(D(b=b, y=b.y+b.h-12, x1=b.x+b.w,
                         x2=width-MARGIN+14 if rightmost else b.x+b.w+GAPX-6, label=rightmost))
    return D(width=width, LV=LV, levels=levels, conns=conns, C1=C1, C2=C2, blk=blk, ext=ext,
             needGap=needGap, bottom=y, signalPorts=signalPorts)


def blockLines(b, state):
    it = b.item
    if b.kind == 'item':
        return [it['type']]
    if b.kind == 'panel':
        return ['KVM-удлинители', f"Стоек подключено: {sum(bool(r['kvm']) for r in state['racks'])}"]
    if b.kind == 'rack':
        return [f"Серверов: {it['servers']}"] + [label for f, label in [('ntp', 'Сервер NTP'), ('kvm', 'KVM'), ('ups', 'ИБП RACK')] if it[f]]
    if b.kind == 'net':
        lines = [f"Коммутаторов: {it['switches']}"]
        for f, label in [('fw', 'Межсетевых экранов'), ('cross', 'Опт. кроссов')]:
            try:
                positive = float(it[f]) > 0
            except (ValueError, TypeError):
                positive = False
            if positive:
                lines.append(f'{label}: {it[f]}')
        return lines + [label for f, label in [('external', 'Внешняя связь'), ('ups', 'ИБП RACK')] if it[f]]
    return [f"Контроллеров: {it['ctrls']}"]


def buildScheme(state):
    state = normalizeState(state)
    p = state['project']
    gap = GAP_MIN
    for _ in range(32):
        m = layout(state, gap)
        if m.needGap <= gap:
            break
        gap = m.needGap
    else:
        raise ValueError('Не удалось подобрать ширину каналов')
    blocks = [b for l in m.levels for b in l.blocks]
    for b in blocks:
        b.name, b.lines = b.item['name'], blockLines(b, state)
        b.fill = '#f1f5f9' if b.kind == 'panel' else '#ffffff'
    rooms = [D(id='lvl_'+l.key, name=p[{'op': 'operatorName', 'srv': 'serverName', 'auto': 'autoName'}[l.key]],
               fill=LEVEL_FILL[l.key], x=MARGIN, y=l.y, w=m.width-2*MARGIN, h=l.height) for l in m.levels]
    signals = []
    for b in m.LV.auto.blocks:
        sigs = signalsOf(b.item)
        for i, s in enumerate(sigs):
            x = m.signalPorts[(b.id, i)].x
            signals.append(D(block=b, kind=s['k'], color=COLORS[s['k']], label=signalLabel(s, p['showSignalCounts']),
                             exitX=(x-b.x)/b.w, x=x, y1=b.y+b.h, y2=b.y+b.h+SIG_LEN))
    used = {NAME_BY_COLOR[c.color] for c in m.conns} | {s.kind for s in signals}
    if m.ext:
        used.add('Оптика')
    names = [k for k in COLORS if k in used]
    cols = max(1, math.floor((m.width-2*MARGIN)/LEGEND_ITEM_W))
    ly = m.bottom+24
    legend = D(x=MARGIN, y=ly, w=m.width-2*MARGIN, h=34+max(1, math.ceil(len(names)/cols))*24,
               itemW=LEGEND_ITEM_W, items=[D(name=k, color=COLORS[k], x=MARGIN+14+(i%cols)*LEGEND_ITEM_W,
                                           y=ly+36+(i//cols)*24) for i, k in enumerate(names)])
    lines = [s for s in p['notesText'].split('\n') if s] if p['showNotes'] else []
    ny = legend.y+legend.h+18
    notes = D(x=MARGIN, y=ny, lines=lines) if lines else None
    # Публичная модель не содержит внутренних полос и циклических ссылок.
    conns = [D({k: c[k] for k in ['src', 'tgt', 'color', 'sx', 'tx', 'sy', 'ty', 'sEdge', 'tEdge', 'pts']}) for c in m.conns]
    return D(width=m.width, height=ny+(20+16*len(lines) if lines else 0)+24, title=p['title'], subtitle=p['subtitle'],
             fileName=fileNameOf(p), rooms=rooms, blocks=blocks, conns=conns, ext=m.ext, signals=signals,
             legend=legend, notes=notes)


# Имена Python и совместимые имена исходного JS API.
create_default_state = createDefaultState
normalize_state = normalizeState
serialize_state = serializeState
parse_state = parseState
make_resolvers = makeResolvers
clamp_per_row = clampPerRow
raster_scale = rasterScale
route_band = routeBand
build_scheme = buildScheme

from .render import to_svg, to_drawio  # noqa: E402

toSvg, toDrawio = to_svg, to_drawio
