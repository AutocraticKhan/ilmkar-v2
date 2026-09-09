// Chains page: create groups, create/pick owner logins, assign schools.
const chains = hydrate('chains-data', []);
const schools = hydrate('schools-data', []);

const CSRF = document.body.dataset.csrfToken || '';

const overlay = document.getElementById('overlay');
const drawerEl = document.getElementById('drawer');

function closeDrawer(){ overlay.classList.remove('open'); }
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
    <div class="stat"><div class="label">Owner logins</div><div class="value">${chains.length}</div></div>
  `;
  document.getElementById('subhead').textContent = chains.length
    ? `${chains.length} chain${chains.length===1?'':'s'} \u00b7 owners see only their own branches`
    : 'Create a chain, give it an owner login, then assign schools';
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
      <td>@${esc(c.owner_username)}<span class="loc">${esc(c.owner_email)}</span></td>
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
        <select onchange="assignSchool(${s.id}, this.value)" style="width:auto">
          <option value="">Assign to chain\u2026</option>
          ${chains.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('')}
        </select>
      </td>
    </tr>`).join('');
}

// ---------- drawers ----------

function openNewChainDrawer(){
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div><h2>New chain</h2><div class="loc">a group of schools with one owner login</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>

    <label class="formlabel" for="cName">Chain name</label>
    <input type="text" id="cName" placeholder="e.g. Ilmkar Group of Schools">

    <label class="formlabel" for="cUsername">Owner username</label>
    <input type="text" id="cUsername" placeholder="e.g. groupowner" autocomplete="off">
    <p style="font-size:12px;color:var(--muted);margin:4px 0 0">
      If this username already exists, that account becomes the owner.
      Otherwise a new account is created with the password below.
    </p>

    <label class="formlabel" for="cPassword">Password <span style="color:var(--muted)">(new accounts only)</span></label>
    <input type="password" id="cPassword" placeholder="min. 8 characters" autocomplete="new-password">

    <label class="formlabel" for="cEmail">Owner email</label>
    <input type="text" id="cEmail" placeholder="e.g. owner@group.edu">

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
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div><h2>${esc(c.name)}</h2><div class="loc">owner: @${esc(c.owner_username)} \u00b7 ${c.school_count} branch${c.school_count===1?'':'es'}</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>

    <label class="formlabel" for="cwPassword">Set a new password for @${esc(c.owner_username)}</label>
    <div class="btn-row">
      <input type="password" id="cwPassword" placeholder="min. 8 characters" autocomplete="new-password">
      <button class="btn small" onclick="resetOwnerPassword(${c.id})">Set</button>
    </div>

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
  const username = document.getElementById('cUsername').value.trim();
  if(!name || !username){ showToast('Chain name and owner username are required'); return; }
  const btn = document.getElementById('createChainBtn');
  btn.disabled = true; btn.textContent = 'Creating\u2026';
  try{
    const data = await apiPost('/chains/create/', {
      name,
      owner_username: username,
      owner_password: document.getElementById('cPassword').value,
      owner_email: document.getElementById('cEmail').value.trim(),
    });
    chains.unshift(data.chain);
    renderStats();
    renderTable();
    renderFreeSchools();
    closeDrawer();
    showToast(`${name} created \u2014 @${data.chain.owner_username} can sign in now`);
  }catch(err){
    showToast(err.message);
    btn.disabled = false; btn.textContent = 'Create chain';
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

async function assignSchool(schoolId, chainId){
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
