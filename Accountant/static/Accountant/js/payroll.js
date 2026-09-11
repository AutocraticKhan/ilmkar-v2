// Payroll page: create runs, calculate, edit pay lines, approve, mark paid.

const payrollItems = hydrate('payroll-items-data', []);
const currentPeriod = hydrate('current-period-data', '');

/* ----- open a new payroll run ----- */
function openPeriodDrawer(){
  openDrawer(`
    ${drawerHead('New payroll run', 'One run per billing period (e.g. ' + esc(currentPeriod) + ').')}
    ${field('Period', 'ppPeriod', `<input type="text" id="ppPeriod" value="${esc(currentPeriod)}" placeholder="e.g. September 2026">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="ppBtn" onclick="submitPeriod()">Open run</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitPeriod(){
  const period = document.getElementById('ppPeriod').value.trim();
  if(!period){ showToast('Enter a period label'); return; }
  const btn = document.getElementById('ppBtn');
  btn.disabled = true;
  try{
    const data = await apiPost('/finance/payroll/periods/create/', { period });
    flash('Payroll run opened');
    location.href = '/finance/payroll/?period=' + data.period.id;
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}

/* ----- calculate (draft runs only) ----- */
async function calculateRun(periodId){
  try{
    const data = await apiPost(`/finance/payroll/periods/${periodId}/calculate/`);
    flash('Calculated — ' + data.created + ' new pay line(s)');
    location.reload();
  }catch(err){
    showToast(err.message);
  }
}

/* ----- approve / mark paid ----- */
async function approveRun(periodId){
  if(!confirm('Approve this run? Pay lines are frozen until payout.')){ return; }
  try{
    await apiPost(`/finance/payroll/periods/${periodId}/approve/`);
    flash('Payroll approved');
    location.reload();
  }catch(err){
    showToast(err.message);
  }
}

async function markPaid(periodId){
  if(!confirm('Mark this run as PAID? Salary expenses and payslip history are written now.')){ return; }
  try{
    await apiPost(`/finance/payroll/periods/${periodId}/paid/`);
    flash('Payroll marked as paid');
    location.reload();
  }catch(err){
    showToast(err.message);
  }
}

/* ----- edit a pay line ----- */
function openItemDrawer(itemId){
  const item = payrollItems.find(i => i.id === itemId);
  if(!item){ showToast('Item not found'); return; }
  openDrawer(`
    ${drawerHead('Edit pay line', item.staff_name + ' — ' + esc(currentPeriod))}
    ${field('Basic (Rs)', 'piBasic', `<input type="number" id="piBasic" min="0" step="0.01" value="${item.basic}">`)}
    ${field('Allowances (Rs)', 'piAllow', `<input type="number" id="piAllow" min="0" step="0.01" value="${item.allowances}">`)}
    ${field('Deductions (Rs)', 'piDeduct', `<input type="number" id="piDeduct" min="0" step="0.01" value="${item.deductions}">`)}
    <div class="small-note" style="margin-top:8px">Net pay: <b class="mono" id="piNet">${fmtMoney(item.net_pay)}</b></div>
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="piBtn" onclick="submitItem(${item.id})">Save line</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
  ['piBasic', 'piAllow', 'piDeduct'].forEach(id =>
    document.getElementById(id).addEventListener('input', updateNet)
  );
}

function updateNet(){
  const val = id => Number(document.getElementById(id).value || 0);
  document.getElementById('piNet').textContent =
    fmtMoney(val('piBasic') + val('piAllow') - val('piDeduct'));
}

async function submitItem(itemId){
  const btn = document.getElementById('piBtn');
  btn.disabled = true;
  try{
    await apiPost(`/finance/payroll/items/${itemId}/update/`, {
      basic: document.getElementById('piBasic').value,
      allowances: document.getElementById('piAllow').value,
      deductions: document.getElementById('piDeduct').value,
    });
    flash('Pay line updated');
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}
