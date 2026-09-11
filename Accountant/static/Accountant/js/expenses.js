// Expenses page: record vendor payments, utility bills, salaries, rent.

const categories = hydrate('categories-data', []);

function categoryOptions(){
  return categories.map(c =>
    `<option value="${c.value}">${esc(c.label)}</option>`
  ).join('');
}

function openExpenseDrawer(){
  openDrawer(`
    ${drawerHead('Record expense', 'Money out — vendor payment, utility bill, salary or rent.')}
    ${field('Title', 'expTitle', `<input type="text" id="expTitle" placeholder="e.g. Stationery vendor — September">`)}
    ${field('Category', 'expCategory', `<select id="expCategory" style="width:100%">${categoryOptions()}</select>`)}
    ${field('Vendor / payee', 'expVendor', `<input type="text" id="expVendor" placeholder="e.g. Anwar Stationers">`)}
    ${field('Amount (Rs)', 'expAmount', `<input type="number" id="expAmount" min="0" step="0.01" placeholder="e.g. 12500">`)}
    ${field('Paid via', 'expMethod', `
      <select id="expMethod" style="width:100%">
        <option value="cash">Cash</option>
        <option value="bank">Bank transfer</option>
        <option value="cheque">Cheque</option>
        <option value="online">Online</option>
      </select>`)}
    ${field('Paid on', 'expDate', `<input type="date" id="expDate">`)}
    ${field('Reference / bill no.', 'expRef', `<input type="text" id="expRef" placeholder="e.g. INV-2231">`)}
    ${field('Details', 'expDetails', `<textarea id="expDetails" rows="3" placeholder="Optional note"></textarea>`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="expBtn" onclick="submitExpense()">Record expense</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('expDate').value = today;
}

async function submitExpense(){
  const title = document.getElementById('expTitle').value.trim();
  const amount = document.getElementById('expAmount').value;
  if(!title){ showToast('Give the expense a title'); return; }
  if(!amount || Number(amount) <= 0){ showToast('Enter a valid amount'); return; }
  const btn = document.getElementById('expBtn');
  btn.disabled = true;
  try{
    await apiPost('/finance/expenses/create/', {
      title,
      category: document.getElementById('expCategory').value,
      vendor: document.getElementById('expVendor').value,
      amount: Number(amount),
      method: document.getElementById('expMethod').value,
      paid_on: document.getElementById('expDate').value,
      reference_no: document.getElementById('expRef').value,
      details: document.getElementById('expDetails').value,
    });
    flash('Expense recorded');
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}
