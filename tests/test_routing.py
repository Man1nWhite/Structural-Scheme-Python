import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from structural_scheme.scheme_core import *
from structural_scheme.validation import layoutProblems
from tests.projects import loadedState, makeRandom, sampleState


def check(s):
    m = buildScheme(s)
    assert layoutProblems(m) == []
    return m


def test_reference_projects():
    check(createDefaultState())
    check(sampleState())
    check(loadedState())
    check(normalizeState({}))
    s = createDefaultState()
    s['racks'] = []
    s['netCabs'] = []
    check(s)


@pytest.mark.parametrize('per', [1, 12])
def test_rows(per):
    s = loadedState()
    s['project']['blocksPerRow'] = per
    check(s)


@pytest.mark.parametrize('seed,count', [(7,40), (11,20)])
def test_original_random(seed, count):
    next_state = makeRandom(seed)
    for i in range(count):
        s = next_state()
        m = buildScheme(s)
        assert layoutProblems(m) == [], f'проект №{i}, seed={seed}: {layoutProblems(m)[:5]}'


name = st.text(max_size=60)
count = st.one_of(st.integers(-5, 5000), st.floats(-2, 1e6, allow_nan=False, allow_infinity=False), st.text(max_size=4))


@st.composite
def projects(draw):
    s = normalizeState({})
    s['project'].update(blocksPerRow=draw(st.one_of(st.integers(1,12), st.floats(-1,99,allow_nan=False,allow_infinity=False), st.text(max_size=3))),
                        kvmPanel=draw(st.booleans()), showSignalCounts=draw(st.booleans()),
                        title=draw(name), notesText=draw(st.one_of(st.just('Первое\nВторое'), name)),
                        fileName=draw(st.one_of(st.just('scheme'), name)))
    for k, max_n in [('netCabs',8), ('racks',8), ('opItems',16), ('autoCabs',16)]:
        for i in range(draw(st.integers(0,max_n))):
            it = {**ITEM_DEFAULTS[k], 'id': k+str(i), 'name': draw(name)}
            for f, default in it.copy().items():
                if type(default) is bool:
                    it[f] = draw(st.booleans())
                elif type(default) is int:
                    it[f] = draw(count)          # числа, строки-числа и мусор
            if k == 'opItems':
                it['target'] = draw(st.sampled_from([None, 'missing', KVM_PANEL_ID] + [c['id'] for c in s['netCabs']+s['racks']]))
                it['link'] = draw(st.sampled_from(OP_LINKS))
            if k in ['racks','autoCabs']:
                it['netTarget'] = draw(st.sampled_from([None, 'missing']+[c['id'] for c in s['netCabs']]))
            if k == 'autoCabs':
                it['rs485Target'] = 'autoCabs'+str(draw(st.integers(0,16)))
                it['uplink'] = draw(st.sampled_from(AUTO_UPLINKS))
            s[k].append(it)
    return s


@given(projects())
@settings(max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_1000(s):
    check(s)


def test_interval_assignment_is_optimal():
    runs = [dict(lo=a, hi=b) for a,b in [(0,3),(1,2),(4,6),(2,5),(7,8)]]
    assert assign_gap_slots(runs) == 3
    for a in runs:
        for b in runs:
            if a is not b and a['slot'] == b['slot']:
                assert a['hi'] < b['lo'] or b['hi'] < a['lo']


def test_dense_corridor_regression():
    # Сжатый контрпример Hypothesis: общая граница коридора и разные сетки.
    s = normalizeState({})
    s['project']['blocksPerRow'] = 2
    for k, n in [('opItems',4),('racks',1),('netCabs',1),('autoCabs',10)]:
        s[k] = [{**ITEM_DEFAULTS[k], 'id': f'{k}{i}'} for i in range(n)]
    check(s)


def test_signal_ports_do_not_share_connection_verticals():
    from shapely.geometry import LineString
    m = check(loadedState())
    for s in m.signals:
        line = LineString([(s.x,s.y1),(s.x,s.y2)])
        for c in m.conns:
            assert line.intersection(LineString(c.pts)).length <= 1.5


@given(st.lists(st.tuples(st.integers(-10,10),st.integers(-10,10)),max_size=30))
def test_interval_coloring_equals_maximum_depth(pairs):
    runs = [dict(lo=min(a,b),hi=max(a,b)) for a,b in pairs]
    count = assign_gap_slots(runs)
    depth = max([0]+[sum(r['lo']<=x<=r['hi'] for r in runs) for x in range(-10,11)])
    assert count == depth
    for i,a in enumerate(runs):
        for b in runs[i+1:]:
            if a['slot'] == b['slot']:
                assert a['hi'] < b['lo'] or b['hi'] < a['lo']


def test_validator_detects_original_failure_modes():
    from structural_scheme.scheme_core import D
    b = D(id='b',x=20,y=20,w=20,h=20)
    m = D(width=100,height=100,blocks=[b],rooms=[],signals=[],ext=[],notes=None,
          legend=D(x=0,y=80,w=100,h=20,items=[]), conns=[])
    endpoint = dict(id='other')
    m.conns = [dict(src=endpoint,tgt=endpoint,pts=[[0,30],[60,30]]),
               dict(src=endpoint,tgt=endpoint,pts=[[10,30],[101,30]]),
               dict(src=endpoint,tgt=endpoint,pts=[[5,50],[5,50.005],[15,50]])]
    p = layoutProblems(m)
    assert any('Наложение' in x for x in p)
    assert any('сквозь блок' in x for x in p)
    assert any('выходит за лист' in x for x in p)
    assert any('Пустой отрезок' in x for x in p)
