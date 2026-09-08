// ---------- data (hydrated from the server) ----------
const usageEl = document.getElementById('usage-data');
let rows = usageEl ? JSON.parse(usageEl.textContent) : [];

function esc(value){
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const fmtDate = d => d
  ? new Date(d + "T00:00:00").toLocaleDateString('en-US',{ month:'short', day:'numeric', year:'numeric' })
  : '\u2014';

function fmtDelta(cur, prev, invert){
  if(prev == null) return '';
  const diff = cur - prev;
  if(diff === 0) return '<span class="delta">no change</span>';
  const pct = prev ? Math.round(Math.abs(diff) / prev * 100) : 100;
  const down = diff < 0;
  // for churn risk, a drop in usage is bad (red); used with invert=false
  const cls = (down !== !!invert) ? 'delta down' : 'delta';
  const arrow = down ? '\u2193' : '\u2191';
  return `<span class="${cls}">${arrow} ${pct}% vs prev.</span>`;
}

const RISK_LABEL = { at_risk: 'At risk', watch: 'Watch', healthy: 'Healthy', no_data: 'No data' };

// ---------- rendering ----------
function renderStats(){
  const total = rows.length;
  const atRisk = rows.filter(r=>r.risk==='at_risk').length;
  const watch = rows.filter(r=>r.risk==='watch').length;
  const active = rows.reduce((a,r)=>a+(r.active_students||0),0);
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="label">Schools tracked</div><div class="value">${total}</div></div>
    <div class="stat"><div class="label">At risk of churning</div><div class="value" style="color:var(--red)">${atRisk}</div></div>
    <div class="stat"><div class="label">Worth watching</div><div class="value" style="color:var(--amber)">${watch}</div></div>
    <div class="stat"><div class="label">Active students (latest)</div><div class="value">${Number(active).toLocaleString()}</div></div>
  `;
  document.getElementById('subhead').textContent =
    `${total} school${total===1?'':'s'} \u00b7 ${atRisk + watch} need${(atRisk+watch)===1?'s':''} attention`;
}

function getFiltered(){
  const q = document.getElementById('searchInput').value.trim().toLowerCase();
  const risk = document.getElementById('riskFilter').value;
  return rows.filter(r =>
    (!q || r.name.toLowerCase().includes(q) || r.city.toLowerCase().includes(q)) &&
    (risk === 'all' || r.risk === risk)
  );
}

function renderTable(){
  const list = getFiltered();
  const body = document.getElementById('tableBody');
  const empty = document.getElementById('emptyState');
  if(list.length === 0){
    body.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  body.innerHTML = list.map(r => `
    <tr>
      <td class="school-name">${esc(r.name)}<span class="loc">${esc(r.city)}</span></td>
      <td class="mono">${Number(r.logins).toLocaleString()} ${fmtDelta(r.logins, r.logins_prev)}</td>
      <td class="mono">${Number(r.active_students).toLocaleString()} <span style="color:var(--muted);font-size:12px">/ ${Number(r.enrolled).toLocaleString()} enrolled</span></td>
      <td class="mono">${Number(r.storage_mb).toLocaleString()} MB</td>
      <td>${fmtDate(r.snapshot_date)}</td>
      <td><span class="risk ${esc(r.risk)}">${RISK_LABEL[r.risk] || r.risk}</span></td>
    </tr>`).join('');
}

// ---------- init ----------
document.getElementById('searchInput').addEventListener('input', renderTable);
document.getElementById('riskFilter').addEventListener('change', renderTable);
renderStats();
renderTable();