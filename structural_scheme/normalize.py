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
from .text_utils import D, clampPerRow, clean_text, fit, pad2, uid


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


# Готовые проекты для «быстрого старта» веб-интерфейса: один клик — рабочая схема.
# id → (заголовок кнопки, подсказка). Порядок словаря — порядок показа в интерфейсе.
PRESET_META: dict[str, tuple[str, str]] = {
    'demo': ('Демонстрационный проект', 'Готовый пример: 4 устройства, стойка, сетевой шкаф и три шкафа автоматики'),
    'typical': ('Типовая АСУ ТП', 'KVM-щит, две стойки, два сетевых шкафа и три шкафа ША с RS-485'),
    'minimal': ('Минимальный проект', 'Одно АРМ, стойка, сетевой шкаф и один шкаф автоматики'),
    'empty': ('Пустой проект', 'Только названия помещений — соберите схему с нуля'),
}


def createPresetState(kind: str) -> dict[str, Any]:
    """Готовый проект шаблона `kind` (см. PRESET_META); неизвестный шаблон — ValueError."""
    if kind not in PRESET_META:
        raise ValueError('Неизвестный шаблон проекта.')
    if kind == 'demo':
        return createDefaultState()
    s: dict[str, Any] = {'project': deepcopy(PROJECT_DEFAULTS), **{k: [] for k in ITEM_DEFAULTS}}
    if kind == 'empty':
        s['project'].update(title='Новый проект', subtitle='Структурная схема АСУ ТП', fileName='new_scheme')
        return s
    net = newNetCab(s)
    if kind == 'minimal':
        net.update(switches=2, fw=1, cross=1, external=True)
    else:
        net.update(switches=3, fw=1, cross=2, external=True)
    s['netCabs'].append(net)
    if kind == 'typical':
        second = newNetCab(s)
        second.update(switches=2, fw=0, cross=2, external=False)
        s['netCabs'].append(second)
    op = newOpItem(s)
    op.update(name='АРМ оператора №1', type='АРМ', kvmToPanel=kind == 'typical')
    s['opItems'].append(op)
    rack = newRack(s)
    rack.update(servers=2 if kind == 'minimal' else 4, kvm=True, ntp=True, ups=True)
    s['racks'].append(rack)
    if kind == 'typical':
        for name, type_, link, kvm in [
            ('АРМ оператора №2', 'АРМ', 'Витая пара', True),
            ('АРМ технолога', 'АРМ', 'Оптика', False),
            ('Принтер сетевой', 'Принтер', 'Витая пара', False),
            ('Панель управления', 'Панель управления', 'Витая пара', False),
        ]:
            it = newOpItem(s)
            it.update(name=name, type=type_, link=link, kvmToPanel=kvm)
            s['opItems'].append(it)
        rack2 = newRack(s)
        rack2.update(name='Серверная стойка №2', servers=2, kvm=True, ntp=False, ups=True)
        rack2['netTarget'] = s['netCabs'][1]['id']
        s['racks'].append(rack2)
    auto = newAutoCab(s)
    auto.update(ctrls=2 if kind == 'typical' else 1, rs485=True, diN=32 if kind == 'typical' else 16,
                doN=32 if kind == 'typical' else 8, aiN=16 if kind == 'typical' else 8,
                aoN=2 if kind == 'typical' else 0, ao=kind == 'typical')
    s['autoCabs'].append(auto)
    if kind == 'typical':
        for step, ctrls in enumerate([1, 1], start=2):
            it = newAutoCab(s)
            it.update(ctrls=ctrls, rs485=True, ao=step == 2, diN=32, doN=32, aiN=16, aoN=2 if step == 2 else 0)
            it['rs485Cab'] = True
            it['rs485Target'] = s['autoCabs'][-1]['id']
            if step == 3:
                it['netTarget'] = s['netCabs'][1]['id']
            s['autoCabs'].append(it)
        s['project'].update(
            title='Структурная схема АСУ ТП',
            subtitle='Автоматизированная система управления технологическим процессом',
            fileName='asu_tp_scheme',
            kvmPanel=True,
            showSignalCounts=True,
        )
    return s


def listPresets() -> list[dict[str, Any]]:
    """Шаблоны для веб-интерфейса: id, заголовок, подсказка и готовое состояние."""
    return [
        {'id': kind, 'title': meta[0], 'hint': meta[1], 'state': createPresetState(kind)}
        for kind, meta in PRESET_META.items()
    ]


def _finite(v: Any) -> bool:
    """Конечное число; очень большой int (например, из JSON) не роняет float()."""
    try:
        return math.isfinite(v)
    except (OverflowError, TypeError, ValueError):
        return False


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
            else (isinstance(v, str) or type(v) in (int, float) and _finite(v))
            if type(d) in (int, float)
            else isinstance(v, str)
        )
        if ok:
            # Числа в char-полях (например, servers='3') остаются как есть,
            # строки очищаются от символов, ломающих XML/SVG/Draw.io.
            out[k] = clean_text(v) if isinstance(v, str) else v
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
            except (ValueError, TypeError, OverflowError):
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
                except (TypeError, ValueError, OverflowError):
                    bad = True
                if bad:
                    # Значение может быть произвольно длинной строкой из JSON:
                    # предупреждение уходит в статус редактора и ответ API,
                    # поэтому repr обрезается, а не размножается целиком.
                    shown = repr(it[f])
                    if len(shown) > 42:
                        shown = shown[:39] + '…'
                    out.append(
                        f'{fit(it["name"], 24)}: «{FIELD_LABELS[f]}» = {shown} — '
                        'ожидается неотрицательное число'
                    )
    return out


create_default_state = createDefaultState
create_preset_state = createPresetState
list_presets = listPresets
normalize_state = normalizeState
serialize_state = serializeState
parse_state = parseState
make_resolvers = makeResolvers
