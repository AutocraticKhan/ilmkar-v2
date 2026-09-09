// Approval workflows: branch requests decided centrally by the owner.
const requests = hydrate('requests-data', []);
const branches = hydrate('branches-data', []);

const overlay = document.getElementById('overlay');
const drawerEl = document.getElementById('drawer');

function closeDrawer(){ overlay.classList.remove('open'); }
overlay.addEventListener('click', e => { if(e.target === overlay) closeDrawer(); });
document.addEventListener('keydown', e => { if(e.key === 'Escape') closeDrawer(); });

function replaceReq(updated){
  const i = requests.findIndex(r => r.id === updated.id);
  if(i !== -1){ requests[i] = updated; }
  else { requests.unshift(updated); }
}

const STATUS_BADGE = {
  pending: 'st-pending', approved: 'st-approved', rejected: 'st-rejected',
};
const STATUS_LABEL = {
  pending: 'Pending', approved: 'Approved', rejected: 'Rejected',
};

let currentTab = 'pending';

function renderFeed(){
  const pending = requests.filter(r => r.status === 'pending').length;
  document.getElementById('pendingCount').textContent = pending || '';
  document.getElementById('subhead').textContent = pending
    ? `${pending} request${pending===1?'':'s'} waiting for your decision.`
    : 'No requests are waiting \u2014 all clear.';

  let list = requests;
  if(currentTab === 'pending'){ list = requests.filter(r => r.status === 'pending'); }
  else if(currentTab === 'decided'){ list = requests.filter(r => r.status !== 'pending'); }

  const feed = document.getElementById('feed');
  const empty = document.getElementById('emptyState');
  document.getElementById('emptyTitle').textContent =
    currentTab === 'pending' ? 'No pending requests' : 'Nothing here';
  if(list.length === 0){
    feed.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  feed.innerHTML = list.map(r => `
    <div class="policy-card">
      <div class="pol-head">
        <div>
          <span class="badge type-${esc(r.request_type)}">${esc(r.request_type_display)}</span>
          <span class="badge ${STATUS_BADGE[r.status] || ''}">${STATUS_LABEL[r.status] || esc(r.status)}</span>
          <h3 style="display:inline;margin-left:8px">${esc(r.title)}</h3>
        </div>
        ${r.status === 'pending' ? `
          <span>
            <button class="btn small" onclick="decide(${r.id}, 'approved')">Approve</button>
            <button class="btn small danger" onclick="decide(${r.id}, 'rejected')">Reject</button>
          </span>` : ''}
      </div>
      <p class="pol-value">${esc(r.details) || '<em style="color:var(--muted)">No details provided.</em>'}</p>
      <div class="ann-meta">
        ${esc(r.school_name)} &middot; requested by ${esc(r.requested_by)}
        ${r.amount != null ? ` &middot; <span class="mono">${fmtMoney(r.amount)}</span>` : ''}
        &middot; ${esc(r.created_at)}
        ${r.decided_at ? ` &middot; decided ${esc(r.decided_at)}` : ''}
        ${r.decision_note ? ` &middot; note: ${esc(r.decision_note)}` : ''}
      </div>
    </div>`).join('');
}

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    currentTab = tab.dataset.tab;
    renderFeed();
  });
});

// TODO(placeholder): manual intake until branch principals submit requests
// from their own dashboards.
function openIntakeDrawer(){
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div><h2>Record a branch request</h2><div class="loc">temporary intake until principals have their own dashboard</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>

    <label class="formlabel" for="rBranch">Requesting branch</label>
    <select id="rBranch" style="width:100%">
      <option value="">Select a branch&hellip;</option>
      ${branches.map(b => `<option value="${b.id}">${esc(b.name)} \u2014 ${esc(b.city)}</option>`).join('')}
    </select>

    <label class="formlabel" for="rType">Type</label>
    <select id="rType" style="width:100%">
      <option value="budget">Budget</option>
      <option value="new_hire">New hire</option>
      <option value="other">Other</option>
    </select>

    <label class="formlabel" for="rTitle">Title</label>
    <input type="text" id="rTitle" placeholder="e.g. Science lab budget \u2014 Q3">

    <label class="formlabel" for="rAmount">Amount (optional)</label>
    <input type="number" id="rAmount" min="0" placeholder="e.g. 250000">

    <label class="formlabel" for="rBy">Requested by</label>
    <input type="text" id="rBy" placeholder="e.g. Principal, Branch A">

    <label class="formlabel" for="rDetails">Details</label>
    <textarea id="rDetails" rows="4" placeholder="What is needed and why&hellip;"></textarea>

    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="intakeBtn" onclick="intakeRequest()">Record request</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>
  `;
  overlay.classList.add('open');
}

async function intakeRequest(){
  const branchId = document.getElementById('rBranch').value;
  const title = document.getElementById('rTitle').value.trim();
  if(!branchId){ showToast('Pick the requesting branch'); return; }
  if(!title){ showToast('Request title is required'); return; }
  const btn = document.getElementById('intakeBtn');
  btn.disabled = true;
  try{
    const data = await apiPost('/chain/approvals/create/', {
      school_id: branchId,
      request_type: document.getElementById('rType').value,
      title,
      amount: document.getElementById('rAmount').value || null,
      requested_by: document.getElementById('rBy').value.trim(),
      details: document.getElementById('rDetails').value.trim(),
    });
    replaceReq(data.request);
    renderFeed();
    closeDrawer();
    showToast('Request recorded \u2014 it is now pending your decision');
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}

async function decide(id, decision){
  const note = decision === 'rejected'
    ? (prompt('Rejection note (optional):') || '')
    : '';
  try{
    const data = await apiPost(`/chain/approvals/${id}/decide/`, {
      decision, note,
    });
    replaceReq(data.request);
    renderFeed();
    showToast(`Request ${decision}`);
  }catch(err){
    showToast(err.message);
  }
}

renderFeed();

