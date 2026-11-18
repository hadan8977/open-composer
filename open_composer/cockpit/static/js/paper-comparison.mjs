// One presentation/calculation module for the native and React workspaces.
const finite = value => typeof value === 'number' && Number.isFinite(value);
const mean = values => values.length && values.every(finite) ? values.reduce((a, b) => a + b, 0) / values.length : null;
export function calculateComparison(payload, selectedIds) {
  const ids = new Set(selectedIds);
  const selected = payload.strategies.filter(s => ids.has(s.id) && s.selectable);
  const capital = payload.initial_capital_usd || 100000;
  const first = selected.map(s => s.start_day).filter(Boolean).sort()[0];
  const maps = selected.map(s => new Map(s.points.map(p => [p.day, p])));
  const days = first ? payload.days.filter(day => day >= first) : [];
  let previous = null;
  const series = days.map(day => {
    const values = selected.map((s, i) => day < s.start_day ? 0 : maps[i].get(day)?.return_pct ?? null);
    const percent = mean(values);
    const equity = percent === null ? null : capital * (1 + percent / 100);
    const daily = equity !== null && previous !== null && previous > 0 ? (equity / previous - 1) * 100 : null;
    const point = {day, return_pct:percent, equity_usd:equity, pnl_usd:percent === null ? null : capital * percent / 100, daily_pct:daily, values};
    previous = equity;
    return point;
  });
  const percent = mean(selected.map(s => s.latest_return_pct));
  return {selected, series, latest:{return_pct:percent, equity_usd:percent === null ? null : capital * (1 + percent / 100), pnl_usd:percent === null ? null : capital * percent / 100, daily_pct:null}};
}
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = value => finite(value) ? `${value > 0 ? '+' : ''}${value.toFixed(2)}%` : '—';
const money = value => finite(value) ? `${value < 0 ? '-' : ''}$${Math.abs(value).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}` : '—';
const tone = value => !finite(value) || value === 0 ? '' : value > 0 ? 'pc-up' : 'pc-down';
const utc = value => { const date = new Date(value); return Number.isNaN(date.getTime()) ? '暂无估值' : `${date.toISOString().slice(5,16).replace('T',' ')} UTC`; };
const PREF_KEY = 'oc-paper-comparison-v1';

export function mountPaperComparison(element, initialPayload) {
  let payload = initialPayload, mode = 'return', range = 'all', query = '', pinnedDay = null, hoverDay = null;
  let preference = null;
  try { preference = JSON.parse(localStorage.getItem(PREF_KEY)); } catch (_) { /* private browsing */ }
  let custom = Array.isArray(preference?.selected);
  let selected = new Set(custom ? preference.selected : payload.strategies.filter(s => s.default_selected).map(s => s.id));
  if (['return','equity','daily'].includes(preference?.mode)) mode = preference.mode;
  let calculated, shown, destroyed = false;
  let compact = element.clientWidth < 600;
  element.classList.add('pc-workspace');
  function save() { try { localStorage.setItem(PREF_KEY, JSON.stringify({selected:[...selected],mode})); } catch (_) { /* memory state still works */ } }
  function focusControl(action, id) {
    const control = [...element.querySelectorAll('[data-pc-action]')].find(b => b.dataset.pcAction === action && (!id || b.dataset.id === id));
    control?.focus({preventScroll:true});
  }
  function render() {
    if (destroyed) return;
    const eligible = new Set(payload.strategies.filter(s => s.selectable).map(s => s.id));
    selected = new Set([...selected].filter(id => eligible.has(id)));
    calculated = calculateComparison(payload, selected);
    shown = range === 'all' ? calculated.series : calculated.series.slice(-Number(range));
    if (pinnedDay && !shown.some(p => p.day === pinnedDay)) pinnedDay = null;
    hoverDay = null;
    const n = calculated.selected.length;
    element.innerHTML = `
      <section class="pc-panel pc-hero" aria-label="等权组合">
        <header class="pc-heading"><span>等权组合 <small data-pc-count>${n} 个策略</small></span><span data-pc-date>${escape(utc(payload.snapshot_at))}</span></header>
        <div class="pc-readings"><div class="pc-primary"><span class="pc-caption">累计收益率</span><strong data-pc-return></strong></div><div><span class="pc-caption">100k 参考净值</span><strong data-pc-equity></strong></div><div class="pc-extra"><span class="pc-caption" data-pc-extra-label>参考盈亏</span><strong data-pc-extra></strong></div></div>
        <div class="pc-chart-toolbar"><div class="pc-segment" role="group" aria-label="图表显示">${[['return','收益率'],['equity','100k 净值'],['daily','每日涨跌']].map(([value,label])=>`<button type="button" data-pc-action="mode" data-id="${value}" aria-pressed="${mode===value}">${label}</button>`).join('')}</div><div class="pc-ranges" role="group" aria-label="日期范围">${[['all','全部'],['20','20日'],['5','5日']].map(([value,label])=>`<button type="button" data-pc-action="range" data-id="${value}" aria-pressed="${range===value}">${label}</button>`).join('')}</div></div>
        <div class="pc-chart-well">${chartMarkup()}</div>
        <div class="pc-date-controls"><span data-pc-day-label>${escape(shown.at(-1)?.day || '—')}</span><input type="range" min="0" max="${Math.max(0,shown.length-1)}" value="${Math.max(0,shown.length-1)}" step="1" aria-label="查看交易日" data-pc-slider ${shown.length?'':'disabled'}><button type="button" data-pc-action="latest">最新快照</button></div>
        <div class="pc-day-status" data-pc-day-status aria-live="polite"></div>
      </section>
      <section class="pc-strategies" aria-label="选择策略"><header class="pc-selection-heading"><h2>策略 <span>${payload.strategies.length}</span></h2><div><button type="button" data-pc-action="all">全选</button><button type="button" data-pc-action="none">清空</button><a href="/paper/accounts">账户 ↗</a></div></header><div class="pc-panel pc-list"><div class="pc-row pc-table-head"><span>策略</span><span>累计</span><span>当日</span><span></span><span></span></div>${payload.strategies.map(s=>`<div class="pc-row${s.selectable?'':' pc-unavailable'}" data-pc-row="${escape(s.id)}"><label class="pc-name"><input type="checkbox" data-pc-action="toggle" data-id="${escape(s.id)}" aria-label="纳入 ${escape(s.label)}" ${selected.has(s.id)?'checked':''} ${s.selectable?'':'disabled'}><span>${escape(s.label)}${s.selectable?'':'<small>收益率待补</small>'}</span></label><span class="pc-percent" data-pc-row-return></span><span class="pc-day-return" data-pc-row-daily>—</span><button type="button" data-pc-action="solo" data-id="${escape(s.id)}" ${s.selectable?'':'disabled'}>只看</button><a href="${escape(s.href)}" data-detail aria-label="${escape(s.label)} 详情">↗</a></div>`).join('')}</div><p class="pc-empty-filter" hidden>没有匹配的策略</p></section>`;
    readout(); filter();
  }
  function chartMarkup() {
    if (!calculated.selected.length) return '<div class="pc-empty">选择策略，查看组合表现</div>';
    if (!shown.length) return '<div class="pc-empty">暂无每日收益记录</div>';
    const key = mode === 'return' ? 'return_pct' : mode === 'equity' ? 'equity_usd' : 'daily_pct';
    const base = mode === 'equity' ? (payload.initial_capital_usd || 100000) : 0;
    const vals = shown.map(p=>p[key]).filter(finite);
    if (!vals.length) return '<div class="pc-empty">所选策略缺少同日收益记录</div>';
    const low=Math.min(base,...vals), high=Math.max(base,...vals), padding=(high-low || (mode==='equity'?100:1))*.15;
    const bottom=low-padding, top=high+padding;
    const height=compact?520:240;
    const floor=height-35;
    const y=v=> floor-(v-bottom)/(top-bottom)*(floor-20);
    const x=i=> 20+i/Math.max(1,shown.length-1)*870;
    let segments=[], current=[];
    shown.forEach((p,i)=>{ if(finite(p[key])) current.push([x(i),y(p[key])]); else if(current.length){segments.push(current);current=[];} });
    if(current.length) segments.push(current);
    const color=tone(shown.findLast(p=>finite(p[key]))?.[key]-(mode==='equity'?base:0));
    const ticks=[high,(high+low)/2,low];
    const grid=ticks.map(v=>`<line x1="20" x2="890" y1="${y(v)}" y2="${y(v)}" class="pc-grid"/><text x="905" y="${y(v)+4}" class="pc-y-label">${mode==='equity'?`$${(v/1000).toFixed(1)}k`:pct(v)}</text>`).join('');
    let graphic;
    if(mode==='daily') graphic=shown.map((p,i)=>finite(p[key])?`<rect x="${x(i)-Math.min(9,300/shown.length)}" y="${Math.min(y(0),y(p[key]))}" width="${Math.min(18,600/shown.length)}" height="${Math.max(1,Math.abs(y(p[key])-y(0)))}" rx="2" class="${tone(p[key])} pc-daily-bar"/>`:'').join('');
    else graphic=segments.map(points=>{const d=points.map(([a,b],i)=>`${i?'L':'M'}${a},${b}`).join(' ');return `<path d="${d} L${points.at(-1)[0]},${y(base)} L${points[0][0]},${y(base)} Z" class="pc-area ${color}"/><path d="${d}" class="pc-line ${color}"/>${points.length===1?`<circle cx="${points[0][0]}" cy="${points[0][1]}" r="3" class="pc-daily-bar ${color}"/>`:''}`;}).join('');
    const gaps=shown.map((p,i)=>!finite(p[key])?`<circle cx="${x(i)}" cy="${height-27}" r="2.4" class="pc-gap"/>`:'').join('');
    return `<svg viewBox="0 0 1000 ${height}" class="pc-chart${compact?' pc-compact':''}" role="img" aria-label="${mode==='return'?'等权累计收益率':mode==='equity'?'100k 参考净值':'每日涨跌'}">${grid}${graphic}${gaps}<line data-pc-cursor x1="20" x2="20" y1="10" y2="${height-25}" class="pc-cursor" visibility="hidden"/><text x="20" y="${height-5}" class="pc-x-label">${shown[0].day}</text><text x="890" y="${height-5}" text-anchor="end" class="pc-x-label">${shown.at(-1).day}</text><rect x="0" y="0" width="900" height="${height-20}" fill="transparent" data-pc-plot/></svg>`;
  }
  function readout() {
    const day=hoverDay || pinnedDay;
    const point=day?calculated.series.find(p=>p.day===day):calculated.latest;
    const current=point || calculated.latest;
    const ret=element.querySelector('[data-pc-return]'); ret.textContent=pct(current.return_pct);ret.className=tone(current.return_pct);
    element.querySelector('[data-pc-equity]').textContent=money(current.equity_usd);
    element.querySelector('[data-pc-extra-label]').textContent=day?'当日涨跌':'参考盈亏';
    const extra=element.querySelector('[data-pc-extra]');extra.textContent=day?pct(current.daily_pct):money(current.pnl_usd);extra.className=tone(day?current.daily_pct:current.pnl_usd);
    element.querySelector('[data-pc-date]').textContent=day || utc(payload.snapshot_at);
    element.querySelector('[data-pc-day-label]').textContent=day || shown.at(-1)?.day || '—';
    element.querySelector('[data-pc-day-status]').textContent=!calculated.selected.length?'':current.return_pct===null?(day?`${day} · 所选策略缺少估值`:'所选策略收益率待补'):!day&&shown.at(-1)?.return_pct===null?`${shown.at(-1).day} 缺少估值`:'';
    const cursor=element.querySelector('[data-pc-cursor]');
    if(cursor){const i=shown.findIndex(p=>p.day===day);cursor.setAttribute('visibility',i<0?'hidden':'visible');if(i>=0){const x=20+i/Math.max(1,shown.length-1)*870;cursor.setAttribute('x1',x);cursor.setAttribute('x2',x);element.querySelector('[data-pc-slider]').value=String(i);}}
    element.querySelectorAll('[data-pc-row]').forEach(row=>{
      const s=payload.strategies.find(s=>s.id===row.dataset.pcRow);
      const i=payload.days.indexOf(day);
      const p=day?s.points.find(p=>p.day===day):null;
      const value=day?(day<s.start_day?0:p?.return_pct??null):s.latest_return_pct;
      const prev=i>0?s.points.find(p=>p.day===payload.days[i-1]):null;
      const prevValue=i>0&&payload.days[i-1]<s.start_day?0:prev?.return_pct;
      const daily=finite(value)&&finite(prevValue)&&prevValue>-100?((1+value/100)/(1+prevValue/100)-1)*100:null;
      const r=row.querySelector('[data-pc-row-return]');r.textContent=pct(value);r.className=`pc-percent ${tone(value)}`;
      const d=row.querySelector('[data-pc-row-daily]');d.textContent=pct(day?daily:null);d.className=`pc-day-return ${tone(day?daily:null)}`;
      row.classList.toggle('pc-selected',selected.has(s.id));
    });
  }
  function filter(){element.querySelectorAll('[data-pc-row]').forEach(row=>{const s=payload.strategies.find(s=>s.id===row.dataset.pcRow);row.hidden=!!query&&!`${s.id} ${s.label}`.toLowerCase().includes(query);});element.querySelector('.pc-empty-filter').hidden=!query||!!element.querySelector('[data-pc-row]:not([hidden])');}
  function click(event){const button=event.target.closest('[data-pc-action]');if(!button||button.disabled)return;const {pcAction:action,id}=button.dataset;
    if(action==='toggle') return; // Native change event carries the checkbox's intended state.
    if(action==='mode'){mode=id;save();}
    if(action==='range')range=id;
    if(action==='all'){selected=new Set(payload.strategies.filter(s=>s.selectable).map(s=>s.id));custom=true;save();}
    if(action==='none'){selected.clear();custom=true;save();}
    if(action==='solo'){selected=new Set([id]);custom=true;save();}
    if(action==='latest'){pinnedDay=null;hoverDay=null;}
    render();focusControl(action,id);
  }
  function change(event){const control=event.target;if(control.dataset.pcAction!=='toggle')return;control.checked?selected.add(control.dataset.id):selected.delete(control.dataset.id);custom=true;save();render();focusControl('toggle',control.dataset.id);}
  function input(event){if(!event.target.matches('[data-pc-slider]'))return;pinnedDay=shown[Number(event.target.value)]?.day||null;hoverDay=null;readout();}
  function plotDay(event){const svg=event.target.closest('.pc-chart');if(!svg||!shown.length)return null;const box=svg.getBoundingClientRect();const px=(event.clientX-box.left)/box.width*1000;return shown[Math.max(0,Math.min(shown.length-1,Math.round((px-20)/870*(shown.length-1))))]?.day;}
  function pointer(event){if(!event.target.matches('[data-pc-plot]'))return;hoverDay=plotDay(event);if(event.type==='pointerdown'){pinnedDay=hoverDay;event.target.setPointerCapture?.(event.pointerId);}if(event.buttons===1)pinnedDay=hoverDay;readout();}
  function leave(event){if(!event.target.matches('[data-pc-plot]'))return;hoverDay=null;readout();}
  element.addEventListener('click',click);element.addEventListener('change',change);element.addEventListener('input',input);element.addEventListener('pointermove',pointer);element.addEventListener('pointerdown',pointer);element.addEventListener('pointerout',leave);
  render();
  const resize = new ResizeObserver(() => {const next=element.clientWidth<600;if(next!==compact){compact=next;render();}});
  resize.observe(element);
  return {update(next){const active=element.contains(document.activeElement)?document.activeElement:null;const action=active?.dataset.pcAction,id=active?.dataset.id;const slider=active?.matches('[data-pc-slider]');payload=next;if(!custom)selected=new Set(payload.strategies.filter(s=>s.default_selected).map(s=>s.id));render();if(action)focusControl(action,id);else if(slider)element.querySelector('[data-pc-slider]')?.focus({preventScroll:true});},setFilter(value){query=String(value).trim().toLowerCase();filter();},destroy(){destroyed=true;resize.disconnect();element.removeEventListener('click',click);element.removeEventListener('change',change);element.removeEventListener('input',input);element.removeEventListener('pointermove',pointer);element.removeEventListener('pointerdown',pointer);element.removeEventListener('pointerout',leave);element.innerHTML='';}};
}

// Native page navigation replaces its content in place. React mounts explicitly.
if(typeof window!=='undefined'){
 let instance=null,host=null;
 function boot(){const next=document.querySelector('[data-native-comparison]');if(next===host)return;if(instance)instance.destroy();host=next;instance=null;if(!next)return;const data=next.querySelector('script[type="application/json"]');const root=next.querySelector('[data-comparison-root]');if(data&&root){try{instance=mountPaperComparison(root,JSON.parse(data.textContent));}catch(_){root.textContent='收益数据暂不可用';}}}
 window.addEventListener('cockpit:content',boot);
 window.addEventListener('cockpit:filter',event=>instance?.setFilter(event.detail));
 window.addEventListener('cockpit:comparison',event=>instance?.update(event.detail));
 boot();
}
