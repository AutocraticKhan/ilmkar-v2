// Fees page: fee heads, invoice issue, payment recording.

const heads = hydrate('fee-heads-data', []);
const studentsData = hydrate('students-data', []);
const invoices = hydrate('invoices-data', []);
const sections = hydrate('sections-data', []);

function sectionOptions(selectedId){
  return `<option value="">All classes</option>` +
    sections.map(s =>
      `<option value="${s.id}" ${String(s.id) === String(selectedId) ? 'selected' : ''}>${esc(s.label)}</option>`
    ).join('');
}

function studentOptions(selectedId){
  return `<option value="">Pick a student&hellip;</option>` +
    studentsData.map(s =>
      `<option value="${s.id}" ${String(s.id) === String(selectedId) ? 'selected' : ''}>${esc(s.full_name)} &mdash; ${esc(s.class_section)}</option>`
    ).join('');
}

function headOptions(selectedId){
  return `<option value="">Student&rsquo;s monthly fee</option>` +
    heads.filter(h => h.is_active).map(h =>
      `<option value="${h.id}" ${String(h.id) === String(selectedId) ? 'selected' : ''}>${esc(h.name)} &mdash; Rs ${h.amount}</option>`
    ).join('');
}

/* ----- fee heads ----- */
function openHeadDrawer(){
  openDrawer(`
    ${drawerHead('Add fee head', 'One row per chargeable head (tuition, transport, exam fee, ...).')}
    <label class="formlabel" for="fhName">Head name</label>
    <input type="text" id="fhName" placeholder="e.g. Tuition">
    <label class="formlabel" for="fhClass">Applies to class</label>
    <select id="fhClass" style="width:100%">${sectionOptions('')}</select>
    <label class="formlabel" for="fhAmount">Amount (Rs)</label>
    <input type="number" id="fhAmount" min="0" placeholder="e.g. 2500">
    <label class="formlabel" for="fhFreq">Frequency</label>
    <select id="fhFreq" style="width:100%">
      <option value="monthly">Monthly</option>
      <option value="one_time">One time</option>
      <option value="annual">Annual</option>
    </select>
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="fhBtn" onclick="submitHead()">Add fee head</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitHead(){
  const name = document.getElementById('fhName').value.trim();
  if(!name){ showToast('Fee head name is required'); return; }
  const btn = document.getElementById('fhBtn');
  btn.disabled = true;
  try{
    await apiPost('/school/fees/heads/create/', {
      name,
      class_section_id: document.getElementById('fhClass').value || null,
      amount: document.getElementById('fhAmount').value,
      frequency: document.getElementById('fhFreq').value,
    });
    flash('Fee head added');
    closeDrawer();
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}

async function deleteHead(headId){
  try{
    await apiPost(`/school/fees/heads/${headId}/delete/`, {});
    flash('Fee head deactivated');
    location.reload();
  }catch(err){ showToast(err.message); }
}

/* ----- invoice issuance ----- */
function openInvoiceDrawer(){
  openDrawer(`
    ${drawerHead('Issue an invoice', 'Amount defaults to the student&rsquo;s monthly fee or the chosen head.')}
    <label class="formlabel" for="ivStudent">Student</label>
    <select id="ivStudent" style="width:100%">${studentOptions('')}</select>
    <label class="formlabel" for="ivHead">Fee head (optional)</label>
    <select id="ivHead" style="width:100%">${headOptions('')}</select>
    <label class="formlabel" for="ivAmount">Amount (Rs, optional)</label>
    <input type="number" id="ivAmount" min="0" placeholder="Leave blank to auto-fill">
    <label class="formlabel" for="ivPeriod">Period</label>
    <input type="text" id="ivPeriod" value="${new Date().toLocaleString('en-US', { month:'long', year:'numeric' })}">
    <label class="formlabel" for="ivDue">Due date</label>
    <input type="date" id="ivDue">
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="ivBtn" onclick="submitInvoice()">Issue invoice</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitInvoice(){
  const studentId = document.getElementById('ivStudent').value;
  if(!studentId){ showToast('Pick a student'); return; }
  const btn = document.getElementById('ivBtn');
  btn.disabled = true;
  try{
    await apiPost('/school/fees/invoices/create/', {
      student_id: studentId,
      fee_head_id: document.getElementById('ivHead').value || null,
      amount: document.getElementById('ivAmount').value,
      period: document.getElementById('ivPeriod').value.trim(),
      due_date: document.getElementById('ivDue').value,
    });
    flash('Invoice issued');
    closeDrawer();
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
/* ----- payments ----- */
function openPayDrawer(invoiceId){
  const inv = invoices.find(i => String(i.id) === String(invoiceId));
  if(!inv){ return; }
  const outstanding = Number(inv.amount) - Number(inv.paid_amount || 0);
  openDrawer(`
    ${drawerHead('Record payment', `${esc(inv.student_name)} \u2014 ${esc(inv.period)}`)}
    <div class="feed-card" style="border-left-color:var(--amber)">
      Amount Rs ${Number(inv.amount).toLocaleString()} &middot; paid Rs ${Number(inv.paid_amount || 0).toLocaleString()}
      <div class="f-meta">Outstanding: <b>Rs ${outstanding.toLocaleString()}</b></div>
    </div>
    <label class="formlabel" for="payAmount">Amount (Rs)</label>
    <input type="number" id="payAmount" min="0.01" step="any" placeholder="e.g. ${outstanding}">
    <label class="formlabel" for="payMethod">Method</label>
    <select id="payMethod" style="width:100%">
      <option value="cash">Cash</option>
      <option value="bank">Bank transfer</option>
      <option value="online">Online</option>
      <option value="cheque">Cheque</option>
    </select>
    <label class="formlabel" for="payDate">Payment date</label>
    <input type="date" id="payDate" value="${new Date().toISOString().slice(0,10)}">
    <label class="formlabel" for="payBy">Received by</label>
    <input type="text" id="payBy" placeholder="e.g. Front desk">
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="payBtn" onclick="submitPayment(${invoiceId})">Record payment</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitPayment(invoiceId){
  const amount = document.getElementById('payAmount').value;
  if(!amount || Number(amount) <= 0){ showToast('Enter a valid amount'); return; }
  const btn = document.getElementById('payBtn');
  btn.disabled = true;
  try{
    await apiPost(`/school/fees/invoices/${invoiceId}/pay/`, {
      amount,
      method: document.getElementById('payMethod').value,
      paid_on: document.getElementById('payDate').value,
      received_by: document.getElementById('payBy').value.trim(),
    });
    flash('Payment recorded');
    closeDrawer();
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}
}