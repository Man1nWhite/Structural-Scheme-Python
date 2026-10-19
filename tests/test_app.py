import json
import subprocess
import sys
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from structural_scheme.app import app
from structural_scheme.scheme_core import (
    ITEM_DEFAULTS,
    createDefaultState,
    createPresetState,
    listPresets,
    serializeState,
)

client = TestClient(app)


def test_offline_assets_and_api():
    html = client.get('/')
    assert html.status_code == 200
    assert 'cdn' not in html.text and 'https://' not in html.text
    for path in ['/static/app.js','/static/style.css']:
        assert client.get(path).status_code == 200
    defaults = client.get('/api/defaults').json()
    s = defaults['state']
    normalized = client.post('/api/normalize',json=s)
    assert normalized.status_code == 200
    preview = client.post('/api/preview',json=s)
    assert preview.status_code == 200
    assert ET.fromstring(preview.json()['svg']).tag.endswith('svg')
    assert client.post('/api/normalize',json={'format':'bad'}).status_code == 422
    assert client.post('/api/export/bad',json=s).status_code == 422
    assert client.post('/api/normalize',content='broken',headers={'content-type':'application/json'}).status_code == 422


def test_module_main_uses_host_port_and_env(monkeypatch, capsys):
    from structural_scheme import __main__ as runner
    calls = {}
    monkeypatch.setattr(runner.uvicorn, 'run',
                        lambda target, host, port: calls.update(target=target, host=host, port=port))
    monkeypatch.setattr(sys, 'argv', ['app', '--host', '127.0.0.1', '--port', '8123'])
    runner.main()
    assert calls == {'target': 'structural_scheme.app:app', 'host': '127.0.0.1', 'port': 8123}
    assert 'Внимание' not in capsys.readouterr().err
    monkeypatch.setattr(sys, 'argv', ['app'])
    monkeypatch.setenv('PORT', '9001')
    runner.main()
    # По умолчанию слушаем 0.0.0.0 (в том числе для preview в Arena) и берём PORT из окружения.
    assert calls == {'target': 'structural_scheme.app:app', 'host': '0.0.0.0', 'port': 9001}
    assert '0.0.0.0' in capsys.readouterr().err


def test_export_filename_fallback_for_cyrillic_name():
    s = createDefaultState()
    s['project']['fileName'] = 'схема'
    r = client.post('/api/export/svg', json=s)
    assert r.status_code == 200
    # ASCII-fallback не должен схлопываться в пустое имя '.svg'.
    assert 'filename="scheme.svg"' in r.headers['content-disposition']
    assert "filename*=UTF-8''%D1%81%D1%85%D0%B5%D0%BC%D0%B0.svg" in r.headers['content-disposition']
    s['project']['fileName'] = 'проект А'
    r = client.post('/api/export/svg', json=s)
    assert 'filename="scheme.svg"' in r.headers['content-disposition']


def test_block_limit_counts_only_dict_items():
    # Не-словари нормализация отбрасывает, а не считает блоками: пред-подсчёт
    # лимита обязан сохранять эту семантику.
    payload = {'opItems': ['мусор'] * 501, 'racks': [], 'netCabs': [], 'autoCabs': []}
    assert client.post('/api/preview', json=payload).status_code == 200


def test_checked_rechecks_limit_after_normalize(monkeypatch):
    # Пост-проверка в checked — защита на случай, если нормализация когда-нибудь
    # начнёт добавлять элементы: лимит обязан сработать и после неё.
    from structural_scheme import app as app_module

    big = {'project': {}, 'opItems': [{}] * 501, 'racks': [], 'netCabs': [], 'autoCabs': []}
    monkeypatch.setattr(app_module, 'normalizeState', lambda raw: big)
    with pytest.raises(HTTPException) as exc:
        app_module.checked({})
    assert exc.value.status_code == 422
    assert '500 блоков' in str(exc.value.detail)


def test_block_limit_is_enforced_by_api():
    from concurrent.futures import ThreadPoolExecutor

    s = createDefaultState()
    s['opItems'] = [{**ITEM_DEFAULTS['opItems'], 'id': f'o{i}'} for i in range(501)]
    r = client.post('/api/preview', json=s)
    assert r.status_code == 422
    assert '500 блоков' in r.json()['detail']
    s['opItems'], s['netCabs'], s['autoCabs'] = [], [], []
    s['racks'] = [{**ITEM_DEFAULTS['racks'], 'id': f'r{i}', 'servers': 1} for i in range(500)]
    # Ровно 500 блоков — предел веб-API; лимит защищает локальный процесс.
    assert client.post('/api/preview', json=s).status_code == 200
    # 4 одновременных превью не конфликтуют по состоянию.
    default_state = createDefaultState()
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post('/api/preview', json=default_state), range(4)))
    assert all(res.status_code == 200 and res.json()['blocks'] == 9 for res in responses)


def test_preview_reports_warnings_and_layout_errors(monkeypatch):
    s = createDefaultState()
    s['project']['blocksPerRow'] = 1
    s['racks'][0]['servers'] = 'много'
    s['opItems'][0]['name'] = 'АРМ оператора центрального пульта управления установки №12'
    r = client.post('/api/preview', json=s)
    assert r.status_code == 200
    warnings = r.json()['warnings']
    assert any('«Серверов»' in w for w in warnings)
    assert any('Сокращено подписей' in w for w in warnings)
    assert client.get('/openapi.json').status_code == 404

    def broken(state):
        raise ValueError('Тест: невозможно уложить связи')
    monkeypatch.setattr('structural_scheme.app.buildScheme', broken)
    r = client.post('/api/preview', json=createDefaultState())
    assert r.status_code == 422
    assert 'невозможно уложить связи' in r.json()['detail']


def test_all_exports(monkeypatch):
    s = createDefaultState()
    for f in ['svg','drawio','png','jpg']:
        r = client.post('/api/export/'+f,json=s)
        assert r.status_code == 200
        assert "filename*=UTF-8''" in r.headers['content-disposition']
        assert 'filename="' in r.headers['content-disposition']
        if f in ['svg','drawio']:
            ET.fromstring(r.content)
        else:
            with Image.open(BytesIO(r.content)) as im:
                assert im.format == ('PNG' if f == 'png' else 'JPEG')
                assert im.width*im.height <= 16_000_000
                assert im.getbbox()
    monkeypatch.setattr('structural_scheme.export.resvg_py.svg_to_bytes', lambda **kw: b'')
    assert client.post('/api/export/png', json=s).status_code == 422
    def fail_resvg(**kw):
        raise RuntimeError('resvg error')
    monkeypatch.setattr('structural_scheme.export.resvg_py.svg_to_bytes', fail_resvg)
    assert client.post('/api/export/png', json=s).status_code == 422


def test_presets_endpoint_and_states():
    r = client.get('/api/presets')
    assert r.status_code == 200
    presets = r.json()['presets']
    assert [p['id'] for p in presets] == ['demo', 'typical', 'minimal', 'empty']
    for p in presets:
        assert p['title'] and p['hint']
        assert client.post('/api/preview', json=p['state']).status_code == 200
    empty, typical = presets[3], presets[1]
    assert empty['state']['opItems'] == empty['state']['autoCabs'] == []
    assert empty['state']['project']['title'] == 'Новый проект'
    assert len(typical['state']['opItems']) == 5 and len(typical['state']['autoCabs']) == 3
    assert typical['state']['project']['kvmPanel'] is True
    assert typical['state']['project']['showSignalCounts'] is True
    # Цепочка RS-485 между шкафами типовой схемы связана и не ссылается на себя.
    autos = {c['id']: c for c in typical['state']['autoCabs']}
    for cab in autos.values():
        assert cab['rs485Target'] != cab['id']
    assert autos[typical['state']['autoCabs'][1]['id']]['rs485Target'] == typical['state']['autoCabs'][0]['id']
    demo, base = createPresetState('demo'), createDefaultState()
    assert demo['project'] == base['project']
    assert [len(demo[k]) for k in ITEM_DEFAULTS] == [len(base[k]) for k in ITEM_DEFAULTS]


def test_unknown_preset_kind_is_rejected():
    with pytest.raises(ValueError, match='Неизвестный шаблон'):
        createPresetState('nope')
    assert {p['id'] for p in listPresets()} == {'demo', 'typical', 'minimal', 'empty'}


def test_export_zip_bundle_contains_every_format():
    s = createDefaultState()
    s['project']['fileName'] = 'bundle'
    for route in ['all', 'zip']:
        r = client.post('/api/export/' + route, json=s)
        assert r.status_code == 200
        assert r.headers['content-type'] == 'application/zip'
        assert 'filename="bundle.zip"' in r.headers['content-disposition']
        with zipfile.ZipFile(BytesIO(r.content)) as archive:
            assert sorted(archive.namelist()) == [
                'bundle.drawio', 'bundle.jpg', 'bundle.json', 'bundle.png', 'bundle.svg',
            ]
            assert ET.fromstring(archive.read('bundle.svg')).tag.endswith('svg')
            assert ET.fromstring(archive.read('bundle.drawio')).tag == 'mxfile'
            assert json.loads(archive.read('bundle.json'))['project']['title'] == s['project']['title']
            with Image.open(BytesIO(archive.read('bundle.png'))) as image:
                assert image.format == 'PNG'
                image.verify()
            with Image.open(BytesIO(archive.read('bundle.jpg'))) as image:
                assert image.format == 'JPEG'
                image.verify()


def test_export_zip_sanitizes_member_names():
    s = createDefaultState()
    s['project']['fileName'] = '../в/название файла'
    r = client.post('/api/export/zip', json=s)
    assert r.status_code == 200
    with zipfile.ZipFile(BytesIO(r.content)) as archive:
        assert archive.namelist()
        assert all('/' not in n and '\\' not in n and not n.startswith('.') for n in archive.namelist())


def test_cli_zip_bundle(tmp_path):
    project = tmp_path / 'проект.json'
    project.write_text(serializeState(createDefaultState()), encoding='utf-8-sig')
    out = tmp_path / 'out.zip'
    r = subprocess.run([sys.executable, 'generate.py', str(project), '-o', str(out)], capture_output=True)
    assert r.returncode == 0, r.stderr
    with zipfile.ZipFile(out) as archive:
        assert {n.rsplit('.', 1)[-1] for n in archive.namelist()} == {'svg', 'png', 'jpg', 'drawio', 'json'}


def test_cli(tmp_path):
    project = tmp_path/'проект.json'
    project.write_text(serializeState(createDefaultState()),encoding='utf-8-sig')
    for ext in ['svg','drawio','png','jpg']:
        out = tmp_path/('out.'+ext)
        r = subprocess.run([sys.executable,'generate.py',str(project),'-o',str(out)],capture_output=True)
        assert r.returncode == 0, r.stderr
        assert out.stat().st_size > 100
    bad = subprocess.run([sys.executable,'generate.py',str(project),'-o',str(tmp_path/'out.bad')],capture_output=True)
    assert bad.returncode == 1
    missing = subprocess.run([sys.executable,'generate.py',str(tmp_path/'missing.json'),'-o',str(tmp_path/'out.svg')],capture_output=True)
    assert missing.returncode == 1
    loud = createDefaultState()
    loud['racks'][0]['servers'] = 'много'
    project.write_text(serializeState(loud), encoding='utf-8')
    r = subprocess.run([sys.executable,'generate.py',str(project),'-o',str(tmp_path/'warn.svg')],capture_output=True)
    assert r.returncode == 0
    assert 'Предупреждение' in r.stderr.decode('utf-8')


def test_hostile_json_values_do_not_return_500():
    """Огромные int и одиночные суррогаты — валидный JSON, но не валидный проект."""
    bodies = [
        '{"racks":[{"id":"r0","servers":%s}]}' % ('9' * 400),
        '{"format":"structural-scheme","version":1,"project":{"title":"A\\ud800B","blocksPerRow":%s}}' % ('9' * 400),
        '{"format":"structural-scheme","version":1,"project":{"title":"A\\u0000B"},"racks":[{"id":"r","name":"N\\u0001"}]}',
    ]
    for body in bodies:
        r = client.post('/api/preview', content=body, headers={'content-type': 'application/json'})
        assert r.status_code == 200, body[:80]
        ET.fromstring(r.json()['svg'])
        r = client.post('/api/export/svg', content=body, headers={'content-type': 'application/json'})
        assert r.status_code == 200
        ET.fromstring(r.content)
