"""Локальный HTTP API. Никаких внешних сервисов и CDN."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from structural_scheme.export import export_model
from structural_scheme.scheme_core import (
    AUTO_UPLINKS,
    ITEM_DEFAULTS,
    KVM_PANEL_ID,
    OP_LINKS,
    OP_TYPES,
    PROJECT_DEFAULTS,
    buildScheme,
    createDefaultState,
    normalizeState,
    to_svg,
)

app = FastAPI(title='Структурные схемы АСУ ТП', docs_url=None, redoc_url=None, openapi_url=None)
STATIC = Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')


@app.get('/')
def index() -> FileResponse:
    return FileResponse(STATIC / 'index.html')


@app.get('/api/defaults')
def defaults() -> dict[str, Any]:
    return dict(
        state=createDefaultState(),
        items=ITEM_DEFAULTS,
        project=PROJECT_DEFAULTS,
        options=dict(type=OP_TYPES, link=OP_LINKS, uplink=AUTO_UPLINKS, kvmPanelId=KVM_PANEL_ID),
    )


def checked(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        state = normalizeState(raw)
        if sum(len(state[k]) for k in ITEM_DEFAULTS) > 500:
            raise ValueError('Допускается не более 500 блоков в одном проекте.')
        return state
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post('/api/normalize')
def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    return checked(raw)


@app.post('/api/preview')
def preview(raw: dict[str, Any]) -> dict[str, Any]:
    state = checked(raw)
    try:
        model = buildScheme(state)
    except ValueError as e:
        # Как и экспорт: причина видна пользователю, а не 500 Internal Server Error.
        raise HTTPException(422, str(e)) from e
    return dict(
        svg=to_svg(model),
        width=model['width'],
        height=model['height'],
        blocks=len(model['blocks']),
        conns=len(model['conns']),
        warnings=model['warnings'],
    )


@app.post('/api/export/{format}')
def export(format: str, raw: dict[str, Any]) -> Response:
    state = checked(raw)
    try:
        model = buildScheme(state)
        data, mime = export_model(model, format)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    ext = format.lower().lstrip('.')
    full_name = f"{model['fileName']}.{ext}"
    ascii_fallback = re.sub(r'[^A-Za-z0-9_.-]+', '_', full_name).strip('_') or f'scheme.{ext}'
    encoded = quote(full_name)
    disposition = f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'
    return Response(data, media_type=mime, headers={'Content-Disposition': disposition})
