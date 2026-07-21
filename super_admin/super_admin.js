// =========================================
// super_admin.js - كود العمليات للإدارة العليا
// =========================================

// تشغيل الدوال بمجرد تحميل القائمة
loadModerators();
loadAdminLogs();

// 1. دالة إضافة مشرف جديد
function addNewModerator() {
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

    const newMod = {
        id: modId,
        name: modName,
        permissions: permissions,
        addedAt: new Date().toLocaleDateString('ar-EG')
    };

    console.log("البيانات الجاهزة للإرسال لقاعدة البيانات:", newMod);
    
    // محاكاة النجاح
    alert(`✅ تم إضافة المشرف (${modName}) بنجاح!`);
    
    // تصفير الخانات بعد الإضافة
    document.getElementById('modTelegramId').value = '';
    document.getElementById('modName').value = '';
    
    loadModerators();
}

// 2. دالة جلب قائمة المشرفين
function loadModerators() {
    const listContainer = document.getElementById('moderatorsList');
    
    // داتا مؤقتة للتجربة لحد ما نربط قاعدة البيانات
    const mockMods = [
        { id: "123456789", name: "المدير الأساسي", addedAt: "2026-07-20", isMain: true },
        { id: "987654321", name: "أحمد (دعم فني)", addedAt: "2026-07-21", isMain: false }
    ];

    if (mockMods.length === 0) {
        listContainer.innerHTML = `<p class="empty-msg">لا يوجد مشرفين حالياً.</p>`;
        return;
    }

    let html = '';
    mockMods.forEach(mod => {
        const deleteBtn = mod.isMain 
            ? `<span style="font-size: 10px; color: #f59e0b;">👑 لا يمكن حذفه</span>` 
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
}

// 3. دالة حذف مشرف
function deleteModerator(modId, modName) {
    if (confirm(`⚠️ هل أنت متأكد من حذف المشرف (${modName}) وسحب صلاحياته؟`)) {
        console.log(`تم إرسال أمر حذف المشرف ID: ${modId}`);
        alert("✅ تم سحب الصلاحيات بنجاح.");
        loadModerators();
    }
}

// 4. دالة جلب السجلات
function loadAdminLogs() {
    const logsContainer = document.getElementById('adminLogs');
    
    const mockLogs = [
        { admin: "أحمد (دعم فني)", action: "رد على تذكرة المستخدم ID: 555444", time: "منذ 15 دقيقة" },
        { admin: "المدير الأساسي", action: "تعديل إعدادات الأسعار", time: "منذ ساعتين" }
    ];

    if (mockLogs.length === 0) {
        logsContainer.innerHTML = `<p class="empty-msg">لا توجد تحركات مسجلة حالياً.</p>`;
        return;
    }

    let html = '';
    mockLogs.forEach(log => {
        html += `
            <div class="log-item">
                <span class="log-admin">⚙️ ${log.admin}</span>
                <span>${log.action}</span>
                <span class="log-time">${log.time}</span>
            </div>
        `;
    });

    logsContainer.innerHTML = html;
}
