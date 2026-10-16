import subprocess
import sys
from io import BytesIO
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient
from PIL import Image

from structural_scheme.app import app
from structural_scheme.scheme_core import ITEM_DEFAULTS, createDefaultState, serializeState

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


def test_module_main_uses_host_port_and_env(monkeypatch):
    from structural_scheme import __main__ as runner
    calls = {}
    monkeypatch.setattr(runner.uvicorn, 'run',
                        lambda target, host, port: calls.update(target=target, host=host, port=port))
    monkeypatch.setattr(sys, 'argv', ['app', '--host', '127.0.0.1', '--port', '8123'])
    runner.main()
    assert calls == {'target': 'structural_scheme.app:app', 'host': '127.0.0.1', 'port': 8123}
    monkeypatch.setattr(sys, 'argv', ['app'])
    monkeypatch.setenv('PORT', '9001')
    runner.main()
    # По умолчанию слушаем 0.0.0.0 (в том числе для preview в Arena) и берём PORT из окружения.
    assert calls == {'target': 'structural_scheme.app:app', 'host': '0.0.0.0', 'port': 9001}


def test_block_limit_is_enforced_by_api():
    s = createDefaultState()
    s['opItems'] = [{**ITEM_DEFAULTS['opItems'], 'id': f'o{i}'} for i in range(501)]
    r = client.post('/api/preview', json=s)
    assert r.status_code == 422
    assert '500 блоков' in r.json()['detail']
    s['opItems'], s['netCabs'], s['autoCabs'] = [], [], []
    s['racks'] = [{**ITEM_DEFAULTS['racks'], 'id': f'r{i}', 'servers': 1} for i in range(500)]
    # Ровно 500 блоков — предел веб-API; лимит защищает локальный процесс.
    assert client.post('/api/preview', json=s).status_code == 200


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


def test_all_exports():
    s = createDefaultState()
    for f in ['svg','drawio','png','jpg']:
        r = client.post('/api/export/'+f,json=s)
        assert r.status_code == 200
        assert "filename*=UTF-8''" in r.headers['content-disposition']
        if f in ['svg','drawio']:
            ET.fromstring(r.content)
        else:
            with Image.open(BytesIO(r.content)) as im:
                assert im.format == ('PNG' if f == 'png' else 'JPEG')
                assert im.width*im.height <= 16_000_000
                assert im.getbbox()


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
    loud = createDefaultState()
    loud['racks'][0]['servers'] = 'много'
    project.write_text(serializeState(loud), encoding='utf-8')
    r = subprocess.run([sys.executable,'generate.py',str(project),'-o',str(tmp_path/'warn.svg')],capture_output=True)
    assert r.returncode == 0
    assert 'Предупреждение' in r.stderr.decode('utf-8')
