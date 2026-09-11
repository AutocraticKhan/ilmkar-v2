/* Enquiries & leads page — funnel management. */
const ROWS = hydrate('enquiry-rows', []);
const SECTIONS = hydrate('section-options', []);
const STUDENTS = hydrate('student-options', []);

const findRow = id => ROWS.find(r => r.id === id);

const SOURCE_SELECT = `
  <select id="source" name="source">
    <option value="walk_in">Walk-in</option>
    <option value="phone">Phone</option>
    <option value="online">Online</option>
    <option value="referral">Referral</option>
    <option value="other">Other</option>
  </select>`;

function openEnquiryDrawer(){
  openDrawer(`
    ${drawerHead('Log admission enquiry', 'Track it till the student enrolls — or drops off')}
    ${field('Applicant name', 'applicant_name', '<input id="applicant_name" required placeholder="Student name">')}
    ${field('Guardian name', 'guardian_name', '<input id="guardian_name" placeholder="Parent / guardian">')}
    ${field('Guardian phone', 'guardian_phone', '<input id="guardian_phone" placeholder="03xx xxxxxxx">')}
    ${field('Interested grade', 'interested_grade', '<input id="interested_grade" placeholder="e.g. Grade 2">')}
    ${field('Source', 'source', SOURCE_SELECT)}
    ${field('Follow-up date', 'follow_up_date', '<input id="follow_up_date" type="date">')}
    ${field('Follow-up note', 'follow_up_note', '<input id="follow_up_note" placeholder="e.g. call after result day">')}
    ${field('Notes', 'notes', '<textarea id="notes" rows="3" placeholder="Context for the desk"></textarea>')}
    ${field('Assigned to', 'assigned_to', '<input id="assigned_to" placeholder="Front desk member">')}
    <div class="drawer-actions">
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
      <button class="btn" onclick="createEnquiry()">Log enquiry</button>
    </div>`);
}

async function createEnquiry(){
  try{
    const { enquiry } = await apiPost('/frontdesk/enquiries/create/', {
      applicant_name: getValue('applicant_name'),
      guardian_name: getValue('guardian_name'),
      guardian_phone: getValue('guardian_phone'),
      interested_grade: getValue('interested_grade'),
      source: getValue('source'),
      follow_up_date: getValue('follow_up_date'),
      follow_up_note: getValue('follow_up_note'),
      notes: getValue('notes'),
      assigned_to: getValue('assigned_to'),
    });
    flash('Enquiry logged — ' + enquiry.applicant_name);
    location.reload();
  }catch(e){ showToast(e.message); }
}

function openStageDrawer(id){
  const row = findRow(id);
  const next = row && {
    new: 'contacted', contacted: 'site_visit', site_visit: 'applied',
    applied: 'enrolled'
  }[row.stage] || 'contacted';
  openDrawer(`
    ${drawerHead('Advance enquiry — ' + (row && row.applicant_name || ''), 'currently ' + (row && row.stage || ''))}
    <label class="formlabel">New stage</label>
    <select id="stage">
      <option value="new">New</option>
      <option value="contacted" ${next === 'contacted' ? 'selected' : ''}>Contacted</option>
      <option value="site_visit" ${next === 'site_visit' ? 'selected' : ''}>Site visit</option>
      <option value="applied" ${next === 'applied' ? 'selected' : ''}>Applied (formal application)</option>
      <option value="enrolled" ${next === 'enrolled' ? 'selected' : ''}>Enrolled</option>
      <option value="dropped">Dropped off</option>
    </select>
    <div id="apply-row" style="display:none">
      ${field('Link existing application', 'application_id', '<select id="application_id"><option value="">— create new —</option></select>')}
      ${field('Or choose class section', 'class_section_id', '<select id="class_section_id"><option value="">— pick section —</option>' + options(SECTIONS) + '</select>')}
    </div>
    <div id="enroll-row" style="display:none">
      ${field('Enrolled student', 'student_id', '<select id="student_id">' + options(STUDENTS) + '</select>')}
    </div>
    ${field('Note for the trail', 'note', '<textarea id="note" rows="3" placeholder="What happened (shown on the audit trail)"></textarea>')}
    <div class="drawer-actions">
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
      <button class="btn" onclick="stageEnquiry(${id})">Save stage</button>
    </div>`);
  drawerEl.querySelector('#stage').addEventListener('change', e => {
    const v = e.target.value;
    drawerEl.querySelector('#apply-row').style.display = v === 'applied' ? 'block' : 'none';
    drawerEl.querySelector('#enroll-row').style.display = v === 'enrolled' ? 'block' : 'none';
  });
}

async function stageEnquiry(id){
  try{
    const payload = {
      stage: getValue('stage'),
      note: getValue('note'),
      class_section_id: getValue('class_section_id'),
      student_id: getValue('student_id'),
    };
    await apiPost(`/frontdesk/enquiries/${id}/stage/`, payload);
    flash('Enquiry staged.');
    location.reload();
  }catch(e){ showToast(e.message); }
}

function getValue(id){
  const el = drawerEl && drawerEl.querySelector('#' + id);
  return el ? el.value.trim() : '';
}