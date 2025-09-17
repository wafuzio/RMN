(function(){
  const el = s => document.querySelector(s);
  const els = s => Array.from(document.querySelectorAll(s));

  async function fetchJSON(url){ const r = await fetch(url); if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); }

  function pairwise(arr){ const out=[]; for(let i=0;i<arr.length;i+=2){ out.push(arr.slice(i,i+2)); } return out; }

  // Global aggregation state (by display date)
  const aggState = {
    map: new Map(), // date => { date, week, ads: [] }
    order: [] // first-seen order (for stability)
  };

  function resetAgg(){ aggState.map.clear(); aggState.order.length = 0; }

  function mergeUniqueAds(existing, incoming){
    const out = existing.slice();
    const seen = new Set(out.map(a => (a.image_url||'') + '|' + (a.message||'')));
    for(const ad of incoming){
      const k = (ad.image_url||'') + '|' + (ad.message||'');
      if(!seen.has(k)){ seen.add(k); out.push(ad); }
    }
    return out;
  }

  function ingestSchedule(items){
    (items||[]).forEach(item => {
      const key = (item.date||'').trim() || 'Unknown';
      if(!aggState.map.has(key)){
        aggState.order.push(key);
        aggState.map.set(key, { date: key, week: item.week || '', ads: (item.ads||[]).slice() });
      } else {
        const cur = aggState.map.get(key);
        cur.week = cur.week || item.week || '';
        cur.ads = mergeUniqueAds(cur.ads, item.ads||[]);
      }
    });
  }

  function parseDisplayDate(s){
    if(!s) return -1;
    const up = String(s).trim().toUpperCase();
    const parts = up.split(/\s+/);
    if(parts.length < 2) return -1;
    const m = parts[0];
    const d = parseInt(parts[1], 10) || 0;
    const months = { JAN:1, FEB:2, MAR:3, APR:4, MAY:5, JUN:6, JUL:7, AUG:8, SEP:9, OCT:10, NOV:11, DEC:12 };
    const mi = months[m] || 0;
    return mi*100 + d; // comparable within a single year
  }

  function buildScheduleRow(group){
    const row = document.createElement('div'); row.className='week-row';
    const date = document.createElement('div'); date.className='week-date';
    const dp = document.createElement('div'); dp.className='date-primary'; dp.textContent = group.week || '—';
    const ds = document.createElement('div'); ds.className='date-secondary'; ds.textContent = group.date || '';
    date.append(dp, ds);

    // Right side: AM/PM columns like templates
    const right = document.createElement('div'); right.className='templates-right';
    const { amAds, pmAds } = splitAmPm(group.ads || []);

    const amGroup = buildTimeGroup('AM');
    amAds.forEach((ad, idx) => amGroup.grid.appendChild(flag(idx % 2 === 0 ? 'team-a' : 'team-b', ad)));

    const pmGroup = buildTimeGroup('PM');
    pmAds.forEach((ad, idx) => pmGroup.grid.appendChild(flag(idx % 2 === 0 ? 'team-a' : 'team-b', ad)));

    right.appendChild(amGroup.wrapper);
    right.appendChild(pmGroup.wrapper);

    row.append(date, right);
    return row;
  }

  function renderFromAgg(){
    const root = el('#nflContent');
    let col = el('#nflContent .schedule-col');
    root.innerHTML = '';
    col = document.createElement('div'); col.className='schedule-col';

    let groups = Array.from(aggState.map.values()).sort((a,b)=> parseDisplayDate(b.date) - parseDisplayDate(a.date));

    // Setup date range picker and apply filter
    ensureRangePickerUI();
    if(selectedStartKey || selectedEndKey){
      groups = groups.filter(g => {
        const k = parseDisplayDateKey(g.date);
        if(selectedStartKey && k < selectedStartKey) return false;
        if(selectedEndKey && k > selectedEndKey) return false;
        return true;
      });
    }

    groups.forEach(g => {
      const row = buildScheduleRow(g);
      col.appendChild(row);
      const sep = document.createElement('div'); sep.className='date-divider'; sep.setAttribute('role','separator'); sep.setAttribute('aria-hidden','true');
      col.appendChild(sep);
    });
    root.appendChild(col);

    // Also render the templates deck with the same AM/PM layout
    renderTemplatesDeckAggregated(groups);
  }

  function renderGrid(data){
    ingestSchedule(data.schedule || []);
    renderFromAgg();
  }

  function renderTemplatesDeckAggregated(groups){
    const deck = el('#templatesDeck'); if(!deck) return; deck.innerHTML = '';
    groups.forEach(item => {
      const unique = [];
      const seen = new Set();
      (item.ads||[]).forEach(a=>{ const k=a.image_url||a.message||''; if(k && !seen.has(k)){ seen.add(k); unique.push(a);} });
      if(unique.length === 0) return;

      const block = document.createElement('div'); block.className = 'templates-block';

      // Left date column (reuse week-date styles)
      const left = document.createElement('div'); left.className = 'week-date';
      const dp = document.createElement('div'); dp.className = 'date-primary'; dp.textContent = item.week || '—';
      const ds = document.createElement('div'); ds.className = 'date-secondary'; ds.textContent = item.date || '';
      left.append(dp, ds);

      const right = document.createElement('div'); right.className='templates-right';
      const { amAds, pmAds } = splitAmPm(unique);

      const amGroup = buildTimeGroup('AM');
      amAds.forEach((ad, idx) => amGroup.grid.appendChild(flag(idx % 2 === 0 ? 'team-a' : 'team-b', ad)));

      const pmGroup = buildTimeGroup('PM');
      pmAds.forEach((ad, idx) => pmGroup.grid.appendChild(flag(idx % 2 === 0 ? 'team-a' : 'team-b', ad)));

      right.appendChild(amGroup.wrapper);
      right.appendChild(pmGroup.wrapper);

      block.append(left, right);
      deck.appendChild(block);

      const sep = document.createElement('div'); sep.className = 'date-divider'; sep.setAttribute('role','separator'); sep.setAttribute('aria-hidden','true');
      deck.appendChild(sep);
    });
  }

  function buildTimeGroup(label){
    const wrap = document.createElement('div'); wrap.className = 'templates-group';
    const head = document.createElement('div'); head.className = 'time-header'; head.textContent = label;
    const grid = document.createElement('div'); grid.className = 'templates-grid';
    wrap.append(head, grid);
    return { wrapper: wrap, grid };
  }

  function splitAmPm(list){
    const am = []; const pm = []; const unk = [];
    list.forEach(ad => {
      const t = detectMeridiem(ad);
      if(t==='am') am.push(ad); else if(t==='pm') pm.push(ad); else unk.push(ad);
    });
    unk.forEach((ad) => { (am.length <= pm.length) ? am.push(ad) : pm.push(ad); });
    return { amAds: am, pmAds: pm };
  }

  function detectMeridiem(ad){
    const src = (ad?.image_url || '').toLowerCase();
    const msg = (ad?.message || '').toLowerCase();
    const combined = src + ' ' + msg;
    if(/(?:^|[^a-z])am(?:[^a-z]|$)/i.test(combined)) return 'am';
    if(/(?:^|[^a-z])pm(?:[^a-z]|$)/i.test(combined)) return 'pm';
    if(/\b\d{1,2}(?::?\d{0,2})?\s?am\b/i.test(combined)) return 'am';
    if(/\b\d{1,2}(?::?\d{0,2})?\s?pm\b/i.test(combined)) return 'pm';
    return null;
  }

  function flag(side, ad){
    const d = document.createElement('div'); d.className = 'team-flag '+side;
    if(ad && ad.image_url){
      const img=document.createElement('img');
      img.src=ad.image_url; img.alt=ad.brand||''; img.loading='lazy';
      img.onerror = () => {
        d.innerHTML = '';
        const span=document.createElement('span'); span.className='team-code'; span.textContent = side==='team-a'?'A':'B'; d.appendChild(span);
      };
      d.appendChild(img);
    } else {
      const span=document.createElement('span'); span.className='team-code'; span.textContent = side==='team-a'?'A':'B'; d.appendChild(span);
    }
    return d;
  }

  function getTerm(){ const v = (el('#nflTerm')?.value || '').trim(); return v || 'packaged deli meat'; }
  async function loadTerms(client){
    try{
      const data = await fetchJSON(`/api/terms/${encodeURIComponent(client)}`);
      const sel = el('#nflTerm');
      if(!sel) return;
      sel.innerHTML = '';
      const terms = (data.terms||[]);
      if(terms.length===0){
        const o=document.createElement('option'); o.value=''; o.textContent='—'; sel.appendChild(o);
      } else {
        terms.forEach(t=>{ const o=document.createElement('option'); o.value=t; o.textContent=t; sel.appendChild(o); });
        const preferred = terms.find(t => t.toLowerCase()==='packaged deli meat') || terms[0];
        sel.value = preferred;
      }
      sel.onchange = () => { currentPage=1; hasMore=true; selectedStartKey=null; selectedEndKey=null; resetAgg(); loadClient(currentClient||el('#nflClient')?.value); };
    }catch(e){ console.error(e); }
  }

  let currentClient = null;
  let currentPage = 1;
  let hasMore = true;
  let isLoading = false;
  let selectedStartKey = null; // numeric key mm*100+dd
  let selectedEndKey = null;   // numeric key mm*100+dd

  function parseDisplayDateKey(s){
    if(!s) return -1;
    const up = String(s).trim().toUpperCase();
    const parts = up.split(/\s+/);
    if(parts.length < 2) return -1;
    const months = { JAN:1, FEB:2, MAR:3, APR:4, MAY:5, JUN:6, JUL:7, AUG:8, SEP:9, OCT:10, NOV:11, DEC:12 };
    const mi = months[parts[0]] || 0;
    const d = parseInt(parts[1], 10) || 0;
    return mi*100 + d;
  }

  function ensureRangePickerUI(){
    const trigger = el('#nflDateRange'); if(!trigger) return;
    let pop = document.querySelector('.date-range-popover');

    function labelFromKeys(){
      if(!selectedStartKey && !selectedEndKey) return 'All dates';
      const fmt = k => {
        const mm = Math.floor(k/100); const dd = k%100;
        const d = new Date(new Date().getFullYear(), mm-1, dd);
        return d.toLocaleString('en-US', { month:'short', day:'2-digit' }).toUpperCase();
      };
      if(selectedStartKey && selectedEndKey) return fmt(selectedStartKey) + ' – ' + fmt(selectedEndKey);
      if(selectedStartKey) return fmt(selectedStartKey) + ' – …';
      return '… – ' + fmt(selectedEndKey);
    }

    trigger.textContent = labelFromKeys();

    if(!pop){
      pop = document.createElement('div'); pop.className='date-range-popover'; pop.style.display='none';
      pop.innerHTML = `
        <div class="cal-header">
          <button class="cal-nav" data-nav="prev">‹</button>
          <div class="cal-title"></div>
          <button class="cal-nav" data-nav="next">›</button>
        </div>
        <div class="cal-weekdays">
          <div>Su</div><div>Mo</div><div>Tu</div><div>We</div><div>Th</div><div>Fr</div><div>Sa</div>
        </div>
        <div class="cal-grid"></div>
        <div class="date-popover-actions">
          <button class="date-btn" data-act="clear">Clear</button>
          <button class="date-btn primary" data-act="apply">Apply</button>
        </div>`;
      document.body.appendChild(pop);

      pop.addEventListener('click', (e)=>{ e.stopPropagation(); });
      document.addEventListener('click', (e)=>{
        if(pop.style.display==='none') return;
        if(e.target !== trigger && !pop.contains(e.target)) pop.style.display='none';
      });

      const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
      function rebuildCalendar(){
        const title = pop.querySelector('.cal-title');
        const grid = pop.querySelector('.cal-grid');
        const y = pop._year; const m = pop._month; // 0-indexed
        title.textContent = months[m] + ' ' + y;
        grid.innerHTML = '';
        const first = new Date(y, m, 1);
        const startDay = first.getDay();
        const daysInMonth = new Date(y, m+1, 0).getDate();
        const today = new Date();
        const todayKey = (today.getMonth()+1)*100 + today.getDate();
        for(let i=0;i<startDay;i++){ const d=document.createElement('div'); d.className='cal-day cal-empty'; grid.appendChild(d); }
        for(let day=1; day<=daysInMonth; day++){
          const btn = document.createElement('button'); btn.type='button'; btn.className='cal-day'; btn.textContent=String(day);
          const k = (m+1)*100 + day; if(k===todayKey) btn.classList.add('is-today');
          const s = pop._draftStartKey, e = pop._draftEndKey;
          if(s && k===s) btn.classList.add('is-selected');
          if(e && k===e) btn.classList.add('is-selected');
          if(s && e && k>s && k<e) btn.classList.add('in-range');
          btn.addEventListener('click', ()=>{
            if(!pop._draftStartKey || (pop._draftStartKey && pop._draftEndKey)){
              pop._draftStartKey = k; pop._draftEndKey = null;
            } else if(k < pop._draftStartKey){
              pop._draftEndKey = pop._draftStartKey; pop._draftStartKey = k;
            } else if(k === pop._draftStartKey){
              pop._draftEndKey = k; // single-day range
            } else {
              pop._draftEndKey = k;
            }
            rebuildCalendar();
          });
          grid.appendChild(btn);
        }
      }
      pop.querySelector('[data-nav="prev"]').addEventListener('click', ()=>{ if(pop._month===0){ pop._month=11; pop._year-=1; } else pop._month-=1; rebuildCalendar(); });
      pop.querySelector('[data-nav="next"]').addEventListener('click', ()=>{ if(pop._month===11){ pop._month=0; pop._year+=1; } else pop._month+=1; rebuildCalendar(); });

      pop.querySelector('[data-act="clear"]').addEventListener('click', ()=>{
        selectedStartKey = null; selectedEndKey = null;
        pop._draftStartKey = null; pop._draftEndKey = null;
        trigger.textContent = labelFromKeys();
        pop.style.display = 'none';
        renderFromAgg();
      });
      pop.querySelector('[data-act="apply"]').addEventListener('click', ()=>{
        selectedStartKey = pop._draftStartKey || null;
        selectedEndKey = pop._draftEndKey || null;
        trigger.textContent = labelFromKeys();
        pop.style.display = 'none';
        renderFromAgg();
      });

      pop._rebuildCalendar = rebuildCalendar;
    }

    trigger.onclick = (e)=>{
      e.stopPropagation();
      const rect = trigger.getBoundingClientRect();
      pop.style.top = window.scrollY + rect.bottom + 6 + 'px';
      pop.style.left = window.scrollX + rect.left + 'px';
      const newestGroup = Array.from(aggState.map.values()).sort((a,b)=> parseDisplayDate(b.date) - parseDisplayDate(a.date))[0];
      if(newestGroup){
        const key = parseDisplayDateKey(newestGroup.date);
        pop._month = Math.max(1, Math.floor(key/100)) - 1;
        pop._year = new Date().getFullYear();
      } else {
        const t = new Date(); pop._month = t.getMonth(); pop._year = t.getFullYear();
      }
      pop._draftStartKey = selectedStartKey || null;
      pop._draftEndKey = selectedEndKey || null;
      pop._rebuildCalendar();
      pop.style.display = (pop.style.display==='none') ? 'block' : 'none';
    };
  }

  async function loadClients(){
    try {
      const data = await fetchJSON('/api/ads');
      const clients = (data.clients||[]).sort();
      const sel = el('#nflClient'); sel.innerHTML='';
      clients.forEach(c=>{ const o=document.createElement('option'); o.value=c; o.textContent=c; sel.appendChild(o); });
      if(clients.length){
        const preferred = clients.includes('Land_O_Frost') ? 'Land_O_Frost' : clients[0];
        sel.value = preferred;
        await loadTerms(sel.value);
        await loadClient(sel.value);
      }
      sel.onchange = async () => { resetAgg(); selectedStartKey=null; selectedEndKey=null; await loadTerms(sel.value); await loadClient(sel.value); };
    } catch(e) {
      console.error(e);
    }
  }

  async function loadClient(name){
    try {
      currentClient = name;
      currentPage = 1; hasMore = true; isLoading = false; selectedStartKey=null; selectedEndKey=null; resetAgg();
      const data = await fetchJSON(`/api/nfl-grid/${encodeURIComponent(name)}?term=${encodeURIComponent(getTerm())}&page=${currentPage}`);
      renderGrid(data);
      hasMore = !!data.has_more;
      setupInfiniteScroll();
    } catch(e) {
      console.error(e);
    }
  }

  async function loadMore(){
    if(isLoading || !hasMore || !currentClient) return;
    isLoading = true;
    try{
      currentPage += 1;
      const data = await fetchJSON(`/api/nfl-grid/${encodeURIComponent(currentClient)}?term=${encodeURIComponent(getTerm())}&page=${currentPage}`);
      renderGrid(data);
      hasMore = !!data.has_more;
    } catch(e){ console.error(e); }
    finally { isLoading = false; }
  }

  function clearContainers(){
    const root = el('#nflContent'); if(root) root.innerHTML = '';
    const deck = el('#templatesDeck'); if(deck) deck.innerHTML = '';
  }

  function setupInfiniteScroll(){
    let sentinel = el('#infiniteSentinel');
    if(!sentinel){
      sentinel = document.createElement('div');
      sentinel.id = 'infiniteSentinel';
      sentinel.style.height = '1px';
      sentinel.style.width = '100%';
      const container = document.querySelector('.nfl-container') || document.body;
      container.appendChild(sentinel);
    }
    const io = new IntersectionObserver((entries)=>{
      entries.forEach(en=>{ if(en.isIntersecting) loadMore(); });
    });
    io.observe(sentinel);
  }

  document.addEventListener('DOMContentLoaded', () => { clearContainers(); ensureRangePickerUI(); loadClients(); });
})();
