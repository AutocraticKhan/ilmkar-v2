// Central announcements: one notice to all branches, or targeted at one.
const notices = hydrate('notices-data', []);
const branches = hydrate('branches-data', []);

const overlay = document.getElementById('overlay');
const drawerEl = document.getElementById('drawer');

function closeDrawer(){ overlay.classList.remove('open'); }
overlay.addEventListener('click', e => { if(e.target === overlay) closeDrawer(); });
document.addEventListener('keydown', e => { if(e.key === 'Escape') closeDrawer(); });

function renderFeed(){
  const all = notices.filter(n => n.scope === 'all').length;
  document.getElementById('subhead').textContent =
    `${notices.length} notice${notices.length===1?'':'s'} \u00b7 ${all} to the whole group, ${notices.length - all} targeted.`;
  const feed = document.getElementById('feed');
  const empty = document.getElementById('emptyState');
  if(notices.length === 0){
    feed.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  feed.innerHTML = notices.map(n => `
    <div class="announcement-card sev-${n.scope === 'all' ? 'update' : 'info'}">
      <div class="ann-head">
        <div>
          <span class="badge ${n.scope === 'all' ? 'all-branches' : 'one-branch'}">${n.scope === 'all' ? 'All branches' : esc(n.school_name || '')}</span>
          <h3 style="display:inline;margin-left:8px">${esc(n.title)}</h3>
        </div>
        <button class="close-btn" title="Delete notice" onclick="deleteNotice(${n.id})">&times;</button>
      </div>
      <p class="ann-body">${esc(n.body)}</p>
      <div class="ann-meta">sent ${esc(n.created_at)}</div>
    </div>`).join('');
}

function openNewNoticeDrawer(){
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div><h2>New notice</h2><div class="loc">pick the whole group or one branch</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>

    <label class="formlabel" for="nScope">Send to</label>
    <select id="nScope" style="width:100%">
      <option value="">All branches (group-wide)</option>
      ${branches.map(b => `<option value="${b.id}">${esc(b.name)} only</option>`).join('')}
    </select>

    <label class="formlabel" for="nTitle">Title</label>
    <input type="text" id="nTitle" placeholder="e.g. Parent-teacher meeting next Friday">

    <label class="formlabel" for="nBody">Message</label>
    <textarea id="nBody" rows="6" placeholder="Write the notice&hellip;"></textarea>

    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="createNoticeBtn" onclick="createNotice()">Send notice</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>
  `;
  overlay.classList.add('open');
}

async function createNotice(){
  const title = document.getElementById('nTitle').value.trim();
  const body = document.getElementById('nBody').value.trim();
  if(!title || !body){ showToast('Title and message are required'); return; }
  const scope = document.getElementById('nScope');
  const btn = document.getElementById('createNoticeBtn');
  btn.disabled = true; btn.textContent = 'Sending\u2026';
  try{
    const data = await apiPost('/chain/announcements/create/', {
      title, body, school_id: scope.value || null,
    });
    notices.unshift(data.announcement);
    renderFeed();
    closeDrawer();
    showToast(data.announcement.scope === 'all'
      ? 'Notice sent to every branch'
      : `Notice sent to ${data.announcement.school_name}`);
  }catch(err){
    showToast(err.message);
    btn.disabled = false; btn.textContent = 'Send notice';
  }
}

async function deleteNotice(id){
  const n = notices.find(x => x.id === id);
  if(!n){ return; }
  try{
    await apiPost(`/chain/announcements/${id}/delete/`);
    const i = notices.findIndex(x => x.id === id);
    if(i !== -1){ notices.splice(i, 1); }
    renderFeed();
    showToast(`\u201c${n.title}\u201d removed`);
  }catch(err){
    showToast(err.message);
  }
}

renderFeed();
