// Front desk page: complaints intake/status + activity log entries.

const complaintsData = hydrate('complaints-data', []);

/* ----- complaints ----- */
function openComplaintDrawer(){
  openDrawer(`
    ${drawerHead('Log a complaint', 'Walk-in, phone, online or letter — wherever it came in.')}
    <label class="formlabel" for="cpName">Complainant name</label>
    <input type="text" id="cpName" placeholder="e.g. Mrs. Rabia Ahmed">
    <label class="formlabel" for="cpContact">Contact</label>
    <input type="text" id="cpContact" placeholder="e.g. 0300 1234567">
    <label class="formlabel" for="cpSource">Source</label>
    <select id="cpSource" style="width:100%">
      <option value="walk_in">Walk-in</option>
      <option value="phone">Phone</option>
      <option value="online">Online</option>
      <option value="letter">Letter</option>
    </select>
    <label class="formlabel" for="cpCategory">Category</label>
    <select id="cpCategory" style="width:100%">
      <option value="academic">Academic</option>
      <option value="transport">Transport</option>
      <option value="facilities">Facilities</option>
      <option value="fees">Fees</option>
      <option value="other">Other</option>
    </select>
    <label class="formlabel" for="cpSubject">Subject</label>
    <input type="text" id="cpSubject" placeholder="e.g. Bus late on route 2">
    <label class="formlabel" for="cpDetails">Details</label>
    <textarea id="cpDetails" rows="3" placeholder="What happened..."></textarea>
    <label class="formlabel" for="cpAssigned">Assigned to</label>
    <input type="text" id="cpAssigned" placeholder="e.g. Transport in-charge">
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="cpBtn" onclick="submitComplaint()">Log complaint</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitComplaint(){
  const name = document.getElementById('cpName').value.trim();
  const subject = document.getElementById('cpSubject').value.trim();
  if(!name || !subject){ showToast('Complainant and subject are required'); return; }
  const btn = document.getElementById('cpBtn');
  btn.disabled = true;
  try{
    await apiPost('/school/frontdesk/complaints/create/', {
      complainant_name: name,
      contact: document.getElementById('cpContact').value.trim(),
      source: document.getElementById('cpSource').value,
      category: document.getElementById('cpCategory').value,
      subject,
      details: document.getElementById('cpDetails').value.trim(),
      assigned_to: document.getElementById('cpAssigned').value.trim(),
    });
    flash('Complaint logged');
    closeDrawer();
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}

async function changeComplaintStatus(select){
  try{
    await apiPost(`/school/frontdesk/complaints/${select.dataset.complaintId}/status/`, { status: select.value });
    flash('Complaint status updated');
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

async function resolveComplaint(complaintId){
  const note = prompt('Resolution note (optional):') || '';
  try{
    await apiPost(`/school/frontdesk/complaints/${complaintId}/resolve/`, { note });
    flash('Complaint resolved');
    location.reload();
  }catch(err){ showToast(err.message); }
}

/* ----- front desk log ----- */
function openEntryDrawer(){
  openDrawer(`
    ${drawerHead('Log a visit / call', 'Visitor, enquiry, phone call, delivery, ...')}
    <label class="formlabel" for="enType">Type</label>
    <select id="enType" style="width:100%">
      <option value="visitor">Visitor</option>
      <option value="enquiry">Enquiry</option>
      <option value="phone_call">Phone call</option>
      <option value="delivery">Delivery</option>
      <option value="other">Other</option>
    </select>
    <label class="formlabel" for="enPerson">Person</label>
    <input type="text" id="enPerson" placeholder="e.g. Mr. Kamran (courier)">
    <label class="formlabel" for="enSummary">Summary</label>
    <input type="text" id="enSummary" placeholder="e.g. Dropped off science lab equipment">
    <label class="formlabel" for="enHandled">Handled by</label>
    <input type="text" id="enHandled" placeholder="e.g. Front desk">
    <label class="formlabel" for="enTime">Time</label>
    <input type="datetime-local" id="enTime" value="${new Date().toISOString().slice(0,16)}">
    <label class="checkline">
      <input type="checkbox" id="enFollow"> Needs follow-up
    </label>
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="enBtn" onclick="submitEntry()">Log entry</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitEntry(){
  const person = document.getElementById('enPerson').value.trim();
  const summary = document.getElementById('enSummary').value.trim();
  if(!person || !summary){ showToast('Person and summary are required'); return; }
  const btn = document.getElementById('enBtn');
  btn.disabled = true;
  try{
    await apiPost('/school/frontdesk/entries/create/', {
      entry_type: document.getElementById('enType').value,
      person,
      summary,
      handled_by: document.getElementById('enHandled').value.trim(),
      occurred_at: document.getElementById('enTime').value,
      follow_up_needed: document.getElementById('enFollow').checked,
    });
    flash('Entry logged');
    closeDrawer();
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}