// =========================================
// super_admin.js - كود الربط الفعلي مع السيرفر
// =========================================

// تحميل البيانات فور فتح القائمة
loadModerators();
loadAdminLogs();

// 1. دالة إضافة مشرف جديد
async function addNewModerator() {
    const modId = document.getElementById('modTelegramId').value.trim();
    const modName = document.getElementById('modName').value.trim();

    if (!modId || !modName) {
        alert("⚠️ يرجى إدخال ID المشرف والاسم بشكل صحيح!");
        return;
    }

    const permissions = {
        users: document.getElementById('perm_users').checked,
        support: document.getElementById('perm_support').checked,
        settings: document.getElementById('perm_settings').checked,
        transactions: document.getElementById('perm_transactions').checked,
        security: document.getElementById('perm_security').checked,
        ads: document.getElementById('perm_ads').checked,
    };

    const payload = {
        id: modId,
        name: modName,
        permissions: permissions,
        addedBy: "المدير العام"
    };

    try {
        const response = await fetch('/api/moderators', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (result.success) {
            alert(`✅ ${result.message}`);
            // تصفير المدخلات
            document.getElementById('modTelegramId').value = '';
            document.getElementById('modName').value = '';
            // تحديث القوائم والسجل
            loadModerators();
            loadAdminLogs();
        } else {
            alert(`❌ خطأ: ${result.message || result.error}`);
        }
    } catch (error) {
        console.error("خطأ في الاتصال:", error);
        alert("⚠️ فشل الاتصال بالسيرفر!");
    }
}

// 2. دالة جلب المشرفين من الفايربيس
async function loadModerators() {
    const listContainer = document.getElementById('moderatorsList');
    listContainer.innerHTML = `<p class="empty-msg">⏳ جاري التحميل من قاعدة البيانات...</p>`;

    try {
        const response = await fetch('/api/moderators');
        const result = await response.json();

        if (!result.success || !result.moderators || result.moderators.length === 0) {
            listContainer.innerHTML = `<p class="empty-msg">لا يوجد مشرفين مضافين حالياً.</p>`;
            return;
        }

        let html = '';
        result.moderators.forEach(mod => {
            const deleteBtn = mod.isMain 
                ? `<span style="font-size: 10px; color: #f59e0b;">👑 مدير رئيسي</span>` 
                : `<button class="btn-danger-sm" onclick="deleteModerator('${mod.id}', '${mod.name}')">حذف ❌</button>`;

            html += `
                <div class="mod-item">
                    <div class="mod-info">
                        <strong>👤 ${mod.name}</strong>
                        <span>ID: ${mod.id} | أضيف في: ${mod.addedAt}</span>
                    </div>
                    ${deleteBtn}
                </div>
            `;
        });

        listContainer.innerHTML = html;

    } catch (error) {
        console.error("خطأ في جلب البيانات:", error);
        listContainer.innerHTML = `<p class="empty-msg" style="color:#ef4444;">⚠️ تعذر جلب قائمة المشرفين.</p>`;
    }
}

// 3. دالة حذف مشرف
async function deleteModerator(modId, modName) {
    if (!confirm(`⚠️ هل أنت متأكد من حذف المشرف (${modName}) وسحب جميع صلاحياته؟`)) {
        return;
    }

    try {
        const response = await fetch(`/api/moderators/${modId}?deletedBy=المدير العام`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            alert(`✅ ${result.message}`);
            loadModerators();
            loadAdminLogs();
        } else {
            alert(`❌ خطأ: ${result.message || result.error}`);
        }
    } catch (error) {
        console.error("خطأ أثناء الحذف:", error);
        alert("⚠️ فشل الاتصال بالسيرفر أثناء الحذف!");
    }
}

// 4. دالة جلب سجل النشاطات (Logs)
async function loadAdminLogs() {
    const logsContainer = document.getElementById('adminLogs');
    logsContainer.innerHTML = `<p class="empty-msg">⏳ جاري تحميل السجل...</p>`;

    try {
        const response = await fetch('/api/admin-logs');
        const result = await response.json();

        if (!result.success || !result.logs || result.logs.length === 0) {
            logsContainer.innerHTML = `<p class="empty-msg">لا توجد تحركات مسجلة حالياً.</p>`;
            return;
        }

        let html = '';
        result.logs.forEach(log => {
            html += `
                <div class="log-item">
                    <span class="log-admin">⚙️ ${log.admin}</span>
                    <span style="color:#e2e8f0;">${log.action}</span>
                    <span class="log-time">${log.timestamp}</span>
                </div>
            `;
        });

        logsContainer.innerHTML = html;

    } catch (error) {
        console.error("خطأ في جلب السجلات:", error);
        logsContainer.innerHTML = `<p class="empty-msg" style="color:#ef4444;">⚠️ تعذر تحميل سجل النشاط.</p>`;
    }
}
