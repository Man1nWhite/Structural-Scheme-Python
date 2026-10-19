"""python generate.py project.json -o out.svg"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from structural_scheme.export import export_bundle, export_model
from structural_scheme.scheme_core import buildScheme, parseState


def main() -> None:
    parser = argparse.ArgumentParser(description='Генератор структурных схем АСУ ТП')
    parser.add_argument('project', type=Path, help='Проект JSON (совместим с JS v1)')
    parser.add_argument('-o', '--output', required=True, type=Path, help='Файл .svg/.png/.jpg/.drawio/.zip')
    args = parser.parse_args()
    try:
        state = parseState(args.project.read_text(encoding='utf-8-sig'))
        model = buildScheme(state)
        if args.output.suffix.lower() == '.zip':
            data, _ = export_bundle(state, model)
        else:
            data, _ = export_model(model, args.output.suffix)
        args.output.write_bytes(data)
    except (ValueError, OSError) as e:
        parser.exit(1, f'Ошибка: {e}\n')
    for warning in model['warnings']:
        print(f'Предупреждение: {warning}', file=sys.stderr)
    print(f'Сохранено: {args.output} ({model["width"]} × {model["height"]})')


if __name__ == '__main__':  # pragma: no cover
    main()
