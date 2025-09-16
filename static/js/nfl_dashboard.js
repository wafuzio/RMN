(function(){
  const el = s => document.querySelector(s);
  const els = s => Array.from(document.querySelectorAll(s));

  async function fetchJSON(url){ const r = await fetch(url); if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); }

  function pairwise(arr){ const out=[]; for(let i=0;i<arr.length;i+=2){ out.push(arr.slice(i,i+2)); } return out; }

  function renderGrid(data){
    const root = el('#nflContent');
    root.innerHTML='';
    const col = document.createElement('div'); col.className='schedule-col';
    const allAds=[];
    (data.schedule||[]).forEach(item=>{
      const row = document.createElement('div'); row.className='week-row';
      const date = document.createElement('div'); date.className='week-date';
      const dp = document.createElement('div'); dp.className='date-primary'; dp.textContent = item.week || '—';
      const ds = document.createElement('div'); ds.className='date-secondary'; ds.textContent = item.date || '';
      date.append(dp, ds);

      const games = document.createElement('div'); games.className='week-games';
      const pairs = pairwise(item.ads||[]);
      (item.ads||[]).forEach(a=> allAds.push(a));
      if(pairs.length===0){
        const matchup = document.createElement('div'); matchup.className='matchup';
        matchup.append(flag('team-a'), flag('team-b'));
        games.appendChild(matchup);
      } else {
        pairs.forEach(p=>{
          const matchup = document.createElement('div'); matchup.className='matchup';
          matchup.append(flag('team-a', p[0]), flag('team-b', p[1]));
          games.appendChild(matchup);
        });
      }

      row.append(date, games);
      col.appendChild(row);
    });
    root.appendChild(col);

    renderTemplatesDeck(allAds);
  }

  function renderTemplatesDeck(ads){
    const deck = el('#templatesDeck');
    if(!deck) return;
    deck.innerHTML='';

    const seen = new Set();
    const unique = [];
    (ads||[]).forEach(a=>{ const key=a.image_url||a.message||''; if(key && !seen.has(key)){ seen.add(key); unique.push(a);} });
    const base = unique.slice(0,12);

    const groups = 4; // packaged deli meat & its clone + 3 more double rows
    for(let g=0; g<groups; g++){
      const row1 = document.createElement('div'); row1.className='templates-row';
      const row2 = document.createElement('div'); row2.className='templates-row';

      const offset = (g*3) % (base.length || 1);
      const r1 = rotate(base, offset);
      const r2 = rotate(base, (offset + 6) % (base.length || 1));

      [ [row1, r1], [row2, r2] ].forEach(([row, items]) => {
        items.forEach(ad => {
          const card = document.createElement('div'); card.className='template-card';
          const thumb = document.createElement('div'); thumb.className='template-thumb';
          if(ad.image_url){ const img = new Image(); img.src = ad.image_url; img.alt = ad.brand || ''; thumb.appendChild(img); }
          const meta = document.createElement('div'); meta.className='template-meta';
          const brand = document.createElement('span'); brand.textContent = ad.brand || 'Ad';
          const featured = document.createElement('span'); featured.textContent = ad.featured ? 'Featured' : '';
          meta.append(brand, featured);
          card.append(thumb, meta);
          row.appendChild(card);
        });
        deck.appendChild(row);
      });
    }
  }

  function rotate(arr, n){
    if(!arr || !arr.length) return [];
    const len = arr.length;
    const k = ((n % len) + len) % len;
    return arr.slice(k).concat(arr.slice(0, k));
  }

  function flag(side, ad){
    const d = document.createElement('div'); d.className = 'team-flag '+side;
    if(ad && ad.image_url){ const img=document.createElement('img'); img.src=ad.image_url; img.alt=ad.brand||''; d.appendChild(img); }
    else { const span=document.createElement('span'); span.className='team-code'; span.textContent = side==='team-a'?'A':'B'; d.appendChild(span); }
    return d;
  }

  function getTerm(){ const v = (el('#nflTerm')?.value || '').trim(); return v || 'packaged deli meat'; }

  async function loadClients(){
    try {
      const data = await fetchJSON('/api/ads');
      const clients = (data.clients||[]).sort();
      const sel = el('#nflClient'); sel.innerHTML='';
      clients.forEach(c=>{ const o=document.createElement('option'); o.value=c; o.textContent=c; sel.appendChild(o); });
      if(clients.length){
        const preferred = clients.includes('Land_O_Frost') ? 'Land_O_Frost' : clients[0];
        sel.value = preferred;
        await loadClient(sel.value);
      }
      sel.onchange = () => loadClient(sel.value);
      const term = el('#nflTerm'); if(term){ term.addEventListener('change', ()=> loadClient(sel.value)); }
    } catch(e) {
      console.error(e);
    }
  }

  async function loadClient(name){
    try {
      const data = await fetchJSON(`/api/nfl-grid/${encodeURIComponent(name)}?term=${encodeURIComponent(getTerm())}`);
      renderGrid(data);
    } catch(e) {
      console.error(e);
    }
  }

  document.addEventListener('DOMContentLoaded', loadClients);
})();
