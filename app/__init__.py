"""Локальный HTTP API. Никаких внешних сервисов и CDN."""
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from python.scheme_core import (createDefaultState, normalizeState, buildScheme, to_svg,
                                 ITEM_DEFAULTS, PROJECT_DEFAULTS, makeResolvers)
from python.export import export_model

app = FastAPI(title='Структурные схемы АСУ ТП', docs_url=None, redoc_url=None)
STATIC = Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')


@app.get('/')
def index():
    return FileResponse(STATIC / 'index.html')


@app.get('/api/defaults')
def defaults():
    return dict(state=createDefaultState(), items=ITEM_DEFAULTS, project=PROJECT_DEFAULTS)


def checked(raw):
    try:
        state = normalizeState(raw)
        if sum(len(state[k]) for k in ITEM_DEFAULTS) > 500:
            raise ValueError('Допускается не более 500 блоков в одном проекте.')
        return state
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post('/api/normalize')
def normalize(raw: dict):
    return checked(raw)


@app.post('/api/preview')
def preview(raw: dict):
    state = checked(raw)
    model = buildScheme(state)
    return dict(svg=to_svg(model), width=model['width'], height=model['height'],
                blocks=len(model['blocks']), conns=len(model['conns']))


@app.post('/api/export/{format}')
def export(format: str, raw: dict):
    state = checked(raw)
    try:
        model = buildScheme(state)
        data, mime = export_model(model, format)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    name = quote(model['fileName']+'.'+format)
    return Response(data, media_type=mime, headers={'Content-Disposition': f"attachment; filename*=UTF-8''{name}"})
