"""Геометрические, цветовые и форматные константы схемы АСУ ТП."""

from __future__ import annotations

from typing import Any

# Размеры блоков и шаги сетки/трассировки (в пикселях)
BW: int = 190          # ширина стандартного блока (px)
GAP_MIN: int = 30      # минимальный межколоночный зазор (px)
SLOT: int = 7          # стандартный шаг между параллельными вертикалями в зазоре (px)
SLOT_M: int = 8        # отступ крайнего слота от границы блока в зазоре (px)
LSTEP: int = 8         # шаг между горизонтальными треками в полосе/коридоре (px)
EXIT_STEP: int = 20    # максимальный шаг между портами на грани блока (px)

# Высоты блоков по типам и отступы листа (в пикселях)
OP_H: int = 86         # высота устройства операторной / KVM-щита (px)
RACK_H: int = 110      # высота серверной стойки (px)
NET_H: int = 128       # высота сетевого шкафа (px)
AUTO_H: int = 88       # высота шкафа автоматики (px)
SIG_H: int = 64        # резерв по высоте под стрелки сигналов DI/DO/AI/AO/RS-485 (px)
MARGIN: int = 18       # внешний отступ листа до рамок помещений (px)
SIG_LEN: int = 44      # длина стрелки сигнала вниз от шкафа автоматики (px)
HEAD: int = 32         # высота шапки помещения над первым рядом блоков (px)
LEGEND_ITEM_W: int = 170  # ширина одной ячейки в блоке условных обозначений (px)

# Размеры шрифта для оценки ширины текста (px)
NAME_SIZE: int = 11
LINE_SIZE: int = 10

# Ниже PORT_WARN_STEP порты одной грани визуально сближаются — выдаём предупреждение,
# но не считаем геометрию ошибочной. Ниже PORT_MIN_STEP — ошибка слияния портов.
PORT_WARN_STEP: float = 2.0
PORT_MIN_STEP: float = 0.05
# Предел читаемости одной грани: (BW - 24) / (559 + 1) ≈ 0.296 px на порт.
# Больше линий на грани 190 px визуально сливаются, поэтому раскладка
# останавливается понятной ошибкой (см. README). Проверка явная: раньше этот
# предел возникал случайно — из-за ограничения поиска свободной координаты.
MAX_PORTS_PER_EDGE: int = 559

# Допуск сравнения ширины зазора при поиске неподвижной точки (производный от SLOT)
GAP_TOL: float = SLOT * 1e-9
MAX_GAP_ITERS: int = 32

# Совместимость с JS API: явный словарь констант (без хрупкой интроспекции globals()).
CONSTS: dict[str, int] = {
    'BW': BW,
    'GAP_MIN': GAP_MIN,
    'SLOT': SLOT,
    'SLOT_M': SLOT_M,
    'LSTEP': LSTEP,
    'EXIT_STEP': EXIT_STEP,
    'OP_H': OP_H,
    'RACK_H': RACK_H,
    'NET_H': NET_H,
    'AUTO_H': AUTO_H,
    'SIG_H': SIG_H,
    'MARGIN': MARGIN,
}

COLORS: dict[str, str] = {
    'Витая пара': '#2563eb',
    'Оптика': '#f97316',
    'KVM': '#6b7280',
    'RS-485': '#16a34a',
    'DI': '#0891b2',
    'DO': '#7c3aed',
    'AI': '#db2777',
    'AO': '#a16207',
}
NAME_BY_COLOR: dict[str, str] = {v: k for k, v in COLORS.items()}
LEVEL_FILL: dict[str, str] = {'op': '#eff6ff', 'srv': '#f0fdf4', 'auto': '#fefce8'}

OP_TYPES: list[str] = ['АРМ', 'Принтер', 'Панель управления']
OP_LINKS: list[str] = ['Витая пара', 'Оптика', 'KVM']
AUTO_UPLINKS: list[str] = ['Витая пара', 'Оптика']
KVM_PANEL_ID: str = 'kvmpanel'

PER_ROW_MAX: int = 12
RASTER_SCALE: int = 2
RASTER_MAX_PIXELS: int = 16_000_000
RASTER_MAX_SIDE: int = 16_384

FORMAT: str = 'structural-scheme'
FORMAT_VERSION: int = 1
STORAGE_KEY: str = 'structural-scheme:project'

PROJECT_DEFAULTS: dict[str, Any] = dict(
    title='Структурная схема комплекса',
    subtitle='АСУ ТП установки',
    fileName='structural_scheme',
    operatorName='Операторная',
    serverName='Серверная',
    autoName='Помещение шкафов автоматики',
    blocksPerRow=4,
    showNotes=True,
    showSignalCounts=False,
    kvmPanel=False,
    kvmPanelName='Щит КВМ-удлинителей',
    notesText='',
)

ITEM_DEFAULTS: dict[str, dict[str, Any]] = {
    'opItems': dict(id='', name='АРМ оператора', type='АРМ', link='Витая пара', target=None, kvmToPanel=False),
    'racks': dict(id='', name='Серверная стойка', servers=2, kvm=False, ntp=False, ups=True, netTarget=None),
    'netCabs': dict(id='', name='Шкаф сетевой', switches=2, fw=0, cross=1, external=False, ups=True),
    'autoCabs': dict(
        id='',
        name='Шкаф ША',
        ctrls=1,
        uplink='Витая пара',
        netTarget=None,
        di=True,
        dO=True,
        ai=True,
        ao=False,
        rs485=False,
        rs485Cab=False,
        rs485Target=None,
        diN=16,
        doN=8,
        aiN=8,
        aoN=0,
    ),
}

MAX_WARNINGS: int = 6
COUNT_FIELDS: dict[str, tuple[str, ...]] = {
    'racks': ('servers',),
    'netCabs': ('switches', 'fw', 'cross'),
    'autoCabs': ('ctrls', 'diN', 'doN', 'aiN', 'aoN'),
}
FIELD_LABELS: dict[str, str] = {
    'servers': 'Серверов',
    'switches': 'Коммутаторов',
    'fw': 'Межсетевых экранов',
    'cross': 'Опт. кроссов',
    'ctrls': 'Контроллеров',
    'diN': 'Количество DI',
    'doN': 'Количество DO',
    'aiN': 'Количество AI',
    'aoN': 'Количество AO',
}
