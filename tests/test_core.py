import json
from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest

from python.scheme_core import *
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
    s['racks'][0]['servers'] = '3'
    n = normalizeState(s)
    assert n['project']['blocksPerRow'] == '12'
    assert 'unknown' not in n['project']
    ids = [i['id'] for k in ITEM_DEFAULTS for i in n[k]]
    assert len(set(ids)) == len(ids)
    assert KVM_PANEL_ID not in ids
    assert n['racks'][0]['servers'] == '3'
    assert normalizeState({'project': {'kvmPanel': 'false', 'title': False}})['project'] == PROJECT_DEFAULTS


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
    for c, edge in zip(m['conns'], [c for c in cells if c.get('edge') == '1']):
        points = edge.findall('./mxGeometry/Array/mxPoint')
        assert [(float(p.get('x')),float(p.get('y'))) for p in points] == [tuple(p) for p in c['pts'][1:-1]]


def test_route_band_disjoint_and_overlapping():
    hs=[dict(x1=a,x2=b,top=[],bot=[]) for a,b in [(0,10),(20,30),(5,15)]]
    assert routeBand(hs) == 2
    assert hs[0]['track'] != hs[2]['track']
    assert routeBand([]) == 0
