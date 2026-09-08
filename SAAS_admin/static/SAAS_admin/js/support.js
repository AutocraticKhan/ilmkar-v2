// ---------- data (hydrated from the server) ----------
const ticketsEl = document.getElementById('tickets-data');
let tickets = ticketsEl ? JSON.parse(ticketsEl.textContent) : [];

const impEl = document.getElementById('impersonations-data');
const impersonations = impEl ? JSON.parse(impEl.textContent) : [];

const CSRF = document.body.dataset.csrfToken || '';

function esc(value){
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function apiGet(url){
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  if(!res.ok){ throw new Error(data.error || 'Something went wrong'); }
  return data;
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

// ---------- tabs ----------
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tab-tickets').style.display = tab.dataset.tab === 'tickets' ? 'block' : 'none';
    document.getElementById('tab-impersonation').style.display = tab.dataset.tab === 'impersonation' ? 'block' : 'none';
  });
});

// ---------- tickets ----------
function replaceTicket(t){
  const i = tickets.findIndex(x => x.id === t.id);
  if(i !== -1) tickets[i] = t;
}

function renderImpersonations(){
  const body = document.getElementById('impBody');
  const empty = document.getElementById('impEmpty');
  if(impersonations.length === 0){
    body.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  body.innerHTML = impersonations.map(l => `
    <tr>
      <td class="mono">@${esc(l.operator)}</td>
      <td>${esc(l.school_name)}</td>
      <td class="mono">@${esc(l.user_display)}</td>
      <td>${esc(l.note)}</td>
      <td>${esc(l.started_at)}</td>
      <td>${l.active ? '<span class="status active"><span class="dot"></span>Active now</span>' : esc(l.ended_at)}</td>
    </tr>`).join('');
}

function renderTickets(){
  const status = document.getElementById('statusFilter').value;
  const priority = document.getElementById('priorityFilter').value;
  const list = tickets.filter(t =>
    (status === 'all' || t.status === status) &&
    (priority === 'all' || t.priority === priority)
  );
  const body = document.getElementById('tableBody');
  const empty = document.getElementById('emptyState');

  const open = tickets.filter(t=>t.status==='open').length;
  const pending = tickets.filter(t=>t.status==='pending').length;
  document.getElementById('tabTicketsCount').textContent =
    `(${open} open \u00b7 ${pending} pending)`;
  document.getElementById('subhead').textContent =
    `${tickets.length} ticket${tickets.length===1?'':'s'} \u00b7 ${open} open \u00b7 ${pending} pending`;

  if(list.length === 0){
    body.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  body.innerHTML = list.map(t => `
    <tr onclick="openTicket(${t.id})">
      <td class="school-name">${esc(t.subject)}<span class="loc">from ${esc(t.requester)}</span></td>
      <td>${esc(t.school_name)}</td>
      <td><span class="badge prio-${esc(t.priority)}">${esc(t.priority)}</span></td>
      <td><span class="status ${t.status === 'closed' ? 'suspended' : t.status === 'open' ? 'trial' : 'active'}"><span class="dot"></span>${esc(t.status)}</span></td>
      <td class="mono">${t.replies}</td>
      <td>${esc(t.updated_at)}</td>
    </tr>`).join('');
}

// ---------- ticket drawer ----------
let currentTicketId = null;

async function openTicket(id){
  currentTicketId = id;
  drawerEl.innerHTML = `<div class="drawer-head"><div><h2>Loading&hellip;</h2></div></div>`;
  overlay.classList.add('open');
  try{
    const data = await apiGet(`/tickets/${id}/`);
    if(currentTicketId !== id) return;
    renderTicketDrawer(data.ticket, data.replies);
  }catch(err){
    showToast(err.message);
    closeDrawer();
  }
}

function renderTicketDrawer(t, replies){
  drawerEl.innerHTML = `
    <div class="drawer-head">
      <div><h2>${esc(t.subject)}</h2><div class="loc">${esc(t.school_name)} \u00b7 from ${esc(t.requester)} \u00b7 ${esc(t.created_at)}</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>

    <div class="field-grid">
      <div class="field"><span class="k">Status</span><span class="v">
        <select id="tStatus" class="role-select" onchange="setTicketStatus(${t.id}, this.value)">
          ${['open','pending','closed'].map(s=>`<option value="${s}" ${s===t.status?'selected':''}>${s}</option>`).join('')}
        </select></span></div>
      <div class="field"><span class="k">Priority</span><span class="v">
        <select id="tPriority" class="role-select" onchange="setTicketPriority(${t.id}, this.value)">
          ${['high','normal','low'].map(p=>`<option value="${p}" ${p===t.priority?'selected':''}>${p}</option>`).join('')}
        </select></span></div>
    </div>

    <div class="section-title">Conversation</div>
    <div class="thread">
      <div class="msg school-msg"><div class="msg-head">${esc(t.requester)} \u00b7 ${esc(t.created_at)}</div>${esc(t.body)}</div>
      ${replies.map(r => `
        <div class="msg ${r.is_staff ? 'staff-msg' : 'school-msg'}">
          <div class="msg-head">${esc(r.author)} \u00b7 ${esc(r.created_at)}</div>
          ${esc(r.body)}
        </div>`).join('')}
    </div>

    <div class="section-title">Reply as operator</div>
    <textarea id="replyBody" rows="4" placeholder="Write a reply to the school&hellip;"></textarea>
    <div class="btn-row" style="margin-top:12px">
      <button class="btn" id="replyBtn" onclick="sendReply(${t.id})">Send reply</button>
    </div>
  `;
}

async function sendReply(id){
  const body = document.getElementById('replyBody').value.trim();
  if(!body){ showToast('Write a reply first'); return; }
  const btn = document.getElementById('replyBtn');
  if(btn){ btn.disabled = true; btn.textContent = 'Sending\u2026'; }
  try{
    const data = await apiPost(`/tickets/${id}/reply/`, { body });
    replaceTicket(data.ticket);
    renderTickets();
    const replies = await (await apiGet(`/tickets/${id}/`)).replies;
    const t = tickets.find(x=>x.id===id);
    renderTicketDrawer(t, replies);
    showToast('Reply sent \u2014 ticket moved to pending');
  }catch(err){
    showToast(err.message);
    if(btn){ btn.disabled = false; btn.textContent = 'Send reply'; }
  }
}

async function setTicketStatus(id, status){
  try{
    const data = await apiPost(`/tickets/${id}/status/`, { status });
    replaceTicket(data.ticket);
    renderTickets();
    showToast(`Ticket marked ${status}`);
  }catch(err){ showToast(err.message); }
}

async function setTicketPriority(id, priority){
  try{
    const data = await apiPost(`/tickets/${id}/priority/`, { priority });
    replaceTicket(data.ticket);
    renderTickets();
    showToast(`Priority set to ${priority}`);
  }catch(err){ showToast(err.message); }
}

// ---------- init ----------
document.getElementById('statusFilter').addEventListener('change', renderTickets);
document.getElementById('priorityFilter').addEventListener('change', renderTickets);
renderTickets();
renderImpersonations();