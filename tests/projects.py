"""Перенос reference/routing.test.js; LCG учитывает JS double, не Python int."""
from python.scheme_core import *


def loadedState():
    s = createDefaultState()
    s['project'].update(blocksPerRow=4, kvmPanel=True, showSignalCounts=True)
    s['netCabs'] = [{**ITEM_DEFAULTS['netCabs'], 'id': f'net{i}', 'name': f'ШС-0{i+1}',
                     'switches': 2 if i == 0 else 1, 'fw': 1 if i == 0 else 0,
                     'cross': 2 if i == 0 else 1, 'external': i == 0} for i in range(2)]
    s['opItems'] = [{**ITEM_DEFAULTS['opItems'], 'id': f'op{i}', 'name': f'АРМ №{i+1}',
                     'link': 'Оптика' if i == 3 else 'Витая пара', 'target': f'net{i%2}',
                     'kvmToPanel': i%2 == 1} for i in range(5)]
    s['racks'] = [{**ITEM_DEFAULTS['racks'], 'id': f'r{i}', 'name': f'Стойка №{i+1}',
                  'servers': 1+i, 'kvm': i < 3, 'ntp': i == 0, 'netTarget': f'net{i%2}'} for i in range(5)]
    s['autoCabs'] = [{**ITEM_DEFAULTS['autoCabs'], 'id': f'a{i}', 'name': f'ША-0{i+1}',
                     'ctrls': 1+i%3, 'uplink': 'Оптика' if i%3 == 0 else 'Витая пара',
                     'netTarget': f'net{i%2}', 'rs485': True, 'rs485Cab': i%2 == 0,
                     'rs485Target': f'a{(i+1)%7}', 'ao': i < 2} for i in range(7)]
    return s


def sampleState():
    s = normalizeState({
        'project': {**PROJECT_DEFAULTS, 'kvmPanel': True, 'showSignalCounts': True, 'notesText': 'Первое\nВторое'},
        'opItems': [dict(id='op1', name='АРМ 1', target='net1', kvmToPanel=True),
                    dict(id='op2', name='Принтер', type='Принтер', link='Оптика', target='rack1'),
                    dict(id='op3', name='АРМ 3', link='KVM', target=KVM_PANEL_ID)],
        'racks': [dict(id='rack1', name='Стойка 1', servers=3, kvm=True, ntp=True, ups=True, netTarget='net1')],
        'netCabs': [dict(id='net1', name='ШС-01', switches=2, fw=1, cross=2, external=True, ups=True),
                    dict(id='net2', name='ШС-02', switches=1, fw=0, cross=0, external=False, ups=False)],
        'autoCabs': [dict(id='a1', name='ША-01', netTarget='net1', rs485=True, rs485Cab=True, rs485Target='a2', aoN=0, ao=True),
                     dict(id='a2', name='ША-02', netTarget='net2', rs485Cab=True, rs485Target='a1'),
                     dict(id='a3', name='ША-03', netTarget='missing', uplink='Оптика')]})
    return s


def makeRandom(seed=7):
    def rnd():
        nonlocal seed
        seed = int(float(seed)*1103515245 + 12345) & 0x7fffffff
        return seed/0x7fffffff
    def pick(a):
        return a[int(rnd()*len(a))]
    def integer(a, b):
        return a+int(rnd()*(b-a+1))
    def next_state():
        s = createDefaultState()
        s['project'].update(blocksPerRow=integer(1,6), kvmPanel=rnd()<.5,
                            showSignalCounts=rnd()<.5, showNotes=rnd()<.5,
                            notesText='Первое\nВторое' if rnd()<.5 else '')
        s['opItems'] = [{**ITEM_DEFAULTS['opItems'], 'id': f'op{i}', 'name': f'АРМ {i}',
                         'type': pick(OP_TYPES), 'link': pick(OP_LINKS), 'kvmToPanel': rnd()<.5}
                        for i in range(integer(1,8))]
        s['racks'] = [{**ITEM_DEFAULTS['racks'], 'id': f'r{i}', 'name': f'Стойка {i}',
                      'servers': integer(0,8), 'kvm': rnd()<.5} for i in range(integer(0,5))]
        s['netCabs'] = [{**ITEM_DEFAULTS['netCabs'], 'id': f'n{i}', 'name': f'ШС-{i}',
                        'switches': integer(0,4), 'fw': integer(0,2), 'cross': integer(0,3), 'external': rnd()<.4}
                       for i in range(integer(1,5))]
        s['autoCabs'] = [{**ITEM_DEFAULTS['autoCabs'], 'id': f'a{i}', 'name': f'ША-{i}',
                         'ctrls': integer(0,3), 'uplink': pick(AUTO_UPLINKS), 'di': rnd()<.8,
                         'dO': rnd()<.8, 'ai': rnd()<.8, 'ao': rnd()<.5, 'rs485': rnd()<.6, 'rs485Cab': rnd()<.5}
                        for i in range(integer(1,8))]
        for it in s['opItems']:
            if rnd()<.8:
                it['target'] = pick(s['netCabs'])['id'] if rnd()<.9 else 'потерян'
        for r in s['racks']:
            if rnd()<.8:
                r['netTarget'] = pick(s['netCabs'])['id']
        for c in s['autoCabs']:
            c['netTarget'] = pick(s['netCabs'])['id'] if rnd()<.9 else 'потерян'
            c['rs485Target'] = pick(s['autoCabs'])['id'] if rnd()<.9 else 'потерян'
        return s
    return next_state
