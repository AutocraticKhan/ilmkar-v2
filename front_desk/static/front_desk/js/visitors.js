/* Visitor log page — check in / check out. */
const ROWS = hydrate('visitor-rows', []);

const PURPOSE_SELECT = `
  <select id="purpose" name="purpose">
    <option value="admission">Admission enquiry</option>
    <option value="meeting">Meeting staff</option>
    <option value="parent">Parent / guardian</option>
    <option value="delivery">Delivery</option>
    <option value="maintenance">Maintenance</option>
    <option value="other">Other</option>
  </select>`;

function openCheckinDrawer(){
  openDrawer(`
    ${drawerHead('Check in visitor', 'Badge issued at the desk; check-out fills the “Out” column')}
    ${field('Visitor name', 'visitor_name', '<input id="visitor_name" required placeholder="Full name">')}
    ${field('Contact', 'contact', '<input id="contact" placeholder="03xx xxxxxxx">')}
    ${field('ID number', 'id_number', '<input id="id_number" placeholder="CNIC / passport">')}
    ${field('Purpose', 'purpose', PURPOSE_SELECT)}
    ${field('Meeting', 'whom_to_meet', '<input id="whom_to_meet" placeholder="e.g. Principal">')}
    ${field('Badge no', 'badge_no', '<input id="badge_no" placeholder="e.g. V-12">')}
    ${field('Notes', 'notes', '<input id="notes" placeholder="Anything the desk should know">')}
    <div class="drawer-actions">
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
      <button class="btn" onclick="checkin()">Check in</button>
    </div>`);
}

async function checkin(){
  try{
    const { visitor } = await apiPost('/frontdesk/visitors/checkin/', {
      visitor_name: getVal('visitor_name'),
      contact: getVal('contact'),
      id_number: getVal('id_number'),
      purpose: getVal('purpose'),
      whom_to_meet: getVal('whom_to_meet'),
      badge_no: getVal('badge_no'),
      notes: getVal('notes'),
    });
    flash('Checked in — ' + visitor.visitor_name);
    location.reload();
  }catch(e){ showToast(e.message); }
}

async function checkout(id){
  if(!confirm('Check out this visitor now?')){ return; }
  try{
    await apiPost(`/frontdesk/visitors/${id}/checkout/`, {});
    flash('Visitor checked out.');
    location.reload();
  }catch(e){ showToast(e.message); }
}

function getVal(id){
  const el = drawerEl && drawerEl.querySelector('#' + id);
  return el ? el.value.trim() : '';
}