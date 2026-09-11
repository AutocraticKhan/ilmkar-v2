// Reconciliation page: sync the ledger + mark entries reconciled.

async function reconcileEntry(entryId){
  try{
    await apiPost(`/finance/ledger/${entryId}/reconcile/`);
    flash('Entry reconciled');
    location.reload();
  }catch(err){
    showToast(err.message);
  }
}

async function syncLedger(){
  try{
    const data = await apiPost('/finance/ledger/sync/');
    flash(data.created ? `Pulled ${data.created} new entr${data.created === 1 ? 'y' : 'ies'}` : 'Ledger already up to date');
    location.reload();
  }catch(err){
    showToast(err.message);
  }
}
