// Staff documents: register documents with expiry watch.

const staffOptions = hydrate('staff-options', []);
const today = new Date().toISOString().slice(0, 10);

function openDocDrawer(){
  openDrawer(`
    ${drawerHead('Add staff document', 'Certifications / CNIC / degrees / contract copies.')}
    ${field('Staff member', 'dStaff', `<select id="dStaff">${options(staffOptions)}</select>`)}
    ${field('Kind', 'dKind', `<select id="dKind">
      <option value="certification">Certification</option>
      <option value="contract">Contract</option>
      <option value="cnic">CNIC / ID</option>
      <option value="degree">Degree / transcript</option>
      <option value="other">Other</option>
    </select>`)}
    ${field('Title *', 'dTitle', `<input type="text" id="dTitle" placeholder="e.g. B.Ed degree / First-Aid certificate">`)}
    ${field('Number', 'dNumber', `<input type="text" id="dNumber">`)}
    ${field('Issued on', 'dIssued', `<input type="date" id="dIssued">`)}
    ${field('Expiry date (blank = no expiry)', 'dExpiry', `<input type="date" id="dExpiry">`)}
    ${field('File link (optional)', 'dUrl', `<input type="url" id="dUrl" placeholder="https://...">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="dBtn" onclick="submitDoc()">Save document</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitDoc(){
  const btn = document.getElementById('dBtn'); btn.disabled = true;
  try{
    await apiPost('/hr/documents/add/', {
      staff_id: Number(document.getElementById('dStaff').value),
      kind: document.getElementById('dKind').value,
      title: document.getElementById('dTitle').value,
      number: document.getElementById('dNumber').value,
      issued_on: document.getElementById('dIssued').value || null,
      expiry_date: document.getElementById('dExpiry').value || null,
      file_url: document.getElementById('dUrl').value,
    });
    flash('Document added');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}
