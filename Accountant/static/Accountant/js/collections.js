// Collections page: record fee payments + log defaulter follow-ups.

const defaulters = hydrate('defaulters-data', []);
const openInvoices = hydrate('open-invoices-data', []);

function invoiceOptions(selectedId){
  return `<option value="">Pick an open invoice&hellip;</option>` +
    openInvoices.map(inv =>
      `<option value="${inv.id}" ${inv.id === selectedId ? 'selected' : ''}>` +
      `${esc(inv.student_name)} &mdash; ${esc(inv.period)} &mdash; Rs ${fmtNum(inv.amount - (inv.paid_amount || 0))} due` +
      `</option>`
    ).join('');
}

/* ----- record a fee payment ----- */
function openPayDrawer(invoiceId){
  openDrawer(`
    ${drawerHead('Record fee payment', 'Full or partial payment against an open invoice.')}
    ${field('Invoice', 'payInvoice', `<select id="payInvoice" style="width:100%">${invoiceOptions(invoiceId || null)}</select>`)}
    ${field('Amount (Rs)', 'payAmount', `<input type="number" id="payAmount" min="0" step="0.01" placeholder="e.g. 2800">`)}
    ${field('Method', 'payMethod', `
      <select id="payMethod" style="width:100%">
        <option value="cash">Cash</option>
        <option value="bank">Bank transfer</option>
        <option value="online">Online</option>
        <option value="cheque">Cheque</option>
      </select>`)}
    ${field('Paid on', 'payDate', `<input type="date" id="payDate">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="payBtn" onclick="submitPayment()">Record payment</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('payDate').value = today;
}

async function submitPayment(){
  const invoiceId = document.getElementById('payInvoice').value;
  const amount = document.getElementById('payAmount').value;
  if(!invoiceId){ showToast('Pick an open invoice'); return; }
  if(!amount || Number(amount) <= 0){ showToast('Enter a valid amount'); return; }
  const btn = document.getElementById('payBtn');
  btn.disabled = true;
  try{
    await apiPost('/finance/payments/record/', {
      invoice_id: Number(invoiceId),
      amount: Number(amount),
      method: document.getElementById('payMethod').value,
      paid_on: document.getElementById('payDate').value,
    });
    flash('Payment recorded');
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}

/* ----- log a defaulter follow-up ----- */
function openFollowupDrawer(studentId, studentName){
  openDrawer(`
    ${drawerHead('Log follow-up', studentName ? `Follow-up on ${studentName}.` : 'Record a touchpoint with a defaulter\u2019s family.')}
    ${field('Student', 'fuStudent', `<select id="fuStudent" style="width:100%">
      <option value="">Pick a student&hellip;</option>
      ${defaulters.map(d =>
        `<option value="${d.student_id}" ${d.student_id === studentId ? 'selected' : ''}>${esc(d.student_name)} &mdash; Rs ${fmtNum(d.owed)} owed</option>`
      ).join('')}
    </select>`)}
    ${field('Outcome', 'fuOutcome', `
      <select id="fuOutcome" style="width:100%" onchange="document.getElementById('fuPromised').closest('label').style.display = this.value === 'promised' ? '' : 'none'">
        <option value="called">Called</option>
        <option value="no_answer">No answer</option>
        <option value="promised">Promised to pay</option>
        <option value="visited">Parent visited school</option>
        <option value="settled">Cleared / paid</option>
      </select>`)}
    <label class="formlabel" for="fuPromised" style="display:none">Promised payment date</label>
    <input type="date" id="fuPromised" style="display:none">
    ${field('Note', 'fuNote', `<textarea id="fuNote" rows="3" placeholder="What was agreed?"></textarea>`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="fuBtn" onclick="submitFollowup(${studentId || 'null'})">Log follow-up</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitFollowup(studentId){
  const select = document.getElementById('fuStudent');
  const id = studentId || Number(select.value || 0);
  if(!id){ showToast('Pick a student'); return; }
  const outcome = document.getElementById('fuOutcome').value;
  const promised = document.getElementById('fuPromised').value;
  if(outcome === 'promised' && !promised){ showToast('A promised date is required'); return; }
  const btn = document.getElementById('fuBtn');
  btn.disabled = true;
  try{
    await apiPost('/finance/followups/create/', {
      student_id: id,
      outcome,
      promised_on: promised || null,
      note: document.getElementById('fuNote').value,
    });
    flash('Follow-up logged');
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}
