// Recruitment page: postings, applicants, interviews, hire hand-off.

const postingOptions = hydrate('posting-options', []);
const applicationRows = hydrate('application-rows', []);
const today = new Date().toISOString().slice(0, 10);
const STAGES = ['new', 'shortlisted', 'interviewed', 'offered', 'hired', 'rejected'];

function openPostingDrawer(){
  openDrawer(`
    ${drawerHead('New job posting', 'One posting per vacancy; applicants attach to it.')}
    ${field('Job title *', 'pTitle', `<input type="text" id="pTitle" placeholder="e.g. Physics Teacher (Secondary)">`)}
    ${field('Department', 'pDept', `<input type="text" id="pDept">`)}
    ${field('Openings', 'pOpen', `<input type="number" id="pOpen" min="1" value="1">`)}
    ${field('Posted on', 'pPosted', `<input type="date" id="pPosted" value="${today}">`)}
    ${field('Closes on', 'pCloses', `<input type="date" id="pCloses">`)}
    ${field('Description', 'pDesc', `<textarea id="pDesc" rows="3" placeholder="Role, requirements..."></textarea>`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="pBtn" onclick="submitPosting()">Open posting</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitPosting(){
  const btn = document.getElementById('pBtn'); btn.disabled = true;
  try{
    await apiPost('/hr/postings/create/', {
      title: val('pTitle'), department: val('pDept'),
      openings: val('pOpen'), posted_on: val('pPosted'),
      closes_on: val('pCloses') || null, description: val('pDesc'),
    });
    flash('Posting opened');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}

async function closePosting(id, status){
  try{
    await apiPost(`/hr/postings/${id}/close/`, { status });
    flash('Posting updated');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); }
  }
}

function openApplicantDrawer(){
  if(!postingOptions.length){ showToast('Open a posting first'); return; }
  openDrawer(`
    ${drawerHead('Add applicant', 'Walk-in / referral candidates.')}
    ${field('Job posting', 'aPosting', `<select id="aPosting">${options(postingOptions.filter(p => p.status === 'open').map(p => ({id: p.id, name: p.title})))}</select>`)}
    ${field('Candidate name *', 'aName', `<input type="text" id="aName">`)}
    ${field('Phone', 'aPhone', `<input type="text" id="aPhone">`)}
    ${field('Email', 'aEmail', `<input type="email" id="aEmail">`)}
    ${field('Experience', 'aExp', `<input type="text" id="aExp" placeholder="e.g. 3 years, O-Level campus">`)}
    ${field('Note', 'aNote', `<input type="text" id="aNote">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="aBtn" onclick="submitApplicant()">Add applicant</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitApplicant(){
  const btn = document.getElementById('aBtn'); btn.disabled = true;
  try{
    await apiPost('/hr/applications/create/', {
      posting_id: Number(document.getElementById('aPosting').value),
      candidate_name: val('aName'), phone: val('aPhone'),
      email: val('aEmail'), experience: val('aExp'), note: val('aNote'),
    });
    flash('Applicant added');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}

function val(id){ const el = document.getElementById(id); return el ? el.value.trim() : ''; }

function moveStage(appId, currentStage){
  openDrawer(`
    ${drawerHead('Move stage', 'Advance or reject the applicant.')}
    ${field('Stage', 'sStage', `<select id="sStage">${options(STAGES, currentStage)}</select>`)}
    ${field('Note', 'sNote', `<input type="text" id="sNote">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="sBtn" onclick="submitStage(${appId})">Save stage</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitStage(appId){
  const btn = document.getElementById('sBtn'); btn.disabled = true;
  try{
    await apiPost(`/hr/applications/${appId}/stage/`, {
      stage: document.getElementById('sStage').value,
      note: document.getElementById('sNote').value,
    });
    flash('Stage updated');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}

function scheduleInterview(appId, name){
  openDrawer(`
    ${drawerHead('Schedule interview', name)}
    ${field('Date *', 'iDate', `<input type="date" id="iDate" value="${today}">`)}
    ${field('Time', 'iTime', `<input type="time" id="iTime">`)}
    ${field('Interviewer', 'iWho', `<input type="text" id="iWho" placeholder="e.g. Principal / HOD">`)}
    ${field('Note', 'iNote', `<input type="text" id="iNote">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="iBtn" onclick="submitInterview(${appId})">Schedule</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitInterview(appId){
  const btn = document.getElementById('iBtn'); btn.disabled = true;
  try{
    await apiPost('/hr/interviews/create/', {
      application_id: appId,
      scheduled_on: val('iDate'),
      scheduled_at: val('iTime'),
      interviewer: val('iWho'),
      note: val('iNote'),
    });
    flash('Interview scheduled');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}

function recordOutcome(interviewId){
  openDrawer(`
    ${drawerHead('Record outcome', 'Score 0-100; passing moves the applicant to interviewed.')}
    ${field('Outcome', 'oOutcome', `<select id="oOutcome">
      <option value="passed">Passed</option>
      <option value="failed">Failed</option>
      <option value="no_show">No show</option>
      <option value="scheduled">Reschedule later</option>
    </select>`)}
    ${field('Score (0-100)', 'oScore', `<input type="number" id="oScore" min="0" max="100">`)}
    ${field('Note', 'oNote', `<input type="text" id="oNote">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="oBtn" onclick="submitOutcome(${interviewId})">Save outcome</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitOutcome(interviewId){
  const btn = document.getElementById('oBtn'); btn.disabled = true;
  try{
    await apiPost(`/hr/interviews/${interviewId}/outcome/`, {
      outcome: document.getElementById('oOutcome').value,
      score: document.getElementById('oScore').value,
      note: document.getElementById('oNote').value,
    });
    flash('Outcome recorded');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}

function hireApplicant(appId, name){
  openDrawer(`
    ${drawerHead('Hire ' + name, 'Creates the staff directory entry, first contract and onboarding checklist.')}
    ${field('Join date', 'hDate', `<input type="date" id="hDate" value="${today}">`)}
    ${field('Contract type', 'hKind', `<select id="hKind">
      <option value="probation">Probation</option>
      <option value="permanent">Permanent</option>
      <option value="contract">Fixed-term contract</option>
      <option value="part_time">Part-time</option>
      <option value="visiting">Visiting</option>
    </select>`)}
    ${field('Monthly salary (Rs)', 'hSalary', `<input type="number" id="hSalary" min="0" step="0.01" placeholder="0">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="hBtn" onclick="submitHire(${appId})">Confirm hire</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitHire(appId){
  const btn = document.getElementById('hBtn'); btn.disabled = true;
  try{
    await apiPost(`/hr/applications/${appId}/hire/`, {
      join_date: val('hDate'),
      contract_kind: document.getElementById('hKind').value,
      monthly_salary: val('hSalary') || 0,
    });
    flash('Applicant hired — added to the staff directory');
    location.href = '/hr/staff/';
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}
