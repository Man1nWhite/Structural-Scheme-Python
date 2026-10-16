import argparse
import os
import uvicorn


def main():
    p = argparse.ArgumentParser(description='Локальный генератор структурных схем АСУ ТП')
    p.add_argument('--host', default='0.0.0.0')
    p.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8000')))
    args = p.parse_args()
    uvicorn.run('app:app', host=args.host, port=args.port)


if __name__ == '__main__':
    main()
