// Staff page: add staff + activate/deactivate.

const staffData = hydrate('staff-data', []);

function openStaffDrawer(){
  const today = new Date().toISOString().slice(0, 10);
  openDrawer(
    drawerHead('Add staff member',
      'TODO(integration): a staff-side login + payroll connect here later.') +
    '<label class="formlabel" for="sfName">Full name</label>' +
    '<input type="text" id="sfName" placeholder="e.g. Ms. Sana Tariq">' +
    '<label class="formlabel" for="sfDesig">Designation</label>' +
    '<input type="text" id="sfDesig" placeholder="e.g. Senior Teacher">' +
    '<label class="formlabel" for="sfDept">Department</label>' +
    '<input type="text" id="sfDept" placeholder="e.g. Science">' +
    '<label class="formlabel" for="sfPhone">Phone</label>' +
    '<input type="text" id="sfPhone" placeholder="e.g. 0300 5556677">' +
    '<label class="formlabel" for="sfEmail">Email</label>' +
    '<input type="email" id="sfEmail" placeholder="e.g. sana.tariq@school.edu">' +
    '<label class="formlabel" for="sfJoin">Join date</label>' +
    '<input type="date" id="sfJoin" value="' + today + '">' +
    '<div class="btn-row" style="margin-top:22px">' +
    '<button class="btn" id="sfBtn" onclick="submitStaff()">Add staff member</button>' +
    '<button class="btn ghost" onclick="closeDrawer()">Cancel</button>' +
    '</div>'
  );
}

async function submitStaff(){
  const name = document.getElementById('sfName').value.trim();
  if(!name){ showToast('Staff name is required'); return; }
  const btn = document.getElementById('sfBtn');
  btn.disabled = true;
  try{
    await apiPost('/school/staff/create/', {
      full_name: name,
      designation: document.getElementById('sfDesig').value.trim(),
      department: document.getElementById('sfDept').value.trim(),
      phone: document.getElementById('sfPhone').value.trim(),
      email: document.getElementById('sfEmail').value.trim(),
      join_date: document.getElementById('sfJoin').value,
    });
    flash('Staff member added');
    closeDrawer();
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}

async function toggleStaff(staffId){
  try{
    await apiPost('/school/staff/' + staffId + '/toggle/', {});
    flash('Staff status updated');
    location.reload();
  }catch(err){ showToast(err.message); }
}