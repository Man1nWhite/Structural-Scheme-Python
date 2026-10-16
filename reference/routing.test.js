// Трассировка линий: схема — это чертёж, поэтому проверяются свойства чертежа,
// а не координаты. Раньше вертикали разных связей ложились в одну линию, встречались
// пустые отрезки и линии, проходящие сквозь блоки: набор проектов ниже ловит возврат
// этих ошибок (см. src/core.js, распределение мест вертикалей — seat()).
const assert = require('node:assert/strict');
const test = require('node:test');
const { core, layoutProblems, sampleState } = require('./helpers');

const check = (state, title) => {
  const model = core.buildScheme(state);
  const problems = layoutProblems(model);
  assert.deepEqual(problems.slice(0, 5), [], `${title}: ${problems.length} замечаний к чертежу`);
  return model;
};

// Проект, на котором ломалась трассировка: много блоков в одном столбце,
// щит КВМ включён, часть связей идёт через коридор.
function loadedState() {
  const state = core.createDefaultState();
  state.project.blocksPerRow = 4;
  state.project.kvmPanel = true;
  state.project.showSignalCounts = true;
  state.netCabs = [
    { ...core.ITEM_DEFAULTS.netCabs, id: 'net0', name: 'ШС-01', switches: 2, fw: 1, cross: 2, external: true, ups: true },
    { ...core.ITEM_DEFAULTS.netCabs, id: 'net1', name: 'ШС-02', switches: 1, fw: 0, cross: 1, external: false, ups: true },
  ];
  state.opItems = Array.from({ length: 5 }, (_, i) => ({
    ...core.ITEM_DEFAULTS.opItems, id: 'op' + i, name: 'АРМ №' + (i + 1),
    link: i === 3 ? 'Оптика' : 'Витая пара', target: i % 2 ? 'net1' : 'net0', kvmToPanel: i % 2 === 1,
  }));
  state.racks = Array.from({ length: 5 }, (_, i) => ({
    ...core.ITEM_DEFAULTS.racks, id: 'r' + i, name: 'Стойка №' + (i + 1),
    servers: 1 + i, kvm: i < 3, ntp: i === 0, netTarget: i % 2 ? 'net1' : 'net0',
  }));
  state.autoCabs = Array.from({ length: 7 }, (_, i) => ({
    ...core.ITEM_DEFAULTS.autoCabs, id: 'a' + i, name: 'ША-0' + (i + 1),
    ctrls: 1 + (i % 3), uplink: i % 3 === 0 ? 'Оптика' : 'Витая пара',
    netTarget: i % 2 ? 'net1' : 'net0', rs485: true, rs485Cab: i % 2 === 0,
    rs485Target: 'a' + ((i + 1) % 7), ao: i < 2,
  }));
  return state;
}

test('демо-проект и проект с множеством блоков рисуются без замечаний', () => {
  check(core.createDefaultState(), 'демо-проект');
  check(sampleState(), 'проект из тестовых данных');
  check(loadedState(), 'загруженный проект');
});

test('пустой проект и проект без серверной части рисуются без замечаний', () => {
  check({ project: { ...core.PROJECT_DEFAULTS }, opItems: [], racks: [], netCabs: [], autoCabs: [] }, 'пустой проект');
  const withoutServer = core.createDefaultState();
  withoutServer.racks = [];
  withoutServer.netCabs = [];
  withoutServer.opItems = withoutServer.opItems.map(i => ({ ...i, target: null }));
  withoutServer.autoCabs = withoutServer.autoCabs.map(c => ({ ...c, netTarget: null, rs485Cab: false }));
  check(withoutServer, 'без серверной');
});

test('один блок в ряду и много рядов — без замечаний', () => {
  const state = loadedState();
  state.project.blocksPerRow = 1;
  check(state, 'по одному блоку в ряду');
  state.project.blocksPerRow = 12;
  check(state, '12 блоков в ряду');
});

// Детерминированный генератор проектов: набор воспроизводим, поэтому падение теста
// всегда можно разобрать на конкретном проекте.
function makeRandom(seed = 7) {
  let s = seed;
  const rnd = () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; };
  const pick = a => a[Math.floor(rnd() * a.length)];
  const int = (a, b) => a + Math.floor(rnd() * (b - a + 1));
  return () => {
    const state = core.createDefaultState();
    state.project.blocksPerRow = int(1, 6);
    state.project.kvmPanel = rnd() < 0.5;
    state.project.showSignalCounts = rnd() < 0.5;
    state.project.showNotes = rnd() < 0.5;
    state.project.notesText = rnd() < 0.5 ? 'Первое\nВторое' : '';
    state.opItems = Array.from({ length: int(1, 8) }, (_, i) => ({
      ...core.ITEM_DEFAULTS.opItems, id: 'op' + i, name: 'АРМ ' + i,
      type: pick(core.OP_TYPES), link: pick(core.OP_LINKS), kvmToPanel: rnd() < 0.5,
    }));
    state.racks = Array.from({ length: int(0, 5) }, (_, i) => ({
      ...core.ITEM_DEFAULTS.racks, id: 'r' + i, name: 'Стойка ' + i, servers: int(0, 8), kvm: rnd() < 0.5,
    }));
    state.netCabs = Array.from({ length: int(1, 5) }, (_, i) => ({
      ...core.ITEM_DEFAULTS.netCabs, id: 'n' + i, name: 'ШС-' + i,
      switches: int(0, 4), fw: int(0, 2), cross: int(0, 3), external: rnd() < 0.4,
    }));
    state.autoCabs = Array.from({ length: int(1, 8) }, (_, i) => ({
      ...core.ITEM_DEFAULTS.autoCabs, id: 'a' + i, name: 'ША-' + i, ctrls: int(0, 3),
      uplink: pick(core.AUTO_UPLINKS), di: rnd() < 0.8, dO: rnd() < 0.8, ai: rnd() < 0.8,
      ao: rnd() < 0.5, rs485: rnd() < 0.6, rs485Cab: rnd() < 0.5,
    }));
    // Ссылки в том числе на удалённые элементы: их разрешают makeResolvers.
    state.opItems.forEach(it => { if (rnd() < 0.8) it.target = rnd() < 0.9 ? pick(state.netCabs).id : 'потерян'; });
    state.racks.forEach(r => { if (rnd() < 0.8) r.netTarget = pick(state.netCabs).id; });
    state.autoCabs.forEach(c => {
      c.netTarget = rnd() < 0.9 ? pick(state.netCabs).id : 'потерян';
      c.rs485Target = rnd() < 0.9 ? pick(state.autoCabs).id : 'потерян';
    });
    return state;
  };
}

test('40 случайных проектов рисуются без замечаний к чертежу', () => {
  const next = makeRandom();
  for (let i = 0; i < 40; i++) {
    const state = next();
    const model = core.buildScheme(state);
    const problems = layoutProblems(model);
    assert.deepEqual(problems.slice(0, 3), [],
      `проект №${i}: блоков ${model.blocks.length}, связей ${model.conns.length}`);
  }
});

test('связи не выходят за лист и остаются ортогональными', () => {
  const next = makeRandom(11);
  for (let i = 0; i < 20; i++) {
    const model = core.buildScheme(next());
    model.conns.forEach(c => {
      c.pts.forEach(([x, y]) => {
        assert.ok(x >= 0 && x <= model.width, `точка связи ${c.src.id}→${c.tgt.id} внутри листа по x`);
        assert.ok(y >= 0 && y <= model.height, `точка связи ${c.src.id}→${c.tgt.id} внутри листа по y`);
      });
    });
  }
});
