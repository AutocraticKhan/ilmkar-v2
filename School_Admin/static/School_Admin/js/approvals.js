// Approvals page: one decision feed for leave, expense and admission requests.

const leaves = hydrate('leaves-data', []);
const expenses = hydrate('expenses-data', []);
const applications = hydrate('applications-data', []);
const staffData = hydrate('staff-data', []);
const sections = hydrate('sections-data', []);

const STATUS_BADGE = { pending: 'pending', approved: 'approved', rejected: 'rejected', waitlisted: 'waitlisted' };
const STATUS_LABEL = { pending: 'Pending', approved: 'Approved', rejected: 'Rejected', waitlisted: 'Waitlisted' };

function buildRequests(){
  return [
    ...leaves.map(l => ({
      id: l.id, kind: 'leave', kind_label: 'Leave',
      title: `${l.staff_name} \u2014 leave`,
      detail: `${l.from_date} \u2192 ${l.to_date}`,
      body: l.reason && l.reason !== '\u2014' ? l.reason : '',
      amount: null, requested_by: '\u2014',
      status: l.status, note: l.decision_note, created: l.created_at,
      url: '/school/approvals/leave/' + l.id + '/decide/',
    })),
    ...expenses.map(e => ({
      id: e.id, kind: 'expense', kind_label: 'Expense',
      title: e.title,
      detail: 'requested by ' + e.requested_by,
      body: e.details,
      amount: e.amount, requested_by: e.requested_by,
      status: e.status, note: e.decision_note, created: e.created_at,
      url: '/school/approvals/expenses/' + e.id + '/decide/',
    })),
    ...applications.map(a => ({
      id: a.id, kind: 'admission', kind_label: 'Admission',
      title: a.applicant_name,
      detail: 'applied for ' + (a.class_section !== '\u2014' ? a.class_section : 'unassigned class'),
      body: a.note,
      amount: null, requested_by: a.guardian_name,
      status: a.status, note: a.decision_note, created: a.created_at,
      url: '/school/students/admissions/' + a.id + '/decide/',
    })),
  ];
}

let currentTab = 'pending';
let requests = buildRequests();

function renderFeed(){
  const pending = requests.filter(r => r.status === 'pending').length;
  document.getElementById('pendingCount').textContent = pending || '';
  document.getElementById('subhead').textContent = pending
    ? `${pending} request${pending === 1 ? '' : 's'} waiting for your decision.`
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
    <div class="feed-card">
      <div class="f-head">
        <div>
          <span class="badge activity">${esc(r.kind_label)}</span>
          <span class="badge ${STATUS_BADGE[r.status] || 'inactive'}">${STATUS_LABEL[r.status] || esc(r.status)}</span>
          <h3 style="display:inline;margin-left:8px">${esc(r.title)}</h3>
        </div>
        ${r.status === 'pending' ? `
          <span class="btn-row">
            <button class="btn small" onclick="decide('${r.kind}', ${r.id}, 'approved')">Approve</button>
            <button class="btn small danger" onclick="decide('${r.kind}', ${r.id}, 'rejected')">Reject</button>
          </span>` : ''}
      </div>
      <div class="f-body">${esc(r.body) || '<em style="color:var(--muted)">No details provided.</em>'}</div>
      <div class="f-meta">
        ${r.kind === 'expense' ? '<span class="mono">' + fmtMoney(r.amount) + '</span> &middot; ' : ''}
        ${esc(r.detail)} &middot; ${esc(r.created)}
        ${r.note ? ' &middot; note: ' + esc(r.note) : ''}
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

async function decide(kind, id, decision){
  let url;
  if(kind === 'admission'){ url = `/school/students/admissions/${id}/decide/`; }
  else if(kind === 'leave'){ url = `/school/approvals/leave/${id}/decide/`; }
  else { url = `/school/approvals/expenses/${id}/decide/`; }
  const note = decision === 'rejected'
    ? (prompt('Rejection note (optional):') || '')
    : '';
  try{
    await apiPost(url, { decision, note });
    flash(`Request ${decision}`);
    location.reload();
  }catch(err){ showToast(err.message); }
}

/* ----- manual intake drawers ----- */
function sectionOptions(selectedId){
  return `<option value="">No class assigned</option>` +
    sections.map(s =>
      `<option value="${s.id}" ${String(s.id) === String(selectedId) ? 'selected' : ''}>${esc(s.label)}</option>`
    ).join('');
}

function staffOptions(){
  return `<option value="">Pick a staff member&hellip;</option>` +
    staffData.map(s =>
      `<option value="${s.id}">${esc(s.full_name)}</option>`
    ).join('');
}

function openLeaveDrawer(){
  openDrawer(`
    ${drawerHead('Record leave request', 'TODO(integration): the teacher app will submit these itself later.')}
    <label class="formlabel" for="lvStaff">Staff member</label>
    <select id="lvStaff" style="width:100%">${staffOptions()}</select>
    <label class="formlabel" for="lvFrom">From</label>
    <input type="date" id="lvFrom">
    <label class="formlabel" for="lvTo">To</label>
    <input type="date" id="lvTo">
    <label class="formlabel" for="lvReason">Reason</label>
    <input type="text" id="lvReason" placeholder="e.g. Medical leave">
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="lvBtn" onclick="submitLeave()">Save request</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitLeave(){
  const staffId = document.getElementById('lvStaff').value;
  if(!staffId){ showToast('Pick a staff member'); return; }
  const btn = document.getElementById('lvBtn');
  btn.disabled = true;
  try{
    await apiPost('/school/approvals/leave/create/', {
      staff_id: staffId,
      from_date: document.getElementById('lvFrom').value,
      to_date: document.getElementById('lvTo').value,
      reason: document.getElementById('lvReason').value.trim(),
    });
    flash('Leave request recorded');
    closeDrawer();
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}

function openExpenseDrawer(){
  openDrawer(`
    ${drawerHead('Record expense request', 'Request an expense for your approval.')}
    <label class="formlabel" for="exTitle">Title</label>
    <input type="text" id="exTitle" placeholder="e.g. Science lab consumables">
    <label class="formlabel" for="exAmount">Amount (Rs)</label>
    <input type="number" id="exAmount" min="0" placeholder="e.g. 15000">
    <label class="formlabel" for="exBy">Requested by</label>
    <input type="text" id="exBy" placeholder="e.g. Lab teacher">
    <label class="formlabel" for="exDetails">Details</label>
    <textarea id="exDetails" rows="3" placeholder="What is needed and why..."></textarea>
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="exBtn" onclick="submitExpense()">Save request</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitExpense(){
  const title = document.getElementById('exTitle').value.trim();
  if(!title){ showToast('Expense title is required'); return; }
  const btn = document.getElementById('exBtn');
  btn.disabled = true;
  try{
    await apiPost('/school/approvals/expenses/create/', {
      title,
      amount: document.getElementById('exAmount').value,
      requested_by: document.getElementById('exBy').value.trim(),
      details: document.getElementById('exDetails').value.trim(),
    });
    flash('Expense request recorded');
    closeDrawer();
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}

function openOwnerRequestDrawer(){
  openDrawer(`
    ${drawerHead('Request owner approval', 'Sent to the group owner\u2019s approval feed — they decide centrally.')}
    <label class="formlabel" for="orType">Type</label>
    <select id="orType" style="width:100%">
      <option value="budget">Budget</option>
      <option value="new_hire">New hire</option>
      <option value="other">Other</option>
    </select>
    <label class="formlabel" for="orTitle">Title</label>
    <input type="text" id="orTitle" placeholder="e.g. Additional lab budget for Q3">
    <label class="formlabel" for="orAmount">Amount (Rs, optional)</label>
    <input type="number" id="orAmount" min="0" placeholder="e.g. 250000">
    <label class="formlabel" for="orDetails">Details</label>
    <textarea id="orDetails" rows="3" placeholder="What is needed and why..."></textarea>
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="orBtn" onclick="submitOwnerRequest()">Send to owner</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitOwnerRequest(){
  const title = document.getElementById('orTitle').value.trim();
  if(!title){ showToast('Request title is required'); return; }
  const btn = document.getElementById('orBtn');
  btn.disabled = true;
  try{
    await apiPost('/school/approvals/owner/create/', {
      request_type: document.getElementById('orType').value,
      title,
      amount: document.getElementById('orAmount').value,
      details: document.getElementById('orDetails').value.trim(),
    });
    flash('Request sent to the group owner');
    closeDrawer();
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}

function openAdmissionDrawer(){
  openDrawer(`
    ${drawerHead('Record admission application', 'For parents applying for the new term.')}
    <label class="formlabel" for="apName">Applicant name</label>
    <input type="text" id="apName" placeholder="e.g. Hamza Ali">
    <label class="formlabel" for="apClass">Applied class</label>
    <select id="apClass" style="width:100%">${sectionOptions('')}</select>
    <label class="formlabel" for="apGuardian">Guardian name</label>
    <input type="text" id="apGuardian" placeholder="e.g. Mr. Ali Raza">
    <label class="formlabel" for="apPhone">Guardian phone</label>
    <input type="text" id="apPhone" placeholder="e.g. 0300 1234567">
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="apBtn" onclick="submitAdmissionHere()">Save application</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitAdmissionHere(){
  const name = document.getElementById('apName').value.trim();
  if(!name){ showToast('Applicant name is required'); return; }
  const btn = document.getElementById('apBtn');
  btn.disabled = true;
  try{
    await apiPost('/school/students/admissions/create/', {
      applicant_name: name,
      class_section_id: document.getElementById('apClass').value || null,
      guardian_name: document.getElementById('apGuardian').value.trim(),
      guardian_phone: document.getElementById('apPhone').value.trim(),
    });
    flash('Admission application recorded');
    closeDrawer();
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}
renderFeed();