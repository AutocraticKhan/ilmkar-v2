/* Complaints & request register — log and status moves. */
const ROWS = hydrate('complaint-rows', []);

const CATEGORY_SELECT = `
  <select id="category" name="category">
    <option value="academic">Academic</option>
    <option value="transport">Transport</option>
    <option value="facilities">Facilities</option>
    <option value="fees">Fees</option>
    <option value="request">Request</option>
    <option value="other">Other</option>
  </select>`;

const SOURCE_SELECT = `
  <select id="source" name="source">
    <option value="walk_in">Walk-in</option>
    <option value="phone">Phone</option>
    <option value="online">Online</option>
    <option value="letter">Letter</option>
  </select>`;

function openRegisterDrawer(){
  openDrawer(`
    ${drawerHead('Log complaint / request', 'Shared with the principal — the same row appears in both desks')}
    ${field('From (name)', 'complainant_name', '<input id="complainant_name" required placeholder="Who is it from?">')}
    ${field('Contact', 'contact', '<input id="contact" placeholder="03xx xxxxxxx">')}
    ${field('Category', 'category', CATEGORY_SELECT)}
    ${field('Source', 'source', SOURCE_SELECT)}
    ${field('Subject', 'subject', '<input id="subject" required placeholder="Brief title">')}
    ${field('Details', 'details', '<textarea id="details" rows="3" placeholder="What happened / what is being asked?"></textarea>')}
    ${field('Assigned to', 'assigned_to', '<input id="assigned_to" placeholder="Who should work it">')}
    <div class="drawer-actions">
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
      <button class="btn" onclick="createEntry()">Log entry</button>
    </div>`);
}

async function createEntry(){
  try{
    await apiPost('/frontdesk/complaints/create/', {
      complainant_name: getVal('complainant_name'),
      contact: getVal('contact'),
      category: getVal('category'),
      source: getVal('source'),
      subject: getVal('subject'),
      details: getVal('details'),
      assigned_to: getVal('assigned_to'),
    });
    flash('Logged in the register.');
    location.reload();
  }catch(e){ showToast(e.message); }
}

function openStatusDrawer(id){
  const row = ROWS.find(r => r.id === id);
  openDrawer(`
    ${drawerHead('Update — ' + (row && row.subject || ''), 'currently ' + (row && row.status || ''))}
    <label class="formlabel">Status</label>
    <select id="status">
      <option value="open" ${row && row.status === 'open' ? 'selected' : ''}>Open</option>
      <option value="in_progress" ${row && row.status === 'in_progress' ? 'selected' : ''}>In progress</option>
      <option value="resolved" ${row && row.status === 'resolved' ? 'selected' : ''}>Resolved</option>
      <option value="closed" ${row && row.status === 'closed' ? 'selected' : ''}>Closed</option>
    </select>
    ${field('Assigned to', 'assigned_to', '<input id="assigned_to" placeholder="Who is working it">')}
    ${field('Resolution / update note', 'resolution_note', '<textarea id="resolution_note" rows="3" placeholder="What was done / decided"></textarea>')}
    <div class="drawer-actions">
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
      <button class="btn" onclick="updateEntry(${id})">Save</button>
    </div>`);
}

async function updateEntry(id){
  try{
    await apiPost(`/frontdesk/complaints/${id}/status/`, {
      status: getVal('status'),
      assigned_to: getVal('assigned_to'),
      resolution_note: getVal('resolution_note'),
    });
    flash('Register updated.');
    location.reload();
  }catch(e){ showToast(e.message); }
}

function getVal(id){
  const el = drawerEl && drawerEl.querySelector('#' + id);
  return el ? el.value.trim() : '';
}