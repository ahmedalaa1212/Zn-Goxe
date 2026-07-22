// =========================================
// ملف إدارة المستخدمين الفرعي (users.js)
// =========================================

let uDataList = [];

async function uFetch() {
    const tbody = document.getElementById('uTableBody');
    if(!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="5" style="color: #f59e0b; padding: 25px;">جاري تحديث البيانات... ⏳</td></tr>';
    
    try {
        let res = await fetch('/api/users?t=' + new Date().getTime());
        let json = await res.json();
        
        if(json.success) {
            uDataList = json.users;
            uRender(uDataList);
        } else {
            tbody.innerHTML = '<tr><td colspan="5" style="color: #ef4444; padding: 25px;">❌ فشل جلب البيانات من السيرفر</td></tr>';
        }
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="5" style="color: #ef4444; padding: 25px;">❌ خطأ في الاتصال بالسيرفر</td></tr>';
    }
}

function uRender(usersList) {
    const tbody = document.getElementById('uTableBody');
    if(!tbody) return;
    tbody.innerHTML = '';
    
    if(!usersList || usersList.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="color: #94a3b8; padding: 25px;">لا يوجد مستخدمين مسجلين.</td></tr>';
        return;
    }

    usersList.forEach(u => {
        let tr = document.createElement('tr');
        if(u.isBanned) tr.style.opacity = "0.4";
        
        let actionBtn = u.isBanned 
            ? `<button class="u-btn u-btn-unban" onclick="uAction('${u.id}', 'unban')">فك الحظر</button>`
            : `<button class="u-btn u-btn-ban" onclick="uAction('${u.id}', 'ban')">حظر</button>`;

        tr.innerHTML = `
            <td style="color: #f59e0b; font-weight: bold;">${u.id}</td>
            <td>${u.name}</td>
            <td><span class="u-badge">${u.balance} 💰</span></td>
            <td style="color: #94a3b8; font-size: 11px;">${u.joinDate}</td>
            <td>
                ${actionBtn}
                <button class="u-btn u-btn-add" onclick="uAddBal('${u.id}')">➕ رصيد</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function uSearch() {
    let term = document.getElementById('uSearchInput').value.toLowerCase();
    let filtered = uDataList.filter(u => 
        u.id.includes(term) || u.name.toLowerCase().includes(term)
    );
    uRender(filtered);
}

async function uAction(id, action) {
    if(!confirm(action === 'ban' ? 'هل أنت متأكد من حظر المستخدم؟' : 'هل أنت متأكد من فك الحظر؟')) return;
    try {
        await fetch('/api/users/' + id + '/action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: action })
        });
        uFetch();
    } catch(e) { alert('حدث خطأ أثناء التنفيذ!'); }
}

async function uAddBal(id) {
    let val = prompt("أدخل قيمة الرصيد المراد إضافته (أرقام فقط):");
    if(!val || isNaN(val)) return;
    try {
        await fetch('/api/users/' + id + '/action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: 'add_balance', value: parseInt(val) })
        });
        alert('✅ تم إضافة الرصيد بنجاح!');
        uFetch();
    } catch(e) { alert('حدث خطأ أثناء الإضافة!'); }
}

// تشغيل جلب البيانات تلقائياً أول ما الملف يتحمل عن طريق الـ main.js
uFetch();
