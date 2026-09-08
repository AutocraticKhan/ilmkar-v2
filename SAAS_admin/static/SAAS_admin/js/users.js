// ---------- data (hydrated from the server) ----------
const schoolsEl = document.getElementById('schools-data');
let schools = schoolsEl ? JSON.parse(schoolsEl.textContent) : [];

const CSRF = document.body.dataset.csrfToken || '';

// keep in sync with SAAS_admin.models.SchoolUser.Role
const ROLES = [
  ['owner', 'Owner'],
  ['principal', 'School Admin / Principal'],
  ['teacher', 'Teacher'],
  ['student', 'Student'],
  ['hr', 'HR'],
  ['front_desk', 'Front Desk / Admissions'],
  ['accountant', 'Accountant'],
  ['parent', 'Parent/Family'],
];

let currentSchoolId = null;
let users = [];

function esc(value){
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const fmtDate = d => d
  ? new Date(d + "T00:00:00").toLocaleDateString('en-US',{ month:'short', day:'numeric', year:'numeric' })
  : '\u2014';

// ---------- api ----------
async function apiGet(url){
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  if(!res.ok){
    throw new Error(data.error || 'Something went wrong');
  }
  return data;
}

async function apiPost(url, payload){
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': CSRF
    },
    body: JSON.stringify(payload || {})
  });
  const data = await res.json().catch(() => ({}));
  if(!res.ok){
    throw new Error(data.error || 'Something went wrong');
  }
  return data;
}

// ---------- toast ----------
function showToast(msg){
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(()=>t.classList.remove('show'), 2200);
}

// ---------- drawer ----------
const overlay = document.getElementById('overlay');
const drawerEl = document.getElementById('drawer');

function closeDrawer(){ overlay.classList.remove('open'); }
overlay.addEventListener('click', e=>{ if(e.target===overlay) closeDrawer(); });
document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeDrawer(); });

// ---------- school picker ----------
function currentSchool(){
  return schools.find(s => s.id === currentSchoolId) || null;
}

function renderSchoolList(){
  const q = document.getElementById('schoolSearch').value.trim().toLowerCase();
  const listEl = document.getElementById('schoolList');
  const empty = document.getElementById('pickerEmpty');
  const list = schools.filter(s =>
    !q || s.name.toLowerCase().includes(q) || s.city.toLowerCase().includes(q)
  );
  listEl.innerHTML = list.map(s => `
    <button class="school-item ${s.id===currentSchoolId ? 'active' : ''}" onclick="selectSchool(${s.id})">
      <span class="si-name">${esc(s.name)}<span class="si-loc">${esc(s.city)}</span></span>
      <span class="si-count mono" title="user accounts">${s.users ?? 0}</span>
    </button>`).join('');
  empty.style.display = list.length ? 'none' : 'block';
}

async function selectSchool(id){
  currentSchoolId = id;
  renderSchoolList();
  document.getElementById('addUserBtn').disabled = false;

  const s = currentSchool();
  document.getElementById('panelHead').style.display = 'flex';
  document.getElementById('panelTitle').textContent = s.name;
  document.getElementById('panelSub').textContent =
    `${s.users ?? 0} user account${(s.users ?? 0) === 1 ? '' : 's'} \u00b7 ${s.city}`;
  document.getElementById('impersonateSchoolBtn').disabled = !users.length;

  try{
    const data = await apiGet(`/schools/${id}/users/`);
    users = data.users;
    s.users = users.length;
    document.getElementById('panelSub').textContent =
      `${users.length} user account${users.length === 1 ? '' : 's'} \u00b7 ${s.city}`;
    renderSchoolList();
    renderUsers();
  }catch(err){
    showToast(err.message);
  }
}

// ---------- users table ----------
function renderUsers(){
  const table = document.getElementById('usersTable');
  const empty = document.getElementById('usersEmpty');
  const body = document.getElementById('usersBody');

  if(currentSchoolId === null){
    table.style.display = 'none';
    empty.style.display = 'block';
    document.getElementById('usersEmptyTitle').textContent = 'No school selected';
    document.getElementById('usersEmptyText').textContent = 'Pick a school from the list to see its users.';
    return;
  }

  if(users.length === 0){
    table.style.display = 'none';
    empty.style.display = 'block';
    document.getElementById('usersEmptyTitle').textContent = 'No users yet';
    document.getElementById('usersEmptyText').textContent = 'Click \u201cAdd user\u201d to create the first account for this school.';
    return;
  }

  empty.style.display = 'none';
  table.style.display = 'table';
  body.innerHTML = users.map(u => `
    <tr>
      <td class="school-name">${esc(u.full_name || u.username)}<span class="loc mono">@${esc(u.username)}</span></td>
      <td class="mono">${esc(u.email)}</td>
      <td>
        <select class="role-select" onchange="changeRole(${u.user_id}, this.value)" aria-label="Role for ${esc(u.username)}">
          ${ROLES.map(([v, l]) => `<option value="${v}" ${v===u.role ? 'selected' : ''}>${l}</option>`).join('')}
        </select>
      </td>
      <td>${fmtDate(u.created_at)}</td>
      <td class="cell-actions"><button class="btn small danger" id="del-${u.user_id}" onclick="removeUser(${u.user_id})">Delete</button></td>
    </tr>`).join('');
}

// ---------- actions ----------
async function changeRole(userId, role){
  const u = users.find(x => x.user_id === userId);
  if(!u) return;
  try{
    const data = await apiPost(`/schools/${currentSchoolId}/users/${userId}/role/`, { role });
    Object.assign(u, data.membership);
    showToast(`${u.username} is now ${data.membership.role_display}`);
  }catch(err){
    showToast(err.message);
    renderUsers(); // restore the previous selection
  }
}

let confirmTimer = null;
async function removeUser(userId){
  const btn = document.getElementById(`del-${userId}`);
  if(btn && btn.dataset.armed !== '1'){
    btn.dataset.armed = '1';
    btn.textContent = 'Confirm?';
    clearTimeout(confirmTimer);
    confirmTimer = setTimeout(() => {
      if(btn){
        btn.dataset.armed = '0';
        btn.textContent = 'Delete';
      }
    }, 3000);
    return;
  }
  clearTimeout(confirmTimer);
  const u = users.find(x => x.user_id === userId);
  try{
    await apiPost(`/schools/${currentSchoolId}/users/${userId}/delete/`);
    users = users.filter(x => x.user_id !== userId);
    const s = currentSchool();
    if(s){
      s.users = users.length;
      document.getElementById('panelSub').textContent =
        `${users.length} user account${users.length === 1 ? '' : 's'} \u00b7 ${s.city}`;
    }
    renderSchoolList();
    renderUsers();
    showToast(`@${u ? u.username : userId} deleted`);
  }catch(err){
    showToast(err.message);
    if(btn){ btn.dataset.armed = '0'; btn.textContent = 'Delete'; }
  }
}

// ---------- impersonation ----------
async function impersonateSchool(){
  if(currentSchoolId === null) return;
  const btn = document.getElementById('impersonateSchoolBtn');
  const s = currentSchool();
  if(btn.dataset.armed !== '1'){
    btn.dataset.armed = '1';
    btn.textContent = `Confirm: sign in as ${s.name}`;
    setTimeout(() => {
      if(btn){ btn.dataset.armed = '0'; btn.textContent = 'Log in as school'; }
    }, 4000);
    return;
  }
  btn.disabled = true;
  btn.textContent = 'Signing in\u2026';
  try{
    const data = await apiPost(`/impersonate/${currentSchoolId}/start/`, { note: 'support session from users page' });
    window.location.href = data.redirect || '/workspace/';
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
    btn.dataset.armed = '0';
    btn.textContent = 'Log in as school';
  }
}

// ---------- drawer: add user ----------
function openNewUserDrawer(){
  if(currentSchoolId === null) return;
  const s = currentSchool();
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div><h2>Add a user</h2><div class="loc">for ${esc(s.name)}</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>

    <label class="formlabel" for="uFirst">First name</label>
    <input type="text" id="uFirst" placeholder="e.g. Ayesha">

    <label class="formlabel" for="uLast">Last name</label>
    <input type="text" id="uLast" placeholder="e.g. Khan">

    <label class="formlabel" for="uUsername">Username</label>
    <input type="text" id="uUsername" placeholder="e.g. ayesha.khan" autocomplete="off">

    <label class="formlabel" for="uEmail">Email</label>
    <input type="text" id="uEmail" placeholder="e.g. ayesha@school.edu">

    <label class="formlabel" for="uPassword">Password</label>
    <input type="password" id="uPassword" placeholder="min. 8 characters" autocomplete="new-password">

    <label class="formlabel" for="uRole">Role</label>
    <select id="uRole" style="width:100%">
      ${ROLES.map(([v, l]) => `<option value="${v}">${l}</option>`).join('')}
    </select>

    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="createUserBtn" onclick="createUser()">Create user</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>
  `;
  overlay.classList.add('open');
}

async function createUser(){
  const first = document.getElementById('uFirst').value.trim();
  const last = document.getElementById('uLast').value.trim();
  const username = document.getElementById('uUsername').value.trim();
  const email = document.getElementById('uEmail').value.trim();
  const password = document.getElementById('uPassword').value;
  const role = document.getElementById('uRole').value;

  if(!username || !password){
    showToast('Username and password are required');
    return;
  }

  const btn = document.getElementById('createUserBtn');
  if(btn){ btn.disabled = true; btn.textContent = 'Creating\u2026'; }

  try{
    const data = await apiPost(`/schools/${currentSchoolId}/users/create/`, {
      first_name: first, last_name: last, username, email, password, role
    });
    users.push(data.membership);
    users.sort((a, b) => a.username.localeCompare(b.username));
    const s = currentSchool();
    if(s){
      s.users = users.length;
      document.getElementById('panelSub').textContent =
        `${users.length} user account${users.length === 1 ? '' : 's'} \u00b7 ${s.city}`;
    }
    renderSchoolList();
    renderUsers();
    closeDrawer();
    showToast(`@${username} added as ${data.membership.role_display}`);
  }catch(err){
    showToast(err.message);
    if(btn){ btn.disabled = false; btn.textContent = 'Create user'; }
  }
}

// ---------- init ----------
document.getElementById('schoolSearch').addEventListener('input', renderSchoolList);
renderSchoolList();
renderUsers();