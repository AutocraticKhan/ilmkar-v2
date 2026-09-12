// Notices page: post + delete circulars, and direct-message a staff member.

const noticesData = hydrate('notices-data', []);
const staffData = hydrate('staff-data', []);

function openNoticeDrawer(){
  openDrawer(`
    ${drawerHead('Post a notice', 'Portal fan-out is live — staff, student and parent dashboards read these notices from their own inboxes.')}
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

// Direct 1:1 message to one staff member's inbox at /teacher.
function openMessageDrawer(){
  if(!staffData.length){
    showToast('Add staff members first (Staff page)');
    return;
  }
  const options = staffData.map(s =>
    `<option value="${s.id}">${esc(s.full_name)}${
      s.designation && s.designation !== '\u2014' ? ' \u2014 ' + esc(s.designation) : ''
    }</option>`
  ).join('');
  openDrawer(`
    ${drawerHead('Message a staff member', 'Lands in their inbox on the teacher/staff dashboard.')}
    <label class="formlabel" for="msgStaff">To</label>
    <select id="msgStaff" style="width:100%">${options}</select>
    <label class="formlabel" for="msgSubject">Subject</label>
    <input type="text" id="msgSubject" placeholder="e.g. Staff meeting on Friday at 2pm">
    <label class="formlabel" for="msgBody">Message</label>
    <textarea id="msgBody" rows="4" placeholder="Write your message..."></textarea>
    <div class="btn-row" style="margin-top:22px">
      <button class="btn" id="msgBtn" onclick="submitStaffMessage()">Send message</button>
      <button class="btn ghost" onclick="closeDrawer()">Cancel</button>
    </div>`);
}

async function submitStaffMessage(){
  const subject = document.getElementById('msgSubject').value.trim();
  const body = document.getElementById('msgBody').value.trim();
  if(!subject || !body){ showToast('Subject and message are required'); return; }
  const btn = document.getElementById('msgBtn');
  btn.disabled = true;
  try{
    await apiPost('/school/messages/create/', {
      staff_id: document.getElementById('msgStaff').value,
      subject,
      body,
    });
    flash('Message sent to ' + document.getElementById('msgStaff').selectedOptions[0].textContent.split(' \u2014 ')[0]);
    closeDrawer();
    location.reload();
  }catch(err){
    showToast(err.message);
    btn.disabled = false;
  }
}