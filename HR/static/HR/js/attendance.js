// Attendance grid: click a day cell -> mark drawer (present/absent/late/
// half-day/leave, with the unpaid toggle that drives payroll deductions).

function markDay(staffId, date){
  openDrawer(`
    ${drawerHead('Mark attendance', date)}
    ${field('Status', 'aStatus', `<select id="aStatus" onchange="updateUnpaid()">
      <option value="present">Present</option>
      <option value="absent">Absent</option>
      <option value="late">Late</option>
      <option value="half_day">Half day</option>
      <option value="leave">On leave (paid)</option>
    </select>`)}
    <div id="unpaidWrap" style="display:none">
      <label class="formlabel" style="display:flex;gap:8px;align-items:center">
        <input type="checkbox" id="aUnpaid" checked> Unpaid absence (deducts in payroll)
      </label>
    </div>
    ${field('Note', 'aNote', `<input type="text" id="aNote" placeholder="optional">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="aBtn" onclick="submitMark(${staffId}, '${date}')">Save</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

function updateUnpaid(){
  const absent = document.getElementById('aStatus').value === 'absent';
  document.getElementById('unpaidWrap').style.display = absent ? 'block' : 'none';
}

async function submitMark(staffId, date){
  const btn = document.getElementById('aBtn'); btn.disabled = true;
  try{
    await apiPost('/hr/attendance/mark/', {
      staff_id: staffId,
      date: date,
      status: document.getElementById('aStatus').value,
      unpaid: document.getElementById('aUnpaid') ? document.getElementById('aUnpaid').checked : false,
      note: document.getElementById('aNote').value,
    });
    flash('Attendance saved');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}
