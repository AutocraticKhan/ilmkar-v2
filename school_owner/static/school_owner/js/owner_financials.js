// Financial statement page: consolidated totals, per-branch breakdown and
// group history per billing period.
const branches = hydrate('branches-data', []);
const totals = hydrate('totals-data', null);
const months = hydrate('months-data', []);

function renderStats(){
  if(!totals){ return; }
  document.getElementById('periodLabel').textContent = totals.period || 'this month';
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="label">Billed (this month)</div><div class="value">${fmtMoney(totals.invoiced)}</div></div>
    <div class="stat"><div class="label">Collected (this month)</div><div class="value" style="color:var(--green)">${fmtMoney(totals.collected)}</div></div>
    <div class="stat"><div class="label">Outstanding (this month)</div><div class="value">${fmtMoney(totals.outstanding)}</div></div>
    <div class="stat"><div class="label">Overdue (all periods)</div><div class="value" style="color:var(--red)">${fmtMoney(totals.overdue_amount)}</div><div class="delta">${fmtPct(totals.collection_pct)} overall collection</div></div>
  `;
  document.getElementById('subhead').textContent =
    `${totals.branches} branch${totals.branches===1?'':'es'} \u00b7 ${fmtPct(totals.collection_pct)} of this month's billing collected`;
}

function renderBranches(){
  const body = document.getElementById('tableBody');
  const empty = document.getElementById('emptyState');
  if(branches.length === 0){
    body.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  body.innerHTML = branches.map(b => `
    <tr>
      <td class="school-name">${esc(b.name)}<span class="loc">${esc(b.city)} \u00b7 ${fmtNum(b.students)} students</span></td>
      <td class="mono">${fmtMoney(b.invoiced)}</td>
      <td class="mono">${fmtMoney(b.collected)}</td>
      <td class="mono">${fmtMoney(b.outstanding)}</td>
      <td class="mono" ${b.overdue_amount > 0 ? 'style="color:var(--red)"' : ''}>${fmtMoney(b.overdue_amount)}<span class="delta">${fmtNum(b.overdue_count)} unpaid invoice${b.overdue_count===1?'':'s'} past due</span></td>
      <td class="mono">${fmtPct(b.collection_pct)}</td>
    </tr>`).join('');
}

function renderMonths(){
  const body = document.getElementById('monthsBody');
  const empty = document.getElementById('monthsEmpty');
  if(months.length === 0){
    body.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  body.innerHTML = months.map(m => `
    <tr>
      <td>${esc(m.period)}${m.current ? ' <span class="badge all-branches">current</span>' : ''}</td>
      <td class="mono">${fmtMoney(m.invoiced)}</td>
      <td class="mono">${fmtMoney(m.collected)}</td>
      <td class="mono">${fmtPct(m.collection_pct)}</td>
    </tr>`).join('');
}

renderStats();
renderBranches();
renderMonths();
