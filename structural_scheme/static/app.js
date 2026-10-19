'use strict';
/* Локальный редактор структурных схем АСУ ТП. Без внешних библиотек и сети. */
const $ = s => document.querySelector(s);
const KEY = 'structural-scheme:project';
const tabs = [['project', 'Проект'], ['op', 'Операторная'], ['srv', 'Серверная'], ['auto', 'Шкафы автоматики']];
const labels = {
  title: 'Название схемы', subtitle: 'Подзаголовок', fileName: 'Имя выходных файлов',
  blocksPerRow: 'Блоков в одном ряду', operatorName: 'Название операторной',
  serverName: 'Название серверной', autoName: 'Помещение шкафов автоматики',
  showNotes: 'Показывать примечания', showSignalCounts: 'Показывать количества сигналов',
  notesText: 'Текст примечаний', kvmPanel: 'Щит КВМ-удлинителей в операторной',
  kvmPanelName: 'Название щита', name: 'Название', type: 'Тип', link: 'Связь', target: 'Куда',
  kvmToPanel: 'KVM → щит', servers: 'Серверов', kvm: 'KVM', ntp: 'NTP', ups: 'ИБП',
  netTarget: 'Подключение к', switches: 'Коммутаторов', fw: 'Межсетевых экранов',
  cross: 'Опт. кроссов', external: 'Внешняя связь', ctrls: 'Контроллеров', uplink: 'Связь сверху',
  di: 'DI', dO: 'DO', ai: 'AI', ao: 'AO', rs485: 'RS-485 вниз', rs485Cab: 'RS-485 между',
  rs485Target: 'Связать со шкафом', diN: 'Количество DI', doN: 'Количество DO',
  aiN: 'Количество AI', aoN: 'Количество AO',
};
/* Подсказки-всплывашки к полям: помогают понять смысл, не меняя подписи. */
const hints = {
  title: 'Заголовок листа схемы',
  subtitle: 'Строка под заголовком',
  fileName: 'Базовое имя для скачанных файлов',
  blocksPerRow: 'Сколько блоков помещается в один ряд помещения (1–12)',
  operatorName: 'Название помещения над блоками операторной',
  serverName: 'Название помещения серверной',
  autoName: 'Название помещения шкафов автоматики',
  showNotes: 'Показывать блок примечаний внизу листа',
  showSignalCounts: 'Показывать числа DI/DO/AI/AO под шкафами автоматики',
  notesText: 'Каждая строка — отдельное примечание',
  kvmPanel: 'Добавить щит КВМ-удлинителей в операторную',
  kvmPanelName: 'Как подписать щит КВМ-удлинителей',
  name: 'Подпись блока на схеме (длинные подписи сокращаются)',
  type: 'Тип устройства операторной',
  link: 'Среда связи устройства',
  target: 'Куда подключается устройство; «Автоматически» — первый подходящий блок',
  kvmToPanel: 'Показать линию KVM от устройства к щиту',
  servers: 'Количество серверов в стойке',
  kvm: 'Есть ли KVM в стойке',
  ntp: 'Сервер времени NTP',
  ups: 'Источник бесперебойного питания',
  netTarget: 'Сетевой шкаф для подключения',
  switches: 'Количество коммутаторов',
  fw: 'Количество межсетевых экранов',
  cross: 'Количество оптических кроссов',
  external: 'Связь с внешними сетями',
  ctrls: 'Количество контроллеров в шкафу',
  uplink: 'Среда связи шкафа вверх по иерархии',
  di: 'Условные обозначения входов DI',
  dO: 'Условные обозначения выходов DO',
  ai: 'Условные обозначения аналоговых входов AI',
  ao: 'Условные обозначения аналоговых выходов AO',
  rs485: 'Показать линию RS-485 вниз от шкафа',
  rs485Cab: 'Показать линию RS-485 между шкафами автоматики',
  rs485Target: 'С каким шкафом связать по RS-485',
  diN: 'Число сигналов DI',
  doN: 'Число сигналов DO',
  aiN: 'Число сигналов AI',
  aoN: 'Число сигналов AO',
};
let state, defaults, tab = 'project', timer, revision = 0, previewController, idSeq = 0, presets = [];
let history = [], future = [], historyAt = 0, toastTimer;

/* ---------- Мелкие помощники ---------- */
function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
function error(e) {
  $('#error').hidden = !e;
  $('#error').textContent = e ? String(e.message || e) : '';
}
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 3200);
}
function newId() {
  return crypto.randomUUID?.()?.replace(/-/g, '').slice(0, 12) || `${Date.now().toString(36)}-${++idSeq}`;
}
function renderSvg(svgText) {
  const doc = new DOMParser().parseFromString(svgText, 'image/svg+xml');
  const root = doc.documentElement;
  if (!root || root.tagName.toLowerCase() !== 'svg' || doc.querySelector('parsererror')) throw new Error('Некорректный SVG предпросмотра');
  for (const bad of root.querySelectorAll('script,foreignObject,iframe,object,embed')) bad.remove();
  for (const node of [root, ...root.querySelectorAll('*')]) {
    for (const attr of [...node.attributes]) {
      if (attr.name.toLowerCase().startsWith('on') || /^\s*javascript:/i.test(attr.value)) node.removeAttribute(attr.name);
    }
  }
  $('#preview').replaceChildren(document.importNode(root, true));
}
async function api(url, data, signal) {
  const r = await fetch(url, data === undefined ? { signal } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data), signal });
  if (!r.ok) {
    let msg;
    try { msg = (await r.json()).detail; } catch { msg = r.statusText; }
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return r;
}
function download(blob, name) {
  const url = URL.createObjectURL(blob), a = el('a');
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function safeFileName() {
  return ((state?.project?.fileName || 'scheme').replace(/[^\wа-яА-ЯёЁ-]+/g, '_').slice(0, 120)) || 'scheme';
}

/* ---------- Отмена и повтор действий ---------- */
function syncHistory() {
  $('#undo').disabled = !history.length;
  $('#redo').disabled = !future.length;
}
function pushHistory(force) {
  const now = Date.now();
  // Подряд идущие правки одного поля — одна точка отмены: undo возвращает
  // состояние до начала правки, а не до последней буквы.
  if (!force && history.length && now - historyAt < 700) return;
  historyAt = now;
  history.push(JSON.stringify(state));
  if (history.length > 40) history.shift();
  future = [];
  syncHistory();
}
function restore(json) {
  state = JSON.parse(json);
  render();
  error(null);
  changed();
}
function undo() {
  if (!history.length) return;
  future.push(JSON.stringify(state));
  restore(history.pop());
  syncHistory();
  toast('Действие отменено');
}
function redo() {
  if (!future.length) return;
  history.push(JSON.stringify(state));
  restore(future.pop());
  syncHistory();
  toast('Действие повторено');
}

/* ---------- Состояние, автосохранение и предпросмотр ---------- */
function persist() {
  try {
    localStorage.setItem(KEY, JSON.stringify({ format: 'structural-scheme', version: 1, ...state }));
  } catch (e) {
    error(new Error('Не удалось сохранить в браузере. Скачайте JSON: ' + e.message));
  }
}
function changed() {
  persist();
  const rev = ++revision;
  clearTimeout(timer);
  $('#status').textContent = 'Перестроение…';
  timer = setTimeout(() => preview(rev), 220);
}
async function preview(rev = revision) {
  previewController?.abort();
  const controller = new AbortController();
  previewController = controller;
  try {
    const m = await (await api('/api/preview', state, controller.signal)).json();
    if (rev !== revision) return;
    renderSvg(m.svg);
    zoom();
    const w = m.warnings && m.warnings.length ? ' · ' + m.warnings.join(' · ') : '';
    $('#status').textContent = `${m.width} × ${m.height} px · Блоков: ${m.blocks} · Связей: ${m.conns}${w}`;
    $('#status').classList.toggle('warn', Boolean(w));
  } catch (e) {
    if (e.name === 'AbortError') return; /* отменён более новым редактированием */
    if (rev === revision) {
      error(e);
      $('#status').textContent = 'Ошибка построения';
    }
  }
}
function zoom() {
  const svg = $('#preview svg');
  if (!svg) return;
  const v = $('#zoom').value;
  const w = Number(svg.getAttribute('width')), h = Number(svg.getAttribute('height'));
  let scale = v === 'fit' ? Math.min(1, Math.max(100, $('#preview').clientWidth - 48) / w) : Number(v);
  svg.style.width = (w * scale) + 'px';
  svg.style.height = (h * scale) + 'px';
}

/* ---------- Поля форм ---------- */
function optionsFor(key, item) {
  const opt = defaults?.options;
  if (key === 'type') return (opt?.type || ['АРМ', 'Принтер', 'Панель управления']).map(x => [x, x]);
  if (key === 'link') return (opt?.link || ['Витая пара', 'Оптика', 'KVM']).map(x => [x, x]);
  if (key === 'uplink') return (opt?.uplink || ['Витая пара', 'Оптика']).map(x => [x, x]);
  const panelId = opt?.kvmPanelId || 'kvmpanel';
  let a;
  if (key === 'target') a = [...state.netCabs, ...state.racks, ...(state.project.kvmPanel ? [{ id: panelId, name: state.project.kvmPanelName }] : [])];
  if (key === 'netTarget') a = state.netCabs;
  if (key === 'rs485Target') a = state.autoCabs.filter(c => c.id !== item.id);
  return a ? [[null, 'Автоматически'], ...a.map(c => [c.id, c.name])] : null;
}
function field(obj, key, parent, wide = false) {
  const value = obj[key], label = el('label', undefined, 'field' + (typeof value === 'boolean' ? ' check' : '') + (wide ? ' wide' : '') + (key === 'name' ? ' name' : ''));
  const opts = optionsFor(key, obj);
  let input;
  if (opts) {
    input = el('select');
    if (value && !opts.some(([id]) => id === value)) opts.push([value, 'Удалён — авто-выбор']);
    for (const [id, name] of opts) {
      const o = el('option', name);
      o.value = id === null ? '' : id;
      input.append(o);
    }
    input.value = value ?? '';
  } else if (key === 'notesText') {
    input = el('textarea');
    input.value = value;
  } else {
    input = el('input');
    input.type = typeof value === 'boolean' ? 'checkbox' : typeof defaults.project[key] === 'number' || Object.values(defaults.items).some(d => typeof d[key] === 'number') ? 'number' : 'text';
    if (input.type === 'checkbox') input.checked = value;
    else input.value = value ?? '';
    if (input.type === 'number') {
      input.min = key === 'blocksPerRow' ? '1' : '0';
      if (key === 'blocksPerRow') input.max = '12';
    }
  }
  input.setAttribute('aria-label', labels[key] || key);
  if (hints[key]) input.title = hints[key];
  const update = () => {
    pushHistory();
    obj[key] = input.type === 'checkbox' ? input.checked : opts ? (input.value || null) : input.value;
    error(null);
    changed();
    if (['kvmPanel', 'showNotes', 'showSignalCounts', 'rs485Cab'].includes(key)) render();
  };
  input.addEventListener(opts || input.type === 'checkbox' ? 'change' : 'input', update);
  label.append(el('span', labels[key] || key), input);
  if (input.type === 'checkbox') label.prepend(input);
  parent.append(label);
}

/* ---------- Списки устройств ---------- */
function addItem(key) {
  pushHistory(true);
  const n = state[key].length + 1, first = state.netCabs[0]?.id ?? null;
  const it = { ...defaults.items[key], id: newId() };
  it.name = key === 'opItems' ? `АРМ оператора №${n}` : key === 'racks' ? `Серверная стойка №${n}` : key === 'netCabs' ? `Шкаф сетевой ШС-${String(n).padStart(2, '0')}` : `Шкаф ША-${String(n).padStart(2, '0')}`;
  if (key === 'opItems') it.target = first;
  if (['racks', 'autoCabs'].includes(key)) it.netTarget = first;
  if (key === 'autoCabs') it.rs485Target = state.autoCabs[0]?.id ?? null;
  state[key].push(it);
  changed();
  render();
}
function duplicateItem(key, item) {
  pushHistory(true);
  const copy = JSON.parse(JSON.stringify(item));
  copy.id = newId();
  copy.name = item.name + ' (копия)';
  state[key].splice(state[key].indexOf(item) + 1, 0, copy);
  changed();
  render();
  toast('Создана копия блока');
}
function removeItem(key, item) {
  pushHistory(true);
  state[key] = state[key].filter(i => i !== item);
  changed();
  render();
  toast('Блок удалён');
}
function group(parent, key, title, button) {
  const head = el('h3', undefined, 'group-title');
  head.append(el('span', title), el('span', String(state[key].length), 'count'));
  parent.append(head);
  const list = el('div', undefined, 'items');
  if (!state[key].length) list.append(el('p', 'Пока пусто — нажмите кнопку ниже, чтобы добавить первый блок.', 'empty-hint'));
  for (const item of state[key]) {
    const card = el('div', undefined, 'card');
    for (const fieldKey of Object.keys(defaults.items[key])) {
      if (fieldKey === 'id') continue;
      if (['diN', 'doN', 'aiN', 'aoN'].includes(fieldKey) && !state.project.showSignalCounts) continue;
      field(item, fieldKey, card);
    }
    const row = el('div', undefined, 'card-actions');
    const dup = el('button', 'Дублировать', 'ghost');
    dup.onclick = () => duplicateItem(key, item);
    const del = el('button', 'Удалить', 'remove');
    del.onclick = () => removeItem(key, item);
    row.append(dup, del);
    card.append(row);
    list.append(card);
  }
  parent.append(list);
  const add = el('button', button, 'add');
  add.onclick = () => addItem(key);
  parent.append(add);
}
function render() {
  $('#tabs').replaceChildren();
  for (const [id, name] of tabs) {
    const b = el('button', name, id === tab ? 'active' : '');
    b.setAttribute('aria-selected', String(id === tab));
    b.onclick = () => { tab = id; render(); };
    $('#tabs').append(b);
  }
  const root = $('#fields');
  root.replaceChildren();
  if (tab === 'project') {
    const grid = el('div', undefined, 'grid');
    for (const key of Object.keys(defaults.project)) {
      if (key.startsWith('kvmPanel')) continue;
      if (key === 'notesText' && !state.project.showNotes) continue;
      field(state.project, key, grid, key === 'notesText');
    }
    root.append(grid);
  }
  if (tab === 'op') {
    const panel = el('div', undefined, 'panel');
    field(state.project, 'kvmPanel', panel);
    if (state.project.kvmPanel) field(state.project, 'kvmPanelName', panel);
    root.append(panel);
    group(root, 'opItems', 'Операторные станции и устройства', '+ Добавить устройство');
  }
  if (tab === 'srv') {
    group(root, 'racks', 'Серверные стойки', '+ Добавить стойку');
    group(root, 'netCabs', 'Сетевые шкафы', '+ Добавить сетевой шкаф');
  }
  if (tab === 'auto') group(root, 'autoCabs', 'Шкафы автоматики', '+ Добавить шкаф');
}

/* ---------- Шаблоны, импорт и экспорт ---------- */
function renderPresets() {
  const wrap = $('#presets');
  wrap.replaceChildren();
  for (const p of presets) {
    const b = el('button', undefined, 'preset');
    b.type = 'button';
    b.setAttribute('aria-label', p.title);
    b.append(el('strong', p.title), el('span', p.hint));
    b.onclick = () => loadPreset(p);
    wrap.append(b);
  }
}
function loadPreset(p) {
  pushHistory(true);
  state = JSON.parse(JSON.stringify(p.state));
  render();
  error(null);
  changed();
  toast(`Загружен шаблон «${p.title}» — просто уточните названия и количества`);
}
async function importFile(file) {
  try {
    const text = (await file.text()).replace(/^\uFEFF/, '');
    let raw;
    try {
      raw = JSON.parse(text);
    } catch {
      throw new Error('Файл повреждён или не является JSON.');
    }
    const next = await (await api('/api/normalize', raw)).json();
    pushHistory(true);
    state = next;
    render();
    error(null);
    changed();
    toast('Проект открыт: ' + file.name);
  } catch (e) {
    error(e);
  } finally {
    $('#file').value = '';
  }
}
async function exportFormat(b) {
  if (!state) return;
  b.disabled = true;
  try {
    error(null);
    const f = b.dataset.format;
    const name = safeFileName() + '.' + (f === 'all' ? 'zip' : f);
    const r = await api('/api/export/' + f, state);
    download(await r.blob(), name);
    toast('Скачан файл: ' + name);
  } catch (e) {
    error(e);
  } finally {
    b.disabled = false;
  }
}

/* ---------- События страницы ---------- */
$('#save').onclick = () => {
  if (!state) return;
  const name = safeFileName() + '.json';
  download(new Blob([JSON.stringify({ format: 'structural-scheme', version: 1, ...state }, null, 2)], { type: 'application/json' }), name);
  toast('Скачан файл: ' + name);
};
$('#open').onclick = () => $('#file').click();
$('#file').onchange = () => {
  const file = $('#file').files[0];
  if (file) importFile(file);
};
$('#reset').onclick = async () => {
  if (!confirm('Заменить текущий проект демонстрационным?')) return;
  try {
    const d = await (await api('/api/defaults')).json();
    pushHistory(true);
    state = d.state;
    render();
    error(null);
    changed();
    toast('Проект заменён демонстрационным — «Отменить» вернёт ваши данные');
  } catch (e) {
    error(e);
  }
};
$('#undo').onclick = undo;
$('#redo').onclick = redo;
for (const b of document.querySelectorAll('[data-format]')) b.onclick = () => exportFormat(b);
$('#zoom').onchange = zoom;
window.addEventListener('resize', zoom);
window.addEventListener('dragover', e => {
  e.preventDefault();
  if (e.dataTransfer && [...e.dataTransfer.types].includes('Files')) $('#dropzone').hidden = false;
});
window.addEventListener('dragleave', e => {
  if (!e.relatedTarget) $('#dropzone').hidden = true;
});
window.addEventListener('drop', e => {
  e.preventDefault();
  $('#dropzone').hidden = true;
  const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (file) importFile(file);
});

/* ---------- Запуск ---------- */
(async () => {
  try {
    const [d, p] = await Promise.all([
      api('/api/defaults').then(r => r.json()),
      api('/api/presets').then(r => r.json()).catch(() => ({ presets: [] })),
    ]);
    defaults = d;
    presets = p.presets || [];
    state = defaults.state;
    try {
      const saved = localStorage.getItem(KEY);
      if (saved) state = await (await api('/api/normalize', JSON.parse(saved))).json();
    } catch (e) {
      error(new Error('Сохранённый проект не открыт: ' + e.message));
    }
    renderPresets();
    render();
    preview();
  } catch (e) {
    error(e);
  }
})();
