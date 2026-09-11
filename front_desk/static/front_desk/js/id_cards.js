/* ID cards page — create cards and mark them printed. */
const ROWS = hydrate('card-rows', []);
const STUDENTS = hydrate('student-options', []);
const STAFF = hydrate('staff-options', []);
const NEXT_CARD_NO = String(hydrate('next-card-no', ''));

const HOLDER_TYPE_SELECT = `
  <select id="holder_type" name="holder_type">
    <option value="student">Student</option>
    <option value="staff">Staff</option>
  </select>`;

function openCardDrawer(){
  openDrawer(`
    ${drawerHead('New ID card', 'Next number: ' + (NEXT_CARD_NO || '—'))}
    <label class="formlabel">Holder</label>
    ${HOLDER_TYPE_SELECT}
    <div id="student-row">
      ${field('Student', 'student_id', '<select id="student_id">' + options(STUDENTS) + '</select>')}
    </div>
    <div id="staff-row" style="display:none">
      ${field('Staff member', 'staff_id', '<select id="staff_id">' + options(STAFF) + '</select>')}
    </div>
    ${field('Issued on', 'issued_on', '<input id="issued_on" type="date">')}
    ${field('Expires on', 'expires_on', '<input id="expires_on" type="date">')}
    ${field('Remarks', 'remarks', '<input id="remarks" placeholder="e.g. replacement card">')}
    <div class="drawer-actions">
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
      <button class="btn" onclick="createCard()">Create card</button>
    </div>`);
  drawerEl.querySelector('#holder_type').addEventListener('change', e => {
    const v = e.target.value;
    drawerEl.querySelector('#student-row').style.display = v === 'student' ? 'block' : 'none';
    drawerEl.querySelector('#staff-row').style.display = v === 'staff' ? 'block' : 'none';
  });
}

async function createCard(){
  try{
    const { card } = await apiPost('/frontdesk/id-cards/create/', {
      holder_type: getVal('holder_type'),
      student_id: getVal('student_id'),
      staff_id: getVal('staff_id'),
      issued_on: getVal('issued_on'),
      expires_on: getVal('expires_on'),
      remarks: getVal('remarks'),
    });
    flash('Card created — ' + card.card_no);
    location.reload();
  }catch(e){ showToast(e.message); }
}

async function markPrinted(id){
  try{
    await apiPost(`/frontdesk/id-cards/${id}/printed/`, {});
    flash('Card marked printed.');
    location.reload();
  }catch(e){ showToast(e.message); }
}

function getVal(id){
  const el = drawerEl && drawerEl.querySelector('#' + id);
  return el ? el.value.trim() : '';
}