// Notices page: post + delete circulars.

const noticesData = hydrate('notices-data', []);

function openNoticeDrawer(){
  openDrawer(`
    ${drawerHead('Post a notice', 'TODO(integration): fan out to staff/student/parent portals when they exist.')}
    <label class="formlabel" for="ntTitle">Title</label>
    <input type="text" id="ntTitle" placeholder="e.g. Holiday on 14 August">
    <label class="formlabel" for="ntAudience">Audience</label>
    <select id="ntAudience" style="width:100%">
      <option value="all">Everyone</option>
      <option value="staff">Staff</option>
      <option value="students">Students</option>
      <option value="parents">Parents</option>
    </select>
    <label class="formlabel" for="ntPriority">Priority</label>
    <select id="ntPriority" style="width:100%">
      <option value="info">Info</option>
      <option value="important">Important</option>
      <option value="urgent">Urgent</option>
    </select>
    <label class="formlabel" for="ntBody">Message</label>
    <textarea id="ntBody" rows="5" placeholder="Write the circular body..."></textarea>
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="ntBtn" onclick="submitNotice()">Post notice</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitNotice(){
  const title = document.getElementById('ntTitle').value.trim();
  const body = document.getElementById('ntBody').value.trim();
  if(!title || !body){ showToast('Title and message are required'); return; }
  const btn = document.getElementById('ntBtn');
  btn.disabled = true;
  try{
    await apiPost('/school/notices/create/', {
      title,
      body,
      audience: document.getElementById('ntAudience').value,
      priority: document.getElementById('ntPriority').value,
    });
    flash('Notice posted');
    closeDrawer();
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}

async function deleteNotice(noticeId){
  try{
    await apiPost(`/school/notices/${noticeId}/delete/`, {});
    flash('Notice deleted');
    location.reload();
  }catch(err){ showToast(err.message); }
}