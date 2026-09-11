// Training & professional development page.

const programOptions = hydrate('program-options', []);
const staffOptions = hydrate('staff-options', []);
const today = new Date().toISOString().slice(0, 10);

function openProgramDrawer(){
  openDrawer(`
    ${drawerHead('New training program', 'Workshop / course / certification / conference.')}
    ${field('Title *', 'prTitle', `<input type="text" id="prTitle" placeholder="e.g. Classroom Assessment Workshop">`)}
    ${field('Type', 'prKind', `<select id="prKind">
      <option value="workshop">Workshop</option>
      <option value="course">Course</option>
      <option value="certification">Certification</option>
      <option value="conference">Conference</option>
    </select>`)}
    ${field('Provider', 'prProvider', `<input type="text" id="prProvider" placeholder="e.g. AKU-IED / TRC">`)}
    ${field('Start date *', 'prStart', `<input type="date" id="prStart" value="${today}">`)}
    ${field('End date', 'prEnd', `<input type="date" id="prEnd">`)}
    ${field('Cost per head (Rs)', 'prCost', `<input type="number" id="prCost" min="0" step="0.01" value="0">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="prBtn" onclick="submitProgram()">Add program</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitProgram(){
  const btn = document.getElementById('prBtn'); btn.disabled = true;
  try{
    await apiPost('/hr/training/programs/create/', {
      title: val('prTitle'), kind: document.getElementById('prKind').value,
      provider: val('prProvider'), start_date: val('prStart'),
      end_date: val('prEnd') || null, cost_per_head: val('prCost') || 0,
    });
    flash('Program added');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}

async function setProgramStatus(programId, status){
  try{
    await apiPost(`/hr/training/programs/${programId}/status/`, { status });
    flash('Program ' + status);
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); }
  }
}

function openEnrollDrawer(){
  if(!programOptions.length){ showToast('Add a program first'); return; }
  openDrawer(`
    ${drawerHead('Enroll staff', 'One enrollment per staff member per program.')}
    ${field('Program', 'eProgram', `<select id="eProgram">${options(programOptions.filter(p => p.status !== 'cancelled').map(p => ({id: p.id, name: p.title})))}</select>`)}
    ${field('Staff member', 'eStaff', `<select id="eStaff">${options(staffOptions)}</select>`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="eBtn" onclick="submitEnroll()">Enroll</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitEnroll(){
  const btn = document.getElementById('eBtn'); btn.disabled = true;
  try{
    await apiPost('/hr/training/enroll/', {
      program_id: Number(document.getElementById('eProgram').value),
      staff_id: Number(document.getElementById('eStaff').value),
    });
    flash('Staff enrolled');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}

async function completeEnrollment(enrollmentId){
  const ref = prompt('Certificate reference (optional):', '');
  if(ref === null){ return; }
  try{
    await apiPost(`/hr/training/enrollments/${enrollmentId}/update/`, {
      status: 'completed', completed_on: today, certificate_ref: ref,
    });
    flash('Training completed');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); }
  }
}

async function dropEnrollment(enrollmentId){
  if(!confirm('Drop this enrollment?')){ return; }
  try{
    await apiPost(`/hr/training/enrollments/${enrollmentId}/update/`, { status: 'dropped' });
    flash('Enrollment dropped');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); }
  }
}

function val(id){ const el = document.getElementById(id); return el ? el.value.trim() : ''; }
