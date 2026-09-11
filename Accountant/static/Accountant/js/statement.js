// Statement page: record other income (rent, canteen, donations...).

function openIncomeDrawer(){
  openDrawer(`
    ${drawerHead('Record other income', 'Non-fee income — gets a receipt number for printing.')}
    ${field('Title', 'incTitle', `<input type="text" id="incTitle" placeholder="e.g. Canteen monthly share">`)}
    ${field('Source', 'incSource', `
      <select id="incSource" style="width:100%">
        <option value="rent">Rent</option>
        <option value="canteen">Canteen</option>
        <option value="donation">Donation</option>
        <option value="sale">Uniform / books sale</option>
        <option value="other">Other</option>
      </select>`)}
    ${field('Amount (Rs)', 'incAmount', `<input type="number" id="incAmount" min="0" step="0.01" placeholder="e.g. 15000">`)}
    ${field('Received via', 'incMethod', `
      <select id="incMethod" style="width:100%">
        <option value="cash">Cash</option>
        <option value="bank">Bank transfer</option>
        <option value="cheque">Cheque</option>
        <option value="online">Online</option>
      </select>`)}
    ${field('Received on', 'incDate', `<input type="date" id="incDate">`)}
    ${field('Details', 'incDetails', `<textarea id="incDetails" rows="3" placeholder="Optional note"></textarea>`)}
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="incBtn" onclick="submitIncome()">Record income</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('incDate').value = today;
}

async function submitIncome(){
  const title = document.getElementById('incTitle').value.trim();
  const amount = document.getElementById('incAmount').value;
  if(!title){ showToast('Give the income a title'); return; }
  if(!amount || Number(amount) <= 0){ showToast('Enter a valid amount'); return; }
  const btn = document.getElementById('incBtn');
  btn.disabled = true;
  try{
    const data = await apiPost('/finance/income/create/', {
      title,
      source: document.getElementById('incSource').value,
      amount: Number(amount),
      method: document.getElementById('incMethod').value,
      received_on: document.getElementById('incDate').value,
      details: document.getElementById('incDetails').value,
    });
    flash('Income recorded — receipt ' + (data.income ? data.income.receipt_no : ''));
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}
