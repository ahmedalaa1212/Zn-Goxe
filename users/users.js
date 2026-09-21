// =========================================
// ملف إدارة المستخدمين الفرعي (users/users.js)
// =========================================

let uDataList = [];

// جلب البيانات من السيرفر
async function uFetch() {
    const tbody = document.getElementById('uTableBody');
    if (!tbody) return;

    // إظهار مؤشر التحميل
    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #f59e0b; padding: 25px;">⏳ جاري جلب كافة بيانات المستخدمين...</td></tr>';

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
        console.error(err);
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
        if (u.isBanned || u.banned) {
            tr.style.opacity = "0.7";
            tr.style.backgroundColor = "rgba(239, 68, 68, 0.08)";
        }

        let isBanned = u.isBanned || u.banned;
        let statusBadge = isBanned 
            ? `<span style="background: rgba(239, 68, 68, 0.2); color: #ef4444; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-right: 5px;">محظور</span>`
            : `<span style="background: rgba(34, 197, 94, 0.2); color: #22c55e; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-right: 5px;">نشط</span>`;

        let actionBtn = isBanned 
            ? `<button class="u-btn u-btn-unban" onclick="uAction('${u.id || u.tg_id}', 'unban')">فك حظر</button>`
            : `<button class="u-btn u-btn-ban" onclick="uAction('${u.id || u.tg_id}', 'ban')">حظر</button>`;

        // تنسيق الرصيد الرئيسية
        let formattedBalance = typeof u.balance === 'number' ? u.balance.toLocaleString() : (u.balance || 0);

        tr.innerHTML = `
            <td style="color: #f59e0b; font-weight: bold; font-family: monospace;">${u.tg_id || u.id}</td>
            <td>${u.first_name || u.name || 'مستخدم'} ${statusBadge}</td>
            <td><span class="u-badge">💰 ${formattedBalance}</span></td>
            <td style="color: #38bdf8; font-size: 11px; white-space: nowrap; direction: ltr; text-align: center;">
                ${u.joinDate || 'غير معروف'}
            </td>
            <td>
                <div style="display: flex; flex-wrap: wrap; gap: 4px; justify-content: center;">
                    <button class="u-btn u-btn-details" onclick="uShowDetails('${u.id || u.tg_id}')">📋 التفاصيل</button>
                    <button class="u-btn u-btn-add" onclick="uAddBal('${u.id || u.tg_id}')">➕ رصيد</button>
                    <button class="u-btn u-btn-deduct" onclick="uDeductBal('${u.id || u.tg_id}')">➖ خصم</button>
                    ${actionBtn}
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// عرض جميع بيانات الفايربيس الشاملة في مودال
function uShowDetails(id) {
    let user = uDataList.find(x => String(x.id) === String(id) || String(x.tg_id) === String(id));
    if (!user) {
        alert("⚠️ لم يتم العثور على بيانات المستخدم");
        return;
    }

    let modal = document.getElementById('uDetailModal');
    let content = document.getElementById('uModalContent');
    if (!modal || !content) return;

    let fmt = (val) => (val !== undefined && val !== null && val !== '') ? val : '0';

    content.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; font-size: 13px;">
            <div class="u-info-card">
                <span class="u-info-title">🆔 ID التليجرام:</span>
                <span class="u-info-val" style="color: #f59e0b;">${user.tg_id || user.id}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">👤 الاسم الأول:</span>
                <span class="u-info-val">${user.first_name || 'غير محدد'}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">💰 الرصيد الرئيسي (Balance):</span>
                <span class="u-info-val" style="color: #10b981;">${fmt(user.balance)}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">💎 رصيد ZNX:</span>
                <span class="u-info-val" style="color: #38bdf8;">${fmt(user.znx_balance)}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">💵 رصيد USD:</span>
                <span class="u-info-val" style="color: #10b981;">$${fmt(user.usd_balance)}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">📺 رصيد الإعلانات:</span>
                <span class="u-info-val">${fmt(user.ad_balance)}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">⚡ معدل التعدين/ساعة:</span>
                <span class="u-info-val">${fmt(user.hourly_rate)}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">🚀 البوست اليومي:</span>
                <span class="u-info-val">${fmt(user.daily_boost_rate)}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">📦 مستوى المخزن:</span>
                <span class="u-info-val">${fmt(user.storage_level)}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">➕ مخزن إضافي:</span>
                <span class="u-info-val">${fmt(user.extra_storage)}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">🔋 السعة القصوى:</span>
                <span class="u-info-val">${fmt(user.max_cap)}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">⚡ الطاقة (Energy):</span>
                <span class="u-info-val">${fmt(user.energy)}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">👥 الأصدقاء المدعوين:</span>
                <span class="u-info-val" style="color: #f59e0b;">${fmt(user.invited_friends_count)}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">🔗 المُحيل (Referred By):</span>
                <span class="u-info-val">${user.referred_by || 'لا يوجد'}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">⏳ أرباح الإحالة المعلقة:</span>
                <span class="u-info-val">${fmt(user.pending_ref_earnings)}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">📊 إجمالي أرباح الإحالات:</span>
                <span class="u-info-val">${fmt(user.total_ref_earnings)}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">👁️ الإعلانات المشاهدة:</span>
                <span class="u-info-val">${fmt(user.ads_watched)}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">🔥 الستريك اليومي (Streak):</span>
                <span class="u-info-val">${fmt(user.daily_streak)}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">📅 تاريخ الانضمام:</span>
                <span class="u-info-val">${user.joined_at || user.joinDate || 'غير مسجل'}</span>
            </div>
            <div class="u-info-card">
                <span class="u-info-title">🕒 آخر نشاط:</span>
                <span class="u-info-val">${user.last_active || 'غير مسجل'}</span>
            </div>
            <div class="u-info-card" style="grid-column: 1 / -1;">
                <span class="u-info-title">👛 عنوان المحفظة:</span>
                <span class="u-info-val" style="word-break: break-all; color: #a7f3d0;">${user.wallet_address || 'لم يتم الربط'}</span>
            </div>
        </div>
    `;

    modal.style.display = 'flex';
}

function uCloseModal() {
    let modal = document.getElementById('uDetailModal');
    if (modal) modal.style.display = 'none';
}

// البحث والفلترة الفورية بكل البيانات
function uSearch() {
    let input = document.getElementById('uSearchInput');
    let term = input ? input.value.trim().toLowerCase() : '';

    let filtered = uDataList.filter(u => 
        String(u.tg_id || u.id).toLowerCase().includes(term) || 
        String(u.first_name || u.name || '').toLowerCase().includes(term) ||
        String(u.wallet_address || '').toLowerCase().includes(term)
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
            uFetch();
        } else {
            alert('⚠️ حدث خطأ: ' + (data.message || 'لم يكتمل الطلب'));
        }
    } catch (e) {
        alert('❌ حدث خطأ أثناء التواصل مع السيرفر!');
    }
}

// إضافة رصيد
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

// خصم رصيد
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

// بدء التشغيل
uFetch();
