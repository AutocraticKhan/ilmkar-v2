// Refunds page: log refund/adjustment requests + the approve/reject/paid
// flow (approvals by a second person only — enforced server-side too).

const students = hydrate('students-data', []);
const refunds = hydrate('refunds-data', []);

function openRefundDrawer(){
  openDrawer(`
    ${drawerHead('Log refund / adjustment', 'A request only — someone else must approve before money moves.')}
    ${field('Student', 'rfStudent', `<select id="rfStudent" style="width:100%">
      <option value="">Pick a student&hellip;</option>
      ${students.map(s =>
        `<option value="${s.id}">${esc(s.name)} &mdash; ${esc(s.class)}</option>`
      ).join('')}
    </select>`)}
    ${field('Kind', 'rfKind', `
      <select id="rfKind" style="width:100%">
        <option value="refund">Refund</option>
        <option value="adjustment">Adjustment</option>
      </select>`)}
    ${field('Amount (Rs)', 'rfAmount', `<input type="number" id="rfAmount" min="0" step="0.01" placeholder="e.g. 1200">`)}
    ${field('Reason', 'rfReason', `<textarea id="rfReason" rows="3" placeholder="Why is this owed back? (becomes part of the audit trail)"></textarea>`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="rfBtn" onclick="submitRefund()">Log request</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitRefund(){
  const studentId = Number(document.getElementById('rfStudent').value || 0);
  const amount = document.getElementById('rfAmount').value;
  const reason = document.getElementById('rfReason').value.trim();
  if(!studentId){ showToast('Pick a student'); return; }
  if(!amount || Number(amount) <= 0){ showToast('Enter a valid amount'); return; }
  if(!reason){ showToast('A reason is required'); return; }
  const btn = document.getElementById('rfBtn');
  btn.disabled = true;
  try{
    await apiPost('/finance/refunds/create/', {
      student_id: studentId,
      kind: document.getElementById('rfKind').value,
      amount: Number(amount),
      reason,
    });
    flash('Refund request logged');
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}

async function approveRefund(refundId){
  const note = prompt('Approval note (optional):') || '';
  try{
    await apiPost(`/finance/refunds/${refundId}/approve/`, { note });
    flash('Refund approved');
    location.reload();
  }catch(err){
    showToast(err.message);
  }
}

async function rejectRefund(refundId){
  const note = prompt('Why is this being rejected?');
  if(!note){ showToast('A rejection reason is required'); return; }
  try{
    await apiPost(`/finance/refunds/${refundId}/reject/`, { note });
    flash('Refund rejected');
    location.reload();
  }catch(err){
    showToast(err.message);
  }
}

async function markRefundPaid(refundId){
  if(!confirm('Mark as PAID? Money leaves the school and the ledger is updated.')){ return; }
  try{
    await apiPost(`/finance/refunds/${refundId}/paid/`);
    flash('Refund marked as paid');
    location.reload();
  }catch(err){
    showToast(err.message);
  }
}
