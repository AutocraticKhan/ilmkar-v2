// Chains page: create groups (name only), pick an owner account, assign schools.
const chains = hydrate('chains-data', []);
const schools = hydrate('schools-data', []);
const users = hydrate('users-data', []);

const CSRF = document.body.dataset.csrfToken || '';

// ---------- shared helpers (self-contained, like every other page script) ----------
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
  if(!el){ return fallback; }
  try{ return JSON.parse(el.textContent); }catch(e){ return fallback; }
}

function showToast(msg){
  const t = document.getElementById('toast');
  if(!t){ return; }
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(()=>t.classList.remove('show'), 2200);
}

const overlay = document.getElementById('overlay');
const drawerEl = document.getElementById('drawer');

// School remembered when the drawer was opened from the “Assign to chain…
// → + New chain…” dropdown; it is assigned to the chain as soon as the
// chain is created. Cleared whenever the drawer closes for any reason.
let pendingAssignSchoolId = null;

function closeDrawer(){
  pendingAssignSchoolId = null;
  overlay.classList.remove('open');
}
overlay.addEventListener('click', e => { if(e.target === overlay) closeDrawer(); });
document.addEventListener('keydown', e => { if(e.key === 'Escape') closeDrawer(); });

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

function replaceSchool(updated){
  const i = schools.findIndex(s => s.id === updated.id);
  if(i !== -1){ schools[i] = updated; }
}

function freeSchools(){
  return schools.filter(s => !s.chain_id);
}

// ---------- rendering ----------

function renderStats(){
  const branchTotal = chains.reduce((a, c) => a + c.school_count, 0);
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="label">Chains</div><div class="value">${chains.length}</div></div>
    <div class="stat"><div class="label">Branches in groups</div><div class="value">${branchTotal}</div></div>
    <div class="stat"><div class="label">Independent schools</div><div class="value">${freeSchools().length}</div></div>
    <div class="stat"><div class="label">Chains with an owner</div><div class="value">${chains.filter(c => c.owner_username).length}</div></div>
  `;
  document.getElementById('subhead').textContent = chains.length
    ? `${chains.length} chain${chains.length===1?'':'s'} \u00b7 assign an owner login from here or the Users page`
    : 'Create a chain, assign schools to it, then pick an owner account';
}

function renderTable(){
  const body = document.getElementById('tableBody');
  const empty = document.getElementById('emptyState');
  if(chains.length === 0){
    body.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  body.innerHTML = chains.map(c => `
    <tr onclick="openChainDrawer(${c.id})">
      <td class="school-name">${esc(c.name)}<span class="loc">${c.school_count} branch${c.school_count===1?'':'es'}</span></td>
      <td>${c.owner_username ? `@${esc(c.owner_username)}<span class="loc">${esc(c.owner_email)}</span>` : '<span style="color:var(--muted)">no owner yet</span>'}</td>
      <td>${c.school_count}</td>
      <td class="mono">${esc(c.created_at)}</td>
    </tr>`).join('');
}

function renderFreeSchools(){
  const body = document.getElementById('freeSchoolsBody');
  const empty = document.getElementById('freeEmpty');
  const free = freeSchools();
  if(free.length === 0){
    body.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  body.innerHTML = free.map(s => `
    <tr>
      <td class="school-name">${esc(s.name)}<span class="loc">${esc(s.city)}</span></td>
      <td><span class="badge ${s.package.toLowerCase()}">${esc(s.package)}</span></td>
      <td class="cell-actions">
        <select onchange="onAssignSelect(${s.id}, this.value)" style="width:auto">
          <option value="">Assign to chain\u2026</option>
          ${chains.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('')}
          <option value="__new__">+ New chain\u2026</option>
        </select>
      </td>
    </tr>`).join('');
}

// ---------- drawers ----------

function openNewChainDrawer(presetSchoolId){
  pendingAssignSchoolId = presetSchoolId || null;
  const presetSchool = pendingAssignSchoolId
    ? schools.find(s => s.id === pendingAssignSchoolId) : null;
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div><h2>New chain</h2><div class="loc">a group of schools under one name</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>

    ${presetSchool ? `<p style="font-size:13px;color:var(--muted);margin:0 0 14px"><strong>${esc(presetSchool.name)}</strong> will be assigned to this chain as soon as it is created.</p>` : ''}

    <label class="formlabel" for="cName">Chain name</label>
    <input type="text" id="cName" placeholder="e.g. Ilmkar Group of Schools">

    <p style="font-size:12px;color:var(--muted);margin:14px 0 0">
      Only a name is needed. Create the owner account on the Users page,
      then assign it to this chain afterwards (from that account's row or
      this chain's page).
    </p>

    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="createChainBtn" onclick="createChain()">Create chain</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>
  `;
  overlay.classList.add('open');
}

function openChainDrawer(chainId){
  const c = chains.find(x => x.id === chainId);
  if(!c){ return; }
  const memberIds = c.school_ids;
  const ownerBlock = c.owner_username ? `
    <div class="section-title" style="border-top:none;padding-top:10px">Owner login</div>
    <p style="font-size:13px;color:var(--muted);margin:0 0 10px">
      @${esc(c.owner_username)} &middot; ${esc(c.owner_email)}
    </p>
    <label class="formlabel" for="cwPassword">Set a new password for @${esc(c.owner_username)}</label>
    <div class="btn-row">
      <input type="password" id="cwPassword" placeholder="min. 8 characters" autocomplete="new-password">
      <button class="btn small" onclick="resetOwnerPassword(${c.id})">Set</button>
    </div>
    <div class="btn-row" style="margin-top:12px">
      <button class="btn small ghost" onclick="clearChainOwner(${c.id})">Remove owner</button>
    </div>
  ` : `
    <div class="section-title" style="border-top:none;padding-top:10px">Owner login</div>
    <p style="font-size:13px;color:var(--muted);margin:0 0 10px">
      No owner yet &mdash; pick an account created on the Users page.
    </p>
    <div class="btn-row">
      <select id="cwOwner" style="flex:1">
        <option value="">Pick a user&hellip;</option>
        ${users.map(u => `<option value="${u.id}">@${esc(u.username)}${u.chain_id ? ' (owns another chain \u2014 moves it here)' : ''}</option>`).join('')}
      </select>
      <button class="btn small" onclick="setChainOwner(${c.id})">Assign owner</button>
    </div>
  `;
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div><h2>${esc(c.name)}</h2><div class="loc">${c.owner_username ? `owner: @${esc(c.owner_username)}` : 'no owner yet'} \u00b7 ${c.school_count} branch${c.school_count===1?'':'es'}</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>

    ${ownerBlock}

    <div class="section-title" style="border-top:none;padding-top:10px">Branches in this chain</div>
    <div class="override-list">
      ${c.school_ids.map(id => {
        const s = schools.find(x => x.id === id);
        if(!s){ return ''; }
        return `
          <div class="override-row">
            <span class="school">${esc(s.name)}</span>
            <span style="flex:1;color:var(--muted)">${esc(s.city)} \u00b7 ${s.students} students</span>
            <button class="btn small ghost" onclick="unassignSchool(${s.id})">Remove</button>
          </div>`;
      }).join('') || '<p style="color:var(--muted);font-size:13px">No branches assigned yet.</p>'}
    </div>

    <label class="formlabel" for="cwSchool">Assign a school</label>
    <div class="btn-row">
      <select id="cwSchool" style="flex:1">
        <option value="">Pick a school&hellip;</option>
        ${schools.filter(s => !memberIds.includes(s.id))
          .map(s => `<option value="${s.id}">${esc(s.name)} \u2014 ${esc(s.city)}${s.chain_id ? ' (moves from its chain)' : ''}</option>`)
          .join('')}
      </select>
      <button class="btn small" onclick="assignToChain(${c.id})">Assign</button>
    </div>

    <div class="warning-box">
      <p>Deleting the chain does not delete schools &mdash; they return to
      &ldquo;no chain&rdquo;. The owner login stays active but can no longer
      sign in to a dashboard.</p>
      <button class="btn danger" onclick="deleteChain(${c.id})">Delete chain</button>
    </div>
  `;
  overlay.classList.add('open');
}

// ---------- actions ----------

async function createChain(){
  const name = document.getElementById('cName').value.trim();
  if(!name){ showToast('Chain name is required'); return; }
  const btn = document.getElementById('createChainBtn');
  btn.disabled = true; btn.textContent = 'Creating\u2026';
  try{
    const data = await apiPost('/chains/create/', { name });
    chains.unshift(data.chain);

    // If the drawer was opened from the “+ New chain…” dropdown option,
    // attach that school to the fresh chain right away.
    let extra = '';
    if(pendingAssignSchoolId){
      const schoolId = pendingAssignSchoolId;
      pendingAssignSchoolId = null;
      try{
        const a = await apiPost(`/chains/${data.chain.id}/assign/`, { school_id: schoolId });
        replaceSchool(a.school);
        const c = chains.find(x => x.id === data.chain.id);
        if(c){ c.school_count = (c.school_count || 0) + 1; c.school_ids.push(schoolId); }
        extra = ` \u00b7 ${a.school.name} assigned`;
      }catch(assignErr){
        showToast(assignErr.message);  // chain exists — just report the assign failure
      }
    }

    renderStats();
    renderTable();
    renderFreeSchools();
    closeDrawer();
    showToast(`${name} created \u2014 assign schools and an owner login next${extra}`);
  }catch(err){
    showToast(err.message);
    if(btn){ btn.disabled = false; btn.textContent = 'Create chain'; }
  }
}

async function assignToChain(chainId){
  const select = document.getElementById('cwSchool');
  const schoolId = parseInt(select.value, 10);
  if(!schoolId){ showToast('Pick a school to assign'); return; }
  try{
    const data = await apiPost(`/chains/${chainId}/assign/`, { school_id: schoolId });
    replaceSchool(data.school);
    const c = chains.find(x => x.id === chainId);
    if(c){ c.school_count = (c.school_count || 0) + 1; c.school_ids.push(schoolId); }
    renderStats();
    renderTable();
    renderFreeSchools();
    openChainDrawer(chainId);   // refresh the drawer contents
    showToast(`${data.school.name} assigned to ${data.chain.name}`);
  }catch(err){
    showToast(err.message);
  }
}

function onAssignSelect(schoolId, value){
  if(value === '__new__'){
    openNewChainDrawer(schoolId);
    return;
  }
  if(value){ assignSchool(schoolId, parseInt(value, 10)); }
}

async function assignSchool(schoolId, chainId){
  chainId = parseInt(chainId, 10);  // select values arrive as strings
  if(!chainId){ return; }
  try{
    const data = await apiPost(`/chains/${chainId}/assign/`, { school_id: schoolId });
    replaceSchool(data.school);
    const c = chains.find(x => x.id === chainId);
    if(c){ c.school_count = (c.school_count || 0) + 1; c.school_ids.push(schoolId); }
    renderStats();
    renderTable();
    renderFreeSchools();
    showToast(`${data.school.name} assigned to ${data.chain.name}`);
  }catch(err){
    showToast(err.message);
  }
}

async function unassignSchool(schoolId){
  try{
    const data = await apiPost(`/schools/${schoolId}/unassign/`);
    replaceSchool(data.school);
    chains.forEach(c => {
      c.school_ids = c.school_ids.filter(id => id !== schoolId);
      c.school_count = c.school_ids.length;
    });
    renderStats();
    renderTable();
    renderFreeSchools();
    showToast(`${data.school.name} removed from its chain`);
  }catch(err){
    showToast(err.message);
  }
}

async function resetOwnerPassword(chainId){
  const password = document.getElementById('cwPassword').value;
  if(!password){ showToast('Enter the new password first'); return; }
  try{
    const data = await apiPost(`/chains/${chainId}/owner-password/`, { password });
    showToast(`Password updated for @${data.owner}`);
    document.getElementById('cwPassword').value = '';
  }catch(err){
    showToast(err.message);
  }
}

function replaceChain(updated){
  const i = chains.findIndex(c => c.id === updated.id);
  if(i !== -1){ chains[i] = { ...chains[i], ...updated }; }
}

async function setChainOwner(chainId){
  const select = document.getElementById('cwOwner');
  const userId = parseInt(select.value, 10);
  if(!userId){ showToast('Pick a user account first'); return; }
  const u = users.find(x => x.id === userId);
  const c = chains.find(x => x.id === chainId);
  // Warn when the account already owns another chain, or when the chain
  // already has an owner picked from a different account.
  if(u && u.chain_id && u.chain_id !== chainId){
    const prev = chains.find(x => x.id === u.chain_id);
    if(!confirm(`@${u.username} already owns "${prev ? prev.name : 'another chain'}". Move that ownership to "${c ? c.name : 'this chain'}"?`)){
      return;
    }
  } else if(c && c.owner_id){
    if(!confirm(`"${c.name}" is currently owned by @${c.owner_username}. Replace that owner?`)){
      return;
    }
  }
  try{
    const data = await apiPost(`/chains/${chainId}/owner/`, { owner_id: userId });
    replaceChain(data.chain);
    if(u){ u.chain_id = chainId; }
    renderStats();
    renderTable();
    openChainDrawer(chainId);
    showToast(`${data.chain.name} owner is now @${data.chain.owner_username}`);
  }catch(err){
    showToast(err.message);
  }
}

async function clearChainOwner(chainId){
  const c = chains.find(x => x.id === chainId);
  if(c && c.owner_username && !confirm(`Remove @${c.owner_username} as owner of "${c.name}"? The account itself is not deleted.`)){
    return;
  }
  try{
    const data = await apiPost(`/chains/${chainId}/owner/`, { owner_id: null });
    replaceChain(data.chain);
    const u = users.find(x => x.id === data.chain.owner_id);
    if(u){ u.chain_id = null; }
    renderStats();
    renderTable();
    openChainDrawer(chainId);
    showToast(`${data.chain.name} has no owner now`);
  }catch(err){
    showToast(err.message);
  }
}

async function deleteChain(chainId){
  const c = chains.find(x => x.id === chainId);
  if(!c){ return; }
  try{
    await apiPost(`/chains/${chainId}/delete/`);
    const i = chains.findIndex(x => x.id === chainId);
    if(i !== -1){ chains.splice(i, 1); }
    // Schools of this chain are back to "no chain".
    schools.forEach(s => {
      if(s.chain_id === chainId){ s.chain_id = null; s.chain_name = null; }
    });
    renderStats();
    renderTable();
    renderFreeSchools();
    closeDrawer();
    showToast(`${c.name} deleted \u2014 schools returned to the free pool`);
  }catch(err){
    showToast(err.message);
  }
}


renderStats();
renderTable();
renderFreeSchools();
