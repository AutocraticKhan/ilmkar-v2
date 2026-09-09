// Group-wide policies: create once, applies to all branches, with optional
// per-branch overrides.
const policies = hydrate('policies-data', []);
const branches = hydrate('branches-data', []);

const overlay = document.getElementById('overlay');
const drawerEl = document.getElementById('drawer');

function closeDrawer(){ overlay.classList.remove('open'); }
overlay.addEventListener('click', e => { if(e.target === overlay) closeDrawer(); });
document.addEventListener('keydown', e => { if(e.key === 'Escape') closeDrawer(); });

function replacePolicy(updated){
  const i = policies.findIndex(p => p.id === updated.id);
  if(i !== -1){ policies[i] = updated; }
  else { policies.unshift(updated); }
}

const CATEGORY_LABEL = {
  fee_structure: 'Fee structure',
  leave_policy: 'Leave policy',
  other: 'Other',
};

function renderFeed(){
  document.getElementById('subhead').textContent =
    `${policies.length} polic${policies.length===1?'y':'ies'} applied group-wide.`;
  const feed = document.getElementById('feed');
  const empty = document.getElementById('emptyState');
  if(policies.length === 0){
    feed.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  feed.innerHTML = policies.map(p => {
    const overridden = p.overrides.map(o => o.school_id);
    return `
      <div class="policy-card">
        <div class="pol-head">
          <div>
            <span class="badge one-branch">${esc(CATEGORY_LABEL[p.category] || p.category)}</span>
            <h3 style="display:inline;margin-left:8px">${esc(p.name)}</h3>
          </div>
          <button class="close-btn" title="Delete policy" onclick="deletePolicy(${p.id})">&times;</button>
        </div>
        <p class="pol-value">${esc(p.default_value) || '<em style="color:var(--muted)">No group default written \u2014 branches decide their own.</em>'}</p>

        <div class="override-list">
          ${p.overrides.map(o => `
            <div class="override-row">
              <span class="school">${esc(o.school_name)}</span>
              <span style="flex:1;color:var(--muted)">\u2192 ${esc(o.value)}</span>
              <button class="btn small ghost" onclick="removeOverride(${p.id}, ${o.school_id})">Remove override</button>
            </div>`).join('')}
          ${branches.filter(b => !overridden.includes(b.id)).map(b => `
            <div class="override-row">
              <span class="school">${esc(b.name)}</span>
              <span style="flex:1;color:var(--muted)">follows group default</span>
              <button class="btn small ghost" onclick="openOverrideDrawer(${p.id}, ${b.id})">Override</button>
            </div>`).join('')}
        </div>
        <div class="ann-meta" style="margin-top:12px">created ${esc(p.created_at)}</div>
      </div>`;
  }).join('');
}

// ---------- drawers ----------

function openNewPolicyDrawer(){
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div><h2>New group policy</h2><div class="loc">applies to every branch at once</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>

    <label class="formlabel" for="pName">Policy name</label>
    <input type="text" id="pName" placeholder="e.g. Monthly tuition 2026">

    <label class="formlabel" for="pCategory">Category</label>
    <select id="pCategory" style="width:100%">
      <option value="fee_structure">Fee structure</option>
      <option value="leave_policy">Leave policy</option>
      <option value="other">Other</option>
    </select>

    <label class="formlabel" for="pValue">Group default</label>
    <textarea id="pValue" rows="5" placeholder="e.g. Tuition Rs 3,500/month; sibling discount 15%; leave 12 paid days/year&hellip;"></textarea>

    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="createBtn" onclick="createPolicy()">Create policy</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>
  `;
  overlay.classList.add('open');
}

function openOverrideDrawer(policyId, branchId){
  const p = policies.find(x => x.id === policyId);
  if(!p){ return; }
  const branch = branches.find(b => b.id === branchId);
  const existing = p.overrides.find(o => o.school_id === branchId);
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div><h2>Override for ${esc(branch ? branch.name : '')}</h2><div class="loc">policy: ${esc(p.name)}</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>
    <p style="font-size:13px;color:var(--muted);margin-top:6px">
      The group default stays in place for every other branch.
    </p>

    <label class="formlabel" for="oValue">This branch's value</label>
    <textarea id="oValue" rows="5" placeholder="e.g. Tuition Rs 3,000/month for this branch only">${esc(existing ? existing.value : '')}</textarea>

    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="saveOverrideBtn" onclick="saveOverride(${policyId}, ${branchId})">${existing ? 'Update override' : 'Apply override'}</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>
  `;
  overlay.classList.add('open');
}

// ---------- actions ----------

async function createPolicy(){
  const name = document.getElementById('pName').value.trim();
  if(!name){ showToast('Policy name is required'); return; }
  const btn = document.getElementById('createBtn');
  btn.disabled = true; btn.textContent = 'Creating\u2026';
  try{
    const data = await apiPost('/chain/policies/create/', {
      name,
      category: document.getElementById('pCategory').value,
      default_value: document.getElementById('pValue').value.trim(),
    });
    replacePolicy(data.policy);
    renderFeed();
    closeDrawer();
    showToast(`\u201c${name}\u201d applies to all ${branches.length} branch${branches.length===1?'':'es'}`);
  }catch(err){
    showToast(err.message);
    btn.disabled = false; btn.textContent = 'Create policy';
  }
}

async function saveOverride(policyId, branchId){
  const value = document.getElementById('oValue').value.trim();
  if(!value){ showToast('Override value is required'); return; }
  const btn = document.getElementById('saveOverrideBtn');
  btn.disabled = true;
  try{
    const data = await apiPost(`/chain/policies/${policyId}/override/`, {
      school_id: branchId, value,
    });
    replacePolicy(data.policy);
    renderFeed();
    closeDrawer();
    showToast('Override applied \u2014 other branches keep the group default');
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}

async function removeOverride(policyId, branchId){
  try{
    const data = await apiPost(`/chain/policies/${policyId}/override/delete/`, {
      school_id: branchId,
    });
    replacePolicy(data.policy);
    renderFeed();
    showToast('Override removed \u2014 branch follows the group default again');
  }catch(err){
    showToast(err.message);
  }
}

async function deletePolicy(id){
  const p = policies.find(x => x.id === id);
  if(!p){ return; }
  try{
    await apiPost(`/chain/policies/${id}/delete/`);
    const i = policies.findIndex(x => x.id === id);
    if(i !== -1){ policies.splice(i, 1); }
    renderFeed();
    showToast(`\u201c${p.name}\u201d deleted everywhere (including overrides)`);
  }catch(err){
    showToast(err.message);
  }
}

renderFeed();


