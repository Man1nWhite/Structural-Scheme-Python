import argparse
import os
import sys

import uvicorn


def main() -> None:
    p = argparse.ArgumentParser(description='Локальный генератор структурных схем АСУ ТП')
    p.add_argument('--host', default='0.0.0.0')
    p.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8000')))
    args = p.parse_args()
    if args.host == '0.0.0.0':
        print(
            'Внимание: сервер слушает на всех интерфейсах (0.0.0.0). '
            'Для доступа только локально используйте --host 127.0.0.1.',
            file=sys.stderr,
        )
    uvicorn.run('structural_scheme.app:app', host=args.host, port=args.port)


if __name__ == '__main__':  # pragma: no cover
    main()
