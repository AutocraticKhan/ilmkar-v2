// Students page: admissions intake/decisions + student records.

const students = hydrate('students-data', []);
const applications = hydrate('applications-data', []);
const sections = hydrate('sections-data', []);

function sectionOptions(selectedId){
  return `<option value="">No class assigned</option>` +
    sections.map(s =>
      `<option value="${s.id}" ${String(s.id) === String(selectedId) ? 'selected' : ''}>${esc(s.label)}</option>`
    ).join('');
}

/* ----- add student ----- */
function openStudentDrawer(){
  openDrawer(`
    ${drawerHead('Add a student', 'Direct admission — creates a student record straight away.')}
    <label class="formlabel" for="stName">Full name</label>
    <input type="text" id="stName" placeholder="e.g. Ayesha Khan">
    <label class="formlabel" for="stAdm">Admission number (blank = auto)</label>
    <input type="text" id="stAdm" placeholder="e.g. ADM-2026-0001">
    <label class="formlabel" for="stClass">Class / section</label>
    <select id="stClass" style="width:100%">${sectionOptions('')}</select>
    <label class="formlabel" for="stGuardian">Guardian name</label>
    <input type="text" id="stGuardian" placeholder="e.g. Mr. Imran Khan">
    <label class="formlabel" for="stPhone">Guardian phone</label>
    <input type="text" id="stPhone" placeholder="e.g. 0300 1234567">
    <label class="formlabel" for="stFee">Monthly fee (Rs)</label>
    <input type="number" id="stFee" min="0" placeholder="e.g. 2500">
    <label class="formlabel" for="stDate">Admission date</label>
    <input type="date" id="stDate" value="${new Date().toISOString().slice(0,10)}">
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="stBtn" onclick="submitStudent()">Add student</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitStudent(){
  const name = document.getElementById('stName').value.trim();
  if(!name){ showToast('Student name is required'); return; }
  const btn = document.getElementById('stBtn');
  btn.disabled = true;
  try{
    await apiPost('/school/students/create/', {
      full_name: name,
      admission_no: document.getElementById('stAdm').value.trim(),
      class_section_id: document.getElementById('stClass').value || null,
      guardian_name: document.getElementById('stGuardian').value.trim(),
      guardian_phone: document.getElementById('stPhone').value.trim(),
      monthly_fee: document.getElementById('stFee').value,
      admission_date: document.getElementById('stDate').value,
    });
    flash('Student added');
    closeDrawer();
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}

/* ----- admission application intake ----- */
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
    <input type="text" id="apPhone" placeholder="e.g. 0300 9876543">
    <label class="formlabel" for="apNote">Notes</label>
    <textarea id="apNote" rows="3" placeholder="Sibling of an existing student, prior school, ..."></textarea>
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="apBtn" onclick="submitAdmission()">Save application</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitAdmission(){
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
      note: document.getElementById('apNote').value.trim(),
    });
    flash('Admission application recorded');
    closeDrawer();
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
/* ----- approve with class + fee ----- */
function openApproveDrawer(appId){
  const app = applications.find(a => String(a.id) === String(appId));
  if(!app){ return; }
  openDrawer(`
    ${drawerHead('Approve admission', `${esc(app.applicant_name)} \u2014 this creates the student record.`)}
    <label class="formlabel" for="avClass">Class / section</label>
    <select id="avClass" style="width:100%">${sectionOptions(app.class_section_id)}</select>
    <label class="formlabel" for="avFee">Monthly fee (Rs)</label>
    <input type="number" id="avFee" min="0" placeholder="e.g. 2500">
    <label class="formlabel" for="avNote">Approval note (optional)</label>
    <input type="text" id="avNote" placeholder="e.g. Seat confirmed for the fall term">
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="avBtn" onclick="approveAdmission(${appId})">Approve &amp; admit</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function approveAdmission(appId){
  const btn = document.getElementById('avBtn');
  btn.disabled = true;
  try{
    await apiPost(`/school/students/admissions/${appId}/decide/`, {
      decision: 'approved',
      class_section_id: document.getElementById('avClass').value || null,
      monthly_fee: document.getElementById('avFee').value,
      note: document.getElementById('avNote').value.trim(),
    });
    flash('Admission approved \u2014 student created');
    closeDrawer();
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}

async function decideAdmission(appId, decision){
  try{
    await apiPost(`/school/students/admissions/${appId}/decide/`, { decision, note: '' });
    flash(decision === 'rejected' ? 'Application rejected' : 'Decision saved');
    location.reload();
  }catch(err){ showToast(err.message); }
}

/* ----- student status change ----- */
async function changeStatus(select){
  try{
    await apiPost(`/school/students/${select.dataset.studentId}/status/`, { status: select.value });
    flash('Student status updated');
    location.reload();
  }catch(err){
    showToast(err.message);
    select.value = select.dataset.previous;
  }
}
document.querySelectorAll('.status-select').forEach(s => {
  s.dataset.previous = s.value;
  s.addEventListener('focus', () => { s.dataset.previous = s.value; });
});
}