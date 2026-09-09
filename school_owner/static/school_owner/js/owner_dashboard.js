// Overview page: group KPIs, traffic-light scorecard and side-by-side
// branch comparison with sortable columns and leader highlighting.
const branches = hydrate('branches-data', []);
const totals = hydrate('totals-data', null);
const pending = hydrate('pending-data', 0);

let sortKey = 'name', sortDir = 1;

function renderStats(){
  if(!totals){ return; }
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="label">Branches</div><div class="value">${fmtNum(totals.branches)}</div></div>
    <div class="stat"><div class="label">Students (group)</div><div class="value">${fmtNum(totals.students)}</div></div>
    <div class="stat"><div class="label">Staff (group)</div><div class="value">${fmtNum(totals.staff)}</div></div>
    <div class="stat"><div class="label">Fees collected this month</div><div class="value">${fmtMoney(totals.collected)}</div><div class="delta">${fmtPct(totals.collection_pct)} of ${fmtMoney(totals.invoiced)} billed</div></div>
  `;
  const bits = [
    `${totals.branches} branch${totals.branches===1?'':'es'}`,
    `${fmtPct(totals.attendance_pct)} average attendance`,
    `${fmtNum(totals.free_seats)} free seats`,
  ];
  if(pending){ bits.push(`${pending} approval${pending===1?'':'s'} waiting`); }
  document.getElementById('subhead').textContent = bits.join(' \u00b7 ');
}

function renderScorecard(){
  const body = document.getElementById('scorecardBody');
  const empty = document.getElementById('scorecardEmpty');
  if(branches.length === 0){
    body.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  body.innerHTML = branches.map(b => {
    const l = b.scorecard.lights;
    return `
      <tr>
        <td class="school-name">${esc(b.name)}<span class="loc">${esc(b.city)}</span></td>
        <td>${lightDot(l.fees)} <span class="delta">${fmtPct(b.collection_pct)} collected</span></td>
        <td>${lightDot(l.attendance)} <span class="delta">${fmtPct(b.attendance_pct)}</span></td>
        <td>${lightDot(l.exams)} <span class="delta">${b.exam_avg == null ? '\u2014' : Number(b.exam_avg).toFixed(1) + '% avg'}</span></td>
        <td>${lightDot(b.scorecard.overall)}</td>
      </tr>`;
  }).join('');
}

function getSorted(){
  const list = [...branches];
  list.sort((a, b) => {
    let av = a[sortKey], bv = b[sortKey];
    if(av == null){ av = -Infinity; }
    if(bv == null){ bv = -Infinity; }
    if(typeof av === 'string'){ av = av.toLowerCase(); bv = String(bv).toLowerCase(); }
    if(av < bv) return -1 * sortDir;
    if(av > bv) return 1 * sortDir;
    return 0;
  });
  return list;
}

function bestValue(key, mode){
  // mode: 'max' (higher is better) or 'min' (lower is better)
  const values = branches.map(b => b[key]).filter(v => v != null);
  if(values.length < 2){ return null; }
  return mode === 'min' ? Math.min(...values) : Math.max(...values);
}

function renderTable(){
  const list = getSorted();
  const body = document.getElementById('tableBody');
  const empty = document.getElementById('emptyState');
  document.querySelectorAll('.arrow').forEach(a => a.textContent = '');
  const arrowEl = document.querySelector(`[data-arrow="${sortKey}"]`);
  if(arrowEl){ arrowEl.textContent = sortDir === 1 ? '\u2191' : '\u2193'; }

  // Highlight the leader per comparable column.
  const leaders = {
    students: null,             // size — not comparable as good/bad
    staff: null,
    attendance_pct: bestValue('attendance_pct', 'max'),
    collection_pct: bestValue('collection_pct', 'max'),
    // For overdue, only a zero (nothing past due) is highlighted as best.
    overdue_amount: 0,
    free_seats: null,
    exam_avg: bestValue('exam_avg', 'max'),
  };

  if(list.length === 0){
    body.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  body.innerHTML = list.map(b => `
    <tr>
      <td class="school-name">${esc(b.name)}<span class="loc">${esc(b.city)}</span></td>
      <td class="mono">${fmtNum(b.students)}</td>
      <td class="mono">${fmtNum(b.staff)}</td>
      <td class="mono ${leaders.attendance_pct != null && b.attendance_pct === leaders.attendance_pct ? 'leader' : ''}">${fmtPct(b.attendance_pct)}</td>
      <td class="mono ${leaders.collection_pct != null && b.collection_pct === leaders.collection_pct ? 'leader' : ''}">${fmtPct(b.collection_pct)}</td>
      <td class="mono ${b.overdue_amount === 0 ? 'leader' : ''}">${fmtMoney(b.overdue_amount)}</td>
      <td class="mono">${fmtNum(b.free_seats)}</td>
      <td class="mono ${leaders.exam_avg != null && b.exam_avg === leaders.exam_avg ? 'leader' : ''}">${b.exam_avg == null ? '\u2014' : Number(b.exam_avg).toFixed(1) + '%'}</td>
    </tr>`).join('');
}

document.querySelectorAll('thead th[data-key]').forEach(th => {
  th.addEventListener('click', () => {
    const key = th.dataset.key;
    if(sortKey === key){ sortDir *= -1; } else { sortKey = key; sortDir = 1; }
    renderTable();
  });
});

renderStats();
renderScorecard();
renderTable();
