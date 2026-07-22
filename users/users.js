// =========================================
// ملف إدارة المستخدمين الفرعي (users/users.js)
// =========================================

let uDataList = [];

// جلب البيانات من السيرفر
async function uFetch() {
    const tbody = document.getElementById('uTableBody');
    if(!tbody) return;
    
    try {
        let res = await fetch('/api/users?t=' + new Date().getTime());
        let json = await res.json();
        
        if(json.success) {
            uDataList = json.users;
            // الحفاظ على عبارة البحث الحالية إن وجدت
            uSearch();
        } else {
            tbody.innerHTML = '<tr><td colspan="5" style="color: #ef4444; padding: 25px;">❌ فشل جلب البيانات من السيرفر</td></tr>';
        }
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="5" style="color: #ef4444; padding: 25px;">❌ خطأ في الاتصال بالسيرفر</td></tr>';
    }
}

// عرض البيانات في الجدول
function uRender(usersList) {
    const tbody = document.getElementById('uTableBody');
    if(!tbody) return;
    tbody.innerHTML = '';
    
    if(!usersList || usersList.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="color: #94a3b8; padding: 25px;">لا يوجد مستخدمين يطابقون البحث.</td></tr>';
        return;
    }

    usersList.forEach(u => {
        let tr = document.createElement('tr');
        if(u.isBanned) tr.style.opacity = "0.5";
        
        let actionBtn = u.isBanned 
            ? `<button class="btn-action btn-unban" onclick="uAction('${u.id}', 'unban')">فك الحظر</button>`
            : `<button class="btn-action btn-ban" onclick="uAction('${u.id}', 'ban')">حظر</button>`;

        tr.innerHTML = `
            <td style="color: #f59e0b; font-weight: bold;">${u.id}</td>
            <td>${u.name}</td>
            <td><span class="badge-balance">💰 ${u.balance}</span></td>
            <td style="color: #94a3b8; font-size: 11px;">${u.joinDate || 'غير معروف'}</td>
            <td>
                <div class="action-buttons">
                    <button class="btn-action btn-add" onclick="uAddBal('${u.id}')">➕ إضافة</button>
                    <button class="btn-action btn-deduct" onclick="uDeductBal('${u.id}')">➖ خصم</button>
                    ${actionBtn}
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// البحث والفلترة الفورية
function uSearch() {
    let input = document.getElementById('uSearchInput');
    let term = input ? input.value.trim().toLowerCase() : '';
    
    let filtered = uDataList.filter(u => 
        String(u.id).toLowerCase().includes(term) || 
        String(u.name).toLowerCase().includes(term)
    );
    uRender(filtered);
}

// تنفيذ أفعال الحظر/فك الحظر
async function uAction(id, action) {
    let msg = action === 'ban' ? 'هل أنت متأكد من حظر المستخدم؟' : 'هل أنت متأكد من فك حظر المستخدم؟';
    if(!confirm(msg)) return;

    try {
        let res = await fetch('/api/users/' + id + '/action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: action })
        });
        let data = await res.json();
        
        if(data.success) {
            uFetch(); // إعادة جلب البيانات لتأكيد الحفظ في Firebase
        } else {
            alert('⚠️ حدث خطأ: ' + (data.message || 'لم يكتمل الطلب'));
        }
    } catch(e) { 
        alert('❌ حدث خطأ أثناء التواصل مع السيرفر!'); 
    }
}

// إضافة رصيد
async function uAddBal(id) {
    let val = prompt("أدخل قيمة الرصيد المراد إضافتها:");
    if(!val || isNaN(val) || parseInt(val) <= 0) return;

    try {
        let res = await fetch('/api/users/' + id + '/action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: 'add_balance', value: parseInt(val) })
        });
        let data = await res.json();
        
        if(data.success) {
            alert('✅ تم إضافة الرصيد وحفظه في السيرفر بنجاح!');
            uFetch();
        } else {
            alert('⚠️ فشل الإضافة: ' + (data.message || 'خطأ غير معروف'));
        }
    } catch(e) { 
        alert('❌ حدث خطأ أثناء الإضافة!'); 
    }
}

// خصم رصيد
async function uDeductBal(id) {
    let val = prompt("أدخل قيمة الرصيد المراد خصمها:");
    if(!val || isNaN(val) || parseInt(val) <= 0) return;

    try {
        let res = await fetch('/api/users/' + id + '/action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: 'deduct_balance', value: parseInt(val) })
        });
        let data = await res.json();
        
        if(data.success) {
            alert('✅ تم خصم الرصيد وحفظه في السيرفر بنجاح!');
            uFetch();
        } else {
            alert('⚠️ فشل الخصم: ' + (data.message || 'خطأ غير معروف'));
        }
    } catch(e) { 
        alert('❌ حدث خطأ أثناء الخصم!'); 
    }
}

// بدء التشغيل
uFetch();
