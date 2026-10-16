"""Совместимость: историческая команда `python -m app` из репозитория.

Канонический запуск — `python -m structural_scheme`. Этот файл существует
только для привычной команды и в устанавливаемый пакет не входит.
"""
from structural_scheme.__main__ import main
from structural_scheme.app import app as app  # noqa: F401  # для uvicorn app:app

if __name__ == '__main__':
    main()
