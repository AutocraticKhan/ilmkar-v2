// Onboarding checklists: start the default template, add custom tasks,
// tick things off.

const staffOptions = hydrate('staff-options', []);
const today = new Date().toISOString().slice(0, 10);

function openStartDrawer(){
  openDrawer(`
    ${drawerHead('Start onboarding checklist', 'Seeds the 6 default tasks (idempotent — nothing is duplicated).')}
    ${field('Staff member', 'oStaff', `<select id="oStaff">${options(staffOptions)}</select>`)}
    ${field('Target due date (optional)', 'oDue', `<input type="date" id="oDue" value="${today}">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="oBtn" onclick="submitStart()">Start checklist</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitStart(){
  const btn = document.getElementById('oBtn'); btn.disabled = true;
  try{
    const data = await apiPost(`/hr/onboarding/start/${document.getElementById('oStaff').value}/`, {
      due_date: document.getElementById('oDue').value || null,
    });
    flash('Checklist started — ' + data.created + ' task(s) created');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}

function openTaskDrawer(){
  openDrawer(`
    ${drawerHead('Add onboarding task', 'Custom step for one hire.')}
    ${field('Staff member', 'tStaff', `<select id="tStaff">${options(staffOptions)}</select>`)}
    ${field('Task *', 'tTitle', `<input type="text" id="tTitle" placeholder="e.g. Collect police verification">`)}
    ${field('Due date (optional)', 'tDue', `<input type="date" id="tDue">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="tBtn" onclick="submitTask()">Add task</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitTask(){
  const btn = document.getElementById('tBtn'); btn.disabled = true;
  try{
    await apiPost('/hr/onboarding/add/', {
      staff_id: Number(document.getElementById('tStaff').value),
      title: document.getElementById('tTitle').value,
      due_date: document.getElementById('tDue').value || null,
    });
    flash('Task added');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}

async function toggleTask(taskId){
  try{
    await apiPost(`/hr/onboarding/${taskId}/toggle/`);
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); location.reload(); }
  }
}
