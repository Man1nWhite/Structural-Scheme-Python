"""Нормализация, сериализация, фабрики элементов и проверка числовых полей."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from typing import Any

from .constants import (
    COUNT_FIELDS,
    FIELD_LABELS,
    FORMAT,
    FORMAT_VERSION,
    ITEM_DEFAULTS,
    KVM_PANEL_ID,
    PROJECT_DEFAULTS,
)
from .text_utils import D, clampPerRow, fit, pad2, uid


def _new(state: dict[str, Any], key: str, name: str) -> dict[str, Any]:
    return {**ITEM_DEFAULTS[key], 'id': uid(), 'name': name}


def newNetCab(state: dict[str, Any]) -> dict[str, Any]:
    return _new(state, 'netCabs', 'Шкаф сетевой ШС-' + pad2(len(state['netCabs']) + 1))


def _net(state: dict[str, Any]) -> Any:
    return state['netCabs'][0]['id'] if state['netCabs'] else None


def newOpItem(state: dict[str, Any]) -> dict[str, Any]:
    return {**_new(state, 'opItems', 'АРМ оператора №' + str(len(state['opItems']) + 1)), 'target': _net(state)}


def newRack(state: dict[str, Any]) -> dict[str, Any]:
    return {**_new(state, 'racks', 'Серверная стойка №' + str(len(state['racks']) + 1)), 'netTarget': _net(state)}


def newAutoCab(state: dict[str, Any]) -> dict[str, Any]:
    return {
        **_new(state, 'autoCabs', 'Шкаф ША-' + pad2(len(state['autoCabs']) + 1)),
        'netTarget': _net(state),
        'rs485Target': state['autoCabs'][0]['id'] if state['autoCabs'] else None,
    }


def createDefaultState() -> dict[str, Any]:
    s: dict[str, Any] = {'project': deepcopy(PROJECT_DEFAULTS), **{k: [] for k in ITEM_DEFAULTS}}
    s['netCabs'] = [{**newNetCab(s), 'fw': 1, 'cross': 2, 'external': True}]
    for name, kind, kvm in [
        ('АРМ оператора №1', 'АРМ', True),
        ('АРМ оператора №2', 'АРМ', True),
        ('Принтер сетевой', 'Принтер', False),
        ('Панель управления', 'Панель управления', False),
    ]:
        s['opItems'].append({**newOpItem(s), 'name': name, 'type': kind, 'kvmToPanel': kvm})
    s['racks'] = [{**newRack(s), 'servers': 3, 'kvm': True, 'ntp': True}]
    for n in [2, 1, 1]:
        s['autoCabs'].append(
            {
                **newAutoCab(s),
                'ctrls': n,
                'ao': True,
                'rs485': True,
                'diN': 32,
                'doN': 32,
                'aiN': 16,
                'aoN': 2,
                'rs485Target': None,
            }
        )
    return s


def _pick(src: Any, defaults: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(defaults)
    if not isinstance(src, dict):
        return out
    for k, d in defaults.items():
        if k not in src:
            continue
        v = src[k]
        ok = (
            (v is None or isinstance(v, str))
            if d is None
            else type(v) is bool
            if type(d) is bool
            else (isinstance(v, str) or type(v) in (int, float) and math.isfinite(v))
            if type(d) in (int, float)
            else isinstance(v, str)
        )
        if ok:
            out[k] = v
    return out


def normalizeState(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError('Файл не содержит проект структурной схемы.')
    if raw.get('format', FORMAT) != FORMAT:
        raise ValueError('Файл не является проектом структурной схемы.')
    if type(raw.get('version')) in (int, float) and raw['version'] > FORMAT_VERSION:
        raise ValueError('Проект сохранён в более новом формате, обновите приложение.')
    s: dict[str, Any] = {'project': _pick(raw.get('project'), PROJECT_DEFAULTS)}
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


def serializeState(state: dict[str, Any]) -> str:
    return json.dumps(
        dict(format=FORMAT, version=FORMAT_VERSION, **{k: state[k] for k in ['project', *ITEM_DEFAULTS]}),
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )


def parseState(text: str) -> dict[str, Any]:
    try:
        raw = json.loads(text, parse_constant=lambda _: None)
    except (ValueError, TypeError) as e:
        raise ValueError('Файл повреждён или не является JSON.') from e
    return normalizeState(raw)


def makeResolvers(state: dict[str, Any]) -> D:
    nets, racks, autos = state['netCabs'], state['racks'], state['autoCabs']
    ids = {i['id'] for i in nets + racks}

    def effTarget(id: Any, allowPanel: bool = False) -> Any:
        if allowPanel and id == KVM_PANEL_ID and state['project']['kvmPanel']:
            return id
        return id if id in ids else (nets + racks)[0]['id'] if nets + racks else None

    def effNet(id: Any) -> Any:
        return id if any(c['id'] == id for c in nets) else _net(state)

    def effAutoTarget(id: Any, sourceId: Any) -> Any:
        if id != sourceId and any(c['id'] == id for c in autos):
            return id
        return next((c['id'] for c in autos if c['id'] != sourceId), None)

    return D(effTarget=effTarget, effNet=effNet, effAutoTarget=effAutoTarget)


def blockLines(b: D, state: dict[str, Any]) -> list[str]:
    it = b.item
    if b.kind == 'item':
        return [it['type']]
    if b.kind == 'panel':
        return ['KVM-удлинители', f"Стоек подключено: {sum(bool(r['kvm']) for r in state['racks'])}"]
    if b.kind == 'rack':
        return [f"Серверов: {it['servers']}"] + [
            label for f, label in [('ntp', 'Сервер NTP'), ('kvm', 'KVM'), ('ups', 'ИБП RACK')] if it[f]
        ]
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


def countWarnings(state: dict[str, Any]) -> list[str]:
    """Числовые поля, которые не неотрицательные числа (например, 'много' или -5)."""
    out = []
    for key, fields in COUNT_FIELDS.items():
        for it in state[key]:
            for f in fields:
                try:
                    value = float(it[f])
                    bad = not math.isfinite(value) or value < 0
                except (TypeError, ValueError):
                    bad = True
                if bad:
                    out.append(
                        f'{fit(it["name"], 24)}: «{FIELD_LABELS[f]}» = {it[f]!r} — '
                        'ожидается неотрицательное число'
                    )
    return out


create_default_state = createDefaultState
normalize_state = normalizeState
serialize_state = serializeState
parse_state = parseState
make_resolvers = makeResolvers
