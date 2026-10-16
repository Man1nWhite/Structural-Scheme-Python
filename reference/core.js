/*
 * Ядро генератора структурных схем: модель проекта, раскладка, трассировка,
 * рендер в SVG и Draw.io, сохранение/загрузка проекта.
 *
 * Чистый JavaScript без зависимостей и без DOM. Подключается в браузере
 * обычным <script> (глобальный объект window.SchemeCore) и через require()
 * в Node.js-тестах.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SchemeCore = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const COLORS = {
    'Витая пара': '#2563eb',
    'Оптика': '#f97316',
    'KVM': '#6b7280',
    'RS-485': '#16a34a',
    'DI': '#0891b2',
    'DO': '#7c3aed',
    'AI': '#db2777',
    'AO': '#a16207',
  };
  const NAME_BY_COLOR = {};
  Object.keys(COLORS).forEach(k => { NAME_BY_COLOR[COLORS[k]] = k; });

  const OP_TYPES = ['АРМ', 'Принтер', 'Панель управления'];
  const OP_LINKS = ['Витая пара', 'Оптика', 'KVM'];
  const AUTO_UPLINKS = ['Витая пара', 'Оптика'];
  const KVM_PANEL_ID = 'kvmpanel';

  // ---------- Утилиты ----------
  const uid = () => Math.random().toString(36).slice(2, 9);
  const chunk = (a, n) => { const r = []; for (let i = 0; i < a.length; i += n) r.push(a.slice(i, i + n)); return r; };
  const groupBy = (arr, keyFn) => {
    const m = new Map();
    arr.forEach(x => { const k = keyFn(x); if (!m.has(k)) m.set(k, []); m.get(k).push(x); });
    return [...m.values()];
  };
  const fit = (s, n) => { s = String(s == null ? '' : s); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
  const pad2 = n => String(n).padStart(2, '0');
  const signalLabel = (signal, showCounts) =>
    showCounts && signal.n != null && signal.n !== '' ? `${signal.k} (${signal.n})` : signal.k;
  // Блоков в ряду: значение из поля ввода может быть строкой, пустым или мусором.
  // Верхний предел нужен, чтобы лист не растянулся на десятки тысяч пикселей
  // (экспорт в PNG ограничен размерами canvas).
  const PER_ROW_MAX = 12;
  const clampPerRow = (value) => {
    const n = Math.floor(Number(value));
    return Number.isFinite(n) ? Math.min(PER_ROW_MAX, Math.max(1, n)) : 1;
  };
  const signalsOf = (c) => {
    const s = [];
    if (c.di) s.push({ k: 'DI', n: c.diN });
    if (c.dO) s.push({ k: 'DO', n: c.doN });
    if (c.ai) s.push({ k: 'AI', n: c.aiN });
    if (c.ao) s.push({ k: 'AO', n: c.aoN });
    if (c.rs485) s.push({ k: 'RS-485' });
    return s;
  };
  const fileNameOf = (project) => (project.fileName || 'scheme').replace(/[^\wа-яА-ЯёЁ-]+/g, '_');

  // ---------- Экспорт растровой картинки ----------
  // Браузеры отказываются растрировать слишком большой лист: canvas ограничен по
  // площади, и вместо картинки приходит пустой результат. Считаем масштаб заранее.
  const RASTER_SCALE = 2;          // обычный масштаб вывода — для чёткости линий
  const RASTER_MAX_PIXELS = 16e6;  // предел площади canvas (учитывает лимиты браузеров)
  const rasterScale = (width, height) => {
    const fit = Math.sqrt(RASTER_MAX_PIXELS / Math.max(1, width * height));
    return Math.max(0.1, Math.min(RASTER_SCALE, fit));
  };

  // ---------- Геометрия ----------
  const BW = 190;        // ширина блока
  const GAP_MIN = 30;    // минимальный зазор между колонками
  const SLOT = 7;        // шаг вертикалей, идущих по межколоночному зазору
  const SLOT_M = 8;      // отступ первой такой вертикали от блока
  const LSTEP = 8;       // шаг горизонтальных каналов в полосе
  const EXIT_STEP = 20;  // разнос точек выхода на одной грани блока
  const OP_H = 86, RACK_H = 110, NET_H = 128, AUTO_H = 88;
  const SIG_H = 64;      // зона стрелок сигналов под шкафами автоматики
  const SIG_LEN = 44;    // длина стрелки сигнала
  const HEAD = 32;       // заголовок уровня (помещения)
  const MARGIN = 18;     // поле листа
  const LEVEL_FILL = { op: '#eff6ff', srv: '#f0fdf4', auto: '#fefce8' };
  const LEGEND_ITEM_W = 170;

  // ============================================================
  // МОДЕЛЬ ПРОЕКТА
  // ============================================================
  // Значения по умолчанию одновременно задают схему данных: при загрузке
  // проекта принимаются только эти поля и только совместимых типов.
  const PROJECT_DEFAULTS = {
    title: 'Структурная схема комплекса',
    subtitle: 'АСУ ТП установки',
    fileName: 'structural_scheme',
    operatorName: 'Операторная',
    serverName: 'Серверная',
    autoName: 'Помещение шкафов автоматики',
    blocksPerRow: 4,
    showNotes: true,
    showSignalCounts: false,
    kvmPanel: false,
    kvmPanelName: 'Щит КВМ-удлинителей',
    notesText: '',
  };
  const ITEM_DEFAULTS = {
    opItems: { id: '', name: 'АРМ оператора', type: 'АРМ', link: 'Витая пара', target: null, kvmToPanel: false },
    racks: { id: '', name: 'Серверная стойка', servers: 2, kvm: false, ntp: false, ups: true, netTarget: null },
    netCabs: { id: '', name: 'Шкаф сетевой', switches: 2, fw: 0, cross: 1, external: false, ups: true },
    autoCabs: {
      id: '', name: 'Шкаф ША', ctrls: 1, uplink: 'Витая пара', netTarget: null,
      di: true, dO: true, ai: true, ao: false, rs485: false, rs485Cab: false, rs485Target: null,
      diN: 16, doN: 8, aiN: 8, aoN: 0,
    },
  };
  const LIST_KEYS = Object.keys(ITEM_DEFAULTS);

  // Новые элементы, которые добавляются кнопками «Добавить …».
  const firstNetId = (state) => state.netCabs[0] ? state.netCabs[0].id : null;
  const newOpItem = (state) => ({
    ...ITEM_DEFAULTS.opItems, id: uid(), name: 'АРМ оператора №' + (state.opItems.length + 1), target: firstNetId(state),
  });
  const newRack = (state) => ({
    ...ITEM_DEFAULTS.racks, id: uid(), name: 'Серверная стойка №' + (state.racks.length + 1), netTarget: firstNetId(state),
  });
  const newNetCab = (state) => ({
    ...ITEM_DEFAULTS.netCabs, id: uid(), name: 'Шкаф сетевой ШС-' + pad2(state.netCabs.length + 1),
  });
  const newAutoCab = (state) => ({
    ...ITEM_DEFAULTS.autoCabs, id: uid(), name: 'Шкаф ША-' + pad2(state.autoCabs.length + 1),
    netTarget: firstNetId(state), rs485Target: state.autoCabs[0] ? state.autoCabs[0].id : null,
  });

  // Демонстрационный проект, который открывается при первом запуске.
  function createDefaultState() {
    const net1 = uid();
    const auto = (name, ctrls) => ({
      ...ITEM_DEFAULTS.autoCabs, id: uid(), name, ctrls, netTarget: net1,
      di: true, dO: true, ai: true, ao: true, rs485: true, diN: 32, doN: 32, aiN: 16, aoN: 2,
    });
    const op = (name, type, kvmToPanel) => ({ id: uid(), name, type, link: 'Витая пара', target: net1, kvmToPanel });
    return {
      project: { ...PROJECT_DEFAULTS },
      opItems: [
        op('АРМ оператора №1', 'АРМ', true),
        op('АРМ оператора №2', 'АРМ', true),
        op('Принтер сетевой', 'Принтер', false),
        op('Панель управления', 'Панель управления', false),
      ],
      racks: [
        { id: uid(), name: 'Серверная стойка №1', servers: 3, kvm: true, ntp: true, ups: true, netTarget: net1 },
      ],
      netCabs: [
        { id: net1, name: 'Шкаф сетевой ШС-01', switches: 2, fw: 1, cross: 2, external: true, ups: true },
      ],
      autoCabs: [auto('Шкаф ША-01', 2), auto('Шкаф ША-02', 1), auto('Шкаф ША-03', 1)],
    };
  }

  // ---------- Сохранение / загрузка ----------
  const FORMAT = 'structural-scheme';
  const FORMAT_VERSION = 1;
  const STORAGE_KEY = 'structural-scheme:project';

  function serializeState(state) {
    const out = { format: FORMAT, version: FORMAT_VERSION, project: state.project };
    LIST_KEYS.forEach(k => { out[k] = state[k]; });
    return JSON.stringify(out, null, 2);
  }

  const isPlainObject = v => v != null && typeof v === 'object' && !Array.isArray(v);
  // Берёт из src только известные поля с подходящим типом, остальное — из defaults.
  function pickKnown(src, defaults) {
    const out = { ...defaults };
    if (!isPlainObject(src)) return out;
    Object.keys(defaults).forEach(key => {
      const v = src[key], d = defaults[key];
      if (v === undefined) return;
      const ok = d === null ? (v === null || typeof v === 'string')
        : typeof d === 'number' ? (typeof v === 'number' && Number.isFinite(v)) || typeof v === 'string'
        : typeof v === typeof d;
      if (ok) out[key] = v;
    });
    return out;
  }

  function normalizeState(raw) {
    if (!isPlainObject(raw)) throw new Error('Файл не содержит проект структурной схемы.');
    if (raw.format !== undefined && raw.format !== FORMAT) throw new Error('Файл не является проектом структурной схемы.');
    if (typeof raw.version === 'number' && raw.version > FORMAT_VERSION) {
      throw new Error('Проект сохранён в более новом формате, обновите приложение.');
    }
    const state = { project: pickKnown(raw.project, PROJECT_DEFAULTS) };
    // Из поля ввода число приходит строкой: сохраняем строку, если в ней было число.
    const perRow = state.project.blocksPerRow;
    const wasNumber = typeof perRow === 'string' && perRow.trim() !== '' && Number.isFinite(Number(perRow));
    state.project.blocksPerRow = wasNumber ? String(clampPerRow(perRow)) : clampPerRow(perRow);
    const seen = new Set([KVM_PANEL_ID]);
    LIST_KEYS.forEach(k => {
      const list = Array.isArray(raw[k]) ? raw[k] : [];
      state[k] = list.filter(isPlainObject).map(item => {
        const it = pickKnown(item, ITEM_DEFAULTS[k]);
        if (!it.id || seen.has(it.id)) it.id = uid();
        seen.add(it.id);
        return it;
      });
    });
    return state;
  }

  function parseState(text) {
    let raw;
    try { raw = JSON.parse(text); } catch (e) { throw new Error('Файл повреждён или не является JSON.'); }
    return normalizeState(raw);
  }

  // ---------- Цели соединений ----------
  // Ссылки на удалённые элементы не ломают схему: они заменяются первым подходящим.
  function makeResolvers(state) {
    const { project, racks, netCabs, autoCabs } = state;
    const srvTargetIds = new Set([...netCabs.map(c => c.id), ...racks.map(r => r.id)]);
    const effTarget = (id, allowPanel) => {
      if (allowPanel && id === KVM_PANEL_ID && project.kvmPanel) return KVM_PANEL_ID;
      if (srvTargetIds.has(id)) return id;
      return netCabs[0] ? netCabs[0].id : (racks[0] ? racks[0].id : null);
    };
    const effNet = (id) => netCabs.some(c => c.id === id) ? id : (netCabs[0] ? netCabs[0].id : null);
    const effAutoTarget = (id, sourceId) => {
      if (id !== sourceId && autoCabs.some(c => c.id === id)) return id;
      const target = autoCabs.find(c => c.id !== sourceId);
      return target ? target.id : null;
    };
    return { effTarget, effNet, effAutoTarget };
  }

  // ============================================================
  // ТРАССИРОВКА
  // ============================================================
  // Раздача каналов внутри одной горизонтальной полосы.
  // h: { x1, x2, top:[x...], bot:[x...] } — пролёт и абсциссы вертикалей, подходящих к нему сверху/снизу.
  // Строится граф «кто обязан быть выше кого», затем каналы раздаются без пересечений (где это возможно).
  function routeBand(hs) {
    const n = hs.length;
    hs.forEach(h => { h.track = -1; });
    if (!n) return 0;
    const above = hs.map(() => new Set()); // above[i] — пролёты, которые должны лежать ВЫШЕ i
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        if (i === j) continue;
        const A = hs[i], B = hs[j];
        const inside = x => x > A.x1 && x < A.x2;
        if (B.top.some(inside)) above[i].add(j); // вертикаль B сверху пересекает пролёт A → A ниже B
        if (B.bot.some(inside)) above[j].add(i); // вертикаль B снизу пересекает пролёт A → A выше B
      }
    }
    const placed = new Array(n).fill(false), order = [];
    for (let s = 0; s < n; s++) {
      let best = -1, bestCnt = Infinity, bestLen = Infinity;
      for (let i = 0; i < n; i++) {
        if (placed[i]) continue;
        let cnt = 0;
        above[i].forEach(j => { if (!placed[j]) cnt++; });
        const len = hs[i].x2 - hs[i].x1;
        if (cnt < bestCnt || (cnt === bestCnt && len < bestLen)) { best = i; bestCnt = cnt; bestLen = len; }
      }
      placed[best] = true;
      order.push(best);
    }
    let tracks = 0;
    order.forEach(i => {
      let t = 0;
      above[i].forEach(j => { if (hs[j].track >= 0) t = Math.max(t, hs[j].track + 1); });
      const busy = tt => hs.some((h, k) => k !== i && h.track === tt && !(h.x2 + 4 < hs[i].x1 || h.x1 > hs[i].x2 + 4));
      while (busy(t)) t++;
      hs[i].track = t;
      tracks = Math.max(tracks, t + 1);
    });
    return tracks;
  }

  // ============================================================
  // РАСКЛАДКА
  // ============================================================
  function layout(state, GAPX) {
    const { project, opItems, racks, netCabs, autoCabs } = state;
    const { effTarget, effNet, effAutoTarget } = makeResolvers(state);
    const perRow = clampPerRow(project.blocksPerRow);
    const hasExternal = netCabs.some(c => c.external);
    const titleH = project.subtitle ? 82 : 58;

    const colStep = BW + GAPX;
    const sidePad = Math.max(GAPX, hasExternal ? 84 : 0);

    // Полоса — горизонтальная область для горизонтальных участков линий:
    // межрядные зазоры внутри уровня ('inner') и коридоры между уровнями ('corridor').
    const mkBand = (id, kind, reserved, last) =>
      ({ id, kind, reserved, last, hs: [], tracks: 0, y: 0, height: 0, pad: kind === 'corridor' ? 22 : 12 });

    // Уровень: ряды блоков на ОБЩЕЙ сетке колонок
    const mkLevel = (key, items, hOf, reserved) => {
      const raw = chunk(items, perRow);
      const cols = Math.max(1, ...raw.map(r => r.length));
      const blocks = [];
      const rows = raw.map((row, r) => {
        const off = Math.floor((cols - row.length) / 2);
        return row.map((item, c) => {
          const b = { id: item.id, item, kind: item.kind, level: key, row: r, col: off + c, w: BW, h: hOf(item), x: 0, y: 0 };
          blocks.push(b);
          return b;
        });
      });
      return {
        key, rows, cols, blocks, nRows: rows.length,
        rowH: rows.map(row => Math.max(...row.map(b => b.h))),
        bands: rows.map((_, r) => mkBand(key + ':' + r, 'inner', reserved, r === rows.length - 1)),
        gapRuns: {}, startX: 0, y: 0, height: 0,
      };
    };

    const opAll = [
      ...opItems.map(i => ({ ...i, kind: 'item' })),
      ...(project.kvmPanel ? [{ id: KVM_PANEL_ID, kind: 'panel', name: project.kvmPanelName }] : []),
    ];
    const srvAll = [...racks.map(r => ({ ...r, kind: 'rack' })), ...netCabs.map(c => ({ ...c, kind: 'net' }))];
    const autoAll = autoCabs.map(c => ({ ...c, kind: 'auto' }));

    const LV = {
      op: mkLevel('op', opAll, () => OP_H, 0),
      srv: mkLevel('srv', srvAll, it => it.kind === 'rack' ? RACK_H : NET_H, 0),
      auto: mkLevel('auto', autoAll, () => AUTO_H, SIG_H),
    };
    const levels = [LV.op, LV.srv, LV.auto];
    const C1 = mkBand('C1', 'corridor', 0, false); // операторная ↔ серверная
    const C2 = mkBand('C2', 'corridor', 0, false); // серверная ↔ автоматика

    const maxCols = Math.max(...levels.map(L => L.cols));
    const width = Math.max(880, 2 * (MARGIN + sidePad) + maxCols * colStep - GAPX);
    levels.forEach(L => {
      L.startX = (width - (L.cols * colStep - GAPX)) / 2;
      L.blocks.forEach(b => { b.x = L.startX + b.col * colStep; });
    });
    const blk = {};
    levels.forEach(L => L.blocks.forEach(b => { blk[b.id] = b; }));
    const cx = b => b.x + b.w / 2;
    const firstNet = LV.srv.blocks.find(b => b.kind === 'net') || LV.srv.blocks[0] || null;
    const panel = blk[KVM_PANEL_ID] || null;

    // ---- логические связи ----
    const conns = [];
    LV.op.blocks.forEach(b => {
      if (b.kind !== 'item') return;
      const it = b.item;
      const tId = effTarget(it.target, true);
      const toPanel = tId === KVM_PANEL_ID && !!panel;
      const tgt = toPanel ? panel : (blk[tId] || firstNet);
      if (tgt) conns.push({ src: b, tgt, color: COLORS[toPanel ? 'KVM' : it.link] || COLORS['Витая пара'] });
      if (panel && it.kvmToPanel && !toPanel) conns.push({ src: b, tgt: panel, color: COLORS['KVM'] });
    });
    LV.srv.blocks.forEach(b => {
      if (b.kind !== 'rack') return;
      if (panel && b.item.kvm) conns.push({ src: b, tgt: panel, color: COLORS['KVM'] });
      const t = blk[effNet(b.item.netTarget)];
      if (t) conns.push({ src: b, tgt: t, color: COLORS['Витая пара'] });
    });
    const rs485CabLinks = new Set();
    LV.auto.blocks.forEach(b => {
      const t = blk[effNet(b.item.netTarget)];
      if (t) conns.push({ src: b, tgt: t, color: COLORS[b.item.uplink] || COLORS['Витая пара'] });

      if (b.item.rs485Cab) {
        const targetId = effAutoTarget(b.item.rs485Target, b.id);
        const target = blk[targetId];
        const linkKey = target ? [b.id, target.id].sort().join('|') : null;
        if (target && !rs485CabLinks.has(linkKey)) {
          rs485CabLinks.add(linkKey);
          conns.push({ src: b, tgt: target, color: COLORS['RS-485'] });
        }
      }
    });

    // ---- грани выхода/входа и основная полоса ----
    const ORD = { op: 0, srv: 1, auto: 2 };
    conns.forEach(c => {
      const S = c.src, T = c.tgt;
      c.u = false;
      if (S.level === T.level) {
        const L = LV[S.level];
        if (S.row < T.row) { c.sEdge = 'bottom'; c.tEdge = 'top'; c.band = L.bands[T.row - 1]; }
        else if (S.row > T.row) { c.sEdge = 'top'; c.tEdge = 'bottom'; c.band = L.bands[T.row]; }
        else { c.u = true; c.sEdge = 'bottom'; c.tEdge = 'bottom'; c.band = L.bands[S.row]; } // U-образная в зазоре под рядом
      } else {
        const down = ORD[S.level] < ORD[T.level];
        c.sEdge = down ? 'bottom' : 'top';
        c.tEdge = down ? 'top' : 'bottom';
        c.band = (S.level === 'op' || T.level === 'op') ? C1 : C2;
      }
    });

    // ---- точки выхода: разнос по грани в порядке положения целей ----
    groupBy(conns, c => c.src.id + '|' + c.sEdge).forEach(g => {
      g.sort((a, b) => cx(a.tgt) - cx(b.tgt));
      g.forEach((c, i) => { c.sx = cx(c.src) + (i - (g.length - 1) / 2) * EXIT_STEP; });
    });

    // ---- подход от грани блока к полосе: прямой либо через межколоночный зазор ----
    const approach = (c, isSrc, otherX) => {
      const B = isSrc ? c.src : c.tgt, O = isSrc ? c.tgt : c.src;
      const edge = isSrc ? c.sEdge : c.tEdge;
      const px = isSrc ? c.sx : c.tx;
      const L = LV[B.level];
      let r0, r1; // ряды, которые пересекает вертикаль
      if (B.level === O.level) {
        if (isSrc) { r0 = Math.min(B.row, O.row) + 1; r1 = Math.max(B.row, O.row) - 1; }
        else { r0 = 1; r1 = 0; }
      } else if (edge === 'bottom') { r0 = B.row + 1; r1 = L.nRows - 1; }
      else { r0 = 0; r1 = B.row - 1; }
      let len = 0, blocked = false;
      for (let r = r0; r <= r1; r++) { len++; if (L.rows[r].some(o => o.col === B.col)) blocked = true; }
      if (!blocked) return { x: px, run: null, jog: null };
      const dir = otherX >= cx(B) ? 'R' : 'L';           // в какую сторону от блока уходим
      const g = dir === 'R' ? B.col + 1 : B.col;          // зазор g — между колонками g-1 и g
      const run = { g, side: dir === 'R' ? 'L' : 'R', len, px, ax: cx(B) };
      (L.gapRuns[g] = L.gapRuns[g] || []).push(run);
      return { x: px, run, jog: edge === 'bottom' ? L.bands[B.row] : L.bands[B.row - 1] };
    };
    const proxyOf = a => a.run ? a.run.ax : a.x;
    const assignSlots = () => levels.forEach(L => Object.keys(L.gapRuns).forEach(k => {
      const g = Number(k), runs = L.gapRuns[k];
      const gl = L.startX + g * colStep - GAPX;
      const Ls = runs.filter(r => r.side === 'L').sort((a, b) => a.len - b.len || a.px - b.px);
      const Rs = runs.filter(r => r.side === 'R').sort((a, b) => a.len - b.len || b.px - a.px);
      Ls.forEach((r, i) => { r.ax = gl + SLOT_M + i * SLOT; });
      Rs.forEach((r, i) => { r.ax = gl + GAPX - SLOT_M - i * SLOT; });
    }));

    conns.forEach(c => { c.sApp = approach(c, true, cx(c.tgt)); });
    assignSlots();

    // ---- точки входа: U-образные слева, сквозные по x источника, U-образные справа ----
    groupBy(conns, c => c.tgt.id + '|' + c.tEdge).forEach(g => {
      const T = g[0].tgt, tc = cx(T);
      const key = c => c.u ? (cx(c.src) < tc ? 0 : 2) : 1;
      g.sort((a, b) => {
        const ka = key(a), kb = key(b);
        if (ka !== kb) return ka - kb;
        return ka === 1 ? proxyOf(a.sApp) - proxyOf(b.sApp) : b.sx - a.sx;
      });
      g.forEach((c, j) => { c.tx = T.x + T.w * (j + 1) / (g.length + 1); });
    });
    conns.forEach(c => { c.tApp = approach(c, false, proxyOf(c.sApp)); });
    assignSlots();

    let needGap = 0;
    levels.forEach(L => Object.values(L.gapRuns).forEach(runs => {
      needGap = Math.max(needGap, 2 * SLOT_M + (runs.length - 1) * SLOT);
    }));

    // ---- горизонтальные участки → полосы ----
    const mk = (a, b) => ({ x1: Math.min(a, b), x2: Math.max(a, b), top: [], bot: [], track: 0 });
    conns.forEach(c => {
      const sX = proxyOf(c.sApp), tX = proxyOf(c.tApp);
      c.main = mk(sX, tX);
      (c.sEdge === 'bottom' ? c.main.top : c.main.bot).push(sX);
      (c.tEdge === 'top' ? c.main.bot : c.main.top).push(tX);
      c.band.hs.push(c.main);
      if (c.sApp.run) {
        c.sJog = mk(c.sx, sX);
        if (c.sEdge === 'bottom') { c.sJog.top.push(c.sx); c.sJog.bot.push(sX); }
        else { c.sJog.bot.push(c.sx); c.sJog.top.push(sX); }
        c.sApp.jog.hs.push(c.sJog);
      }
      if (c.tApp.run) {
        c.tJog = mk(tX, c.tx);
        if (c.tEdge === 'top') { c.tJog.top.push(tX); c.tJog.bot.push(c.tx); }
        else { c.tJog.bot.push(tX); c.tJog.top.push(c.tx); }
        c.tApp.jog.hs.push(c.tJog);
      }
    });
    const allBands = [C1, C2, ...levels.flatMap(L => L.bands)];
    allBands.forEach(b => { b.tracks = routeBand(b.hs); });

    // ---- вертикальная раскладка ----
    const bandH = (b) => {
      const lines = b.tracks ? 2 * b.pad + (b.tracks - 1) * LSTEP : 0;
      if (b.kind === 'corridor') return Math.max(44, lines);
      return b.reserved + Math.max(b.last ? 8 : 18, lines);
    };
    const trackY = (b, t) => b.y + b.reserved + b.pad + t * LSTEP;
    let y = titleH;
    const layoutLevel = (L) => {
      L.y = y; let cy = y + HEAD;
      L.rows.forEach((row, r) => {
        row.forEach(b => { b.y = cy; });
        cy += L.rowH[r];
        const b = L.bands[r]; b.y = cy; b.height = bandH(b); cy += b.height;
      });
      if (!L.nRows) cy += 12;
      L.height = cy + 6 - y; y += L.height;
    };
    layoutLevel(LV.op);
    C1.y = y; C1.height = bandH(C1); y += C1.height;
    layoutLevel(LV.srv);
    C2.y = y; C2.height = bandH(C2); y += C2.height;
    layoutLevel(LV.auto);

    // ---- точки маршрутов ----
    conns.forEach(c => {
      const S = c.src, T = c.tgt;
      c.sy = c.sEdge === 'bottom' ? S.y + S.h : S.y;
      c.ty = c.tEdge === 'top' ? T.y : T.y + T.h;
      const sX = proxyOf(c.sApp), tX = proxyOf(c.tApp);
      const pts = [[c.sx, c.sy]];
      if (c.sApp.run) { const jy = trackY(c.sApp.jog, c.sJog.track); pts.push([c.sx, jy], [sX, jy]); }
      const my = trackY(c.band, c.main.track); pts.push([sX, my], [tX, my]);
      if (c.tApp.run) { const jy = trackY(c.tApp.jog, c.tJog.track); pts.push([tX, jy], [c.tx, jy]); }
      pts.push([c.tx, c.ty]);
      c.pts = pts.filter((p, i) => i === 0 || Math.abs(p[0] - pts[i - 1][0]) > 0.01 || Math.abs(p[1] - pts[i - 1][1]) > 0.01);
    });

    // ---- внешняя связь ----
    const ext = LV.srv.blocks.filter(b => b.kind === 'net' && b.item.external).map(b => {
      const row = LV.srv.rows[b.row];
      const rightmost = row[row.length - 1] === b;
      return {
        b, y: b.y + b.h - 12, x1: b.x + b.w,
        x2: rightmost ? width - MARGIN + 14 : b.x + b.w + GAPX - 6,
        label: rightmost,
      };
    });

    return { width, titleH, LV, levels, conns, C1, C2, blk, ext, needGap, bottom: y };
  }

  // ---------- Описания блоков ----------
  function blockLines(b, state) {
    const it = b.item;
    if (b.kind === 'item') return [it.type];
    if (b.kind === 'panel') return ['KVM-удлинители', `Стоек подключено: ${state.racks.filter(r => r.kvm).length}`];
    if (b.kind === 'rack') {
      const l = [`Серверов: ${it.servers}`];
      if (it.ntp) l.push('Сервер NTP');
      if (it.kvm) l.push('KVM');
      if (it.ups) l.push('ИБП RACK');
      return l;
    }
    if (b.kind === 'net') {
      const l = [`Коммутаторов: ${it.switches}`];
      if (it.fw > 0) l.push(`Межсетевых экранов: ${it.fw}`);
      if (it.cross > 0) l.push(`Опт. кроссов: ${it.cross}`);
      if (it.external) l.push('Внешняя связь');
      if (it.ups) l.push('ИБП RACK');
      return l;
    }
    return [`Контроллеров: ${it.ctrls}`];
  }

  // ============================================================
  // ПОЛНАЯ МОДЕЛЬ СХЕМЫ
  // ============================================================
  // Единственный источник геометрии и текстов для всех форматов вывода:
  // toSvg() (предпросмотр, SVG, PNG, JPG) и toDrawio() рисуют одну и ту же модель.
  function buildScheme(state) {
    const { project, autoCabs, netCabs } = state;

    // Ширина межколоночного зазора подбирается под число вертикалей в нём.
    let M = null, gapx = GAP_MIN;
    for (let i = 0; i < 4; i++) {
      M = layout(state, gapx);
      if (M.needGap <= gapx) break;
      gapx = M.needGap;
    }
    const { width, LV, levels, conns, ext } = M;
    const levelX = MARGIN, levelW = width - 2 * MARGIN;

    const blocks = levels.flatMap(L => L.blocks);
    blocks.forEach(b => {
      b.name = b.item.name;
      b.lines = blockLines(b, state);
      b.fill = b.kind === 'panel' ? '#f1f5f9' : '#ffffff';
    });

    const rooms = [
      { id: 'lvl_op', L: LV.op, name: project.operatorName, fill: LEVEL_FILL.op },
      { id: 'lvl_srv', L: LV.srv, name: project.serverName, fill: LEVEL_FILL.srv },
      { id: 'lvl_auto', L: LV.auto, name: project.autoName, fill: LEVEL_FILL.auto },
    ].map(r => ({ id: r.id, name: r.name, fill: r.fill, x: levelX, y: r.L.y, w: levelW, h: r.L.height }));

    // ---- стрелки сигналов под шкафами автоматики ----
    const signals = [];
    LV.auto.blocks.forEach(b => {
      const sigs = signalsOf(b.item);
      sigs.forEach((s, i) => {
        signals.push({
          block: b, kind: s.k, color: COLORS[s.k],
          label: signalLabel(s, project.showSignalCounts),
          exitX: (i + 1) / (sigs.length + 1),
          x: b.x + b.w * (i + 1) / (sigs.length + 1),
          y1: b.y + b.h, y2: b.y + b.h + SIG_LEN,
        });
      });
    });

    // ---- легенда ----
    const used = new Set();
    conns.forEach(c => { if (NAME_BY_COLOR[c.color]) used.add(NAME_BY_COLOR[c.color]); });
    autoCabs.forEach(c => {
      if (c.rs485) used.add('RS-485');
      if (c.di) used.add('DI'); if (c.dO) used.add('DO');
      if (c.ai) used.add('AI'); if (c.ao) used.add('AO');
    });
    if (netCabs.some(c => c.external)) used.add('Оптика');
    const legendNames = Object.keys(COLORS).filter(k => used.has(k));
    const legCols = Math.max(1, Math.floor((width - 2 * MARGIN) / LEGEND_ITEM_W));
    const legRows = Math.ceil(legendNames.length / legCols) || 1;
    const legendY = M.bottom + 24;
    const legend = {
      x: levelX, y: legendY, w: levelW, h: 34 + legRows * 24, itemW: LEGEND_ITEM_W,
      items: legendNames.map((name, i) => ({
        name, color: COLORS[name],
        x: levelX + 14 + (i % legCols) * LEGEND_ITEM_W,
        y: legendY + 36 + Math.floor(i / legCols) * 24,
      })),
    };

    // ---- примечания ----
    const noteLines = project.showNotes ? String(project.notesText || '').split('\n').filter(Boolean) : [];
    const notesY = legend.y + legend.h + 18;
    const notes = noteLines.length ? { x: levelX, y: notesY, lines: noteLines } : null;
    const height = notesY + (noteLines.length ? 20 + noteLines.length * 16 : 0) + 24;

    return {
      width, height, title: project.title, subtitle: project.subtitle, fileName: fileNameOf(project),
      rooms, blocks, conns, ext, signals, legend, notes,
    };
  }

  // ============================================================
  // ВЫВОД В SVG
  // ============================================================
  const esc = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const svgAttrs = (attrs) => Object.keys(attrs)
    .filter(k => attrs[k] !== undefined && attrs[k] !== null && attrs[k] !== false)
    .map(k => ` ${k}="${esc(attrs[k])}"`).join('');
  const el = (tag, attrs, content) =>
    content === undefined ? `<${tag}${svgAttrs(attrs)}/>` : `<${tag}${svgAttrs(attrs)}>${content}</${tag}>`;
  const txt = (attrs, s) => el('text', attrs, esc(s));

  function toSvg(m) {
    const out = [];
    out.push(el('rect', { x: 0, y: 0, width: m.width, height: m.height, fill: '#ffffff' }));
    out.push(txt({ x: m.width / 2, y: 30, 'text-anchor': 'middle', 'font-size': 18, 'font-weight': 'bold', fill: '#111827' }, m.title));
    if (m.subtitle) out.push(txt({ x: m.width / 2, y: 52, 'text-anchor': 'middle', 'font-size': 12, fill: '#6b7280' }, m.subtitle));

    // помещения
    m.rooms.forEach(r => out.push(el('rect', {
      x: r.x, y: r.y, width: r.w, height: r.h, rx: 8,
      fill: r.fill, stroke: '#94a3b8', 'stroke-width': 1, 'stroke-dasharray': '6 4',
    })));

    // связи
    m.conns.forEach(c => out.push(el('path', {
      d: c.pts.map((p, i) => `${i ? 'L' : 'M'} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' '),
      stroke: c.color, 'stroke-width': 1.7, fill: 'none', 'stroke-linejoin': 'round',
    })));

    // внешняя связь
    const optic = COLORS['Оптика'];
    m.ext.forEach(e => out.push(el('g', {}, [
      el('line', { x1: e.x1, y1: e.y, x2: e.x2, y2: e.y, stroke: optic, 'stroke-width': 1.7, 'stroke-dasharray': '7 4' }),
      el('polygon', { points: `${e.x2},${e.y} ${e.x2 - 8},${e.y - 4} ${e.x2 - 8},${e.y + 4}`, fill: optic }),
      e.label ? txt({ x: e.x2 - 4, y: e.y - 7, 'text-anchor': 'end', 'font-size': 9, fill: optic }, 'Внешняя связь') : '',
    ].join(''))));

    // блоки
    m.blocks.forEach(b => out.push(el('g', {}, [
      el('rect', { x: b.x, y: b.y, width: b.w, height: b.h, rx: 6, fill: b.fill, stroke: '#334155', 'stroke-width': 1.3 }),
      txt({ x: b.x + b.w / 2, y: b.y + 16, 'text-anchor': 'middle', 'font-size': 11, 'font-weight': 'bold', fill: '#111827' }, fit(b.name, 28)),
      el('line', { x1: b.x + 8, y1: b.y + 24, x2: b.x + b.w - 8, y2: b.y + 24, stroke: '#cbd5e1' }),
      ...b.lines.map((t, i) => txt({ x: b.x + 12, y: b.y + 40 + i * 16, 'font-size': 10, fill: '#374151' }, '• ' + fit(t, 30))),
    ].join(''))));

    // подписи помещений (поверх линий)
    m.rooms.forEach(r => out.push(el('g', {}, [
      el('rect', { x: r.x + 8, y: r.y + 7, width: String(r.name).length * 7.2 + 12, height: 19, rx: 4, fill: r.fill }),
      txt({ x: r.x + 14, y: r.y + 21, 'font-size': 12, 'font-weight': 'bold', fill: '#475569' }, r.name),
    ].join(''))));

    // стрелки сигналов
    m.signals.forEach(s => out.push(el('g', {}, [
      el('line', { x1: s.x, y1: s.y1, x2: s.x, y2: s.y2 - 6, stroke: s.color, 'stroke-width': 1.7 }),
      el('polygon', { points: `${s.x},${s.y2} ${s.x - 4},${s.y2 - 7} ${s.x + 4},${s.y2 - 7}`, fill: s.color }),
      txt({ x: s.x, y: s.y2 + 13, 'text-anchor': 'middle', 'font-size': 9, 'font-weight': 'bold', fill: s.color }, s.label),
    ].join(''))));

    // легенда
    const lg = m.legend;
    out.push(el('g', {}, [
      el('rect', { x: lg.x, y: lg.y, width: lg.w, height: lg.h, rx: 6, fill: '#ffffff', stroke: '#94a3b8' }),
      txt({ x: lg.x + 14, y: lg.y + 18, 'font-size': 11, 'font-weight': 'bold', fill: '#374151' }, 'Условные обозначения:'),
      ...lg.items.map(it => el('g', {}, [
        el('line', { x1: it.x, y1: it.y, x2: it.x + 30, y2: it.y, stroke: it.color, 'stroke-width': 3 }),
        txt({ x: it.x + 38, y: it.y + 4, 'font-size': 10, fill: '#374151' }, it.name),
      ].join(''))),
    ].join('')));

    // примечания
    if (m.notes) {
      const n = m.notes;
      out.push(el('g', {}, [
        txt({ x: n.x, y: n.y + 12, 'font-size': 11, 'font-weight': 'bold', fill: '#374151' }, 'Примечания:'),
        ...n.lines.map((t, i) => txt({ x: n.x, y: n.y + 30 + i * 16, 'font-size': 10, fill: '#4b5563' }, t)),
      ].join('')));
    }

    return el('svg', {
      xmlns: 'http://www.w3.org/2000/svg', width: m.width, height: m.height,
      viewBox: `0 0 ${m.width} ${m.height}`, 'font-family': 'Arial, Helvetica, sans-serif', style: 'background: #fff',
    }, out.join(''));
  }

  // ============================================================
  // ВЫВОД В DRAW.IO
  // ============================================================
  function toDrawio(m) {
    const xesc = esc;
    const hesc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const R = n => Math.round(n);
    const cells = [];
    let eid = 0;

    const vtx = (id, value, x, y, w, h, style) =>
      cells.push(`<mxCell id="${id}" value="${xesc(value)}" style="${style}" vertex="1" parent="1"><mxGeometry x="${R(x)}" y="${R(y)}" width="${R(w)}" height="${R(h)}" as="geometry"/></mxCell>`);
    const edge = (value, style, attrs, geometry) =>
      cells.push(`<mxCell id="e${eid++}" value="${xesc(value)}" style="${style}" edge="1" parent="1"${attrs}><mxGeometry relative="1" as="geometry">${geometry}</mxGeometry></mxCell>`);

    vtx('t1', `<b>${hesc(m.title)}</b>`, MARGIN, 8, m.width - 2 * MARGIN, 26,
      'text;html=1;align=center;verticalAlign=middle;fontSize=18;fontColor=#111827;');
    if (m.subtitle) vtx('t2', hesc(m.subtitle), MARGIN, 38, m.width - 2 * MARGIN, 18,
      'text;html=1;align=center;verticalAlign=middle;fontSize=12;fontColor=#6b7280;');

    const roomStyle = f => `rounded=1;dashed=1;dashPattern=6 4;fillColor=${f};strokeColor=#94a3b8;verticalAlign=top;align=left;spacingLeft=10;spacingTop=2;fontSize=12;fontStyle=1;fontColor=#475569;html=1;`;
    m.rooms.forEach(r => vtx(r.id, hesc(r.name), r.x, r.y, r.w, r.h, roomStyle(r.fill)));

    const blockVal = (title, lines) =>
      `<b>${hesc(title)}</b><hr size="1"/>` + lines.map(l => `<div style="text-align:left;">• ${hesc(l)}</div>`).join('');
    const blockStyle = f => `rounded=1;whiteSpace=wrap;html=1;fillColor=${f};strokeColor=#334155;verticalAlign=top;align=center;fontSize=10;fontColor=#111827;spacing=4;`;
    m.blocks.forEach(b => vtx('b_' + b.id, blockVal(b.name, b.lines), b.x, b.y, b.w, b.h, blockStyle(b.fill)));

    m.conns.forEach(c => {
      const S = c.src, T = c.tgt;
      const exitX = ((c.sx - S.x) / S.w).toFixed(3), exitY = c.sEdge === 'top' ? 0 : 1;
      const entryX = ((c.tx - T.x) / T.w).toFixed(3), entryY = c.tEdge === 'top' ? 0 : 1;
      const inner = c.pts.slice(1, -1).map(p => `<mxPoint x="${R(p[0])}" y="${R(p[1])}"/>`).join('');
      edge('', `edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=none;strokeWidth=2;strokeColor=${c.color};exitX=${exitX};exitY=${exitY};exitDx=0;exitDy=0;entryX=${entryX};entryY=${entryY};entryDx=0;entryDy=0;`,
        ` source="b_${S.id}" target="b_${T.id}"`, `<Array as="points">${inner}</Array>`);
    });

    const optic = COLORS['Оптика'];
    m.ext.forEach(e => {
      const exitY = ((e.y - e.b.y) / e.b.h).toFixed(3);
      edge(e.label ? 'Внешняя связь' : '', `endArrow=block;endFill=1;dashed=1;dashPattern=7 4;html=1;strokeWidth=2;strokeColor=${optic};fontColor=${optic};fontSize=9;verticalAlign=bottom;exitX=1;exitY=${exitY};exitDx=0;exitDy=0;`,
        ` source="b_${e.b.id}"`, `<mxPoint x="${R(e.x2)}" y="${R(e.y)}" as="targetPoint"/>`);
    });

    m.signals.forEach(s => {
      edge(s.label, `endArrow=block;endFill=1;html=1;strokeWidth=2;strokeColor=${s.color};fontColor=${s.color};fontSize=9;fontStyle=1;verticalAlign=bottom;exitX=${s.exitX.toFixed(3)};exitY=1;exitDx=0;exitDy=0;`,
        ` source="b_${s.block.id}"`, `<mxPoint x="${R(s.x)}" y="${R(s.y2)}" as="targetPoint"/>`);
    });

    const lg = m.legend;
    vtx('leg', '<b>Условные обозначения:</b>', lg.x, lg.y, lg.w, lg.h,
      'rounded=1;html=1;fillColor=#ffffff;strokeColor=#94a3b8;verticalAlign=top;align=left;spacingLeft=10;spacingTop=2;fontSize=11;fontColor=#374151;');
    lg.items.forEach((it, i) => {
      vtx('leg_' + i, `<font color="${it.color}">▬▬▬</font> ${hesc(it.name)}`, it.x, it.y - 10, lg.itemW - 12, 20,
        'text;html=1;align=left;verticalAlign=middle;fontSize=10;fontColor=#374151;');
    });

    if (m.notes) {
      const val = '<b>Примечания:</b>' + m.notes.lines.map(t => `<div>${hesc(t)}</div>`).join('');
      vtx('notes', val, m.notes.x, m.notes.y, lg.w, 20 + m.notes.lines.length * 16,
        'text;html=1;align=left;verticalAlign=top;fontSize=10;fontColor=#4b5563;');
    }

    return `<mxfile host="app.diagrams.net" agent="scheme-generator" version="1.1"><diagram id="d1" name="Схема"><mxGraphModel dx="800" dy="600" grid="0" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="${R(m.width)}" pageHeight="${R(m.height)}" math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>${cells.join('')}</root></mxGraphModel></diagram></mxfile>`;
  }

  return {
    COLORS, NAME_BY_COLOR, OP_TYPES, OP_LINKS, AUTO_UPLINKS, KVM_PANEL_ID,
    PROJECT_DEFAULTS, ITEM_DEFAULTS, FORMAT, FORMAT_VERSION, STORAGE_KEY,
    PER_ROW_MAX, RASTER_SCALE, RASTER_MAX_PIXELS,
    uid, fit, pad2, clampPerRow, rasterScale, signalLabel, signalsOf, fileNameOf, routeBand,
    createDefaultState, newOpItem, newRack, newNetCab, newAutoCab,
    serializeState, normalizeState, parseState, makeResolvers,
    buildScheme, toSvg, toDrawio,
  };
});
