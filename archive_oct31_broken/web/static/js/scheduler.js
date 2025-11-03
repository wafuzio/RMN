(function(){
  const state = {
    clients: [],
    currentClient: '',
    schedule: { runs: 3, times: [["8","00","AM"],["12","00","PM"],["4","00","PM"]], days: ["Monday","Tuesday","Wednesday","Thursday","Friday"] },
    keywords: []
  };

  const el = sel => document.querySelector(sel);
  const els = sel => Array.from(document.querySelectorAll(sel));

  function setStatus(msg) {
    el('#statusMessage').textContent = msg;
  }

  function getSelectedDays() {
    return els('.days-grid input[type="checkbox"]:checked').map(c => c.value);
  }

  function renderClients() {
    const select = el('#clientSelect');
    select.innerHTML = '';
    const defaultOpt = document.createElement('option');
    defaultOpt.value = '';
    defaultOpt.textContent = '<choose from menu>';
    select.appendChild(defaultOpt);
    state.clients.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c;
      opt.textContent = c;
      select.appendChild(opt);
    });
    select.value = state.currentClient || '';
  }

  function renderTimes() {
    const list = el('#timesList');
    list.innerHTML = '';
    const runs = parseInt(el('#runsPerDay').value, 10) || 1;
    // ensure schedule.times length matches runs
    if (!Array.isArray(state.schedule.times)) state.schedule.times = [];
    while (state.schedule.times.length < runs) {
      state.schedule.times.push(["8","00","AM"]);
    }
    state.schedule.times = state.schedule.times.slice(0, runs);

    state.schedule.times.forEach((t, idx) => {
      const row = document.createElement('div');
      row.className = 'time-row';
      row.dataset.index = idx;

      const label = document.createElement('div');
      label.className = 'time-label';
      label.textContent = `Run ${idx+1}`;

      const hour = document.createElement('select');
      hour.className = 'form-select';
      for (let h=1; h<=12; h++) {
        const o = document.createElement('option');
        o.value = String(h);
        o.textContent = String(h);
        hour.appendChild(o);
      }
      hour.value = t[0];

      const minute = document.createElement('select');
      minute.className = 'form-select';
      for (let m=0; m<60; m+=5) {
        const mm = m.toString().padStart(2,'0');
        const o = document.createElement('option');
        o.value = mm; o.textContent = mm; minute.appendChild(o);
      }
      minute.value = t[1];

      const ampm = document.createElement('select');
      ampm.className = 'form-select';
      ;['AM','PM'].forEach(v=>{ const o=document.createElement('option'); o.value=v;o.textContent=v;ampm.appendChild(o)});
      ampm.value = t[2];

      const conflict = document.createElement('div');
      conflict.className = 'conflict-label';
      conflict.textContent = '';

      [hour, minute, ampm].forEach(ctrl => ctrl.addEventListener('change', () => {
        state.schedule.times[idx] = [hour.value, minute.value, ampm.value];
        checkConflictsForAll();
      }));

      row.appendChild(label);
      row.appendChild(hour);
      row.appendChild(minute);
      row.appendChild(ampm);
      row.appendChild(conflict);
      list.appendChild(row);
    });

    checkConflictsForAll();
  }

  function updateDaysFromSchedule() {
    const days = new Set(state.schedule.days || []);
    els('.days-grid input[type="checkbox"]').forEach(cb => {
      cb.checked = days.has(cb.value);
    });
  }

  async function loadClients() {
    const res = await fetch('/api/clients');
    const data = await res.json();
    state.clients = data.clients || [];
    renderClients();
  }

  async function loadClientData(name) {
    if (!name) return;
    const res = await fetch(`/api/client/${encodeURIComponent(name)}`);
    const data = await res.json();
    state.currentClient = name;
    state.keywords = data.keywords || [];
    state.schedule = data.schedule || state.schedule;
    el('#keywordsInput').value = state.keywords.join('\n');
    el('#runsPerDay').value = state.schedule.runs || 3;
    updateDaysFromSchedule();
    renderTimes();
    setStatus(`Loaded data for ${name}`);
  }

  async function saveKeywords() {
    if (!state.currentClient) { setStatus('Select a client first'); return; }
    const keywords = el('#keywordsInput').value.split('\n').map(s=>s.trim()).filter(Boolean);
    const res = await fetch(`/api/client/${encodeURIComponent(state.currentClient)}/keywords`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ keywords })
    });
    if (res.ok) {
      setStatus(`Saved ${keywords.length} keywords for ${state.currentClient}`);
      await loadClients();
    } else {
      setStatus('Failed to save keywords');
    }
  }

  async function saveSchedule() {
    if (!state.currentClient) { setStatus('Select a client first'); return; }
    const payload = {
      runs: parseInt(el('#runsPerDay').value, 10) || 1,
      times: state.schedule.times,
      days: getSelectedDays(),
      client: state.currentClient
    };
    const res = await fetch(`/api/client/${encodeURIComponent(state.currentClient)}/schedule`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
    });
    if (res.ok) setStatus('Schedule saved'); else setStatus('Failed to save schedule');
  }

  async function checkConflictsForAll() {
    const days = getSelectedDays();
    if (!days.length) { setConflictLabelsClear(); return; }
    try {
      const res = await fetch('/api/conflicts', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client: state.currentClient || null, times: state.schedule.times, days })
      });
      const data = await res.json();
      applyConflictResults(data.results || []);
    } catch {
      // ignore
    }
  }

  function setConflictLabelsClear() {
    els('.time-row').forEach(row => {
      const label = row.querySelector('.conflict-label');
      label.className = 'conflict-label conflict-ok';
      label.textContent = '✓ Available';
    });
  }

  function applyConflictResults(results) {
    els('.time-row').forEach((row, idx) => {
      const info = results[idx];
      const label = row.querySelector('.conflict-label');
      label.className = 'conflict-label';
      if (!info || !info.conflict) {
        label.classList.add('conflict-ok');
        label.textContent = '✓ Available';
      } else if (info.suggestion) {
        label.classList.add('conflict-warn');
        const { hour, minute, ampm } = info.suggestion;
        label.textContent = `⚠ Conflict – Try ${hour}:${String(minute).padStart(2,'0')} ${ampm}`;
        label.onclick = () => {
          const [hSel, mSel, aSel] = row.querySelectorAll('select.form-select');
          hSel.value = String(hour); mSel.value = String(minute).padStart(2,'0'); aSel.value = ampm;
          state.schedule.times[idx] = [hSel.value, mSel.value, aSel.value];
          checkConflictsForAll();
        };
      } else {
        label.classList.add('conflict-bad');
        label.textContent = '⚠ Conflict';
        label.onclick = null;
      }
    });
  }

  async function runNow() {
    if (!state.currentClient) { setStatus('Select a client first'); return; }
    setStatus('Starting run...');
    await fetch(`/api/scrape/${encodeURIComponent(state.currentClient)}`, { method: 'POST' });
    pollStatus();
  }

  async function pollStatus() {
    if (!state.currentClient) return;
    try {
      const res = await fetch(`/api/status/${encodeURIComponent(state.currentClient)}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data && data.message) setStatus(data.message);
      if (data && !data.done) setTimeout(pollStatus, 1500);
      else if (data && data.done) setStatus(data.message || 'Completed');
    } catch {}
  }

  // Event bindings
  document.addEventListener('DOMContentLoaded', async () => {
    await loadClients();
    renderTimes();

    el('#runsPerDay').addEventListener('change', () => renderTimes());
    els('.days-grid input[type="checkbox"]').forEach(cb => cb.addEventListener('change', checkConflictsForAll));

    el('#clientSelect').addEventListener('change', e => loadClientData(e.target.value));

    el('#newClientBtn').addEventListener('click', async () => {
      const name = prompt('Enter new client/product name');
      if (!name) return;
      state.currentClient = name.trim();
      if (!state.currentClient) return;
      if (!state.clients.includes(state.currentClient)) state.clients.unshift(state.currentClient);
      renderClients();
      el('#clientSelect').value = state.currentClient;
      state.keywords = [];
      state.schedule = { runs: 3, times: [["8","00","AM"],["12","00","PM"],["4","00","PM"]], days: ["Monday","Tuesday","Wednesday","Thursday","Friday"], client: state.currentClient };
      el('#keywordsInput').value = '';
      el('#runsPerDay').value = state.schedule.runs;
      updateDaysFromSchedule();
      renderTimes();
      setStatus(`Created ${state.currentClient}. Add keywords and save.`);
    });

    el('#saveKeywordsBtn').addEventListener('click', saveKeywords);
    el('#clearKeywordsBtn').addEventListener('click', () => { el('#keywordsInput').value=''; });
    el('#saveScheduleBtn').addEventListener('click', saveSchedule);
    el('#refreshConflictsBtn').addEventListener('click', checkConflictsForAll);
    el('#refreshOverviewBtn').addEventListener('click', loadOverview);
    el('#runNowBtn').addEventListener('click', runNow);

    await loadOverview();
  });

  async function loadOverview() {
    try {
      const res = await fetch('/api/schedules/overview');
      const data = await res.json();
      const list = el('#overviewList');
      if (!data.items || data.items.length === 0) {
        list.innerHTML = '<div class="text-muted small">No schedules found yet.</div>';
        return;
      }
      const grouped = data.items.reduce((acc, it) => {
        const k = it.client; acc[k] = acc[k] || []; acc[k].push(it); return acc;
      }, {});
      list.innerHTML = Object.keys(grouped).map(client => {
        const rows = grouped[client]
          .sort((a,b)=> a.day.localeCompare(b.day) || a.hour-b.hour || a.minute-b.minute)
          .map(it => `<div class="overview-item"><div class="overview-client">${client}</div><div class="overview-when">${it.day} • ${to12h(it.hour,it.minute)}</div></div>`)
          .join('');
        return rows;
      }).join('');
    } catch {
      // ignore
    }
  }

  function to12h(h, m) {
    const ampm = h>=12 ? 'PM':'AM';
    const h12 = h%12===0 ? 12 : h%12;
    return `${h12}:${String(m).padStart(2,'0')} ${ampm}`;
  }
})();
