// Shared helpers for every chain-owner page (loaded before the page script).

const CSRF = document.body.dataset.csrfToken || '';

function esc(value){
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function hydrate(id, fallback){
  const el = document.getElementById(id);
  return el ? JSON.parse(el.textContent) : fallback;
}

function showToast(msg){
  const t = document.getElementById('toast');
  if(!t){ return; }
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(()=>t.classList.remove('show'), 2200);
}

async function apiPost(url, payload){
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
    body: JSON.stringify(payload || {})
  });
  const data = await res.json().catch(() => ({}));
  if(!res.ok){ throw new Error(data.error || 'Something went wrong'); }
  return data;
}

const fmtMoney = n => 'Rs ' + Number(n || 0).toLocaleString();
const fmtPct = v => (v == null ? '\u2014' : Number(v).toFixed(1) + '%');
const fmtNum = n => Number(n || 0).toLocaleString();
const fmtDate = d => d
  ? new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' })
  : '\u2014';

const LIGHT_LABEL = { green: 'Green', yellow: 'Yellow', red: 'Red', none: 'No data' };

function lightDot(state){
  return `<span class="light ${esc(state)}"></span>${LIGHT_LABEL[state] || state}`;
}
