// ---------- data (hydrated from the server) ----------
const schoolsEl = document.getElementById('schools-data');
let schools = schoolsEl ? JSON.parse(schoolsEl.textContent) : [];

// Chains (school groups) for the assign-to-chain option in the add-school
// drawer. Managed fully on the Chains page.
const chainsEl = document.getElementById('chains-data');
let chains = chainsEl ? JSON.parse(chainsEl.textContent) : [];

const CSRF = document.body.dataset.csrfToken || '';

function esc(value){
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

let sortKey = "name", sortDir = 1;

const fmtMoney = n => "$" + Number(n || 0).toLocaleString();
const fmtDate = d => d
  ? new Date(d + "T00:00:00").toLocaleDateString('en-US',{ month:'short', day:'numeric', year:'numeric' })
  : '\u2014';

// ---------- api ----------
async function apiPost(url, payload){
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': CSRF
    },
    body: JSON.stringify(payload || {})
  });
  const data = await res.json().catch(() => ({}));
  if(!res.ok){
    throw new Error(data.error || 'Something went wrong');
  }
  return data;
}

function replaceSchool(updated){
  const i = schools.findIndex(s => s.id === updated.id);
  if(i !== -1) schools[i] = updated;
}

// ---------- rendering ----------
function renderStats(){
  const total = schools.length;
  const active = schools.filter(s=>s.status==='active').length;
  const trial = schools.filter(s=>s.status==='trial').length;
  const mrr = schools.filter(s=>s.status!=='suspended').reduce((a,s)=>a+s.mrr,0);
  const pct = total ? ((active/total)*100).toFixed(0) + '% of registry' : '\u2014';
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="label">Schools on platform</div><div class="value">${total}</div></div>
    <div class="stat"><div class="label">Active subscriptions</div><div class="value">${active}</div><div class="delta">${esc(pct)}</div></div>
    <div class="stat"><div class="label">In trial</div><div class="value">${trial}</div></div>
    <div class="stat"><div class="label">Monthly recurring revenue</div><div class="value">${fmtMoney(mrr)}</div></div>
  `;
  document.getElementById('subhead').textContent = total
    ? `${total} schools \u00b7 ${fmtMoney(mrr)} MRR under management`
    : 'The registry is empty \u2014 add your first school to get started';
}

function getFiltered(){
  const q = document.getElementById('searchInput').value.trim().toLowerCase();
  const pkg = document.getElementById('packageFilter').value;
  const stat = document.getElementById('statusFilter').value;
  let list = schools.filter(s=>{
    const matchesQ = !q || s.name.toLowerCase().includes(q) || s.city.toLowerCase().includes(q);
    const matchesPkg = pkg==='all' || s.package===pkg;
    const matchesStat = stat==='all' || s.status===stat;
    return matchesQ && matchesPkg && matchesStat;
  });
  list.sort((a,b)=>{
    let av=a[sortKey], bv=b[sortKey];
    if(av == null){ av = ''; }
    if(bv == null){ bv = ''; }
    if(typeof av === 'string') { av=av.toLowerCase(); bv=bv.toLowerCase(); }
    if(av<bv) return -1*sortDir;
    if(av>bv) return 1*sortDir;
    return 0;
  });
  return list;
}

function renderTable(){
  const list = getFiltered();
  const body = document.getElementById('tableBody');
  const empty = document.getElementById('emptyState');
  document.querySelectorAll('.arrow').forEach(a=>a.textContent='');
  const arrowEl = document.querySelector(`[data-arrow="${sortKey}"]`);
  if(arrowEl) arrowEl.textContent = sortDir===1 ? '\u2191' : '\u2193';

  if(list.length===0){
    body.innerHTML = '';
    if(schools.length === 0){
      document.getElementById('emptyTitle').textContent = 'No schools yet';
      document.getElementById('emptyText').textContent = 'Click \u201cAdd school\u201d to create your first registry entry.';
    } else {
      document.getElementById('emptyTitle').textContent = 'No schools match this filter';
      document.getElementById('emptyText').textContent = 'Try a different search term or clear a filter.';
    }
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  body.innerHTML = list.map(s=>`
    <tr onclick="openDetail(${s.id})">
      <td class="school-name">${esc(s.name)}<span class="loc">${esc(s.city)}${s.chain_name ? ` \u00b7 <span class="badge chain-tag">${esc(s.chain_name)}</span>` : ''}</span></td>
      <td><span class="badge ${esc(s.package.toLowerCase())}">${esc(s.package)}</span></td>
      <td class="mono">${Number(s.students).toLocaleString()}</td>
      <td class="mono">${fmtMoney(s.mrr)}</td>
      <td>${fmtDate(s.renewal)}</td>
      <td><span class="status ${esc(s.status)}"><span class="dot"></span>${esc(s.status.charAt(0).toUpperCase()+s.status.slice(1))}</span></td>
    </tr>
  `).join('');
}

function renderAll(){ renderStats(); renderTable(); }

// ---------- sorting ----------
document.querySelectorAll('thead th').forEach(th=>{
  th.addEventListener('click', ()=>{
    const key = th.dataset.key;
    if(sortKey===key){ sortDir *= -1; } else { sortKey = key; sortDir = 1; }
    renderTable();
  });
});

document.getElementById('searchInput').addEventListener('input', renderTable);
document.getElementById('packageFilter').addEventListener('change', renderTable);
document.getElementById('statusFilter').addEventListener('change', renderTable);

// ---------- toast ----------
function showToast(msg){
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(()=>t.classList.remove('show'), 2200);
}

// ---------- drawer: detail ----------
const overlay = document.getElementById('overlay');
const drawerEl = document.getElementById('drawer');

function closeDrawer(){ overlay.classList.remove('open'); }
overlay.addEventListener('click', e=>{ if(e.target===overlay) closeDrawer(); });
document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeDrawer(); });

function openDetail(id){
  const s = schools.find(x=>x.id===id);
  if(!s) return;
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div>
        <h2>${esc(s.name)}</h2>
        <div class="loc">${esc(s.city)}</div>
      </div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>

    <div class="field-grid">
      <div class="field"><span class="k">Chain</span><span class="v">${s.chain_name ? `<span class="badge chain-tag">${esc(s.chain_name)}</span>` : '<span style="color:var(--muted)">none</span>'}</span></div>
      <div class="field"><span class="k">Package</span><span class="v"><span class="badge ${esc(s.package.toLowerCase())}">${esc(s.package)}</span></span></div>
      <div class="field"><span class="k">Status</span><span class="v"><span class="status ${esc(s.status)}"><span class="dot"></span>${esc(s.status.charAt(0).toUpperCase()+s.status.slice(1))}</span></span></div>
      <div class="field"><span class="k">Students enrolled</span><span class="v mono">${Number(s.students).toLocaleString()}</span></div>
      <div class="field"><span class="k">Monthly recurring revenue</span><span class="v mono">${fmtMoney(s.mrr)}</span></div>
      <div class="field"><span class="k">Renewal date</span><span class="v">${fmtDate(s.renewal)}</span></div>
      <div class="field"><span class="k">Primary contact</span><span class="v">${esc(s.contact)}</span></div>
    </div>
    <div class="field"><span class="k">Contact email</span><span class="v mono" style="font-weight:400">${esc(s.email)}</span></div>

    <div class="section-title">Change package</div>
    <select id="pkgChange" style="width:100%">
      <option ${s.package==='Starter'?'selected':''}>Starter</option>
      <option ${s.package==='Growth'?'selected':''}>Growth</option>
      <option ${s.package==='Enterprise'?'selected':''}>Enterprise</option>
    </select>
    <div class="btn-row">
      <button class="btn small" onclick="applyPackage(${s.id})">Save package</button>
    </div>

    <div class="section-title">Account controls</div>
    <div class="btn-row">
      ${s.status!=='active' ? `<button class="btn small" onclick="setStatus(${s.id},'active')">Activate</button>` : ''}
      ${s.status!=='trial' ? `<button class="btn small ghost" onclick="setStatus(${s.id},'trial')">Move to trial</button>` : ''}
      ${s.status!=='suspended' ? `<button class="btn small danger" onclick="setStatus(${s.id},'suspended')">Suspend</button>` : ''}
    </div>

    <div class="section-title">Support</div>
    <div class="btn-row">
      <button class="btn small" id="impersonateBtn" onclick="impersonateSchool(${s.id})">Log in as school</button>
    </div>

    <div class="section-title">Danger zone</div>
    <div class="btn-row">
      <button class="btn small danger" onclick="requestDeleteSchool(${s.id})">Remove from registry</button>
    </div>
    <div class="warning-box" id="deleteConfirm" style="display:none">
      <p><strong>Warning:</strong> this permanently deletes <strong>${esc(s.name)}</strong> and everything linked to it &mdash; including <strong>${s.users ?? 0}</strong> user account${(s.users ?? 0) === 1 ? '' : 's'}. This cannot be undone.</p>
      <div class="btn-row">
        <button class="btn small danger" onclick="removeSchool(${s.id})">Yes, delete everything</button>
        <button class="btn small ghost" onclick="cancelDeleteSchool()">Cancel</button>
      </div>
    </div>
  `;
  overlay.classList.add('open');
}

function requestDeleteSchool(id){
  const box = document.getElementById('deleteConfirm');
  if(box) box.style.display = 'block';
}

function cancelDeleteSchool(){
  const box = document.getElementById('deleteConfirm');
  if(box) box.style.display = 'none';
}

async function impersonateSchool(id){
  const btn = document.getElementById('impersonateBtn');
  const s = schools.find(x=>x.id===id);
  if(!s || !btn) return;
  if(btn.dataset.armed !== '1'){
    btn.dataset.armed = '1';
    btn.textContent = `Confirm: sign in as ${s.name}`;
    setTimeout(() => {
      if(btn){ btn.dataset.armed = '0'; btn.textContent = 'Log in as school'; }
    }, 4000);
    return;
  }
  btn.disabled = true;
  btn.textContent = 'Signing in\u2026';
  try{
    const data = await apiPost(`/impersonate/${id}/start/`, { note: 'support session from school detail' });
    window.location.href = data.redirect || '/workspace/';
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
    btn.dataset.armed = '0';
    btn.textContent = 'Log in as school';
  }
}

async function applyPackage(id){
  const s = schools.find(x=>x.id===id);
  if(!s) return;
  const newPkg = document.getElementById('pkgChange').value;
  try{
    const data = await apiPost(`/schools/${id}/package/`, { package: newPkg });
    replaceSchool(data.school);
    renderAll();
    closeDrawer();
    showToast(`${s.name} moved to ${newPkg}`);
  }catch(err){
    showToast(err.message);
  }
}

async function setStatus(id, status){
  const s = schools.find(x=>x.id===id);
  if(!s) return;
  try{
    const data = await apiPost(`/schools/${id}/status/`, { status });
    replaceSchool(data.school);
    renderAll();
    closeDrawer();
    showToast(`${s.name} marked ${status}`);
  }catch(err){
    showToast(err.message);
  }
}

async function removeSchool(id){
  const s = schools.find(x=>x.id===id);
  if(!s) return;
  try{
    const data = await apiPost(`/schools/${id}/delete/`);
    schools = schools.filter(x=>x.id!==id);
    renderAll();
    closeDrawer();
    const n = data.deleted_users ?? 0;
    showToast(`${s.name} removed \u2014 ${n} user account${n===1?'':'s'} deleted`);
  }catch(err){
    showToast(err.message);
  }
}

// ---------- drawer: add school ----------
function openNewSchoolDrawer(){
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div><h2>Add a school</h2><div class="loc">Create a new registry entry</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>

    <label class="formlabel" for="nName">School name</label>
    <input type="text" id="nName" placeholder="e.g. Oakview Middle School">

    <label class="formlabel" for="nCity">City, state</label>
    <input type="text" id="nCity" placeholder="e.g. Tampa, FL">

    <label class="formlabel" for="nPkg">Package</label>
    <select id="nPkg" style="width:100%">
      <option>Starter</option><option>Growth</option><option>Enterprise</option>
    </select>

    <label class="formlabel" for="nStudents">Students enrolled</label>
    <input type="number" id="nStudents" placeholder="e.g. 500" min="0">

    <label class="formlabel" for="nRenewal">Renewal date</label>
    <input type="date" id="nRenewal">

    <label class="formlabel" for="nContact">Primary contact</label>
    <input type="text" id="nContact" placeholder="e.g. A. Rossi">

    <label class="formlabel" for="nEmail">Contact email</label>
    <input type="text" id="nEmail" placeholder="e.g. a.rossi@school.edu">

    <label class="formlabel" for="nChain">Chain / owner group</label>
    <select id="nChain" style="width:100%">
      <option value="">No chain (independent school)</option>
      ${chains.map(c => `<option value="${c.id}">${esc(c.name)} — owner @${esc(c.owner_username)}</option>`).join('')}
    </select>
    ${chains.length === 0 ? '<p style="font-size:12px;color:var(--muted);margin:4px 0 0">No chains yet — create one on the Chains page.</p>' : ''}

    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="createSchoolBtn" onclick="createSchool()">Add to registry</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>
  `;
  overlay.classList.add('open');
}

async function createSchool(){
  const name = document.getElementById('nName').value.trim();
  const city = document.getElementById('nCity').value.trim();
  if(!name || !city){ showToast('School name and city are required'); return; }
  const pkg = document.getElementById('nPkg').value;
  const students = parseInt(document.getElementById('nStudents').value) || 0;
  const renewal = document.getElementById('nRenewal').value || null;
  const contact = document.getElementById('nContact').value.trim();
  const email = document.getElementById('nEmail').value.trim();
  const chainId = document.getElementById('nChain').value || null;

  const btn = document.getElementById('createSchoolBtn');
  if(btn){ btn.disabled = true; btn.textContent = 'Adding\u2026'; }

  try{
    const data = await apiPost('/schools/create/', { name, city, package: pkg, students, renewal, contact, email, chain_id: chainId });
    schools.push(data.school);
    renderAll();
    closeDrawer();
    showToast(`${name} added to the registry`);
  }catch(err){
    showToast(err.message);
    if(btn){ btn.disabled = false; btn.textContent = 'Add to registry'; }
  }
}

renderAll();
