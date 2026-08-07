// =========================================
// super_admin.js - الربط التفاعلي للوحة الإدارة العليا
// =========================================

// استخدام المسار النسبي لضمان عمل الاتصال مع السيرفر تلقائياً دون مشاكل CORS
const API_BASE = "/api";

// تحميل كافة البيانات تلقائياً فور تحميل الصفحة
document.addEventListener("DOMContentLoaded", () => {
    initEvents();
    loadGameSettings();
    loadModerators();
    loadAdminLogs();
});

// تنفيذ أولي مباشر في حال استدعاء الملف بشكل ديناميكي
initEvents();
loadGameSettings();
loadModerators();
loadAdminLogs();

/**
 * ربط الأحداث التفاعلية لحقول الإدخال والنسب تلقائياً
 */
function initEvents() {
    const targetMarginInput = document.getElementById('targetMarginInput');
    if (targetMarginInput && !targetMarginInput.dataset.bound) {
        targetMarginInput.dataset.bound = "true";
        targetMarginInput.addEventListener('input', calculateMargins);
    }
}

/**
 * حساب نسبة اللاعبين تلقائياً (100 - نسبة البوت) فور كتابة النسبة
 */
function calculateMargins() {
    const targetMarginInput = document.getElementById('targetMarginInput');
    const playerMarginInput = document.getElementById('playerMarginInput');
    
    if (!targetMarginInput || !playerMarginInput) return;

    let botMargin = parseFloat(targetMarginInput.value);
    
    if (isNaN(botMargin)) {
        playerMarginInput.value = '';
        return;
    }

    // تقييد حدود المدخلات للحفاظ على النسبة الصحيحة
    if (botMargin < 0) botMargin = 0;
    if (botMargin > 100) botMargin = 100;

    const playerMargin = (100.0 - botMargin).toFixed(2);
    playerMarginInput.value = parseFloat(playerMargin);
}

/**
 * تفعيل وضع التعديل وتفعيل حقل إدخال نسبة البوت
 */
function enableMarginEdit() {
    const targetMarginInput = document.getElementById('targetMarginInput');
    const btnEditMargin = document.getElementById('btnEditMargin');
    const btnPublishMargin = document.getElementById('btnPublishMargin');

    if (targetMarginInput) {
        targetMarginInput.disabled = false;
        targetMarginInput.focus();
        targetMarginInput.select();
    }

    if (btnEditMargin) btnEditMargin.style.display = 'none';
    if (btnPublishMargin) btnPublishMargin.style.display = 'block';
}

// ==========================================
// 1. نظام التحكم بالألعاب وأرباح البوت (Game & Profit Control)
// ==========================================

/**
 * جلب إحصائيات الأرباح ونسبة أرباح البوت المستهدفة من السيرفر وعرضها حياً
 */
async function loadGameSettings() {
    initEvents();
    const botProfitEl = document.getElementById('statBotProfit');
    const userProfitEl = document.getElementById('statUserProfit');
    const actualMarginEl = document.getElementById('statActualMargin');
    const targetMarginInput = document.getElementById('targetMarginInput');
    const playerMarginInput = document.getElementById('playerMarginInput');
    const btnEditMargin = document.getElementById('btnEditMargin');
    const btnPublishMargin = document.getElementById('btnPublishMargin');

    try {
        const response = await fetch(`${API_BASE}/game-settings`);
        const result = await response.json();

        if (result.success) {
            const stats = result.stats || {};
            const botProfit = stats.total_bot_profit || 0;
            const userProfit = stats.total_user_profit || 0;
            const actualMargin = stats.actual_margin !== undefined ? stats.actual_margin : (stats.actual_bot_percent || 0);
            const targetMargin = result.target_margin !== undefined ? result.target_margin : 70;

            // تحديث كروت الإحصائيات الحية
            if (botProfitEl) botProfitEl.innerText = Number(botProfit).toLocaleString('ar-EG');
            if (userProfitEl) userProfitEl.innerText = Number(userProfit).toLocaleString('ar-EG');
            if (actualMarginEl) actualMarginEl.innerText = `${actualMargin}%`;

            // ملء حقول النسب وحساب نسبة اللاعبين
            if (targetMarginInput) {
                targetMarginInput.value = targetMargin;
                targetMarginInput.disabled = true;
            }
            if (playerMarginInput) {
                playerMarginInput.value = parseFloat((100.0 - targetMargin).toFixed(2));
            }

            // إرجاع الأزرار لوضع العرض الافتراضي
            if (btnEditMargin) btnEditMargin.style.display = 'block';
            if (btnPublishMargin) btnPublishMargin.style.display = 'none';
        } else {
            if (botProfitEl) botProfitEl.innerText = "❌ خطأ";
            if (userProfitEl) userProfitEl.innerText = "❌ خطأ";
            if (actualMarginEl) actualMarginEl.innerText = "❌ خطأ";
        }
    } catch (error) {
        console.error("خطأ في جلب إعدادات الأرباح:", error);
        if (botProfitEl) botProfitEl.innerText = "⚠️ فشل";
        if (userProfitEl) userProfitEl.innerText = "⚠️ فشل";
        if (actualMarginEl) actualMarginEl.innerText = "⚠️ فشل";
    }
}

/**
 * تحديث نسبة أرباح البوت المستهدفة ونشرها فوراً إلى قاعدة البيانات
 */
async function updateGameSettings() {
    const input = document.getElementById('targetMarginInput');
    if (!input) return;

    const targetMarginVal = parseFloat(input.value);

    if (isNaN(targetMarginVal) || targetMarginVal < 0 || targetMarginVal > 100) {
        alert("⚠️ يرجى إدخال نسبة مئوية صحيحة بين 0 و 100!");
        return;
    }

    const payload = {
        target_margin: targetMarginVal,
        updatedBy: "المدير العام"
    };

    try {
        const response = await fetch(`${API_BASE}/game-settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (result.success) {
            alert(`✅ ${result.message || 'تم تحديث ونشر النسب بنجاح!'}`);
            await loadGameSettings();
            loadAdminLogs();
        } else {
            alert(`❌ خطأ: ${result.message || result.error}`);
        }
    } catch (error) {
        console.error("خطأ أثناء تحديث النسب:", error);
        alert("⚠️ فشل الاتصال بالسيرفر أثناء عملية الحفظ!");
    }
}

// دالتان للتوافقية مع المسميات القديمة
function loadHouseEdge() { loadGameSettings(); }
function updateHouseEdge() { updateGameSettings(); }


// ==========================================
// 2. إدارة المشرفين والصلاحيات والسجلات (Admin & Mod Management)
// ==========================================

/**
 * إضافة مشرف جديد مع الصلاحيات المحددة
 */
async function addNewModerator() {
    const modIdInput = document.getElementById('modTelegramId');
    const modNameInput = document.getElementById('modName');

    const modId = modIdInput ? modIdInput.value.trim() : "";
    const modName = modNameInput ? modNameInput.value.trim() : "";

    if (!modId || !modName) {
        alert("⚠️ يرجى إدخال ID المشرف والاسم بشكل صحيح!");
        return;
    }

    const permissions = {
        users: document.getElementById('perm_users')?.checked || false,
        support: document.getElementById('perm_support')?.checked || false,
        settings: document.getElementById('perm_settings')?.checked || false,
        transactions: document.getElementById('perm_transactions')?.checked || false,
        security: document.getElementById('perm_security')?.checked || false,
        ads: document.getElementById('perm_ads')?.checked || false,
    };

    const payload = {
        id: modId,
        name: modName,
        permissions: permissions,
        addedBy: "المدير العام"
    };

    try {
        const response = await fetch(`${API_BASE}/moderators`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (result.success) {
            alert(`✅ ${result.message || 'تمت إضافة المشرف بنجاح!'}`);
            if (modIdInput) modIdInput.value = '';
            if (modNameInput) modNameInput.value = '';
            loadModerators();
            loadAdminLogs();
        } else {
            alert(`❌ خطأ: ${result.message || result.error}`);
        }
    } catch (error) {
        console.error("خطأ في الاتصال عند إضافة المشرف:", error);
        alert("⚠️ فشل الاتصال بالسيرفر أثناء إضافة المشرف!");
    }
}

/**
 * جلب وعرض قائمة المشرفين الحالية
 */
async function loadModerators() {
    const listContainer = document.getElementById('moderatorsList');
    if (!listContainer) return;

    listContainer.innerHTML = `<p class="empty-msg">⏳ جاري التحميل من قاعدة البيانات...</p>`;

    try {
        const response = await fetch(`${API_BASE}/moderators`);
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
                        <span>ID: ${mod.id} | أضيف في: ${mod.addedAt || 'غير محدد'}</span>
                    </div>
                    ${deleteBtn}
                </div>
            `;
        });

        listContainer.innerHTML = html;

    } catch (error) {
        console.error("خطأ في جلب بيانات المشرفين:", error);
        listContainer.innerHTML = `<p class="empty-msg" style="color:#ef4444;">⚠️ تعذر جلب قائمة المشرفين.</p>`;
    }
}

/**
 * حذف مشرف وسحب صلاحياته
 */
async function deleteModerator(modId, modName) {
    if (!confirm(`⚠️ هل أنت متأكد من حذف المشرف (${modName}) وسحب جميع صلاحياته؟`)) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/moderators/${modId}?deletedBy=المدير العام`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            alert(`✅ ${result.message || 'تم حذف المشرف بنجاح'}`);
            loadModerators();
            loadAdminLogs();
        } else {
            alert(`❌ خطأ: ${result.message || result.error}`);
        }
    } catch (error) {
        console.error("خطأ أثناء الحذف:", error);
        alert("⚠️ فشل الاتصال بالسيرفر أثناء عملية الحذف!");
    }
}

/**
 * جلب وعرض سجل النشاطات والتحركات
 */
async function loadAdminLogs() {
    const logsContainer = document.getElementById('adminLogs');
    if (!logsContainer) return;

    logsContainer.innerHTML = `<p class="empty-msg">⏳ جاري تحميل السجل...</p>`;

    try {
        const response = await fetch(`${API_BASE}/admin-logs`);
        const result = await response.json();

        if (!result.success || !result.logs || result.logs.length === 0) {
            logsContainer.innerHTML = `<p class="empty-msg">لا توجد تحركات مسجلة حالياً.</p>`;
            return;
        }

        let html = '';
        result.logs.forEach(log => {
            html += `
                <div class="log-item">
                    <span class="log-admin">⚙️ ${log.admin || 'النظام'}</span>
                    <span style="color:#e2e8f0;">${log.action}</span>
                    <span class="log-time">${log.timestamp || ''}</span>
                </div>
            `;
        });

        logsContainer.innerHTML = html;

    } catch (error) {
        console.error("خطأ في جلب السجلات:", error);
        logsContainer.innerHTML = `<p class="empty-msg" style="color:#ef4444;">⚠️ تعذر تحميل سجل النشاط.</p>`;
    }
}
