(function(){
  const el = s => document.querySelector(s);
  const els = s => Array.from(document.querySelectorAll(s));
  const LS_KEY = 'previewScheduler';

  const store = {
    load(){
      try { return JSON.parse(localStorage.getItem(LS_KEY)) || { clients: {} }; } catch { return { clients: {} }; }
    },
    save(data){ localStorage.setItem(LS_KEY, JSON.stringify(data)); }
  };

  const state = {
    data: store.load(),
    current: ''
  };

  function setStatus(msg){ el('#statusMessage').textContent = msg; }
  function hasClient(){ return !!state.current; }
  function hasKeywords(){
    const text = el('#keywordsInput').value.trim();
    const saved = (state.data.clients[state.current]?.keywords||[]).length;
    return (text.length>0) || saved>0;
  }
  function updateButtons(){
    const saveSched = el('#saveScheduleBtn');
    const startSched = el('#startScheduleBtn');
    const startScrape = el('#startScrapingBtn');
    const bottomClear = el('#bottomClearBtn');
    const enableSave = hasClient();
    const enableStartSched = hasClient() && hasKeywords() && getSelectedDays().length>0;
    const enableScrape = hasClient() && hasKeywords();
    saveSched.disabled = !enableSave;
    startSched.disabled = !enableStartSched;
    startScrape.disabled = !enableScrape;
    bottomClear.disabled = !hasClient();
  }

  function clients(){ return Object.keys(state.data.clients).sort(); }

  function ensureClient(name){
    if(!state.data.clients[name]){
      state.data.clients[name] = { keywords: [], schedule: { runs:3, times:[["8","00","AM"],["12","00","PM"],["4","00","PM"]], days:["Monday","Tuesday","Wednesday","Thursday","Friday"] } };
      store.save(state.data);
    }
  }

  function renderClients(){
    const select = el('#clientSelect');
    select.innerHTML = '';
    const def = document.createElement('option');
    def.value = ''; def.textContent = '<choose from menu>';
    select.appendChild(def);
    clients().forEach(c=>{ const o=document.createElement('option'); o.value=c; o.textContent=c; select.appendChild(o); });
    select.value = state.current || '';
  }

  function loadClient(name){
    if(!name){ return; }
    ensureClient(name);
    state.current = name;
    const c = state.data.clients[name];
    el('#keywordsInput').value = (c.keywords||[]).join('\n');
    el('#runsPerDay').value = c.schedule.runs || 3;
    setCheckedDays(c.schedule.days||[]);
    renderTimes(c.schedule);
    setStatus(`Loaded ${name}`);
    updateButtons();
  }

  function setCheckedDays(days){
    const set = new Set(days);
    els('.days-grid input[type="checkbox"]').forEach(cb=> cb.checked = set.has(cb.value));
  }

  function getSelectedDays(){
    return els('.days-grid input[type="checkbox"]:checked').map(c=>c.value);
  }

  function renderTimes(sched){
    const list = el('#timesList');
    list.innerHTML='';
    const runs = parseInt(el('#runsPerDay').value,10) || 1;
    if(!Array.isArray(sched.times)) sched.times=[];
    while(sched.times.length < runs) sched.times.push(["8","00","AM"]);
    sched.times = sched.times.slice(0, runs);

    sched.times.forEach((t, idx)=>{
      const row = document.createElement('div');
      row.className = 'time-row';
      const label = document.createElement('div'); label.className='time-label'; label.textContent = `Run ${idx+1}`;
      const hour = sel(Array.from({length:12},(_,i)=>String(i+1)), t[0]);
      const minute = sel(minutes(), t[1]);
      const ampm = sel(['AM','PM'], t[2]);
      const conflict = document.createElement('div'); conflict.className='conflict-label';
      [hour, minute, ampm].forEach(ctrl=> ctrl.addEventListener('change', ()=>{ sched.times[idx] = [hour.value, minute.value, ampm.value]; checkConflicts(); }));
      row.append(label,hour,minute,ampm,conflict);
      list.appendChild(row);
    });
    checkConflicts();
  }

  function sel(values, value){ const s=document.createElement('select'); s.className='form-select'; values.forEach(v=>{ const o=document.createElement('option'); o.value=v; o.textContent=v; s.appendChild(o); }); s.value=value; return s; }
  function minutes(){ const a=[]; for(let m=0;m<60;m+=5){ a.push(String(m).padStart(2,'0')); } return a; }

  function to24([h, m, a]){ let H=parseInt(h,10); const M=parseInt(m,10); if(a==='PM' && H<12) H+=12; if(a==='AM' && H===12) H=0; return [H,M]; }

  function allScheduledExceptCurrent(){
    const items=[];
    Object.entries(state.data.clients).forEach(([name, c])=>{
      if(name===state.current) return;
      const days=c.schedule.days||[];
      (c.schedule.times||[]).forEach(t=>{ const [H,M]=to24(t); days.forEach(d=> items.push({day:d,h:H,m:M,name})); });
    });
    return items;
  }

  function checkConflicts(){
    const rows = els('.time-row');
    const other = allScheduledExceptCurrent();
    const selectedDays = new Set(getSelectedDays());
    rows.forEach((row, idx)=>{
      const [hSel, mSel, aSel] = row.querySelectorAll('select.form-select');
      const [H,M] = to24([hSel.value, mSel.value, aSel.value]);
      const label = row.querySelector('.conflict-label');
      const conflict = other.some(o=> selectedDays.has(o.day) && o.h===H && o.m===M);
      if(!conflict){ label.className='conflict-label conflict-ok'; label.textContent='✓ Available'; label.onclick=null; return; }
      // Suggest next available in +5 minute steps up to 60 minutes
      let sH=H, sM=M, found=false;
      for(let i=1;i<=12;i++){ let nm=M+5*i, nH=H; while(nm>=60){ nm-=60; nH=(nH+1)%24; } const hit = other.some(o=> selectedDays.has(o.day) && o.h===nH && o.m===nm); if(!hit){ sH=nH; sM=nm; found=true; break; } }
      const ap = sH>=12?'PM':'AM'; const h12 = (sH%12===0)?12:(sH%12);
      label.className='conflict-label conflict-warn';
      label.textContent = found?`⚠ Conflict – Try ${h12}:${String(sM).padStart(2,'0')} ${ap}`:'⚠ Conflict';
      if(found){ label.onclick=()=>{ hSel.value=String(h12); mSel.value=String(sM).padStart(2,'0'); aSel.value=ap; checkConflicts(); }; }
    });
  }

  function saveKeywords(){
    if(!state.current){ setStatus('Select a client first'); return; }
    const lines = el('#keywordsInput').value.split('\n').map(s=>s.trim()).filter(Boolean);
    state.data.clients[state.current].keywords = lines;
    store.save(state.data);
    setStatus(`Saved ${lines.length} keywords for ${state.current}`);
    renderOverview();
    updateButtons();
  }

  function saveSchedule(){
    if(!state.current){ setStatus('Select a client first'); return; }
    const sched = state.data.clients[state.current].schedule;
    sched.runs = parseInt(el('#runsPerDay').value,10) || 1;
    sched.days = getSelectedDays();
    // times already updated via change handlers
    store.save(state.data);
    setStatus('Schedule saved');
    renderOverview();
    updateButtons();
  }

  function renderOverview(){
    const list = el('#overviewList');
    const items=[];
    Object.entries(state.data.clients).forEach(([name,c])=>{
      (c.schedule.days||[]).forEach(day=>{ (c.schedule.times||[]).forEach(t=>{ const [H,M]=to24(t); items.push({client:name,day,h:H,m:M}); }); });
    });
    if(items.length===0){ list.innerHTML='<div class="text-muted small">No schedules found yet.</div>'; return; }
    items.sort((a,b)=> a.day.localeCompare(b.day) || a.h-b.h || a.m-b.m);
    list.innerHTML = items.map(it=> `<div class="overview-item"><div class="overview-client">${it.client}</div><div class="overview-when">${it.day} • ${to12(it.h,it.m)}</div></div>`).join('');
  }

  function to12(h,m){ const ap=h>=12?'PM':'AM'; const h12=h%12===0?12:h%12; return `${h12}:${String(m).padStart(2,'0')} ${ap}`; }

  function toggleSchedule(){
    state.running = !state.running;
    el('#startScheduleBtn').textContent = state.running ? 'Stop Schedule' : 'Start Schedule';
    setStatus(state.running ? `Scheduler started for ${state.current}` : 'Scheduler stopped');
  }

  function startScraping(){
    if(!hasClient() || !hasKeywords()){ setStatus('Select client and enter keywords'); return; }
    setStatus(`Starting scraper for ${state.current}...`);
    setTimeout(()=> setStatus('Ready'), 1200);
  }

  document.addEventListener('DOMContentLoaded', ()=>{
    // Seed with an example if empty
    if(clients().length===0){ ensureClient('Example Client'); }
    renderClients();
    el('#clientSelect').addEventListener('change', e=> { loadClient(e.target.value); });
    el('#newClientBtn').addEventListener('click', ()=>{ const name = prompt('Enter new client/product name'); if(!name) return; ensureClient(name.trim()); state.current=name.trim(); renderClients(); el('#clientSelect').value=state.current; loadClient(state.current); });
    el('#saveKeywordsBtn').addEventListener('click', saveKeywords);
    el('#clearKeywordsBtn').addEventListener('click', ()=>{ el('#keywordsInput').value=''; updateButtons(); });
    el('#keywordsInput').addEventListener('input', updateButtons);
    el('#runsPerDay').addEventListener('change', ()=>{ const sched = state.data.clients[state.current]?.schedule || { runs:1, times:[], days:[] }; renderTimes(sched); updateButtons(); });
    els('.days-grid input[type="checkbox"]').forEach(cb=> cb.addEventListener('change', ()=>{ checkConflicts(); updateButtons(); }));
    el('#saveScheduleBtn').addEventListener('click', saveSchedule);
    el('#startScheduleBtn').addEventListener('click', toggleSchedule);
    el('#refreshConflictsBtn').addEventListener('click', checkConflicts);
    el('#refreshOverviewBtn').addEventListener('click', renderOverview);
    el('#startScrapingBtn').addEventListener('click', startScraping);
    el('#bottomClearBtn').addEventListener('click', ()=>{ el('#keywordsInput').value=''; updateButtons(); });

    // Auto-load first client
    if(clients().length){ state.current = clients()[0]; renderClients(); el('#clientSelect').value=state.current; loadClient(state.current); }
    renderOverview();
    updateButtons();
  });
})();
