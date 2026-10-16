from io import BytesIO
import subprocess
import sys
from xml.etree import ElementTree as ET
from PIL import Image
from fastapi.testclient import TestClient
from app import app
from python.scheme_core import createDefaultState, serializeState

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
