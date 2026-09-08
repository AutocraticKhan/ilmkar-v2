// ---------- data (hydrated from the server) ----------
const annEl = document.getElementById('announcements-data');
let announcements = annEl ? JSON.parse(annEl.textContent) : [];

const CSRF = document.body.dataset.csrfToken || '';

function esc(value){
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function apiPost(url, payload){
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
    body: JSON.stringify(payload || {})
  });
  const data = await res.json().catch(() => ({}));
  if(!res.ok){ throw new Error(data.error || 'Something went wrong'); }
  return data;
}

function showToast(msg){
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(()=>t.classList.remove('show'), 2200);
}

const overlay = document.getElementById('overlay');
const drawerEl = document.getElementById('drawer');
function closeDrawer(){ overlay.classList.remove('open'); }
overlay.addEventListener('click', e=>{ if(e.target===overlay) closeDrawer(); });
document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeDrawer(); });

// ---------- feed ----------
function renderFeed(){
  const feed = document.getElementById('feed');
  const empty = document.getElementById('emptyState');
  document.getElementById('subhead').textContent =
    `${announcements.length} announcement${announcements.length===1?'':'s'} shared with every school.`;
  if(announcements.length === 0){
    feed.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  feed.innerHTML = announcements.map(a => `
    <div class="announcement-card sev-${esc(a.severity)}">
      <div class="ann-head">
        <div>
          <span class="badge ann-${esc(a.severity)}">${esc(a.severity)}</span>
          <h3 style="display:inline;margin-left:8px">${esc(a.title)}</h3>
        </div>
        <button class="close-btn" title="Delete announcement" onclick="deleteAnnouncement(${a.id})">&times;</button>
      </div>
      <p class="ann-body">${esc(a.body)}</p>
      <div class="ann-meta">posted by ${esc(a.author)} \u00b7 ${esc(a.created_at)}</div>
    </div>`).join('');
}

// ---------- drawer: new announcement ----------
function openNewAnnouncementDrawer(){
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div><h2>New announcement</h2><div class="loc">visible to every school on the platform</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>

    <label class="formlabel" for="aTitle">Title</label>
    <input type="text" id="aTitle" placeholder="e.g. Scheduled maintenance this weekend">

    <label class="formlabel" for="aSeverity">Severity</label>
    <select id="aSeverity" style="width:100%">
      <option value="info">Info</option>
      <option value="update">Update</option>
      <option value="critical">Critical</option>
    </select>

    <label class="formlabel" for="aBody">Message</label>
    <textarea id="aBody" rows="6" placeholder="Write the announcement&hellip;"></textarea>

    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="createBtn" onclick="createAnnouncement()">Publish</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>
  `;
  overlay.classList.add('open');
}

async function createAnnouncement(){
  const title = document.getElementById('aTitle').value.trim();
  const body = document.getElementById('aBody').value.trim();
  const severity = document.getElementById('aSeverity').value;
  if(!title || !body){ showToast('Title and message are required'); return; }
  const btn = document.getElementById('createBtn');
  if(btn){ btn.disabled = true; btn.textContent = 'Publishing\u2026'; }
  try{
    const data = await apiPost('/announcements/create/', { title, body, severity });
    announcements.unshift(data.announcement);
    renderFeed();
    closeDrawer();
    showToast('Announcement published');
  }catch(err){
    showToast(err.message);
    if(btn){ btn.disabled = false; btn.textContent = 'Publish'; }
  }
}

async function deleteAnnouncement(id){
  const a = announcements.find(x=>x.id===id);
  if(!a) return;
  try{
    await apiPost(`/announcements/${id}/delete/`);
    announcements = announcements.filter(x=>x.id!==id);
    renderFeed();
    showToast(`\u201c${a.title}\u201d removed from the log`);
  }catch(err){
    showToast(err.message);
  }
}

renderFeed();