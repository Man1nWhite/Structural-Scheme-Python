// Общие помощники для тестов.
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');
const core = require(path.join(ROOT, 'src', 'core.js'));

// Разбор XML через jsdom: бросает ошибку, если документ не является корректным XML.
function parseXml(text) {
  const { JSDOM } = require('jsdom');
  const doc = new JSDOM(text, { contentType: 'application/xml' }).window.document;
  const err = doc.getElementsByTagName('parsererror')[0];
  if (err) throw new Error('Некорректный XML: ' + err.textContent);
  return doc;
}

// Небольшой проект со всеми типами блоков и связей.
function sampleState(overrides = {}) {
  const state = {
    project: { ...core.PROJECT_DEFAULTS, kvmPanel: true, showSignalCounts: true, notesText: 'Первое\nВторое' },
    opItems: [
      { id: 'op1', name: 'АРМ 1', type: 'АРМ', link: 'Витая пара', target: 'net1', kvmToPanel: true },
      { id: 'op2', name: 'Принтер', type: 'Принтер', link: 'Оптика', target: 'rack1', kvmToPanel: false },
      { id: 'op3', name: 'АРМ 3', type: 'АРМ', link: 'KVM', target: core.KVM_PANEL_ID, kvmToPanel: false },
    ],
    racks: [{ id: 'rack1', name: 'Стойка 1', servers: 3, kvm: true, ntp: true, ups: true, netTarget: 'net1' }],
    netCabs: [
      { id: 'net1', name: 'ШС-01', switches: 2, fw: 1, cross: 2, external: true, ups: true },
      { id: 'net2', name: 'ШС-02', switches: 1, fw: 0, cross: 0, external: false, ups: false },
    ],
    autoCabs: [
      { ...core.ITEM_DEFAULTS.autoCabs, id: 'a1', name: 'ША-01', netTarget: 'net1', rs485: true, rs485Cab: true, rs485Target: 'a2', aoN: 0, ao: true },
      { ...core.ITEM_DEFAULTS.autoCabs, id: 'a2', name: 'ША-02', netTarget: 'net2', rs485Cab: true, rs485Target: 'a1' },
      { ...core.ITEM_DEFAULTS.autoCabs, id: 'a3', name: 'ША-03', netTarget: 'missing', uplink: 'Оптика' },
    ],
  };
  return { ...state, ...overrides };
}

// ---------- Геометрические инварианты схемы ----------
// Используются тестами трассировки: схема читается как чертёж, и по ней проверяется,
// что линии не сливаются, не проходят сквозь блоки и не выходят за лист.

const span = (a1, a2, b1, b2) => Math.min(Math.max(a1, a2), Math.max(b1, b2))
  - Math.max(Math.min(a1, a2), Math.min(b1, b2));

// Отрезки всех связей модели.
function segmentsOf(model) {
  const out = [];
  model.conns.forEach(c => {
    for (let k = 0; k + 1 < c.pts.length; k++) {
      const [x1, y1] = c.pts[k], [x2, y2] = c.pts[k + 1];
      out.push({ c, k, x1, y1, x2, y2, horizontal: Math.abs(y1 - y2) < 0.01, length: Math.hypot(x2 - x1, y2 - y1) });
    }
  });
  return out;
}

// Прямоугольник и отрезок пересекаются (по внутренней части, без касания граней).
function hitsRect(s, r, pad = 0.5) {
  const x1 = Math.min(s.x1, s.x2), x2 = Math.max(s.x1, s.x2);
  const y1 = Math.min(s.y1, s.y2), y2 = Math.max(s.y1, s.y2);
  return x1 < r.x + r.w - pad && x2 > r.x + pad && y1 < r.y + r.h - pad && y2 > r.y + pad;
}

// Все замечания к чертежу: пустой список — схема нарисована корректно.
function layoutProblems(model) {
  const problems = [];
  const name = c => `${c.src.id}→${c.tgt.id}`;
  const segs = segmentsOf(model);

  segs.forEach(s => {
    if (s.length < 0.01) problems.push(`связь ${name(s.c)}: пустой отрезок`);
    else if (!s.horizontal && Math.abs(s.x1 - s.x2) > 0.01) problems.push(`связь ${name(s.c)}: отрезок не горизонтален и не вертикален`);
  });

  for (let a = 0; a < segs.length; a++) {
    for (let b = a + 1; b < segs.length; b++) {
      const A = segs[a], B = segs[b];
      if (A.c === B.c || A.horizontal !== B.horizontal || A.length < 0.01 || B.length < 0.01) continue;
      const len = A.horizontal
        ? (Math.abs(A.y1 - B.y1) < 0.05 ? span(A.x1, A.x2, B.x1, B.x2) : 0)
        : (Math.abs(A.x1 - B.x1) < 0.05 ? span(A.y1, A.y2, B.y1, B.y2) : 0);
      if (len > 1.5) {
        problems.push(`связи ${name(A.c)} и ${name(B.c)} идут по одной линии (${A.horizontal ? 'y' : 'x'}=${(A.horizontal ? A.y1 : A.x1).toFixed(1)}, ${len.toFixed(1)} px)`);
      }
    }
  }

  model.conns.forEach(c => {
    segs.filter(s => s.c === c).forEach(s => {
      model.blocks.forEach(b => {
        if (b === c.src || b === c.tgt) return;
        if (hitsRect(s, b)) problems.push(`связь ${name(c)} проходит сквозь блок ${b.id}`);
      });
    });
  });

  model.signals.forEach(s => {
    const seg = { x1: s.x, x2: s.x, y1: s.y1, y2: s.y2 };
    model.blocks.forEach(b => {
      if (b === s.block || b.y < s.block.y) return;
      if (hitsRect(seg, b)) problems.push(`стрелка ${s.kind} под блоком ${s.block.id} проходит сквозь блок ${b.id}`);
    });
  });

  model.ext.forEach(e => {
    if (e.x2 > model.width) problems.push(`внешняя связь блока ${e.b.id} выходит за лист`);
    const seg = { x1: e.x1, x2: e.x2, y1: e.y, y2: e.y };
    model.blocks.forEach(b => { if (b !== e.b && hitsRect(seg, b, 0)) problems.push(`внешняя связь проходит сквозь блок ${b.id}`); });
  });

  model.legend.items.forEach(it => {
    if (it.x + 100 > model.legend.x + model.legend.w) problems.push(`элемент легенды «${it.name}» выходит за рамку`);
  });
  if (model.legend.y + model.legend.h > model.height) problems.push('легенда выходит за лист');
  if (model.notes && model.notes.y + 20 + model.notes.lines.length * 16 > model.height) problems.push('примечания выходят за лист');

  return problems;
}

module.exports = {
  ROOT, core, parseXml, sampleState, layoutProblems, segmentsOf,
  read: (p) => fs.readFileSync(path.join(ROOT, p), 'utf8'),
};
