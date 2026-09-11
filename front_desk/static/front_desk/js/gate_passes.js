/* Gate passes page — issue, return, cancel. */
const ROWS = hydrate('pass-rows', []);
const STUDENTS = hydrate('student-options', []);
const NEXT_PASS_NO = String(hydrate('next-pass-no', ''));

const PASS_TYPE_SELECT = `
  <select id="pass_type" name="pass_type">
    <option value="student_early">Student early leave</option>
    <option value="visitor">Visitor pass</option>
    <option value="vehicle">Vehicle</option>
    <option value="goods">Goods</option>
  </select>`;

function openIssueDrawer(){
  openDrawer(`
    ${drawerHead('Issue gate pass', 'Next number: ' + (NEXT_PASS_NO || '—'))}
    <label class="formlabel">Pass type</label>
    ${PASS_TYPE_SELECT}
    <div id="student-row">
      ${field('Student leaving early', 'student_id', '<select id="student_id">' + options(STUDENTS) + '</select>')}
    </div>
    <div id="visitor-row" style="display:none">
      ${field('Visitor name', 'visitor_name', '<input id="visitor_name" placeholder="Name on the pass">')}
      ${field('Contact', 'contact', '<input id="contact" placeholder="03xx xxxxxxx">')}
    </div>
    ${field('Reason', 'reason', '<input id="reason" required placeholder="e.g. medical appointment">')}
    ${field('Issued to', 'issued_to', '<input id="issued_to" placeholder="Who collects the pass">')}
    ${field('Expected return', 'expected_return', '<input id="expected_return" type="datetime-local">')}
    ${field('Remarks', 'remarks', '<input id="remarks" placeholder="Anything the gate should know">')}
    <div class="drawer-actions">
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
      <button class="btn" onclick="issuePass()">Issue pass</button>
    </div>`);
  drawerEl.querySelector('#pass_type').addEventListener('change', e => {
    const v = e.target.value;
    drawerEl.querySelector('#student-row').style.display = v === 'student_early' ? 'block' : 'none';
    drawerEl.querySelector('#visitor-row').style.display = v === 'visitor' ? 'block' : 'none';
  });
}

async function issuePass(){
  try{
    const { pass } = await apiPost('/frontdesk/gate-passes/create/', {
      pass_type: getVal('pass_type'),
      student_id: getVal('student_id'),
      visitor_name: getVal('visitor_name'),
      contact: getVal('contact'),
      reason: getVal('reason'),
      issued_to: getVal('issued_to'),
      expected_return: dtToIso(getVal('expected_return')),
      remarks: getVal('remarks'),
    });
    flash('Issued — ' + pass.pass_no);
    location.reload();
  }catch(e){ showToast(e.message); }
}

async function returnPass(id){
  if(!confirm('Mark this pass as returned?')){ return; }
  try{
    await apiPost(`/frontdesk/gate-passes/${id}/return/`, {});
    flash('Pass returned.');
    location.reload();
  }catch(e){ showToast(e.message); }
}

async function cancelPass(id){
  if(!confirm('Cancel this pass? It will no longer be outstanding.')){ return; }
  try{
    await apiPost(`/frontdesk/gate-passes/${id}/cancel/`, {});
    flash('Pass cancelled.');
    location.reload();
  }catch(e){ showToast(e.message); }
}

function dtToIso(v){
  if(!v){ return ''; }
  return new Date(v).toISOString(); // server keeps a local/UTC datetime
}

function getVal(id){
  const el = drawerEl && drawerEl.querySelector('#' + id);
  return el ? el.value.trim() : '';
}