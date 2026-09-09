// Central hiring: post once for the group, mark filled at a branch.
const jobs = hydrate('jobs-data', []);
const branches = hydrate('branches-data', []);

const overlay = document.getElementById('overlay');
const drawerEl = document.getElementById('drawer');

function closeDrawer(){ overlay.classList.remove('open'); }
overlay.addEventListener('click', e => { if(e.target === overlay) closeDrawer(); });
document.addEventListener('keydown', e => { if(e.key === 'Escape') closeDrawer(); });

function replaceJob(updated){
  const i = jobs.findIndex(j => j.id === updated.id);
  if(i !== -1){ jobs[i] = updated; }
  else { jobs.unshift(updated); }
}

function branchName(id){
  const b = branches.find(x => x.id === id);
  return b ? b.name : '\u2014';
}

function renderStats(){
  const open = jobs.filter(j => j.status === 'open').length;
  const filled = jobs.filter(j => j.status === 'filled').length;
  const hiringBranches = new Set(
    jobs.filter(j => j.status === 'open')
        .map(j => j.preferred_branch_id)
        .filter(v => v != null)
  );
  document.getElementById('subhead').textContent =
    `${open} open posting${open===1?'':'s'} \u00b7 ${filled} filled \u00b7 staff placed at the branch that needs them`;
  document.getElementById('filledStat').textContent = filled;
  document.getElementById('hiringStat').textContent = hiringBranches.size;
  document.getElementById('totalStat').textContent = jobs.length;
}

function renderTable(){
  const body = document.getElementById('tableBody');
  const empty = document.getElementById('emptyState');
  if(jobs.length === 0){
    body.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  body.innerHTML = jobs.map(j => `
    <tr>
      <td class="school-name">${esc(j.title)}${j.description ? `<span class="loc">${esc(j.description.length > 90 ? j.description.slice(0, 90) + '\u2026' : j.description)}</span>` : ''}</td>
      <td>${j.preferred_branch ? esc(j.preferred_branch) : '<em style="color:var(--muted)">any branch</em>'}</td>
      <td><span class="badge st-${esc(j.status)}">${esc(j.status)}</span></td>
      <td>${j.filled_branch ? esc(j.filled_branch) + (j.filled_at ? ` <span class="delta">${esc(j.filled_at)}</span>` : '') : '\u2014'}</td>
      <td class="mono">${esc(j.created_at)}</td>
      <td class="cell-actions">
        ${j.status === 'open'
          ? `<button class="btn small ghost" onclick="openFillDrawer(${j.id})">Mark filled</button>
             <button class="btn small ghost" onclick="deleteJob(${j.id})">Delete</button>`
          : `<button class="btn small ghost" onclick="reopenJob(${j.id})">Reopen</button>`}
      </td>
    </tr>`).join('');
}

// ---------- drawers + actions ----------

function openNewJobDrawer(){
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div><h2>Post a job</h2><div class="loc">one posting, shared with every branch</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>

    <label class="formlabel" for="jTitle">Position</label>
    <input type="text" id="jTitle" placeholder="e.g. Physics teacher \u2014 secondary section">

    <label class="formlabel" for="jBranch">Preferred branch</label>
    <select id="jBranch" style="width:100%">
      <option value="">Any branch that needs them</option>
      ${branches.map(b => `<option value="${b.id}">${esc(b.name)} \u2014 ${esc(b.city)}</option>`).join('')}
    </select>

    <label class="formlabel" for="jDesc">Description</label>
    <textarea id="jDesc" rows="5" placeholder="Requirements, salary band, start date&hellip;"></textarea>

    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="createJobBtn" onclick="createJob()">Publish posting</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>
  `;
  overlay.classList.add('open');
}

function openFillDrawer(jobId){
  const j = jobs.find(x => x.id === jobId);
  if(!j){ return; }
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div><h2>Mark filled</h2><div class="loc">${esc(j.title)}</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>
    <p style="font-size:13px;color:var(--muted);margin-top:6px">
      Where was the position placed? The branch is recorded for the group record.
    </p>

    <label class="formlabel" for="fBranch">Placed at</label>
    <select id="fBranch" style="width:100%">
      <option value="">Select a branch&hellip;</option>
      ${branches.map(b => `<option value="${b.id}" ${j.preferred_branch_id === b.id ? 'selected' : ''}>${esc(b.name)} \u2014 ${esc(b.city)}</option>`).join('')}
    </select>

    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="fillBtn" onclick="fillJob(${jobId})">Record placement</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>
  `;
  overlay.classList.add('open');
}

async function createJob(){
  const title = document.getElementById('jTitle').value.trim();
  if(!title){ showToast('Position is required'); return; }
  const btn = document.getElementById('createJobBtn');
  btn.disabled = true; btn.textContent = 'Publishing\u2026';
  try{
    const data = await apiPost('/chain/hiring/create/', {
      title,
      branch_id: document.getElementById('jBranch').value || null,
      description: document.getElementById('jDesc').value.trim(),
    });
    replaceJob(data.job);
    renderStats();
    renderTable();
    closeDrawer();
    showToast(`\u201c${title}\u201d posted for the whole group`);
  }catch(err){
    showToast(err.message);
    btn.disabled = false; btn.textContent = 'Publish posting';
  }
}

async function fillJob(jobId){
  const branchId = document.getElementById('fBranch').value;
  if(!branchId){ showToast('Pick the branch where the position was filled'); return; }
  const btn = document.getElementById('fillBtn');
  btn.disabled = true;
  try{
    const data = await apiPost(`/chain/hiring/${jobId}/fill/`, { branch_id: branchId });
    replaceJob(data.job);
    renderStats();
    renderTable();
    closeDrawer();
    showToast(`Position filled \u2014 staff placed at ${data.job.filled_branch}`);
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}

async function reopenJob(jobId){
  try{
    const data = await apiPost(`/chain/hiring/${jobId}/reopen/`);
    replaceJob(data.job);
    renderStats();
    renderTable();
    showToast('Posting reopened');
  }catch(err){
    showToast(err.message);
  }
}

async function deleteJob(jobId){
  const j = jobs.find(x => x.id === jobId);
  if(!j){ return; }
  try{
    await apiPost(`/chain/hiring/${jobId}/delete/`);
    const i = jobs.findIndex(x => x.id === jobId);
    if(i !== -1){ jobs.splice(i, 1); }
    renderStats();
    renderTable();
    showToast(`\u201c${j.title}\u201d removed`);
  }catch(err){
    showToast(err.message);
  }
}

renderStats();
renderTable();

