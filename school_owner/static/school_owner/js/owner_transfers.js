// Transfers page: pick a student or staff member, move them to another
// branch of the group, see recent history.
const students = hydrate('students-data', []);
const staff = hydrate('staff-data', []);

const typeSelect = document.getElementById('typeSelect');
const searchInput = document.getElementById('personSearch');
const listEl = document.getElementById('personList');
const emptyEl = document.getElementById('personEmpty');
const targetSelect = document.getElementById('moveTarget');
const noteInput = document.getElementById('moveNote');
const moveBtn = document.getElementById('moveBtn');

let selected = null;   // { person_type, id, name, school_id, school_name }
let personType = 'student';

function pool(){
  return personType === 'student' ? students : staff;
}

function renderPeople(){
  const q = searchInput.value.trim().toLowerCase();
  const list = pool().filter(p =>
    !q || p.full_name.toLowerCase().includes(q) ||
    (p.classroom_name || '').toLowerCase().includes(q) ||
    (p.designation || '').toLowerCase().includes(q)
  );
  listEl.innerHTML = list.map(p => `
    <button class="school-item ${selected && selected.id === p.id && selected.person_type === personType ? 'active' : ''}"
            onclick="selectPerson(${p.id})">
      <span class="si-name">${esc(p.full_name)}
        <span class="si-loc">${esc(personType === 'student' ? p.classroom_name : p.designation)} &middot; ${esc(p.school_name)}</span>
      </span>
    </button>`).join('');
  emptyEl.style.display = list.length ? 'none' : 'block';
}

function selectPerson(id){
  const p = pool().find(x => x.id === id);
  if(!p){ return; }
  selected = {
    person_type: personType,
    id: p.id,
    name: p.full_name,
    school_id: p.school_id,
    school_name: p.school_name,
  };
  document.getElementById('moveName').textContent = p.full_name;
  document.getElementById('moveSub').textContent =
    `currently at ${p.school_name}`;
  // Destination options: any branch except the current one.
  targetSelect.disabled = false;
  noteInput.disabled = false;
  moveBtn.disabled = false;
  [...targetSelect.options].forEach(o => {
    if(!o.value){ return; }
    o.disabled = Number(o.value) === p.school_id;
    o.textContent = o.textContent.replace(' \u2014 current', '');
    if(Number(o.value) === p.school_id){ o.textContent += ' \u2014 current'; }
  });
  targetSelect.value = '';
  renderPeople();
}

async function moveSelected(){
  if(!selected){ showToast('Select a person first'); return; }
  const targetId = parseInt(targetSelect.value, 10);
  if(!targetId){ showToast('Pick a destination branch'); return; }
  const fromName = selected.school_name;
  const toName = targetSelect.options[targetSelect.selectedIndex].textContent.replace(' \u2014 current', '');
  moveBtn.disabled = true;
  moveBtn.textContent = 'Moving\u2026';
  try{
    await apiPost('/chain/transfers/move/', {
      person_type: selected.person_type,
      person_id: selected.id,
      from_school_id: selected.school_id,
      to_school_id: targetId,
      note: noteInput.value.trim(),
    });
    showToast(`${selected.name} moved: ${fromName} \u2192 ${toName}`);
    window.location.reload();   // simplest way to refresh counts + history
  }catch(err){
    showToast(err.message);
    moveBtn.disabled = false;
    moveBtn.textContent = 'Move to branch';
  }
}

typeSelect.addEventListener('change', () => {
  personType = typeSelect.value;
  selected = null;
  document.getElementById('moveName').textContent = '\u2014';
  document.getElementById('moveSub').textContent = 'Select a person on the left first.';
  targetSelect.disabled = true;
  noteInput.disabled = true;
  moveBtn.disabled = true;
  targetSelect.value = '';
  renderPeople();
});
searchInput.addEventListener('input', renderPeople);
renderPeople();
