/*
 * Интерфейс генератора структурных схем.
 *
 * React 18 без сборки: разметка пишется на htm (tagged templates), а не на JSX,
 * поэтому Babel в браузере не нужен. Вся геометрия и рендер схемы — в src/core.js.
 */
(function () {
  'use strict';
  const { useState, useEffect, useMemo, useRef } = React;
  const html = htm.bind(React.createElement);
  const C = window.SchemeCore;

  // ---------- Состояние проекта ----------
  function loadInitialState() {
    try {
      const saved = window.localStorage.getItem(C.STORAGE_KEY);
      if (saved) return C.parseState(saved);
    } catch (e) {
      console.warn('Не удалось восстановить сохранённый проект:', e);
    }
    return C.createDefaultState();
  }

  function saveToStorage(state) {
    try {
      window.localStorage.setItem(C.STORAGE_KEY, C.serializeState(state));
    } catch (e) {
      console.warn('Не удалось сохранить проект в браузере:', e);
    }
  }

  function download(blob, name) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // ---------- UI-атомы ----------
  const Inp = (p) => html`<input ...${p} className=${'border border-gray-300 rounded px-2 py-1 text-sm w-full ' + (p.className || '')} />`;
  const Num = (p) => html`<input type="number" min="0" ...${p} className="border border-gray-300 rounded px-2 py-1 text-sm w-16" />`;
  const Sel = ({ className, children, ...p }) =>
    html`<select ...${p} className=${'border border-gray-300 rounded px-2 py-1 text-sm ' + (className || 'w-full')}>${children}</select>`;
  const Chk = ({ checked, onChange, ...p }) =>
    html`<input ...${p} type="checkbox" checked=${!!checked} onChange=${onChange} className="w-4 h-4 accent-blue-600" />`;
  const Lbl = ({ children }) => html`<label className="block text-xs font-medium text-gray-600 mb-1">${children}</label>`;
  const AddBtn = ({ onClick, children }) =>
    html`<button onClick=${onClick} className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 mt-2">＋ ${children}</button>`;
  const DelBtn = ({ onClick }) =>
    html`<button onClick=${onClick} title="Удалить" className="text-red-500 hover:text-red-700 px-2 font-bold">✕</button>`;
  const Dash = () => html`<span className="text-gray-300 text-xs">—</span>`;
  const options = (list) => list.map(v => html`<option key=${v}>${v}</option>`);

  const BTN = 'px-3 py-1.5 text-sm text-white rounded ';
  const BTN_EXPORT = BTN + 'bg-emerald-600 hover:bg-emerald-700';
  const BTN_DRAWIO = BTN + 'bg-indigo-600 hover:bg-indigo-700';
  const BTN_FILE = 'px-3 py-1.5 text-sm rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50';

  const TABS = [['project', 'Проект'], ['op', 'Операторная'], ['srv', 'Серверная'], ['auto', 'Шкафы автоматики']];

  function SchemeGenerator() {
    const [tab, setTab] = useState('project');
    const [state, setState] = useState(loadInitialState);
    const fileInput = useRef(null);
    const { project, opItems, racks, netCabs, autoCabs } = state;

    useEffect(() => { saveToStorage(state); }, [state]);

    const model = useMemo(() => C.buildScheme(state), [state]);
    const svg = useMemo(() => C.toSvg(model), [model]);
    const { effTarget, effNet, effAutoTarget } = C.makeResolvers(state);

    // ---------- Изменение состояния ----------
    const setProject = (patch) => setState(s => ({ ...s, project: { ...s.project, ...patch } }));
    const bindText = (field) => ({ value: project[field], onChange: e => setProject({ [field]: e.target.value }) });
    const bindCheck = (field) => ({ checked: project[field], onChange: e => setProject({ [field]: e.target.checked }) });
    const upd = (key) => (id, field, value) =>
      setState(s => ({ ...s, [key]: s[key].map(x => x.id === id ? { ...x, [field]: value } : x) }));
    const del = (key) => (id) => setState(s => ({ ...s, [key]: s[key].filter(x => x.id !== id) }));
    const add = (key, factory) => () => setState(s => ({ ...s, [key]: [...s[key], factory(s)] }));
    const updOp = upd('opItems'), updRack = upd('racks'), updNet = upd('netCabs'), updAuto = upd('autoCabs');

    // ---------- Экспорт ----------
    const fname = model.fileName;
    const exportSvg = () => download(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }), fname + '.svg');
    const exportRaster = (type) => {
      const ext = type === 'image/jpeg' ? '.jpg' : '.png';
      const fail = (why) => alert('Не удалось сохранить ' + ext.slice(1).toUpperCase() + ': ' + why + ' Попробуйте экспорт в SVG.');
      const img = new Image();
      img.onload = () => {
        const scale = C.rasterScale(model.width, model.height);
        const c = document.createElement('canvas');
        c.width = Math.round(model.width * scale); c.height = Math.round(model.height * scale);
        const ctx = c.getContext('2d');
        ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, c.width, c.height);
        ctx.drawImage(img, 0, 0, c.width, c.height);
        const done = (blob) => blob
          ? download(blob, fname + ext)
          : fail('браузер не справился с размером листа.');
        try { c.toBlob(done, type, 0.95); }
        catch (err) { fail(err.message + '.'); }
      };
      img.onerror = () => fail('браузер не смог разобрать схему.');
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    };
    const exportDrawio = () => download(new Blob([C.toDrawio(model)], { type: 'application/xml' }), fname + '.drawio');

    // ---------- Файл проекта ----------
    const saveProject = () => download(new Blob([C.serializeState(state)], { type: 'application/json' }), fname + '.json');
    const openProject = (e) => {
      const file = e.target.files && e.target.files[0];
      e.target.value = '';
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try { setState(C.parseState(String(reader.result))); }
        catch (err) { alert('Не удалось открыть проект: ' + err.message); }
      };
      reader.readAsText(file);
    };
    const resetProject = () => {
      if (confirm('Заменить текущий проект демонстрационным примером? Несохранённые в файл изменения будут потеряны.')) {
        setState(C.createDefaultState());
      }
    };

    // ---------- Выбор целей ----------
    const targetSelect = (value, onChange, allowPanel) => html`
      <${Sel} value=${value || ''} onChange=${onChange}>
        ${netCabs.map(c => html`<option key=${c.id} value=${c.id}>${c.name}</option>`)}
        ${racks.map(r => html`<option key=${r.id} value=${r.id}>${r.name}</option>`)}
        ${allowPanel && project.kvmPanel && html`<option value=${C.KVM_PANEL_ID}>${project.kvmPanelName}</option>`}
      <//>`;
    const netSelect = (value, onChange) => html`
      <${Sel} value=${value || ''} onChange=${onChange}>
        ${netCabs.map(c => html`<option key=${c.id} value=${c.id}>${c.name}</option>`)}
      <//>`;
    const autoTargetSelect = (sourceId, value, onChange) => html`
      <${Sel} value=${effAutoTarget(value, sourceId) || ''} onChange=${onChange}>
        ${autoCabs.filter(c => c.id !== sourceId).map(c => html`<option key=${c.id} value=${c.id}>${c.name}</option>`)}
      <//>`;

    // ---------- Вкладки ----------
    const projectTab = () => html`
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2 p-3 bg-gray-50 rounded border border-gray-200">
          <span className="text-sm font-medium mr-2">Файл проекта:</span>
          <button onClick=${saveProject} className=${BTN_FILE}>Сохранить проект</button>
          <button onClick=${() => fileInput.current && fileInput.current.click()} className=${BTN_FILE}>Открыть проект</button>
          <button onClick=${resetProject} className=${BTN_FILE}>Начать заново</button>
          <input ref=${fileInput} type="file" accept=".json,application/json" className="hidden" onChange=${openProject} data-testid="project-file" />
          <span className="text-xs text-gray-500">Изменения автоматически сохраняются в этом браузере.</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div><${Lbl}>Название схемы<//><${Inp} ...${bindText('title')} /></div>
          <div><${Lbl}>Подзаголовок<//><${Inp} ...${bindText('subtitle')} /></div>
          <div><${Lbl}>Имя выходных файлов<//><${Inp} ...${bindText('fileName')} /></div>
          <div><${Lbl}>Блоков в одном ряду<//><${Num} ...${bindText('blocksPerRow')} min="1" /></div>
          <div><${Lbl}>Название операторной<//><${Inp} ...${bindText('operatorName')} /></div>
          <div><${Lbl}>Название серверной<//><${Inp} ...${bindText('serverName')} /></div>
          <div><${Lbl}>Название помещения шкафов автоматики<//><${Inp} ...${bindText('autoName')} /></div>
          <div className="flex items-center gap-6 pt-4">
            <label className="flex items-center gap-2 text-sm"><${Chk} ...${bindCheck('showNotes')} />Показывать примечания</label>
            <label className="flex items-center gap-2 text-sm"><${Chk} ...${bindCheck('showSignalCounts')} />Показывать количества сигналов</label>
          </div>
          ${project.showNotes && html`
            <div className="md:col-span-2"><${Lbl}>Текст примечаний<//>
              <textarea ...${bindText('notesText')} className="border border-gray-300 rounded px-2 py-1 text-sm w-full h-20" />
            </div>`}
        </div>
      </div>`;

    const opTab = () => html`
      <div>
        <div className="flex flex-wrap items-center gap-4 mb-4 p-3 bg-gray-50 rounded border border-gray-200">
          <label className="flex items-center gap-2 text-sm font-medium">
            <${Chk} ...${bindCheck('kvmPanel')} />
            Щит КВМ-удлинителей в операторной
          </label>
          ${project.kvmPanel && html`
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Название:</span>
              <${Inp} className="w-64" ...${bindText('kvmPanelName')} />
            </div>`}
        </div>
        <div className="grid grid-cols-12 gap-2 text-xs font-semibold text-gray-500 mb-1 px-1">
          <div className="col-span-3">Название</div><div className="col-span-2">Тип</div>
          <div className="col-span-2">Связь</div><div className="col-span-3">Куда</div>
          <div>KVM→щит</div><div></div>
        </div>
        ${opItems.map(it => html`
          <div key=${it.id} className="grid grid-cols-12 gap-2 items-center mb-1">
            <div className="col-span-3"><${Inp} value=${it.name} onChange=${e => updOp(it.id, 'name', e.target.value)} /></div>
            <div className="col-span-2">
              <${Sel} value=${it.type} onChange=${e => updOp(it.id, 'type', e.target.value)}>${options(C.OP_TYPES)}<//>
            </div>
            <div className="col-span-2">
              <${Sel} value=${it.link} onChange=${e => updOp(it.id, 'link', e.target.value)}>${options(C.OP_LINKS)}<//>
            </div>
            <div className="col-span-3">
              ${targetSelect(effTarget(it.target, true), e => updOp(it.id, 'target', e.target.value), true)}
            </div>
            <div>
              ${project.kvmPanel && effTarget(it.target, true) !== C.KVM_PANEL_ID
                ? html`<${Chk} checked=${it.kvmToPanel} onChange=${e => updOp(it.id, 'kvmToPanel', e.target.checked)} />`
                : html`<${Dash} />`}
            </div>
            <${DelBtn} onClick=${() => del('opItems')(it.id)} />
          </div>`)}
        <${AddBtn} onClick=${add('opItems', C.newOpItem)}>Добавить<//>
      </div>`;

    const srvTab = () => html`
      <div className="space-y-6">
        <div>
          <h3 className="font-semibold text-sm mb-2">Серверные стойки</h3>
          <div className="grid grid-cols-12 gap-2 text-xs font-semibold text-gray-500 mb-1 px-1">
            <div className="col-span-4">Название</div><div>Серверов</div><div className="col-span-3">Подключение к</div>
            <div>KVM</div><div>NTP</div><div>ИБП</div><div></div>
          </div>
          ${racks.map(r => html`
            <div key=${r.id} className="grid grid-cols-12 gap-2 items-center mb-1">
              <div className="col-span-4"><${Inp} value=${r.name} onChange=${e => updRack(r.id, 'name', e.target.value)} /></div>
              <div><${Num} value=${r.servers} onChange=${e => updRack(r.id, 'servers', Number(e.target.value))} /></div>
              <div className="col-span-3">${netSelect(effNet(r.netTarget), e => updRack(r.id, 'netTarget', e.target.value))}</div>
              <div><${Chk} checked=${r.kvm} title="Стойка подключается к щиту КВМ-удлинителей (вкладка «Операторная»)"
                onChange=${e => updRack(r.id, 'kvm', e.target.checked)} /></div>
              <div><${Chk} checked=${r.ntp} onChange=${e => updRack(r.id, 'ntp', e.target.checked)} /></div>
              <div><${Chk} checked=${r.ups} onChange=${e => updRack(r.id, 'ups', e.target.checked)} /></div>
              <${DelBtn} onClick=${() => del('racks')(r.id)} />
            </div>`)}
          ${!project.kvmPanel && racks.some(r => r.kvm) && html`
            <p className="text-xs text-amber-700 mt-1">Линия KVM от стойки строится только при включённом «Щите КВМ-удлинителей» — включите его на вкладке «Операторная».</p>`}
          <${AddBtn} onClick=${add('racks', C.newRack)}>Добавить стойку<//>
        </div>
        <div>
          <h3 className="font-semibold text-sm mb-2">Сетевые шкафы</h3>
          <div className="grid grid-cols-12 gap-2 text-xs font-semibold text-gray-500 mb-1 px-1">
            <div className="col-span-4">Название</div><div>Комм.</div><div>МЭ</div><div className="col-span-2">Опт. кроссы</div>
            <div className="col-span-2">Внешняя связь</div><div>ИБП</div><div></div>
          </div>
          ${netCabs.map(c => html`
            <div key=${c.id} className="grid grid-cols-12 gap-2 items-center mb-1">
              <div className="col-span-4"><${Inp} value=${c.name} onChange=${e => updNet(c.id, 'name', e.target.value)} /></div>
              <div><${Num} value=${c.switches} onChange=${e => updNet(c.id, 'switches', Number(e.target.value))} /></div>
              <div><${Num} value=${c.fw} onChange=${e => updNet(c.id, 'fw', Number(e.target.value))} /></div>
              <div className="col-span-2"><${Num} value=${c.cross} onChange=${e => updNet(c.id, 'cross', Number(e.target.value))} /></div>
              <div className="col-span-2"><${Chk} checked=${c.external} onChange=${e => updNet(c.id, 'external', e.target.checked)} /></div>
              <div><${Chk} checked=${c.ups} onChange=${e => updNet(c.id, 'ups', e.target.checked)} /></div>
              <${DelBtn} onClick=${() => del('netCabs')(c.id)} />
            </div>`)}
          <${AddBtn} onClick=${add('netCabs', C.newNetCab)}>Добавить сетевой шкаф<//>
        </div>
      </div>`;

    const SIGNAL_FIELDS = [['di', 'diN'], ['dO', 'doN'], ['ai', 'aiN'], ['ao', 'aoN']];
    const autoTab = () => html`
      <div className="overflow-x-auto">
        <div className="flex items-center gap-2 text-xs font-semibold text-gray-500 mb-1 px-1">
          <div className="w-40 shrink-0">Название</div><div className="w-16 shrink-0">Контр.</div>
          <div className="w-28 shrink-0">Связь сверху</div><div className="w-44 shrink-0">Куда</div>
          <div className="w-8 shrink-0">DI</div><div className="w-8 shrink-0">DO</div>
          <div className="w-8 shrink-0">AI</div><div className="w-8 shrink-0">AO</div>
          <div className="w-16 shrink-0">RS-485 вниз</div>
          <div className="w-24 shrink-0">RS-485 между</div><div className="w-44 shrink-0">Связать со шкафом</div><div></div>
        </div>
        ${autoCabs.map(c => html`
          <div key=${c.id} className="flex items-start gap-2 mb-1">
            <div className="w-40 shrink-0"><${Inp} value=${c.name} onChange=${e => updAuto(c.id, 'name', e.target.value)} /></div>
            <div className="w-16 shrink-0"><${Num} value=${c.ctrls} onChange=${e => updAuto(c.id, 'ctrls', Number(e.target.value))} /></div>
            <div className="w-28 shrink-0">
              <${Sel} value=${c.uplink} onChange=${e => updAuto(c.id, 'uplink', e.target.value)}>${options(C.AUTO_UPLINKS)}<//>
            </div>
            <div className="w-44 shrink-0">${netSelect(effNet(c.netTarget), e => updAuto(c.id, 'netTarget', e.target.value))}</div>
            ${SIGNAL_FIELDS.map(([f, nf]) => html`
              <div key=${f} className="w-8 shrink-0 flex flex-col items-start gap-1 pt-1">
                <${Chk} checked=${c[f]} onChange=${e => updAuto(c.id, f, e.target.checked)} />
                ${project.showSignalCounts && c[f] && html`
                  <input type="number" min="0" value=${c[nf]} onChange=${e => updAuto(c.id, nf, Number(e.target.value))}
                    className="border border-gray-300 rounded px-1 py-0.5 text-xs w-12" />`}
              </div>`)}
            <div className="w-16 shrink-0 pt-1"><${Chk} checked=${c.rs485} onChange=${e => updAuto(c.id, 'rs485', e.target.checked)} /></div>
            <div className="w-24 shrink-0 pt-1">
              <${Chk} checked=${c.rs485Cab} disabled=${autoCabs.length < 2} onChange=${e => updAuto(c.id, 'rs485Cab', e.target.checked)} />
            </div>
            <div className="w-44 shrink-0">
              ${c.rs485Cab && autoCabs.length > 1
                ? autoTargetSelect(c.id, c.rs485Target, e => updAuto(c.id, 'rs485Target', e.target.value))
                : html`<${Dash} />`}
            </div>
            <${DelBtn} onClick=${() => del('autoCabs')(c.id)} />
          </div>`)}
        <${AddBtn} onClick=${add('autoCabs', C.newAutoCab)}>Добавить шкаф<//>
      </div>`;

    const TAB_VIEWS = { project: projectTab, op: opTab, srv: srvTab, auto: autoTab };

    return html`
      <div className="p-4 bg-gray-100 min-h-screen font-sans">
        <div className="max-w-6xl mx-auto space-y-4">
          <div className="bg-white rounded-lg shadow p-4">
            <div className="flex flex-wrap gap-2 border-b border-gray-200 pb-2 mb-4">
              ${TABS.map(([k, l]) => html`
                <button key=${k} onClick=${() => setTab(k)}
                  className=${'px-3 py-1.5 rounded-t text-sm font-medium ' + (tab === k ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200')}>
                  ${l}
                </button>`)}
              <div className="flex-1" />
              <button onClick=${exportSvg} className=${BTN_EXPORT}>⬇ SVG</button>
              <button onClick=${() => exportRaster('image/png')} className=${BTN_EXPORT}>⬇ PNG</button>
              <button onClick=${() => exportRaster('image/jpeg')} className=${BTN_EXPORT}>⬇ JPG</button>
              <button onClick=${exportDrawio} className=${BTN_DRAWIO}>⬇ Draw.io</button>
            </div>
            ${TAB_VIEWS[tab]()}
          </div>

          <div className="bg-white rounded-lg shadow p-4 overflow-auto" data-testid="preview"
            dangerouslySetInnerHTML=${{ __html: svg }} />
        </div>
      </div>`;
  }

  ReactDOM.createRoot(document.getElementById('root')).render(html`<${SchemeGenerator} />`);
})();
