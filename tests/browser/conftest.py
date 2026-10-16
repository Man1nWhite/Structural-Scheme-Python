"""Настоящий HTTP-сервер и изолированный Chromium-контекст на каждый тест."""
import os
import re
from pathlib import Path
import socket
import threading
from urllib.parse import urlsplit

import pytest
import uvicorn


@pytest.fixture(scope='session')
def live_url():
    ready = threading.Event()

    class TestServer(uvicorn.Server):
        async def startup(self, sockets=None):
            try:
                await super().startup(sockets=sockets)
            finally:
                ready.set()

    # Заранее связанный сокет исключает гонку поиска свободного порта.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        server = TestServer(uvicorn.Config('app:app', log_level='warning'))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
        thread.start()
        try:
            assert ready.wait(20), 'Локальный сервер не запустился за 20 секунд'
            assert server.started, 'Ошибка запуска локального сервера'
            yield f'http://127.0.0.1:{sock.getsockname()[1]}'
        finally:
            server.should_exit = True
            thread.join(timeout=20)
            assert not thread.is_alive(), 'Локальный сервер не завершился'


@pytest.fixture(scope='session')
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        options = {'headless': True}
        # Для окружений с уже установленным Chromium. Обычный путь —
        # python -m playwright install chromium; отсутствие браузера — ошибка,
        # а не молчаливый пропуск E2E-проверок в CI.
        executable = os.environ.get('SCHEME_BROWSER_EXECUTABLE')
        if executable:
            options['executable_path'] = executable
        instance = playwright.chromium.launch(**options)
        yield instance
        instance.close()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, 'rep_' + report.when, report)


@pytest.fixture
def page(browser, live_url, request):
    context = browser.new_context(accept_downloads=True, viewport={'width': 1440, 'height': 1000})
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    errors, external = [], []
    origin = urlsplit(live_url).netloc

    def local_only(route):
        url = urlsplit(route.request.url)
        if url.scheme in ('http', 'https') and url.netloc != origin:
            external.append(route.request.url)
            route.abort()
        else:
            route.continue_()

    context.route('**/*', local_only)
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        yield page
    finally:
        report = getattr(request.node, 'rep_call', None)
        failed = (report is not None and report.failed) or errors or external
        if failed:
            folder = Path('test-results') / re.sub(r'[^\w-]', '_', request.node.name)
            folder.mkdir(parents=True, exist_ok=True)
            if not page.is_closed():
                page.screenshot(path=str(folder / 'failure.png'), full_page=True)
                (folder / 'page.html').write_text(page.content(), encoding='utf-8')
            context.tracing.stop(path=str(folder / 'trace.zip'))
        else:
            context.tracing.stop()
        context.close()
        assert not errors, f'Необработанные ошибки JavaScript: {errors}'
        assert not external, f'Приложение обращается к внешней сети: {external}'
