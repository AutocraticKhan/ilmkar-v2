const CSRF = document.body.dataset.csrfToken || '';

async function endImpersonation(){
  const btn = document.getElementById('endSessionBtn');
  if(btn){ btn.disabled = true; btn.textContent = 'Ending\u2026'; }
  try{
    const res = await fetch('/impersonate/end/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
      body: '{}'
    });
    const data = await res.json().catch(() => ({}));
    if(!res.ok){ throw new Error(data.error || 'Something went wrong'); }
    window.location.href = data.redirect || '/dashboard/';
  }catch(err){
    if(btn){ btn.disabled = false; btn.textContent = 'End session'; }
    const t = document.getElementById('toast');
    t.textContent = err.message;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2200);
  }
}