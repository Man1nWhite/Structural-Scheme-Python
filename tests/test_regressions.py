"""Регрессии из ревью: подписи, плотность портов, зазор, концы связей, числа."""
import time
from xml.etree import ElementTree as ET

import pytest

from structural_scheme.scheme_core import *
from structural_scheme.validation import layoutProblems
from tests.projects import loadedState

LONG = 'АРМ оператора центрального пульта управления установки каталитического крекинга №12'


def dense(n):
    """n целей на одну грань одной стойки — предельный fan-in."""
    s = normalizeState({})
    s['project']['blocksPerRow'] = 4
    s['netCabs'] = [{**ITEM_DEFAULTS['netCabs'], 'id': 'n0'}]
    s['racks'] = [{**ITEM_DEFAULTS['racks'], 'id': 'r0', 'netTarget': 'n0'}]
    s['opItems'] = [{**ITEM_DEFAULTS['opItems'], 'id': f'o{i}', 'target': 'r0'} for i in range(n)]
    return s


def big_project():
    """500 блоков: смешанный плотный проект для проверки зазора и времени."""
    s = normalizeState({})
    s['project']['blocksPerRow'] = 8
    s['netCabs'] = [{**ITEM_DEFAULTS['netCabs'], 'id': f'n{i}', 'external': i == 0} for i in range(10)]
    s['racks'] = [{**ITEM_DEFAULTS['racks'], 'id': f'r{i}', 'netTarget': 'n0', 'kvm': i % 2 == 0} for i in range(60)]
    s['opItems'] = [{**ITEM_DEFAULTS['opItems'], 'id': f'o{i}', 'target': 'n0'} for i in range(120)]
    s['autoCabs'] = [{**ITEM_DEFAULTS['autoCabs'], 'id': f'a{i}', 'netTarget': f'n{i%10}', 'rs485Cab': i > 0,
                      'rs485Target': f'a{i-1}'} for i in range(310)]
    return s


def test_long_labels_are_shortened_to_fit_blocks():
    s = createDefaultState()
    s['opItems'][0]['name'] = LONG
    s['racks'][0]['name'] = 'Серверная стойка резервирования АСУ ТП верхнего уровня'
    s['netCabs'][0]['name'] = 'Шкаф сетевой верхнего уровня ШС-01'
    s['autoCabs'][0]['name'] = 'Шкаф автоматики системы противоаварийной защиты ША-01'
    m = buildScheme(s)
    assert layoutProblems(m) == []
    for b in m['blocks']:
        assert textWidth(b['name'], 11, True) <= b['w']-16, b['name']
        for line in b['lines']:
            assert textWidth(line, 10) <= b['w']-20
    shortened = [b['name'] for b in m['blocks'] if b['name'].endswith('…')]
    assert len(shortened) == 4
    # Полного текста нет ни в SVG, ни в Draw.io, зато есть сокращённый.
    svg, drawio = to_svg(m), to_drawio(m)
    assert LONG not in svg
    assert m['blocks'][0]['name'] in svg
    assert any(m['blocks'][0]['name'] in c.get('value', '') for c in ET.fromstring(drawio).iter('mxCell'))


def test_shortening_and_bad_numbers_are_visible_to_user():
    s = createDefaultState()
    s['opItems'][0]['name'] = LONG
    s['racks'][0]['servers'] = 'много'
    s['autoCabs'][0]['diN'] = -5
    s['netCabs'][0]['switches'] = 'пара'
    m = buildScheme(s)
    text = ' | '.join(m['warnings'])
    assert 'Сокращено подписей' in text
    assert 'Серверная стойка №1' in text and '«Серверов»' in text
    assert '«Количество DI»' in text and '«Коммутаторов»' in text
    # Обычные числа и строки-числа не считаются ошибкой (совместимость v1).
    ok = createDefaultState()
    ok['racks'][0]['servers'] = '3'
    assert buildScheme(ok)['warnings'] == []


def test_warnings_are_capped():
    s = normalizeState({})
    s['racks'] = [{**ITEM_DEFAULTS['racks'], 'id': f'r{i}', 'servers': 'мусор'} for i in range(50)]
    warnings = buildScheme(s)['warnings']
    assert len(warnings) == MAX_WARNINGS + 1
    assert warnings[-1].startswith('…и ещё предупреждений: ')


def test_validator_detects_connection_not_touching_blocks():
    m = buildScheme(createDefaultState())
    assert layoutProblems(m) == []
    # Связь, висящая в пустом месте, раньше проходила все проверки.
    m['conns'][0]['pts'] = [[500, 50], [600, 50], [600, 60]]
    assert any('не касается блока источника' in p for p in layoutProblems(m))
    # Сдвиг поперёк грани уводит концы с граней блоков.
    m2 = buildScheme(createDefaultState())
    m2['conns'][0]['pts'] = [[x, y-25] for x, y in m2['conns'][0]['pts']]
    problems = layoutProblems(m2)
    assert any('не касается блока источника' in p for p in problems)
    assert any('не касается блока цели' in p for p in problems)
    # Сдвиг вдоль грани оставляет концы на гранях — это не ошибка.
    m3 = buildScheme(createDefaultState())
    m3['conns'][0]['pts'] = [[x+25, y] for x, y in m3['conns'][0]['pts']]
    assert not [p for p in layoutProblems(m3) if 'не касается' in p]


def test_validator_detects_almost_coincident_ports():
    def block(id, x, y):
        return dict(id=id, x=x, y=y, w=20, h=20, name='', lines=[])
    m = dict(width=100, height=100, blocks=[block('a', 10, 10), block('b', 60, 10)], rooms=[], signals=[],
             ext=[], notes=None, legend=dict(x=0, y=80, w=100, h=20, items=[]))
    m['conns'] = [dict(src=m['blocks'][0], tgt=m['blocks'][1], sx=20, tx=80, sEdge='top', tEdge='top',
                       pts=[[20, 10], [20, 5], [80, 5], [80, 10]]),
                  dict(src=m['blocks'][0], tgt=m['blocks'][1], sx=20.02, tx=80, sEdge='top', tEdge='top',
                       pts=[[20.02, 10], [20.02, 4], [82, 4], [80, 10]])]
    assert any('Порты блока a (top) почти совпадают' in p for p in layoutProblems(m))


def test_dense_fan_in_warns_but_stays_valid():
    m = buildScheme(dense(200))
    assert any('Шаг портов' in w for w in m['warnings'])
    assert layoutProblems(m) == []
    assert not [p for p in layoutProblems(m) if 'почти совпадают' in p]


def test_gap_converges_to_needed_width_and_is_stable():
    s = big_project()
    m = buildScheme(s)
    # Прежде зазор завышался до 2497 px (лист 24029 px шириной) из-за одного
    # раздутого прохода; сходимость по неподвижной точке даёт ~7370 px.
    assert m['width'] <= 8000, m['width']
    assert layoutProblems(m) == []
    assert buildScheme(s)['width'] == m['width']


def test_dense_layout_time_is_bounded():
    """Охранный порог против возврата квадратичного пересканирования реестра.

    Абсолютное время зависит от машины: Windows CI под coverage работает
    примерно в 5 раз медленнее песочницы (2.6 с на 300 портов против 0.5 с),
    поэтому одного порога мало — проверяется ещё и рост между размерами.
    Прежний перебор всего реестра давал около 40x на четырёхкратном размере,
    текущая реализация — 10–15x. Оба условия вместе ловят возврат регрессии
    и на быстрой, и на медленной машине.
    """
    def best_time(n, runs=2):
        times = []
        for _ in range(runs):
            state = dense(n)
            t0 = time.perf_counter()
            buildScheme(state)
            times.append(time.perf_counter() - t0)
        return min(times)

    t_small, t_large = best_time(75), best_time(300)
    assert t_large < 10, f'раскладка 300 портов заняла {t_large:.1f} с'
    assert t_large / t_small < 20, f'время выросло в {t_large/t_small:.1f} раз: {t_small:.3f} с -> {t_large:.3f} с'


def test_huge_fan_in_fails_with_clear_error():
    """За пределом ширины грани построение останавливается понятной ошибкой.

    559 целей на одну грань 190 px ещё раскладываются (шаг 0.30 px), 560 —
    уже физически невозможны: линии пришлось бы совместить.
    """
    assert layoutProblems(buildScheme(dense(559))) == []
    with pytest.raises(ValueError, match='Недостаточно места для портов блока'):
        buildScheme(dense(560))


def test_loaded_project_has_no_warnings_and_small_sheet():
    m = buildScheme(loadedState())
    assert m['warnings'] == []
    assert layoutProblems(m) == []


def test_output_ports_keep_target_order():
    """Порты выхода идут в порядке положения целей (свойство трассировки backup)."""
    from tests.projects import makeRandom
    states = [loadedState(), createDefaultState(), *(makeRandom(7)() for _ in range(6))]
    for state in states:
        edges = {}
        for c in buildScheme(state)['conns']:
            edges.setdefault((c['src']['id'], c['sEdge']), []).append(
                (c['sx'], c['tgt']['x'] + c['tgt']['w']/2))
        for key, pairs in edges.items():
            order = [tx for _, tx in sorted(pairs)]
            assert order == sorted(order), f'{key}: порядок целей нарушен'


def test_registry_searches_past_512_occupied_slots():
    """Обход длинного зазора обрывался после 512 шагов и давал ложную ошибку."""
    reg = PortRegistry()
    for i in range(600):
        # Все записи конфликтуют по Y с искомым интервалом, но не между собой.
        reg.occupied.append((i * SLOT, 0.0, 1.0, SLOT))
    # Свободное место есть только после последней записи.
    assert reg.seat(0.0, 0.0, 2.0, 0.0) >= 600 * SLOT


def test_many_targets_to_one_net_cabinet_are_laid_out():
    """481 блок на пределе веб-API: 480 целей в один сетевой шкаф.

    Прежний предел поиска свободной координаты (512 шагов) ронял такую
    раскладку с «Недостаточно места для портов блока», хотя физический
    предел грани (559 портов) не достигнут.
    """
    s = normalizeState({})
    s['project']['blocksPerRow'] = 8
    s['netCabs'] = [{**ITEM_DEFAULTS['netCabs'], 'id': 'n0'}]
    s['opItems'] = [{**ITEM_DEFAULTS['opItems'], 'id': f'o{i}', 'target': 'n0'} for i in range(480)]
    m = buildScheme(s)
    assert len(m['blocks']) == 481
    assert any('Шаг портов' in w for w in m['warnings'])
    assert layoutProblems(m) == []


def test_registry_reports_exhausted_search_instead_of_merging_lines():
    """Когда в окне между границами места нет, остаётся понятная ошибка."""
    reg = PortRegistry()
    for i in range(301):
        reg.occupied.append((i * 0.01, 0.0, 10.0, 0.1))
    with pytest.raises(ValueError, match='Недостаточно места для портов блока'):
        reg.seat(0.5, 0.0, 10.0, 0.0, 1.0, 7.0)
