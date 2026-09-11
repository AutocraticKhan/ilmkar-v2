/* Shared helpers for every HR page (loaded before the page script).
   Mirrors Accountant/js/accountant_common.js (same drawer/toast/post
   helpers, HR-scoped flash key + read-only guard). */

const CSRF = document.body.dataset.csrfToken || '';
const HR_CAN_EDIT = document.body.dataset.canEdit === '1';

function esc(value){
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function hydrate(id, fallback){
  const el = document.getElementById(id);
  return el ? JSON.parse(el.textContent) : fallback;
}

function showToast(msg){
  const t = document.getElementById('toast');
  if(!t){ return; }
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(()=>t.classList.remove('show'), 2200);
}

async function apiPost(url, payload){
  if(!HR_CAN_EDIT){
    showToast("Read-only session — principals can't make changes");
    throw new Error('read-only');
  }
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
    body: JSON.stringify(payload || {})
  });
  const data = await res.json().catch(() => ({}));
  if(!res.ok){ throw new Error(data.error || 'Something went wrong'); }
  return data;
}

const fmtMoney = n => 'Rs ' + Number(n || 0).toLocaleString();
const fmtNum = n => Number(n || 0).toLocaleString();
const fmtDate = d => d
  ? new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' })
  : '\u2014';

// Flash a toast across a page reload (shown after a successful action
// triggers location.reload()).
const FLASH_KEY = 'hrFlash';
window.addEventListener('DOMContentLoaded', () => {
  const msg = sessionStorage.getItem(FLASH_KEY);
  if(msg){ sessionStorage.removeItem(FLASH_KEY); showToast(msg); }
});
function flash(msg){ sessionStorage.setItem(FLASH_KEY, msg); }

/* Drawer helpers shared by creation forms.
   Usage: openDrawer(html) shows the overlay; the page script fills
   #drawer with a form and wires a submit button. */
const overlay = document.getElementById('overlay');
const drawerEl = document.getElementById('drawer');

function closeDrawer(){ overlay && overlay.classList.remove('open'); }
if(overlay){
  overlay.addEventListener('click', e => { if(e.target === overlay) closeDrawer(); });
  document.addEventListener('keydown', e => { if(e.key === 'Escape') closeDrawer(); });
}
function openDrawer(html){
  if(!overlay || !drawerEl){ return; }
  drawerEl.innerHTML = html;
  overlay.classList.add('open');
  const first = drawerEl.querySelector('input, select, textarea');
  if(first){ setTimeout(() => first.focus(), 30); }
}

function drawerHead(title, note){
  return `
    <div class="drawer-head">
      <div><h2>${esc(title)}</h2><div class="loc">${esc(note || '')}</div></div>
      <button class="close-btn" onclick="closeDrawer()">&times;</button>
    </div>`;
}

// Standard drawer form field (same markup convention as School_Admin).
function field(label, htmlFor, inner){
  return `<label class="formlabel" for="${esc(htmlFor)}">${esc(label)}</label>${inner}`;
}

// <select> options from [{id, name}] or strings.
function options(list, selected){
  return (list || []).map(item => {
    const val = typeof item === 'object' ? item.id : item;
    const label = typeof item === 'object' ? item.name : item;
    return `<option value="${esc(val)}" ${String(val) === String(selected) ? 'selected' : ''}>${esc(label)}</option>`;
  }).join('');
}
