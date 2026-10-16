'use strict';
const $ = s => document.querySelector(s);
const KEY = 'structural-scheme:project';
const tabs = [['project','Проект'],['op','Операторная'],['srv','Серверная'],['auto','Шкафы автоматики']];
const labels = {title:'Название схемы',subtitle:'Подзаголовок',fileName:'Имя выходных файлов',blocksPerRow:'Блоков в одном ряду',operatorName:'Название операторной',serverName:'Название серверной',autoName:'Помещение шкафов автоматики',showNotes:'Показывать примечания',showSignalCounts:'Показывать количества сигналов',notesText:'Текст примечаний',kvmPanel:'Щит КВМ-удлинителей в операторной',kvmPanelName:'Название щита',name:'Название',type:'Тип',link:'Связь',target:'Куда',kvmToPanel:'KVM → щит',servers:'Серверов',kvm:'KVM',ntp:'NTP',ups:'ИБП',netTarget:'Подключение к',switches:'Коммутаторов',fw:'Межсетевых экранов',cross:'Опт. кроссов',external:'Внешняя связь',ctrls:'Контроллеров',uplink:'Связь сверху',di:'DI',dO:'DO',ai:'AI',ao:'AO',rs485:'RS-485 вниз',rs485Cab:'RS-485 между',rs485Target:'Связать со шкафом',diN:'Количество DI',doN:'Количество DO',aiN:'Количество AI',aoN:'Количество AO'};
let state, defaults, tab='project', timer, revision=0, previewController;
function el(tag, text, cls) {const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n;}
function error(e) {$('#error').hidden=!e; $('#error').textContent=e ? String(e.message||e) : '';}
async function api(url, data, signal) {
  const r=await fetch(url, data===undefined ? {signal} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),signal});
  if(!r.ok) {let msg;try{msg=(await r.json()).detail;}catch{msg=r.statusText;}throw new Error(typeof msg==='string'?msg:JSON.stringify(msg));}
  return r;
}
function persist() {try{localStorage.setItem(KEY,JSON.stringify({format:'structural-scheme',version:1,...state}));}catch(e){error(new Error('Не удалось сохранить в браузере. Скачайте JSON: '+e.message));}}
function changed() {persist();const rev=++revision;clearTimeout(timer);$('#status').textContent='Перестроение…';timer=setTimeout(()=>preview(rev),220);}
async function preview(rev=revision) {previewController?.abort();const controller=new AbortController();previewController=controller;try{const m=await(await api('/api/preview',state,controller.signal)).json();if(rev!==revision)return;$('#preview').innerHTML=m.svg;zoom();const w=m.warnings&&m.warnings.length?' · '+m.warnings.join(' · '):'';$('#status').textContent=`${m.width} × ${m.height} px · Блоков: ${m.blocks} · Связей: ${m.conns}${w}`;$('#status').classList.toggle('warn',Boolean(w));}catch(e){if(e.name==='AbortError')return;/* отменён более новым редактированием */if(rev===revision){error(e);$('#status').textContent='Ошибка построения';}}}
function zoom() {const svg=$('#preview svg');if(!svg)return;const v=$('#zoom').value;const w=Number(svg.getAttribute('width')),h=Number(svg.getAttribute('height'));let scale=v==='fit'?Math.min(1,Math.max(100,$('#preview').clientWidth-48)/w):Number(v);svg.style.width=(w*scale)+'px';svg.style.height=(h*scale)+'px';}
function optionsFor(key,item) {
  if(key==='type')return ['АРМ','Принтер','Панель управления'].map(x=>[x,x]);
  if(key==='link')return ['Витая пара','Оптика','KVM'].map(x=>[x,x]);
  if(key==='uplink')return ['Витая пара','Оптика'].map(x=>[x,x]);
  let a;
  if(key==='target') a=[...state.netCabs,...state.racks,...(state.project.kvmPanel?[{id:'kvmpanel',name:state.project.kvmPanelName}]:[])];
  if(key==='netTarget') a=state.netCabs;
  if(key==='rs485Target') a=state.autoCabs.filter(c=>c.id!==item.id);
  return a ? [[null,'Автоматически'],...a.map(c=>[c.id,c.name])] : null;
}
function field(obj,key,parent,wide=false) {
  const value=obj[key], label=el('label',undefined,'field'+(typeof value==='boolean'?' check':'')+(wide?' wide':'')+(key==='name'?' name':''));
  const opts=optionsFor(key,obj);let input;
  if(opts){input=el('select');if(value && !opts.some(([id])=>id===value))opts.push([value,'Удалён — авто-выбор']);for(const [id,name] of opts){const o=el('option',name);o.value=id===null?'':id;input.append(o);}input.value=value??'';}
  else if(key==='notesText'){input=el('textarea');input.value=value;}
  else {input=el('input');input.type=typeof value==='boolean'?'checkbox':typeof defaults.project[key]==='number'||Object.values(defaults.items).some(d=>typeof d[key]==='number')?'number':'text';if(input.type==='checkbox')input.checked=value;else input.value=value??'';if(input.type==='number'){input.min=key==='blocksPerRow'?'1':'0';if(key==='blocksPerRow')input.max='12';}}
  input.setAttribute('aria-label',labels[key]||key);
  const update=()=>{obj[key]=input.type==='checkbox'?input.checked:opts?(input.value||null):input.value;error(null);changed();if(['kvmPanel','showNotes','showSignalCounts','rs485Cab'].includes(key))render();};
  input.addEventListener(opts||input.type==='checkbox'?'change':'input',update);
  label.append(el('span',labels[key]||key),input);if(input.type==='checkbox')label.prepend(input);parent.append(label);
}
function addItem(key) {
  const n=state[key].length+1, first=state.netCabs[0]?.id??null;
  const it={...defaults.items[key],id:crypto.randomUUID?.()||`${Date.now()}-${Math.random()}`};
  it.name=key==='opItems'?`АРМ оператора №${n}`:key==='racks'?`Серверная стойка №${n}`:key==='netCabs'?`Шкаф сетевой ШС-${String(n).padStart(2,'0')}`:`Шкаф ША-${String(n).padStart(2,'0')}`;
  if(key==='opItems')it.target=first;
  if(['racks','autoCabs'].includes(key))it.netTarget=first;
  if(key==='autoCabs')it.rs485Target=state.autoCabs[0]?.id??null;
  state[key].push(it);changed();render();
}
function group(parent,key,title,button) {
  parent.append(el('h3',title,'group-title'));const list=el('div',undefined,'items');
  for(const item of state[key]) {
    const card=el('div',undefined,'card');
    for(const fieldKey of Object.keys(defaults.items[key])) {
      if(fieldKey==='id')continue;
      if(['diN','doN','aiN','aoN'].includes(fieldKey)&&!state.project.showSignalCounts)continue;
      field(item,fieldKey,card);
    }
    const del=el('button','Удалить','remove');del.onclick=()=>{state[key]=state[key].filter(i=>i!==item);changed();render();};card.append(del);list.append(card);
  }
  parent.append(list);const add=el('button',button,'add');add.onclick=()=>addItem(key);parent.append(add);
}
function render() {
  $('#tabs').replaceChildren();for(const [id,name] of tabs){const b=el('button',name,id===tab?'active':'');b.setAttribute('aria-selected',String(id===tab));b.onclick=()=>{tab=id;render();};$('#tabs').append(b);}
  const root=$('#fields');root.replaceChildren();
  if(tab==='project') {const grid=el('div',undefined,'grid');for(const key of Object.keys(defaults.project)){if(key.startsWith('kvmPanel'))continue;if(key==='notesText'&&!state.project.showNotes)continue;field(state.project,key,grid,key==='notesText');}root.append(grid);}
  if(tab==='op'){const panel=el('div',undefined,'panel');field(state.project,'kvmPanel',panel);if(state.project.kvmPanel)field(state.project,'kvmPanelName',panel);root.append(panel);group(root,'opItems','Операторные станции и устройства','+ Добавить устройство');}
  if(tab==='srv'){group(root,'racks','Серверные стойки','+ Добавить стойку');group(root,'netCabs','Сетевые шкафы','+ Добавить сетевой шкаф');}
  if(tab==='auto')group(root,'autoCabs','Шкафы автоматики','+ Добавить шкаф');
}
function download(blob,name) {const url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('#save').onclick=()=>download(new Blob([JSON.stringify({format:'structural-scheme',version:1,...state},null,2)],{type:'application/json'}),(state.project.fileName||'scheme')+'.json');
$('#open').onclick=()=>$('#file').click();
$('#file').onchange=async()=>{const file=$('#file').files[0];if(!file)return;try{state=await(await api('/api/normalize',JSON.parse((await file.text()).replace(/^\uFEFF/,'')))).json();render();error(null);changed();}catch(e){error(e);}finally{$('#file').value='';}};
$('#reset').onclick=async()=>{if(!confirm('Заменить текущий проект демонстрационным?'))return;try{state=(await(await api('/api/defaults')).json()).state;render();error(null);changed();}catch(e){error(e);}};
for(const b of document.querySelectorAll('[data-format]'))b.onclick=async()=>{b.disabled=true;try{error(null);const f=b.dataset.format,r=await api('/api/export/'+f,state);download(await r.blob(),(state.project.fileName||'scheme').replace(/[^\wа-яА-ЯёЁ-]+/g,'_')+'.'+f);}catch(e){error(e);}finally{b.disabled=false;}};
$('#zoom').onchange=zoom;window.addEventListener('resize',zoom);
(async()=>{try{defaults=await(await api('/api/defaults')).json();state=defaults.state;try{const saved=localStorage.getItem(KEY);if(saved)state=await(await api('/api/normalize',JSON.parse(saved))).json();}catch(e){error(new Error('Сохранённый проект не открыт: '+e.message));}render();preview();}catch(e){error(e);}})();
