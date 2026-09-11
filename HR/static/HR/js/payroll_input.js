// Payroll input page: generate roll-ups, adjust bonus/advance, feed the
// accountant's draft run.

const period = hydrate('period-label', '');

async function generateInputs(){
  if(!confirm('Rebuild this period\'s inputs from attendance + approved leave?\nBonus/advance entries are kept.')){ return; }
  try{
    const data = await apiPost('/hr/payroll-input/generate/', { period });
    flash(`Generated — ${data.created} new, ${data.updated} refreshed`);
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); }
  }
}

function adjustInput(inputId, bonus, advance, note){
  openDrawer(`
    ${drawerHead('Adjust input', 'Attendance numbers come from the grid — use Generate to refresh them.')}
    ${field('Bonus (Rs, added to allowances)', 'adjBonus', `<input type="number" id="adjBonus" min="0" step="0.01" value="${bonus || 0}">`)}
    ${field('Salary advance (Rs, added to deductions)', 'adjAdvance', `<input type="number" id="adjAdvance" min="0" step="0.01" value="${advance || 0}">`)}
    ${field('Note', 'adjNote', `<input type="text" id="adjNote" value="${esc(note || '')}">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="adjBtn" onclick="submitAdjust(${inputId})">Save</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitAdjust(inputId){
  const btn = document.getElementById('adjBtn'); btn.disabled = true;
  try{
    await apiPost(`/hr/payroll-input/${inputId}/update/`, {
      bonus: document.getElementById('adjBonus').value,
      advance: document.getElementById('adjAdvance').value,
      note: document.getElementById('adjNote').value,
    });
    flash('Input adjusted');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}

async function feedPayroll(){
  if(!confirm(`Feed ${period}'s inputs into the finance payroll run?\nCreates/updates the DRAFT run — approval and payout stay with the accountant.`)){ return; }
  try{
    const data = await apiPost('/hr/payroll-input/feed/', { period });
    flash(`Fed ${data.fed} staff into the ${period} draft run`);
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); }
  }
}
