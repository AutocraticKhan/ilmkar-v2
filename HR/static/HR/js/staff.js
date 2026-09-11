// Staff directory page: hire, contracts, activate/deactivate.

const staffRows = hydrate('staff-data', []);
const today = new Date().toISOString().slice(0, 10);

function openHireDrawer(){
  openDrawer(`
    ${drawerHead('Hire staff', 'Creates the directory entry, first contract and onboarding checklist.')}
    ${field('Full name *', 'hName', `<input type="text" id="hName" placeholder="e.g. Ayesha Khan">`)}
    ${field('Designation', 'hDesig', `<input type="text" id="hDesig" placeholder="e.g. Senior Teacher">`)}
    ${field('Department', 'hDept', `<input type="text" id="hDept" placeholder="e.g. Secondary">`)}
    ${field('Phone', 'hPhone', `<input type="text" id="hPhone">`)}
    ${field('Email', 'hEmail', `<input type="email" id="hEmail">`)}
    ${field('Join date', 'hJoin', `<input type="date" id="hJoin" value="${today}">`)}
    ${field('Contract type', 'hKind', `<select id="hKind">
      <option value="permanent">Permanent</option>
      <option value="probation">Probation</option>
      <option value="contract">Fixed-term contract</option>
      <option value="part_time">Part-time</option>
      <option value="visiting">Visiting</option>
    </select>`)}
    ${field('Monthly salary (Rs)', 'hSalary', `<input type="number" id="hSalary" min="0" step="0.01" placeholder="0">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="hBtn" onclick="submitHire()">Hire</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitHire(){
  const payload = {
    full_name: val('hName'), designation: val('hDesig'), department: val('hDept'),
    phone: val('hPhone'), email: val('hEmail'), join_date: val('hJoin'),
    contract_kind: val('hKind'), monthly_salary: val('hSalary') || 0,
  };
  if(!payload.full_name){ showToast('Full name is required'); return; }
  const btn = document.getElementById('hBtn'); btn.disabled = true;
  try{
    const data = await apiPost('/hr/staff/create/', payload);
    flash('Hired ' + data.member.full_name + ' — onboarding checklist created');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}

function openContractDrawer(){
  openDrawer(`
    ${drawerHead('Add / renew contract', 'The previous active contract is closed automatically.')}
    ${field('Staff member', 'cStaff', `<select id="cStaff">${options(staffRows.filter(s => s.is_active).map(s => ({id: s.id, name: s.full_name})))}</select>`)}
    ${field('Contract type', 'cKind', `<select id="cKind">
      <option value="permanent">Permanent</option>
      <option value="probation">Probation</option>
      <option value="contract">Fixed-term contract</option>
      <option value="part_time">Part-time</option>
      <option value="visiting">Visiting</option>
    </select>`)}
    ${field('Start date', 'cStart', `<input type="date" id="cStart" value="${today}">`)}
    ${field('End date (optional)', 'cEnd', `<input type="date" id="cEnd">`)}
    ${field('Monthly salary (Rs)', 'cSalary', `<input type="number" id="cSalary" min="0" step="0.01" placeholder="0">`)}
    ${field('Notes', 'cNotes', `<input type="text" id="cNotes" placeholder="Terms, probation period...">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="cBtn" onclick="submitContract()">Save contract</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitContract(){
  const payload = {
    staff_id: Number(val('cStaff')), kind: val('cKind'), start_date: val('cStart'),
    end_date: val('cEnd') || null, monthly_salary: val('cSalary') || 0, notes: val('cNotes'),
  };
  const btn = document.getElementById('cBtn'); btn.disabled = true;
  try{
    await apiPost('/hr/contracts/create/', payload);
    flash('Contract saved');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}

async function toggleStaff(id, name){
  if(!confirm((name) + ': switch active status?')){ return; }
  try{
    await apiPost(`/hr/staff/${id}/toggle/`);
    flash('Staff status updated');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); }
  }
}

function val(id){ const el = document.getElementById(id); return el ? el.value.trim() : ''; }
