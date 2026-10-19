"""Алгоритмы раскладки уровней, интервального раскрашивания и трассировки связей."""

from __future__ import annotations

import heapq
import math
from bisect import bisect_left, bisect_right, insort
from collections import defaultdict
from collections.abc import Sequence
from itertools import pairwise
from typing import Any

from .constants import (
    BW,
    COLORS,
    EXIT_STEP,
    GAP_MIN,
    GAP_TOL,
    HEAD,
    KVM_PANEL_ID,
    LEGEND_ITEM_W,
    LEVEL_FILL,
    LINE_SIZE,
    LSTEP,
    MARGIN,
    MAX_GAP_ITERS,
    MAX_PORTS_PER_EDGE,
    MAX_WARNINGS,
    NAME_BY_COLOR,
    NAME_SIZE,
    PORT_WARN_STEP,
    ROOM_LABEL_SIZE,
    SIG_H,
    SIG_LEN,
    SIGNAL_LABEL_SIZE,
    SLOT,
    SLOT_M,
    SUBTITLE_SIZE,
    TITLE_SIZE,
)
from .normalize import blockLines, countWarnings, makeResolvers, normalizeState
from .text_utils import D, clampPerRow, fileNameOf, fit, fitText, signalLabel, signalsOf


def routeBand(hs: Sequence[dict[str, Any]]) -> int:
    """Граф «выше» и назначение горизонтальных каналов из backup."""
    for h in hs:
        h['track'] = -1
    above: list[set[int]] = [set() for _ in hs]
    below: list[set[int]] = [set() for _ in hs]
    for i, a in enumerate(hs):
        for j, b in enumerate(hs):
            if i == j:
                continue
            if any(a['x1'] < x < a['x2'] for x in b['top']):
                above[i].add(j)
                below[j].add(i)
            if any(a['x1'] < x < a['x2'] for x in b['bot']):
                above[j].add(i)
                below[i].add(j)
    # Порядок обхода — по (число незанятых соседей выше, ширина, индекс).
    # Счётчики обновляются инкрементально: прежний min(len(above[i] & left))
    # на каждом шаге делал раскладку квадратичной.
    left = set(range(len(hs)))
    deg = [len(a) for a in above]
    heap = [(deg[i], hs[i]['x2'] - hs[i]['x1'], i) for i in range(len(hs))]
    heapq.heapify(heap)
    tracks = 0
    while left:
        while True:
            d, _, i = heap[0]
            if i in left and deg[i] == d:
                break
            heapq.heappop(heap)
        heapq.heappop(heap)
        left.discard(i)
        for j in below[i]:
            if j in left:
                deg[j] -= 1
                heapq.heappush(heap, (deg[j], hs[j]['x2'] - hs[j]['x1'], j))
        h = hs[i]
        t = max([0] + [hs[j]['track'] + 1 for j in above[i] if hs[j]['track'] >= 0])
        while any(
            k != i and b['track'] == t and not (b['x2'] + 4 < h['x1'] or b['x1'] > h['x2'] + 4)
            for k, b in enumerate(hs)
        ):
            t += 1
        h['track'] = t
        tracks = max(tracks, t + 1)
    return tracks


def assign_gap_slots(runs: Sequence[dict[str, Any]]) -> int:
    """Точное раскрашивание интервального графа (оптимум = макс. глубина).

    Интервалы замкнуты: касающиеся интервалы (hi == lo) получают разные слоты,
    поэтому освобождение слотов проверяет строгое неравенство active[0][0] < r['lo'].
    Сортировка по началу + очередь окончаний, не эвристика по длине.
    Внутри каждой связной компоненты слоты упорядочиваются так, чтобы подходы
    слева лежали левее подходов справа, а короткие обходы — ближе к своему блоку.
    """
    active: list[tuple[float, int]] = []
    free: list[int] = []
    count = 0
    comps: list[list[dict[str, Any]]] = []
    comp: list[dict[str, Any]] = []
    for _i, r in sorted(enumerate(runs), key=lambda pair: (pair[1]['lo'], pair[1]['hi'], pair[0])):
        while active and active[0][0] < r['lo']:
            _, slot = heapq.heappop(active)
            heapq.heappush(free, slot)
        if not active and comp:
            comps.append(comp)
            comp = []
        if free:
            slot = heapq.heappop(free)
        else:
            slot = count
            count += 1
        r['slot'] = slot
        comp.append(r)
        heapq.heappush(active, (r['hi'], slot))
    if comp:
        comps.append(comp)
    for group in comps:
        by_slot: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for r in group:
            by_slot[r['slot']].append(r)
        ordered = sorted(
            by_slot,
            key=lambda s: min(
                (0, float(r['hi'] - r['lo']), float(r.get('px', 0.0)))
                if r.get('side', 'L') == 'L'
                else (1, -float(r['hi'] - r['lo']), float(r.get('px', 0.0)))
                for r in by_slot[s]
            ),
        )
        remap = {old: new for new, old in enumerate(ordered)}
        for r in group:
            r['slot'] = remap[r['slot']]
    return count


class PortRegistry:
    """Совместный реестр вертикальных интервалов, отсортированный по X.

    Непересекающиеся по Y линии переиспользуют координаты без сдвигов.
    Конфликты ищутся окном через bisect: записи дальше spacing заведомо
    не могут нарушить разделение sep <= spacing.
    """

    def __init__(self) -> None:
        self.occupied: list[tuple[float, float, float, float]] = []

    def conflicts_near(self, center: float, lo: float, hi: float, radius: float) -> list[tuple[float, float]]:
        occupied = self.occupied
        i = bisect_left(occupied, (center - radius,))
        j = bisect_right(occupied, (center + radius, math.inf, math.inf, math.inf))
        return [(px, min(radius, sep)) for px, a, b, sep in occupied[i:j] if not (hi < a or lo > b)]

    def free_pos(
        self,
        start: float,
        lo: float,
        hi: float,
        spacing: float,
        lower: float,
        upper: float,
        direction: int,
    ) -> float | None:
        """Ближайшая свободная координата от start в одну сторону (без кандидатов)."""
        pos = start
        # Каждый шаг перепрыгивает хотя бы один накрывающий интервал, поэтому
        # попыток не может быть больше числа занятых записей (+ запас на отступ).
        # Жёсткая константа 512 обрывала поиск в длинном зазоре: проект с 490
        # портами у одного шкафа падал с «Недостаточно места для портов блока»,
        # хотя физический предел грани (559 портов) ещё не достигнут.
        for _ in range(len(self.occupied) + 512):
            if direction > 0 and pos > upper + 1e-8:
                return None
            if direction < 0 and pos < lower - 1e-8:
                return None
            covering = [
                (px, sep)
                for px, sep in self.conflicts_near(pos, lo, hi, spacing)
                if abs(pos - px) < sep - 1e-8
            ]
            if not covering:
                return pos
            # Перепрыгиваем весь накрывающий интервал: следующая проверка
            # точная, поэтому шагов ровно столько, сколько слияний до места.
            pos = max(px + sep for px, sep in covering) if direction > 0 else min(px - sep for px, sep in covering)
        # Недостижимо: каждый шаг перепрыгивает хотя бы одну запись, поэтому
        # шагов не может быть больше len(occupied). Оставлено как защита от
        # бесконечного цикла при неожиданных значениях координат.
        return None  # pragma: no cover

    def seat(
        self,
        x: float,
        lo: float,
        hi: float,
        lower: float,
        upper: float | None = None,
        spacing: float = SLOT,
    ) -> float:
        limit = math.inf if upper is None else upper
        candidate = min(max(x, lower), limit)
        # Ближайшая свободная позиция с обеих сторон; при равенстве — левая,
        # как и в прежнем порядке сортировки кандидатов по (|v-x|, v).
        options = [
            v
            for v in (
                self.free_pos(candidate, lo, hi, spacing, lower, limit, -1),
                self.free_pos(candidate, lo, hi, spacing, lower, limit, 1),
            )
            if v is not None
        ]
        if options:
            best = min(options, key=lambda v: (abs(v - x), v))
            insort(self.occupied, (best, lo, hi, spacing))
            return best
        # Очень высокий fan-in: физически невозможно выдержать шаг 7 px
        # на грани 190 px. Уменьшаем шаг, но никогда не совмещаем линии.
        if upper is not None and spacing > 0.1:
            return self.seat(x, lo, hi, lower, upper, spacing / 2)
        raise ValueError('Недостаточно места для портов блока')


def _band(id: str, kind: str = 'inner', reserved: int = 0, last: bool = False) -> D:
    return D(
        id=id,
        kind=kind,
        reserved=reserved,
        last=last,
        hs=[],
        tracks=0,
        y=0,
        height=0,
        pad=22 if kind == 'corridor' else 12,
    )


def _approach_info(LV: D, c: D, source: bool) -> tuple[D, D, str, D, D | None, float, float]:
    b, o = (c.src, c.tgt) if source else (c.tgt, c.src)
    edge = c.sEdge if source else c.tEdge
    lvl = LV[b.level]
    if b.level == o.level:
        r0, r1 = (min(b.row, o.row) + 1, max(b.row, o.row) - 1) if source else (1, 0)
    else:
        r0, r1 = (b.row + 1, lvl.nRows - 1) if edge == 'bottom' else (0, b.row - 1)
    blocked = any(any(bb.col == b.col for bb in lvl.rows[r]) for r in range(r0, r1 + 1))
    jog = lvl.bands[b.row if edge == 'bottom' else b.row - 1] if blocked else None
    port_pos = lvl.base + 4 * b.row + (3 if edge == 'bottom' else 1)
    end = jog.pos if jog else c.band.pos
    return b, o, edge, lvl, jog, min(port_pos, end) - 0.4, max(port_pos, end) + 0.4


def _cx(b: D) -> float:
    return float(b.x + b.w / 2)


def _proxy(a: D) -> float:
    return float(a.run.ax if a.run else a.x)


def _horizontal(a: float, b: float) -> D:
    return D(x1=min(a, b), x2=max(a, b), top=[], bot=[], track=0)


def _band_height(b: D) -> int:
    lines = 2 * b.pad + (b.tracks - 1) * LSTEP if b.tracks else 0
    return int(max(44, lines) if b.kind == 'corridor' else b.reserved + max(8 if b.last else 18, lines))


def _track_y(b: D, t: int) -> float:
    return float(b.y + b.reserved + b.pad + t * LSTEP)


def _block_height(b: D, state: dict[str, Any]) -> int:
    """Высота ячейки по фактическому числу строк описания (без пустого запаса)."""
    return 36 + 16 * len(blockLines(b, state))


def layout(state: dict[str, Any], GAPX: float = GAP_MIN) -> D:
    p = state['project']
    resolve = makeResolvers(state)
    per = clampPerRow(p['blocksPerRow'])
    colStep = BW + GAPX

    def build_level(key: str, items: list[dict[str, Any]]) -> D:
        raw = [items[i : i + per] for i in range(0, len(items), per)]
        cols = max([1] + [len(r) for r in raw])
        rows, blocks = [], []
        for r, row in enumerate(raw):
            off = (cols - len(row)) // 2
            bs = []
            for c, it in enumerate(row):
                b = D(
                    id=it['id'],
                    item=it,
                    kind=it['kind'],
                    level=key,
                    row=r,
                    col=off + c,
                    w=BW,
                    h=0,
                    x=0,
                    y=0,
                )
                b.h = _block_height(b, state)
                bs.append(b)
            rows.append(bs)
            blocks.extend(bs)
        return D(
            key=key,
            rows=rows,
            blocks=blocks,
            cols=cols,
            nRows=len(rows),
            rowH=[max(b.h for b in row) for row in rows],
            bands=[
                _band(f'{key}:{r}', reserved=SIG_H if key == 'auto' else 0, last=r == len(rows) - 1)
                for r in range(len(rows))
            ],
            gapRuns={},
            startX=0,
            y=0,
            height=0,
        )

    op = [{**i, 'kind': 'item'} for i in state['opItems']]
    if p['kvmPanel']:
        op.append(dict(id=KVM_PANEL_ID, kind='panel', name=p['kvmPanelName']))
    LV = D(
        op=build_level('op', op),
        srv=build_level(
            'srv',
            [{**i, 'kind': k} for key, k in [('racks', 'rack'), ('netCabs', 'net')] for i in state[key]],
        ),
        auto=build_level('auto', [{**i, 'kind': 'auto'} for i in state['autoCabs']]),
    )
    levels = list(LV.values())
    C1, C2 = _band('C1', 'corridor'), _band('C2', 'corridor')
    side = max(GAPX, 84 if any(c['external'] for c in state['netCabs']) else 0)
    width = max(880, 2 * (MARGIN + side) + max(lvl.cols for lvl in levels) * colStep - GAPX)
    for lvl in levels:
        lvl.startX = (width - (lvl.cols * colStep - GAPX)) / 2
        for b in lvl.blocks:
            b.x = lvl.startX + b.col * colStep
    blk = {b.id: b for lvl in levels for b in lvl.blocks}
    conns: list[D] = []

    def add_conn(b: D, id: Any, kind: str) -> None:
        if id in blk and id != b.id:
            conns.append(D(src=b, tgt=blk[id], color=COLORS.get(kind, COLORS['Витая пара'])))

    panel = blk.get(KVM_PANEL_ID)
    for b in LV.op.blocks:
        if b.kind != 'item':
            continue
        t = resolve.effTarget(b.item['target'], True)
        add_conn(b, t, 'KVM' if t == KVM_PANEL_ID else b.item['link'])
        if panel and b.item['kvmToPanel'] and t != KVM_PANEL_ID:
            add_conn(b, KVM_PANEL_ID, 'KVM')
    for b in LV.srv.blocks:
        if b.kind == 'rack':
            if panel and b.item['kvm']:
                add_conn(b, KVM_PANEL_ID, 'KVM')
            add_conn(b, resolve.effNet(b.item['netTarget']), 'Витая пара')
    rs: set[tuple[str, str]] = set()
    for b in LV.auto.blocks:
        add_conn(b, resolve.effNet(b.item['netTarget']), b.item['uplink'])
        if b.item['rs485Cab']:
            t = resolve.effAutoTarget(b.item['rs485Target'], b.id)
            if t:
                pair = (min(b.id, t), max(b.id, t))
                if pair not in rs:
                    rs.add(pair)
                    add_conn(b, t, 'RS-485')
    order = dict(op=0, srv=1, auto=2)
    for c in conns:
        s, t = c.src, c.tgt
        c.u = False
        if s.level == t.level:
            lvl = LV[s.level]
            if s.row < t.row:
                c.sEdge, c.tEdge, c.band = 'bottom', 'top', lvl.bands[t.row - 1]
            elif s.row > t.row:
                c.sEdge, c.tEdge, c.band = 'top', 'bottom', lvl.bands[t.row]
            else:
                c.u, c.sEdge, c.tEdge, c.band = True, 'bottom', 'bottom', lvl.bands[s.row]
        else:
            down = order[s.level] < order[t.level]
            c.sEdge, c.tEdge = ('bottom', 'top') if down else ('top', 'bottom')
            c.band = C1 if 'op' in (s.level, t.level) else C2

    # Символическая вертикальная ось не зависит от числа горизонтальных
    # каналов: целый ряд и каждая полоса имеют отдельные порядковые позиции.
    base = 0
    for i, lvl in enumerate(levels):
        lvl.base = base
        for r, band in enumerate(lvl.bands):
            band.pos = base + 4 * r + 4
        base += 4 * (lvl.nRows + 1) + 4
        if i < 2:
            [C1, C2][i].pos = base - 2

    def build_approach(c: D, source: bool, other_x: float) -> D:
        b, _o, _edge, lvl, jog, _, _ = _approach_info(LV, c, source)
        if jog is None:
            return D(x=_cx(b), run=None, jog=None)
        right = other_x >= _cx(b)
        g = b.col + 1 if right else b.col
        run = D(
            g=g,
            side='L' if right else 'R',
            lo=min(jog.pos, c.band.pos) - 0.4,
            hi=max(jog.pos, c.band.pos) + 0.4,
            px=_cx(b) if source else other_x,
            ax=lvl.startX + g * colStep - GAPX / 2,
        )
        lvl.gapRuns.setdefault(g, []).append(run)
        return D(x=_cx(b), run=run, jog=jog)

    for c in conns:
        c.sApp = build_approach(c, True, _cx(c.tgt))
    for c in conns:
        c.tApp = build_approach(c, False, _proxy(c.sApp))
    needGap: float = GAP_MIN
    physical_gaps: dict[float, list[D]] = defaultdict(list)
    for lvl in levels:
        for g, runs in lvl.gapRuns.items():
            gl = lvl.startX + g * colStep - GAPX
            physical_gaps[gl].extend(runs)
    for gl, runs in physical_gaps.items():
        count = assign_gap_slots(runs)
        needGap = max(needGap, 2 * SLOT_M + (count - 1) * SLOT)
        for run in runs:
            run.ax = gl + SLOT_M + run.slot * SLOT

    registry = PortRegistry()
    seat = registry.seat

    ports: dict[tuple[str, str], list[tuple[D, str, tuple[float, ...], tuple[float, float]]]] = defaultdict(list)
    for c in conns:
        s_lo, s_hi = _approach_info(LV, c, True)[-2:]
        t_lo, t_hi = _approach_info(LV, c, False)[-2:]
        s_span = s_hi - s_lo
        s_key = (
            1.0,
            _cx(c.tgt),
            s_span if _cx(c.tgt) < _cx(c.src) else -s_span,
            _proxy(c.sApp) if c.sApp.run else _cx(c.tgt),
        )
        tc = _cx(c.tgt)
        t_key = (
            (0.0 if _cx(c.src) < tc else 2.0, -_cx(c.src), 0.0, 0.0)
            if c.u
            else (1.0, _proxy(c.tApp) if c.tApp.run else _proxy(c.sApp), _proxy(c.sApp), _cx(c.src))
        )
        ports[(c.src.id, c.sEdge)].append((c, 'sx', s_key, (s_lo, s_hi)))
        ports[(c.tgt.id, c.tEdge)].append((c, 'tx', t_key, (t_lo, t_hi)))
    signalPorts: dict[tuple[str, int], D] = {}
    for b in LV.auto.blocks:
        sigs = signalsOf(b.item)
        for i, _sig in enumerate(sigs):
            port = D()
            signalPorts[(b.id, i)] = port
            pos = LV.auto.base + 4 * b.row + 3
            sig_x = b.x + b.w * (i + 1) / (len(sigs) + 1)
            ports[(b.id, 'bottom')].append((port, 'x', (1.0, sig_x, 0.0, 0.0), (pos - 0.4, pos + 0.6)))
    for (bid, _edge), ps in ports.items():
        b = blk[bid]
        if len(ps) > MAX_PORTS_PER_EDGE:
            # При большем числе портов шаг на грани BW меньше 0.3 px: линии
            # сливаются. Сообщаем об этом сразу, а не после поиска координат.
            raise ValueError('Недостаточно места для портов блока')
        ps.sort(key=lambda q: q[2])
        step = (
            BW / (len(ps) + 1)
            if any(field == 'x' for _, field, _, _ in ps)
            else min(EXIT_STEP, (BW - 24) / (len(ps) + 1))
        )
        # Отдельные непересекающиеся ячейки сохраняют порядок целей даже
        # при очень большом числе портов. Шаг адаптируется к fan-in.
        for i, (c, field, _, (lo, hi)) in enumerate(ps):
            x = _cx(b) + (i - (len(ps) - 1) / 2) * step
            c[field] = seat(x, lo, hi, x - step * 0.4, x + step * 0.4, min(SLOT, step * 0.8))
    for c in conns:
        c.sApp.x = c.sx
        c.tApp.x = c.tx

    # Порт сам по себе не ошибка, но слияние подписей и линий пользователь
    # должен видеть: при высоком fan-in шаг ограничен шириной блока.
    warnings: list[str] = []
    for (bid, _edge), ps in ports.items():
        xs = sorted(q[0][q[1]] for q in ps)
        gap = min((b_x - a_x for a_x, b_x in pairwise(xs)), default=math.inf)
        if gap < PORT_WARN_STEP:
            warnings.append(
                f'Шаг портов {gap:.2f} px у блока «{fit(blk[bid].item["name"], 24)}»: '
                'линии могут сливаться, добавьте блоки или разнесите цели'
            )

    for gl, runs in physical_gaps.items():
        for run in sorted(runs, key=lambda r: (r.slot, r.lo, r.hi)):
            run.ax = seat(gl + SLOT_M + run.slot * SLOT, run.lo, run.hi, gl + SLOT_M)
            needGap = max(needGap, math.ceil(run.ax - gl + SLOT_M))
    for c in conns:
        sx, tx = _proxy(c.sApp), _proxy(c.tApp)
        c.main = _horizontal(sx, tx)
        c.main['top' if c.sEdge == 'bottom' else 'bot'].append(sx)
        c.main['bot' if c.tEdge == 'top' else 'top'].append(tx)
        c.band.hs.append(c.main)
        for prefix, a, px, edge in [('s', c.sApp, c.sx, c.sEdge), ('t', c.tApp, c.tx, c.tEdge)]:
            if a.run:
                h = _horizontal(px, _proxy(a))
                h['top' if edge == 'bottom' else 'bot'].append(px)
                h['bot' if edge == 'bottom' else 'top'].append(_proxy(a))
                c[prefix + 'Jog'] = h
                a.jog.hs.append(h)
    for b in [C1, C2] + [b for lvl in levels for b in lvl.bands]:
        b.tracks = routeBand(b.hs)
    y = 82 if p['subtitle'] else 58
    for i, lvl in enumerate(levels):
        lvl.y = y
        cy = y + HEAD
        for r, row in enumerate(lvl.rows):
            for b in row:
                b.y = cy
            cy += lvl.rowH[r]
            band = lvl.bands[r]
            band.y, band.height = cy, _band_height(band)
            cy += band.height
        if not lvl.nRows:
            cy += 12
        lvl.height = cy + 6 - y
        y += lvl.height
        if i < 2:
            b = [C1, C2][i]
            b.y, b.height = y, _band_height(b)
            y += b.height
    for c in conns:
        c.sy = c.src.y + (c.src.h if c.sEdge == 'bottom' else 0)
        c.ty = c.tgt.y + (c.tgt.h if c.tEdge == 'bottom' else 0)
        sx, tx = _proxy(c.sApp), _proxy(c.tApp)
        pts = [[c.sx, c.sy]]
        if c.sApp.run:
            jy = _track_y(c.sApp.jog, c.sJog.track)
            pts += [[c.sx, jy], [sx, jy]]
        my = _track_y(c.band, c.main.track)
        pts += [[sx, my], [tx, my]]
        if c.tApp.run:
            jy = _track_y(c.tApp.jog, c.tJog.track)
            pts += [[tx, jy], [c.tx, jy]]
        pts += [[c.tx, c.ty]]
        c.pts = [pt for i, pt in enumerate(pts) if not i or pt != pts[i - 1]]
    ext = []
    for b in LV.srv.blocks:
        if b.kind == 'net' and b.item['external']:
            rightmost = LV.srv.rows[b.row][-1] is b
            ext.append(
                D(
                    b=b,
                    y=b.y + b.h - 12,
                    x1=b.x + b.w,
                    x2=width - MARGIN + 14 if rightmost else b.x + b.w + GAPX - 6,
                    label=rightmost,
                )
            )
    return D(
        width=width,
        LV=LV,
        levels=levels,
        conns=conns,
        C1=C1,
        C2=C2,
        blk=blk,
        ext=ext,
        needGap=needGap,
        bottom=y,
        signalPorts=signalPorts,
        warnings=warnings,
    )


def buildScheme(state: dict[str, Any]) -> D:
    state = normalizeState(state)
    p = state['project']
    # Зазор между колонками ищется как неподвижная точка: требование при узком
    # зазоре завышено сдвинутыми обходами, поэтому одного роста недостаточно —
    # после стабилизации зазор возвращается к фактически необходимому.
    # Итерации ограничены MAX_GAP_ITERS (32); при осцилляции выбирается
    # максимум посещённых значений, гарантирующий помещаемость всех слотов.
    gap: float = GAP_MIN
    m: D | None = None
    seen: list[float] = []
    for _ in range(MAX_GAP_ITERS):
        m = layout(state, gap)
        want = max(float(GAP_MIN), float(m.needGap))
        if abs(want - gap) <= GAP_TOL:
            break
        if any(abs(want - s) <= GAP_TOL for s in seen):
            gap = max([gap, want, *seen])
            m = layout(state, gap)
            break
        seen.append(gap)
        gap = want
    else:
        raise ValueError('Не удалось подобрать ширину каналов')
    assert m is not None
    if m.needGap > gap + GAP_TOL:
        raise ValueError('Не удалось подобрать ширину каналов')
    blocks = [b for lvl in m.levels for b in lvl.blocks]
    shortened = 0
    for b in blocks:
        full = b.item['name']
        lines = blockLines(b, state)
        # Подписи обрезаются по ширине блока (как fit(name, 28) в core.js),
        # иначе длинное имя наезжает на соседний блок во всех форматах.
        b.name = fitText(full, b.w - 16, NAME_SIZE, True)
        b.lines = [fitText(s, b.w - 20, LINE_SIZE) for s in lines]
        shortened += (b.name != full) + sum(1 for s, t in zip(b.lines, lines, strict=True) if s != t)
        b.fill = '#f1f5f9' if b.kind == 'panel' else '#ffffff'
    warnings = list(m.warnings)
    if shortened:
        warnings.append(f'Сокращено подписей, не помещающихся в блок: {shortened}')
    # Подписи вне блоков (заголовки, помещения, сигналы, примечания) тоже не
    # должны уезжать за лист: они обрезаются по его ширине, а не только имена
    # блоков. Число таких сокращений пользователь видит отдельным пунктом.
    shortened_outer = 0
    title = fitText(p['title'], m.width - 36, TITLE_SIZE, True)
    subtitle = fitText(p['subtitle'], m.width - 36, SUBTITLE_SIZE) if p['subtitle'] else ''
    shortened_outer += (title != p['title']) + (subtitle != p['subtitle'])
    rooms = []
    for lvl in m.levels:
        full_room = p[{'op': 'operatorName', 'srv': 'serverName', 'auto': 'autoName'}[lvl.key]]
        room_name = fitText(full_room, m.width - 2 * MARGIN - 28, ROOM_LABEL_SIZE, True)
        shortened_outer += room_name != full_room
        rooms.append(
            D(
                id='lvl_' + lvl.key,
                name=room_name,
                fill=LEVEL_FILL[lvl.key],
                x=MARGIN,
                y=lvl.y,
                w=m.width - 2 * MARGIN,
                h=lvl.height,
            )
        )
    signals = []
    for b in m.LV.auto.blocks:
        sigs = signalsOf(b.item)
        for i, s in enumerate(sigs):
            x = m.signalPorts[(b.id, i)].x
            full_label = signalLabel(s, p['showSignalCounts'])
            label = fitText(full_label, 64, SIGNAL_LABEL_SIZE, True)
            shortened_outer += label != full_label
            signals.append(
                D(
                    block=b,
                    kind=s['k'],
                    color=COLORS[s['k']],
                    label=label,
                    exitX=(x - b.x) / b.w,
                    x=x,
                    y1=b.y + b.h,
                    y2=b.y + b.h + SIG_LEN,
                )
            )
    used = {NAME_BY_COLOR[c.color] for c in m.conns} | {s.kind for s in signals}
    if m.ext:
        used.add('Оптика')
    names = [k for k in COLORS if k in used]
    cols = max(1, math.floor((m.width - 2 * MARGIN) / LEGEND_ITEM_W))
    ly = m.bottom + 24
    legend = D(
        x=MARGIN,
        y=ly,
        w=m.width - 2 * MARGIN,
        h=34 + max(1, math.ceil(len(names) / cols)) * 24,
        itemW=LEGEND_ITEM_W,
        items=[
            D(
                name=k,
                color=COLORS[k],
                x=MARGIN + 14 + (i % cols) * LEGEND_ITEM_W,
                y=ly + 36 + (i // cols) * 24,
            )
            for i, k in enumerate(names)
        ],
    )
    full_lines = [s for s in p['notesText'].split('\n') if s] if p['showNotes'] else []
    lines = [fitText(s, m.width - 2 * MARGIN, LINE_SIZE) for s in full_lines]
    shortened_outer += sum(1 for s, t in zip(lines, full_lines, strict=True) if s != t)
    if shortened_outer:
        warnings.append(f'Сокращено подписей вне блоков, не помещающихся на лист: {shortened_outer}')
    warnings += countWarnings(state)
    if len(warnings) > MAX_WARNINGS:
        warnings = warnings[:MAX_WARNINGS] + [f'…и ещё предупреждений: {len(warnings) - MAX_WARNINGS}']
    ny = legend.y + legend.h + 18
    notes = D(x=MARGIN, y=ny, lines=lines) if lines else None
    # Публичная модель не содержит внутренних полос и циклических ссылок.
    conns = [
        D({k: c[k] for k in ['src', 'tgt', 'color', 'sx', 'tx', 'sy', 'ty', 'sEdge', 'tEdge', 'pts']})
        for c in m.conns
    ]
    return D(
        width=m.width,
        height=ny + (20 + 16 * len(lines) if lines else 0) + 24,
        title=title,
        subtitle=subtitle,
        fileName=fileNameOf(p),
        rooms=rooms,
        blocks=blocks,
        conns=conns,
        ext=m.ext,
        signals=signals,
        legend=legend,
        notes=notes,
        warnings=warnings,
    )


route_band = routeBand
build_scheme = buildScheme
