// =========================================
// ملف إدارة المستخدمين الفرعي (users/users.js)
// =========================================

let uDataList = [];

// جلب البيانات من السيرفر
async function uFetch() {
    const tbody = document.getElementById('uTableBody');
    if (!tbody) return;

    // إظهار مؤشر التحميل
    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #f59e0b; padding: 25px;">⏳ جاري جلب قائمة المستخدمين...</td></tr>';

    try {
        let res = await fetch('/api/users?t=' + new Date().getTime());
        let json = await res.json();

        if (json.success) {
            uDataList = json.users;
            // الحفاظ على نتائج البحث الحالية إن وجدت
            uSearch();
        } else {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #ef4444; padding: 25px;">❌ فشل جلب البيانات من السيرفر</td></tr>';
        }
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #ef4444; padding: 25px;">❌ خطأ في الاتصال بالسيرفر</td></tr>';
    }
}

// عرض البيانات في الجدول
function uRender(usersList) {
    const tbody = document.getElementById('uTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!usersList || usersList.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #94a3b8; padding: 25px;">لا يوجد مستخدمين يطابقون البحث.</td></tr>';
        return;
    }

    usersList.forEach(u => {
        let tr = document.createElement('tr');
        if (u.isBanned) {
            tr.style.opacity = "0.6";
            tr.style.backgroundColor = "rgba(239, 68, 68, 0.05)";
        }

        let statusBadge = u.isBanned 
            ? `<span style="background: rgba(239, 68, 68, 0.2); color: #ef4444; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-right: 5px;">محظور</span>`
            : `<span style="background: rgba(34, 197, 94, 0.2); color: #22c55e; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-right: 5px;">نشط</span>`;

        let actionBtn = u.isBanned 
            ? `<button class="btn-action btn-unban" onclick="uAction('${u.id}', 'unban')">فك الحظر</button>`
            : `<button class="btn-action btn-ban" onclick="uAction('${u.id}', 'ban')">حظر</button>`;

        // تنسيق الرصيد
        let formattedBalance = typeof u.balance === 'number' ? u.balance.toLocaleString() : u.balance;

        tr.innerHTML = `
            <td style="color: #f59e0b; font-weight: bold;">${u.id}</td>
            <td>${u.name} ${statusBadge}</td>
            <td><span class="badge-balance">💰 ${formattedBalance}</span></td>
            <td style="color: #38bdf8; font-size: 11px; white-space: nowrap; direction: ltr; text-align: center;">
                ${u.joinDate || 'غير معروف'}
            </td>
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
    let msg = action === 'ban' ? 'هل أنت متأكد من حظر هذا المستخدم؟' : 'هل أنت متأكد من فك حظر هذا المستخدم؟';
    if (!confirm(msg)) return;

    try {
        let res = await fetch('/api/users/' + id + '/action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: action })
        });
        let data = await res.json();

        if (data.success) {
            uFetch(); // إعادة جلب البيانات لتحديث العرض من قاعدة البيانات
        } else {
            alert('⚠️ حدث خطأ: ' + (data.message || 'لم يكتمل الطلب'));
        }
    } catch (e) {
        alert('❌ حدث خطأ أثناء التواصل مع السيرفر!');
    }
}

// إضافة رصيد (يدعم الكسور)
async function uAddBal(id) {
    let val = prompt("أدخل قيمة الرصيد المراد إضافتها:");
    if (!val) return;
    
    let numVal = parseFloat(val);
    if (isNaN(numVal) || numVal <= 0) {
        alert("⚠️ يرجى إدخال مبلغ صحيح أكبر من الصفر!");
        return;
    }

    try {
        let res = await fetch('/api/users/' + id + '/action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: 'add_balance', value: numVal })
        });
        let data = await res.json();

        if (data.success) {
            alert('✅ تم إضافة الرصيد وحفظه في السيرفر بنجاح!');
            uFetch();
        } else {
            alert('⚠️ فشل الإضافة: ' + (data.message || 'خطأ غير معروف'));
        }
    } catch (e) {
        alert('❌ حدث خطأ أثناء الإضافة!');
    }
}

// خصم رصيد (يدعم الكسور)
async function uDeductBal(id) {
    let val = prompt("أدخل قيمة الرصيد المراد خصمها:");
    if (!val) return;

    let numVal = parseFloat(val);
    if (isNaN(numVal) || numVal <= 0) {
        alert("⚠️ يرجى إدخال مبلغ صحيح أكبر من الصفر!");
        return;
    }

    try {
        let res = await fetch('/api/users/' + id + '/action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: 'deduct_balance', value: numVal })
        });
        let data = await res.json();

        if (data.success) {
            alert('✅ تم خصم الرصيد وحفظه في السيرفر بنجاح!');
            uFetch();
        } else {
            alert('⚠️ فشل الخصم: ' + (data.message || 'خطأ غير معروف'));
        }
    } catch (e) {
        alert('❌ حدث خطأ أثناء الخصم!');
    }
}

// ربط حدث البحث تلقائياً لو العنصر موجود
const searchElem = document.getElementById('uSearchInput');
if (searchElem) {
    searchElem.addEventListener('input', uSearch);
}

// بدء التشغيل
uFetch();
