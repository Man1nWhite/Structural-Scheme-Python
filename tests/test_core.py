import json
from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest

from structural_scheme.scheme_core import *
from tests.projects import sampleState


@pytest.mark.parametrize('value,result', [('',1),(None,1),('nonsense',1),(-2,1),(3.9,3),('12',12),(999,12),(float('inf'),1),(float('nan'),1)])
def test_clamp(value, result):
    assert clampPerRow(value) == result


def test_roundtrip_and_schema():
    s = sampleState()
    assert parseState(serializeState(s)) == s
    s['project'].update(blocksPerRow='99', unknown='drop')
    s['opItems'][0]['id'] = KVM_PANEL_ID
    s['opItems'][1]['id'] = s['opItems'][2]['id']
    s['opItems'].append('not-a-dict')
    s['racks'][0]['servers'] = '3'
    n = normalizeState(s)
    assert n['project']['blocksPerRow'] == '12'
    assert 'unknown' not in n['project']
    ids = [i['id'] for k in ITEM_DEFAULTS for i in n[k]]
    assert len(set(ids)) == len(ids)
    assert KVM_PANEL_ID not in ids
    assert n['racks'][0]['servers'] == '3'
    assert normalizeState({'project': {'kvmPanel': 'false', 'title': False, 'blocksPerRow': 'abc'}})['project'] == {
        **PROJECT_DEFAULTS,
        'blocksPerRow': 1,
    }


@pytest.mark.parametrize('text', ['bad', '[]', '{"format":"other"}', '{"version":99}'])
def test_bad_projects(text):
    with pytest.raises(ValueError):
        parseState(text)


def test_resolvers():
    s = sampleState()
    r = makeResolvers(s)
    assert r.effNet('missing') == 'net1'
    assert r.effTarget(KVM_PANEL_ID, True) == KVM_PANEL_ID
    assert r.effTarget(KVM_PANEL_ID, False) == 'net1'
    assert r.effAutoTarget('a1', 'a1') == 'a2'
    assert makeResolvers(normalizeState({})).effNet('missing') is None


def test_default_and_new_items_are_independent():
    a, b = createDefaultState(), createDefaultState()
    a['project']['title'] = 'a'
    assert b['project']['title'] == PROJECT_DEFAULTS['title']
    for fn,k in [(newOpItem,'opItems'),(newRack,'racks'),(newNetCab,'netCabs'),(newAutoCab,'autoCabs')]:
        assert set(fn(b)) == set(ITEM_DEFAULTS[k])
    assert signalLabel({'k':'AO','n':0},True) == 'AO (0)'
    assert rasterScale(100,100) == 2
    assert rasterScale(10000,10000) == .4


def test_model_serializable_and_renderers_do_not_mutate():
    s = sampleState()
    s['project']['title'] = '<Тест & "проект">'
    m = buildScheme(s)
    before = deepcopy(m)
    svg, drawio = ET.fromstring(to_svg(m)), ET.fromstring(to_drawio(m))
    assert m == before
    json.dumps(m, allow_nan=False)
    svg_text = ''.join(svg.itertext())
    values = '\n'.join(c.get('value','') for c in drawio.iter('mxCell'))
    from html import unescape
    for b in m['blocks']:
        assert b['name'] in svg_text and b['name'] in unescape(values)
        for line in b['lines']:
            assert line in svg_text and line in unescape(values)
    assert m['title'] in svg_text and m['title'] in unescape(values)
    cells = list(drawio.iter('mxCell'))
    assert len({c.get('id') for c in cells}) == len(cells)
    for c, edge in zip(m['conns'], [c for c in cells if c.get('edge') == '1'], strict=False):
        points = edge.findall('./mxGeometry/Array/mxPoint')
        assert [(float(p.get('x')),float(p.get('y'))) for p in points] == [tuple(p) for p in c['pts'][1:-1]]
    s_no_sub = sampleState()
    s_no_sub['project']['subtitle'] = ''
    s_no_sub['netCabs'][0]['fw'] = 'нет'
    m_no_sub = buildScheme(s_no_sub)
    assert ET.fromstring(to_svg(m_no_sub)).tag.endswith('svg')
    assert ET.fromstring(to_drawio(m_no_sub)).tag == 'mxfile'


def test_route_band_disjoint_and_overlapping():
    hs=[dict(x1=a,x2=b,top=[],bot=[]) for a,b in [(0,10),(20,30),(5,15)]]
    assert routeBand(hs) == 2
    assert hs[0]['track'] != hs[2]['track']
    assert routeBand([]) == 0


def test_consts_and_port_registry_and_filename():
    assert CONSTS['BW'] == BW == 190
    assert CONSTS['GAP_MIN'] == GAP_MIN == 30
    d = D(a=1)
    d.b = 2
    assert d['b'] == 2 and d.a == 1
    with pytest.raises(AttributeError):
        _ = d.missing_attr
    assert len(fileNameOf({'fileName': 'x' * 200})) == 120
    assert fileNameOf({'fileName': ''}) == 'scheme'

    reg = PortRegistry()
    # Непересекающиеся по Y интервалы переиспользуют ту же координату X.
    assert reg.seat(50.0, 0.0, 10.0, 40.0, 60.0) == 50.0
    assert reg.seat(50.0, 20.0, 30.0, 40.0, 60.0) == 50.0
    # Пересекающийся по Y интервал сдвигается на шаг SLOT.
    shifted = reg.seat(50.0, 5.0, 15.0, 40.0, 60.0)
    assert abs(shifted - 50.0) >= SLOT - 1e-6


def test_build_scheme_gap_failure_guards(monkeypatch):
    from structural_scheme import routing

    s = createDefaultState()
    monkeypatch.setattr(routing, 'layout', lambda st, gap=GAP_MIN: D(needGap=gap + 10.0))
    with pytest.raises(ValueError, match='Не удалось подобрать ширину каналов'):
        routing.buildScheme(s)

    calls = 0

    def oscillating(st, gap=GAP_MIN):
        nonlocal calls
        calls += 1
        return D(needGap=60.0 if calls == 1 else (30.0 if calls == 2 else 999.0))

    monkeypatch.setattr(routing, 'layout', oscillating)
    with pytest.raises(ValueError, match='Не удалось подобрать ширину каналов'):
        routing.buildScheme(s)



def test_public_api_exposes_documented_core_functions():
    """README обещает API оригинала; функции должны быть в корне пакета."""
    import structural_scheme as package

    for name in [
        'normalizeState', 'normalize_state', 'parseState', 'serializeState', 'makeResolvers',
        'routeBand', 'rasterScale', 'newOpItem', 'newRack', 'newNetCab', 'newAutoCab',
    ]:
        assert callable(getattr(package, name)), name
    assert package.normalizeState({'project': {'title': 'T'}})['project']['title'] == 'T'


def test_huge_integers_fall_back_to_defaults_instead_of_crashing():
    """JSON позволяет целые любой длины; math.isfinite(int) бросал OverflowError."""
    huge = 10 ** 400
    s = normalizeState({
        'project': {'blocksPerRow': huge},
        'racks': [{'id': 'r0', 'servers': huge}],
        'autoCabs': [{'id': 'a0', 'ctrls': huge}],
    })
    assert s['project']['blocksPerRow'] == PROJECT_DEFAULTS['blocksPerRow']
    assert s['racks'][0]['servers'] == ITEM_DEFAULTS['racks']['servers']
    assert s['autoCabs'][0]['ctrls'] == ITEM_DEFAULTS['autoCabs']['ctrls']
    # Публичная проверка числовых полей тоже не должна падать.
    warnings = countWarnings({'racks': [{'name': 'N', 'servers': huge}], 'netCabs': [], 'autoCabs': []})
    assert warnings and 'Серверов' in warnings[0]


def test_xml_invalid_characters_are_stripped_during_normalization():
    """NUL/одиночные суррогаты ломали SVG/Draw.io и сериализацию ответа API."""
    s = parseState(
        '{"format":"structural-scheme","version":1,'
        '"project":{"title":"A\\u0000B\\ud800C\\u001fD"},'
        '"racks":[{"id":"r\\u0000","name":"N\\u0001"}]}'
    )
    assert s['project']['title'] == 'ABCD'
    assert s['racks'][0]['id'] == 'r'
    assert s['racks'][0]['name'] == 'N'
    m = buildScheme(s)
    assert ET.fromstring(to_svg(m)).tag.endswith('svg')
    assert ET.fromstring(to_drawio(m)).tag == 'mxfile'


def test_root_package_exports_full_public_api():
    import structural_scheme as pkg

    # Полный API исходного JS (core.js), а не только подмножество из README:
    # всё обещанное есть в корне пакета и в __all__.
    js_api = [
        'COLORS', 'NAME_BY_COLOR', 'OP_TYPES', 'OP_LINKS', 'AUTO_UPLINKS', 'KVM_PANEL_ID',
        'PROJECT_DEFAULTS', 'ITEM_DEFAULTS', 'FORMAT', 'FORMAT_VERSION', 'STORAGE_KEY',
        'PER_ROW_MAX', 'RASTER_SCALE', 'RASTER_MAX_PIXELS',
        'uid', 'fit', 'pad2', 'clampPerRow', 'rasterScale', 'signalLabel', 'signalsOf', 'fileNameOf',
        'routeBand', 'createDefaultState', 'newOpItem', 'newRack', 'newNetCab', 'newAutoCab',
        'serializeState', 'normalizeState', 'parseState', 'makeResolvers',
        'buildScheme', 'toSvg', 'toDrawio',
    ]
    for name in js_api:
        assert name in pkg.__all__, name
        assert hasattr(pkg, name), name
    assert all(hasattr(pkg, name) for name in pkg.__all__)
    assert pkg.normalizeState is normalizeState
    assert pkg.newOpItem is newOpItem
