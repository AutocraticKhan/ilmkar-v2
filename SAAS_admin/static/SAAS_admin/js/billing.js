// ---------- data (hydrated from the server) ----------
const invoicesEl = document.getElementById('invoices-data');
let invoices = invoicesEl ? JSON.parse(invoicesEl.textContent) : [];

const schoolsEl = document.getElementById('schools-data');
const schools = schoolsEl ? JSON.parse(schoolsEl.textContent) : [];

const CSRF = document.body.dataset.csrfToken || '';

function esc(value){
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const fmtMoney = n => "$" + Number(n || 0).toLocaleString();
const fmtDate = d => d
  ? new Date(d + "T00:00:00").toLocaleDateString('en-US',{ month:'short', day:'numeric', year:'numeric' })
  : '\u2014';

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

function showToast(msg){
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(()=>t.classList.remove('show'), 2200);
}

const overlay = document.getElementById('overlay');
const drawerEl = document.getElementById('drawer');
function closeDrawer(){ overlay.classList.remove('open'); }
overlay.addEventListener('click', e=>{ if(e.target===overlay) closeDrawer(); });
document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeDrawer(); });

// ---------- filters ----------
function populateSchoolFilter(){
  const sel = document.getElementById('schoolFilter');
  sel.innerHTML = '<option value="all">All schools</option>' +
    schools.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join('');
}

function getFiltered(){
  const school = document.getElementById('schoolFilter').value;
  const status = document.getElementById('statusFilter').value;
  return invoices.filter(i =>
    (school === 'all' || String(i.school_id) === school) &&
    (status === 'all' || i.status === status)
  );
}

// ---------- rendering ----------
function renderStats(){
  const total = invoices.length;
  const unpaid = invoices.filter(i => i.status === 'unpaid');
  const overdue = invoices.filter(i => i.status === 'overdue');
  const outstanding = unpaid.concat(overdue).reduce((a,i)=>a+i.amount, 0);
  const mrr = schools.filter(s=>s.status!=='suspended').reduce((a,s)=>a+s.mrr,0);
  const openCount = unpaid.length + overdue.length;
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="label">Monthly recurring revenue</div><div class="value">${fmtMoney(mrr)}</div></div>
    <div class="stat"><div class="label">Outstanding (who owes you)</div><div class="value">${fmtMoney(outstanding)}</div><div class="delta down">${openCount} invoice${openCount===1?'':'s'} open</div></div>
    <div class="stat"><div class="label">Overdue invoices</div><div class="value" style="color:var(--red)">${overdue.length}</div></div>
    <div class="stat"><div class="label">Invoices issued</div><div class="value">${total}</div></div>
  `;
  document.getElementById('subhead').textContent =
    `${total} invoice${total===1?'':'s'} across ${schools.length} school${schools.length===1?'':'s'} \u00b7 ${fmtMoney(outstanding)} outstanding`;
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
  body.innerHTML = list.map(i => `
    <tr onclick="openInvoice(${i.id})">
      <td class="school-name">${esc(i.school_name)}<span class="loc">${esc((schools.find(s=>s.id===i.school_id)||{}).city || '')}</span></td>
      <td>${esc(i.period)}</td>
      <td class="mono">${fmtMoney(i.amount)}</td>
      <td>${fmtDate(i.due_date)}</td>
      <td><span class="badge inv-${esc(i.status)}">${esc(i.status.charAt(0).toUpperCase()+i.status.slice(1))}</span></td>
      <td class="cell-actions">${i.status !== 'paid' ? `<button class="btn small" onclick="event.stopPropagation();markPaid(${i.id})">Mark paid</button>` : ''}</td>
    </tr>`).join('');
}

function renderAll(){ renderStats(); renderTable(); }

// ---------- drawer ----------
function openInvoice(id){
  const i = invoices.find(x=>x.id===id);
  if(!i) return;
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div><h2>${esc(i.school_name)}</h2><div class="loc">${esc(i.period)} invoice</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>
    <div class="field-grid">
      <div class="field"><span class="k">Amount</span><span class="v mono">${fmtMoney(i.amount)}</span></div>
      <div class="field"><span class="k">Status</span><span class="v"><span class="badge inv-${esc(i.status)}">${esc(i.status)}</span></span></div>
      <div class="field"><span class="k">Due date</span><span class="v">${fmtDate(i.due_date)}</span></div>
      <div class="field"><span class="k">Paid on</span><span class="v">${fmtDate(i.paid_at)}</span></div>
    </div>
    <div class="btn-row" style="margin-top:22px">
      ${i.status !== 'paid' ? `<button class="btn" onclick="markPaid(${i.id})">Mark as paid</button>` : ''}
      <button class="btn ghost" onclick="closeDrawer()">Close</button>
    </div>
  `;
  overlay.classList.add('open');
}

async function markPaid(id){
  const i = invoices.find(x=>x.id===id);
  if(!i) return;
  try{
    const data = await apiPost(`/invoices/${id}/paid/`);
    const idx = invoices.findIndex(x=>x.id===id);
    if(idx !== -1) invoices[idx] = data.invoice;
    renderAll();
    closeDrawer();
    showToast(`${i.school_name} \u00b7 ${i.period} marked paid`);
  }catch(err){
    showToast(err.message);
  }
}

// ---------- init ----------
document.getElementById('schoolFilter').addEventListener('change', renderTable);
document.getElementById('statusFilter').addEventListener('change', renderTable);
populateSchoolFilter();
renderAll();
