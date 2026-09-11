// Appraisals: open, score (criteria 1-5), finalize.

const staffOptions = hydrate('staff-options', []);
const appraisalRows = hydrate('appraisal-rows', []);
const currentCycle = hydrate('current-cycle', '');

function openAppraisalDrawer(){
  openDrawer(`
    ${drawerHead('New appraisal', 'One appraisal per staff member per cycle.')}
    ${field('Staff member', 'apStaff', `<select id="apStaff">${options(staffOptions)}</select>`)}
    ${field('Cycle', 'apPeriod', `<input type="text" id="apPeriod" value="${esc(currentCycle)}" placeholder="e.g. 2025-26">`)}
    ${field('Reviewer', 'apReviewer', `<input type="text" id="apReviewer" placeholder="defaults to you">`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="apBtn" onclick="submitAppraisal()">Open appraisal</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitAppraisal(){
  const btn = document.getElementById('apBtn'); btn.disabled = true;
  try{
    await apiPost('/hr/appraisals/create/', {
      staff_id: Number(document.getElementById('apStaff').value),
      period: document.getElementById('apPeriod').value,
      reviewer: document.getElementById('apReviewer').value,
    });
    flash('Appraisal opened');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}

function openScoreDrawer(appraisalId){
  const a = appraisalRows.find(x => x.id === appraisalId);
  if(!a){ showToast('Appraisal not found'); return; }
  const sc = k => (a.scores && a.scores[k]) || '';
  const crit = (key, label) => field(
    label + ' (1-5)', 'sc_' + key,
    `<input type="number" id="sc_${key}" min="1" max="5" value="${sc(key)}">`
  );
  openDrawer(`
    ${drawerHead('Score appraisal', a.staff_name + ' — ' + a.period)}
    ${crit('teaching', 'Teaching / work quality')}
    ${crit('discipline', 'Discipline')}
    ${crit('teamwork', 'Teamwork')}
    ${crit('punctuality', 'Punctuality')}
    ${crit('growth', 'Growth mindset')}
    ${field('Strengths', 'apStrengths', `<textarea id="apStrengths" rows="2">${esc(a.strengths)}</textarea>`)}
    ${field('Areas to improve', 'apImprove', `<textarea id="apImprove" rows="2">${esc(a.improvements)}</textarea>`)}
    <div class="small-note" style="margin-top:8px">Overall rating: <b class="mono" id="apRating">${a.rating || '—'}</b> (average of scored criteria)</div>
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="scBtn" onclick="submitScores(${a.id})">Save scores</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
  ['sc_teaching','sc_discipline','sc_teamwork','sc_punctuality','sc_growth'].forEach(id =>
    document.getElementById(id).addEventListener('input', updateRating)
  );
}

function updateRating(){
  const ids = ['sc_teaching','sc_discipline','sc_teamwork','sc_punctuality','sc_growth'];
  const vals = ids.map(id => Number(document.getElementById(id).value)).filter(v => v >= 1 && v <= 5);
  document.getElementById('apRating').textContent =
    vals.length ? (vals.reduce((s, v) => s + v, 0) / vals.length).toFixed(1) : '—';
}

async function submitScores(appraisalId){
  const btn = document.getElementById('scBtn'); btn.disabled = true;
  const payload = {
    strengths: document.getElementById('apStrengths').value,
    improvements: document.getElementById('apImprove').value,
  };
  ['teaching','discipline','teamwork','punctuality','growth'].forEach(k => {
    payload['score_' + k] = document.getElementById('sc_' + k).value;
  });
  try{
    await apiPost(`/hr/appraisals/${appraisalId}/update/`, payload);
    flash('Appraisal scored');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); btn.disabled = false; }
  }
}

async function finalizeAppraisal(appraisalId){
  if(!confirm('Finalize this appraisal? It becomes read-only.')){ return; }
  try{
    await apiPost(`/hr/appraisals/${appraisalId}/finalize/`);
    flash('Appraisal finalized');
    location.reload();
  }catch(err){
    if(err.message !== 'read-only'){ showToast(err.message); }
  }
}
