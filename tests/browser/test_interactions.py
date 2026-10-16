"""Пользовательские сценарии в реальном браузере, без Node-проекта и моков DOM."""
import json
from io import BytesIO
from xml.etree import ElementTree as ET

import pytest
from PIL import Image

pytest.importorskip('playwright.sync_api', reason='Установите extra [browser] для E2E-тестов')
from playwright.sync_api import expect

from python.scheme_core import parseState, normalizeState, serializeState
from tests.projects import loadedState

pytestmark = pytest.mark.browser
KEY = 'structural-scheme:project'


def start(page, live_url):
    page.goto(live_url)
    expect(page.locator('#preview svg')).to_be_visible()
    expect(page.locator('#status')).to_contain_text('Блоков:')
    expect(page.get_by_role('alert')).to_be_hidden()


def tab(page, name):
    page.get_by_role('button', name=name, exact=True).click()


def preview_change(page, action):
    """Ждём реальный ответ API и отрисовку, а не произвольный sleep."""
    with page.expect_response(lambda r: r.url.endswith('/api/preview') and r.request.method == 'POST') as pending:
        action()
    assert pending.value.ok
    expect(page.locator('#status')).to_contain_text('Блоков:')


def upload(page, text, name='проект.json'):
    with page.expect_file_chooser() as chooser:
        page.get_by_role('button', name='Открыть JSON', exact=True).click()
    chooser.value.set_files({'name': name, 'mimeType': 'application/json', 'buffer': text.encode('utf-8')})


def saved_state(page):
    return page.evaluate('(key) => JSON.parse(localStorage.getItem(key))', KEY)


def download(page, button, tmp_path):
    with page.expect_download() as pending:
        page.get_by_role('button', name=button, exact=True).click()
    result = pending.value
    assert result.failure() is None
    path = tmp_path / result.suggested_filename
    result.save_as(path)
    return path


def test_edit_project_preview_zoom_and_reload(page, live_url):
    start(page, live_url)
    title = 'Схема <АСУ> & испытание'
    preview_change(page, lambda: page.get_by_label('Название схемы', exact=True).fill(title))
    expect(page.locator('#preview svg')).to_contain_text(title)
    assert saved_state(page)['project']['title'] == title
    preview_change(page, lambda: page.get_by_label('Блоков в одном ряду').fill('1'))
    assert saved_state(page)['project']['blocksPerRow'] == '1'

    page.locator('#zoom').select_option('2')
    svg = page.locator('#preview svg')
    assert svg.evaluate('(s) => parseFloat(s.style.width) === Number(s.getAttribute("width")) * 2')
    page.locator('#zoom').select_option('fit')
    assert svg.evaluate('(s) => s.getBoundingClientRect().width <= s.parentElement.clientWidth')

    page.reload()
    expect(page.get_by_label('Название схемы', exact=True)).to_have_value(title)
    expect(page.get_by_label('Блоков в одном ряду')).to_have_value('1')
    expect(page.locator('#preview svg')).to_contain_text(title)


def test_all_tabs_add_edit_connect_and_delete(page, live_url):
    start(page, live_url)
    tab(page, 'Операторная')
    preview_change(page, lambda: page.get_by_label('Щит КВМ-удлинителей в операторной').check())
    expect(page.get_by_label('Название щита', exact=True)).to_be_visible()
    preview_change(page, lambda: page.get_by_label('Название щита', exact=True).fill('Щит испытаний'))
    preview_change(page, lambda: page.get_by_role('button', name='+ Добавить устройство', exact=True).click())
    expect(page.locator('.card')).to_have_count(5)
    card = page.locator('.card').last
    preview_change(page, lambda: card.get_by_label('Название', exact=True).fill('АРМ испытаний'))
    preview_change(page, lambda: card.get_by_label('Тип', exact=True).select_option(label='Панель управления'))
    preview_change(page, lambda: card.get_by_label('Куда', exact=True).select_option('kvmpanel'))
    expect(page.locator('#preview svg')).to_contain_text('АРМ испытаний')
    assert saved_state(page)['opItems'][-1]['target'] == 'kvmpanel'
    preview_change(page, lambda: card.get_by_role('button', name='Удалить', exact=True).click())
    expect(page.locator('.card')).to_have_count(4)
    expect(page.locator('#preview svg')).not_to_contain_text('АРМ испытаний')

    tab(page, 'Серверная')
    preview_change(page, lambda: page.get_by_role('button', name='+ Добавить стойку', exact=True).click())
    preview_change(page, lambda: page.get_by_role('button', name='+ Добавить сетевой шкаф', exact=True).click())
    state = saved_state(page)
    assert len(state['racks']) == 2 and len(state['netCabs']) == 2
    new_net = state['netCabs'][-1]['id']
    rack = page.locator('.items').nth(0).locator('.card').last
    preview_change(page, lambda: rack.get_by_label('Подключение к', exact=True).select_option(new_net))
    preview_change(page, lambda: rack.get_by_label('NTP', exact=True).check())
    assert saved_state(page)['racks'][-1]['netTarget'] == new_net

    tab(page, 'Проект')
    preview_change(page, lambda: page.get_by_label('Показывать количества сигналов').check())
    tab(page, 'Шкафы автоматики')
    preview_change(page, lambda: page.get_by_role('button', name='+ Добавить шкаф', exact=True).click())
    auto = page.locator('.card').last
    preview_change(page, lambda: auto.get_by_label('Количество DI', exact=True).fill('123'))
    preview_change(page, lambda: auto.get_by_label('RS-485 между', exact=True).check())
    preview_change(page, lambda: page.locator('.card').last.get_by_label('Связать со шкафом', exact=True).select_option(
        saved_state(page)['autoCabs'][1]['id']))
    expect(page.locator('#preview svg')).to_contain_text('DI (123)')
    assert saved_state(page)['autoCabs'][-1]['rs485Cab'] is True


def test_json_save_open_roundtrip_and_invalid_import(page, live_url, tmp_path):
    start(page, live_url)
    state = loadedState()
    state['project']['title'] = 'Импорт плотного проекта'
    preview_change(page, lambda: upload(page, '\ufeff'+serializeState(state)))
    expect(page.get_by_label('Название схемы', exact=True)).to_have_value(state['project']['title'])
    expect(page.locator('#preview svg')).to_contain_text(state['project']['title'])
    project = download(page, 'Сохранить проект', tmp_path)
    assert project.suffix == '.json'
    assert parseState(project.read_text(encoding='utf-8')) == normalizeState(state)
    before = saved_state(page)
    before_svg = page.locator('#preview').inner_html()

    upload(page, '{сломанный json', 'bad.json')
    expect(page.get_by_role('alert')).to_contain_text('JSON')
    for bad, message in [('{"format":"unrelated"}', 'не является проектом'),
                         ('{"version":999}', 'более новом формате')]:
        with page.expect_response(lambda r: r.url.endswith('/api/normalize')) as pending:
            upload(page, bad, 'bad.json')
        assert pending.value.status == 422
        expect(page.get_by_role('alert')).to_contain_text(message)
        assert saved_state(page) == before
        assert page.locator('#preview').inner_html() == before_svg

    # Тот же файл можно открыть повторно: input очищается после импорта.
    preview_change(page, lambda: page.locator('#file').set_input_files(project))
    expect(page.get_by_role('alert')).to_be_hidden()


@pytest.mark.parametrize('format,button', [('svg','⬇ SVG'), ('png','⬇ PNG'), ('jpg','⬇ JPG'), ('drawio','⬇ Draw.io')])
def test_download_export_contents(page, live_url, tmp_path, format, button):
    start(page, live_url)
    preview_change(page, lambda: page.get_by_label('Название схемы', exact=True).fill('Проверка экспорта'))
    preview_change(page, lambda: page.get_by_label('Имя выходных файлов').fill('browser_export'))
    path = download(page, button, tmp_path)
    assert path.name == f'browser_export.{format}'
    data = path.read_bytes()
    assert len(data) > 100
    if format in ('svg','drawio'):
        root = ET.fromstring(data)
        if format == 'svg':
            assert root.tag.endswith('svg')
            assert 'Проверка экспорта' in ''.join(root.itertext())
        else:
            assert root.tag == 'mxfile'
            assert any(c.get('value') == 'Проверка экспорта' for c in root.iter('mxCell'))
    else:
        with Image.open(BytesIO(data)) as image:
            assert image.format == ('PNG' if format == 'png' else 'JPEG')
            assert image.width * image.height <= 16_000_000
            image.verify()
    expect(page.get_by_role('alert')).to_be_hidden()
    expect(page.get_by_role('button', name=button, exact=True)).to_be_enabled()


def test_reset_cancel_and_confirm(page, live_url):
    start(page, live_url)
    preview_change(page, lambda: page.get_by_label('Название схемы', exact=True).fill('Не удалять'))
    page.once('dialog', lambda d: d.dismiss())
    page.get_by_role('button', name='Начать заново', exact=True).click()
    expect(page.get_by_label('Название схемы', exact=True)).to_have_value('Не удалять')
    assert saved_state(page)['project']['title'] == 'Не удалять'
    page.once('dialog', lambda d: d.accept())
    preview_change(page, lambda: page.get_by_role('button', name='Начать заново', exact=True).click())
    expect(page.get_by_label('Название схемы', exact=True)).to_have_value('Структурная схема комплекса')
    assert saved_state(page)['project']['title'] == 'Структурная схема комплекса'


def test_export_failure_is_visible_and_button_recovers(page, live_url, tmp_path):
    start(page, live_url)
    page.route('**/api/export/png', lambda route: route.fulfill(
        status=422, json={'detail': 'Тест: экспорт временно недоступен'}))
    with page.expect_response(lambda r: r.url.endswith('/api/export/png')):
        page.get_by_role('button', name='⬇ PNG', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('экспорт временно недоступен')
    expect(page.get_by_role('button', name='⬇ PNG', exact=True)).to_be_enabled()
    page.unroute('**/api/export/png')
    assert download(page, '⬇ PNG', tmp_path).stat().st_size > 100
    expect(page.get_by_role('alert')).to_be_hidden()


def test_storage_unavailable_does_not_break_editor(page, live_url, tmp_path):
    page.add_init_script("""Storage.prototype.getItem = function() { throw new Error('Storage blocked'); };
        Storage.prototype.setItem = function() { throw new Error('Storage blocked'); };""")
    page.goto(live_url)
    expect(page.locator('#preview svg')).to_be_visible()
    expect(page.get_by_role('alert')).to_contain_text('Сохранённый проект не открыт')
    preview_change(page, lambda: page.get_by_label('Название схемы', exact=True).fill('Без хранилища'))
    expect(page.get_by_role('alert')).to_contain_text('Не удалось сохранить в браузере')
    project = download(page, 'Сохранить проект', tmp_path)
    assert json.loads(project.read_text(encoding='utf-8'))['project']['title'] == 'Без хранилища'


def test_corrupt_saved_state_falls_back_without_losing_editor(page, live_url):
    page.add_init_script(f"localStorage.setItem('{KEY}', '{{broken');")
    page.goto(live_url)
    expect(page.get_by_role('alert')).to_contain_text('Сохранённый проект не открыт')
    expect(page.locator('#preview svg')).to_be_visible()
    expect(page.get_by_label('Название схемы', exact=True)).to_have_value('Структурная схема комплекса')
    preview_change(page, lambda: page.get_by_label('Название схемы', exact=True).fill('Восстановлено'))
    expect(page.get_by_role('alert')).to_be_hidden()
    assert saved_state(page)['project']['title'] == 'Восстановлено'


def test_preview_error_recovers_on_next_edit(page, live_url):
    start(page, live_url)
    page.route('**/api/preview', lambda route: route.fulfill(status=503, json={'detail': 'Тест: нет превью'}))
    with page.expect_response(lambda r: r.url.endswith('/api/preview')):
        page.get_by_label('Название схемы', exact=True).fill('Сбой превью')
    expect(page.get_by_role('alert')).to_contain_text('нет превью')
    expect(page.locator('#status')).to_have_text('Ошибка построения')
    expect(page.locator('#preview svg')).to_be_visible()
    page.unroute('**/api/preview')
    preview_change(page, lambda: page.get_by_label('Название схемы', exact=True).fill('Превью восстановлено'))
    expect(page.locator('#preview svg')).to_contain_text('Превью восстановлено')
    expect(page.get_by_role('alert')).to_be_hidden()


def test_late_preview_response_does_not_overwrite_new_edit(page, live_url):
    start(page, live_url)
    held = []

    def hold_old_response(route):
        if route.request.post_data_json['project']['title'] == 'Старый ответ':
            held.append((route, route.fetch()))
            # Оставляем запрос незавершённым, пока новое превью не нарисовано.
        else:
            route.continue_()

    page.route('**/api/preview', hold_old_response)
    with page.expect_request(lambda r: r.url.endswith('/api/preview')):
        page.get_by_label('Название схемы', exact=True).fill('Старый ответ')
    preview_change(page, lambda: page.get_by_label('Название схемы', exact=True).fill('Новый ответ'))
    expect(page.locator('#preview svg')).to_contain_text('Новый ответ')
    assert len(held) == 1
    route, response = held[0]
    with page.expect_response(lambda r: r.url.endswith('/api/preview') and
                              r.request.post_data_json['project']['title'] == 'Старый ответ'):
        route.fulfill(response=response)
    # Обрабатываем обещания fetch и следующий animation frame без sleep.
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    expect(page.locator('#preview svg')).to_contain_text('Новый ответ')
    expect(page.locator('#preview svg')).not_to_contain_text('Старый ответ')


def test_narrow_viewport_remains_editable(page, live_url):
    page.set_viewport_size({'width': 390, 'height': 844})
    start(page, live_url)
    preview_change(page, lambda: page.get_by_label('Название схемы', exact=True).fill('Мобильный проект'))
    tab(page, 'Шкафы автоматики')
    preview_change(page, lambda: page.get_by_role('button', name='+ Добавить шкаф', exact=True).click())
    expect(page.locator('.card')).to_have_count(4)
    expect(page.locator('#preview svg')).to_contain_text('Мобильный проект')
    assert page.locator('#preview svg').evaluate('(s) => s.getBoundingClientRect().width <= s.parentElement.clientWidth')
