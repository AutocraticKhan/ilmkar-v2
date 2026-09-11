// Leave approvals: file a request, approve/reject with a note, set
// yearly balances.

const staffOptions = hydrate('staff-options', []);
const today = new Date().toISOString().slice(0, 10);

function openLeaveDrawer(){
  openDrawer(`
    ${drawerHead('File a leave request', 'Recorded on behalf of the staff member; approve it to consume their balance.')}
    ${field('Staff member', 'lStaff', `<select id="lStaff">${options(staffOptions)}</select>`)}
    ${field('From', 'lFrom', `<input type="date" id="lFrom" value="${today}">`)}
    ${field('To', 'lTo', `<input type="date" id="lTo" value="${today}">`)}
    ${field('Reason (include "unpaid" if unpaid)', 'lReason', `<input type="text" id="lReason" placeholder="e.g. family event / unpaid">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="lBtn" onclick="submitLeave()">File request</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitLeave(){
  const btn = document.getElementById('lBtn'); btn.disabled = true;
  try{
    await apiPost('/hr/leaves/create/', {
      staff_id: Number(document.getElementById('lStaff').value),
      from_date: document.getElementById('lFrom').value,
      to_date: document.getElementById('lTo').value,
      reason: document.getElementById('lReason').value,
    });
    flash('Leave request filed');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}

async function decide(leaveId, approve){
  const action = approve ? 'approve' : 'reject';
  const note = prompt(
    approve ? 'Approval note (optional):' : 'Rejection reason (optional):', ''
  );
  if(note === null){ return; }
  try{
    await apiPost(`/hr/leaves/${leaveId}/${action}/`, { note });
    flash(approve ? 'Leave approved' : 'Leave rejected');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); }
  }
}

function openBalanceDrawer(){
  const year = new Date().getFullYear();
  openDrawer(`
    ${drawerHead('Set leave balance', 'Annual entitlement for one staff member (upsert).')}
    ${field('Staff member', 'bStaff', `<select id="bStaff">${options(staffOptions)}</select>`)}
    ${field('Year', 'bYear', `<input type="number" id="bYear" value="${year}" min="2000" max="2100">`)}
    ${field('Entitled days', 'bEntitled', `<input type="number" id="bEntitled" min="0" step="0.5" value="20">`)}
    ${field('Carried over from last year', 'bCarried', `<input type="number" id="bCarried" min="0" step="0.5" value="0">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="bBtn" onclick="submitBalance()">Save balance</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitBalance(){
  const btn = document.getElementById('bBtn'); btn.disabled = true;
  try{
    await apiPost('/hr/balances/create/', {
      staff_id: Number(document.getElementById('bStaff').value),
      year: document.getElementById('bYear').value,
      entitled: document.getElementById('bEntitled').value,
      carried_over: document.getElementById('bCarried').value,
    });
    flash('Leave balance saved');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}
