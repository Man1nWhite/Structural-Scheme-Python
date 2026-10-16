"""python generate.py project.json -o out.svg"""
import argparse
from pathlib import Path
from python.scheme_core import parseState, buildScheme
from python.export import export_model


def main():
    parser = argparse.ArgumentParser(description='Генератор структурных схем АСУ ТП')
    parser.add_argument('project', type=Path, help='Проект JSON (совместим с JS v1)')
    parser.add_argument('-o', '--output', required=True, type=Path, help='Файл .svg/.png/.jpg/.drawio')
    args = parser.parse_args()
    try:
        model = buildScheme(parseState(args.project.read_text(encoding='utf-8-sig')))
        data, _ = export_model(model, args.output.suffix)
        args.output.write_bytes(data)
    except (ValueError, OSError) as e:
        parser.exit(1, f'Ошибка: {e}\n')
    print(f'Сохранено: {args.output} ({model["width"]} × {model["height"]})')


if __name__ == '__main__':
    main()
