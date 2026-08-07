// =========================================
// super_admin.js - الربط التفاعلي للوحة الإدارة العليا
// =========================================

const API_BASE = "/api";

/**
 * جلب بيانات التوثيق الخاصة بالتليجرام لتضمينها في طلبات الـ fetch
 */
function getTelegramInitData() {
    return window.Telegram?.WebApp?.initData || "";
}

/**
 * تجهيز الهيدرز الأساسية لمصادقة الأدمن مع السيرفر
 */
function getAuthHeaders() {
    const initData = getTelegramInitData();
    return {
        'Content-Type': 'application/json',
        'X-Telegram-Init-Data': initData,
        'Authorization': `Bearer ${initData}`
    };
}

// تحميل كافة البيانات تلقائياً فور تحميل الصفحة
document.addEventListener("DOMContentLoaded", () => {
    initEvents();
    loadDashboardStats();
    loadModerators();
    loadAdminLogs();
});

/**
 * ربط الأحداث التفاعلية لحقول الإدخال والنسب تلقائياً
 */
function initEvents() {
    const targetMarginInput = document.getElementById('bot-margin-input') || document.getElementById('targetMarginInput');
    if (targetMarginInput && !targetMarginInput.dataset.bound) {
        targetMarginInput.dataset.bound = "true";
        targetMarginInput.addEventListener('input', calculateMargins);
    }

    const updateRatioBtn = document.getElementById('update-ratio-btn');
    if (updateRatioBtn && !updateRatioBtn.dataset.bound) {
        updateRatioBtn.dataset.bound = "true";
        updateRatioBtn.addEventListener('click', updateGameSettings);
    }
}

/**
 * حساب نسبة اللاعبين تلقائياً (100 - نسبة البوت) فور كتابة النسبة
 */
function calculateMargins() {
    const targetMarginInput = document.getElementById('bot-margin-input') || document.getElementById('targetMarginInput');
    const playerMarginInput = document.getElementById('user-margin-input') || document.getElementById('playerMarginInput');
    
    if (!targetMarginInput || !playerMarginInput) return;

    let botMargin = parseFloat(targetMarginInput.value);
    
    if (isNaN(botMargin)) {
        playerMarginInput.value = '';
        return;
    }

    if (botMargin < 0) botMargin = 0;
    if (botMargin > 100) botMargin = 100;

    const playerMargin = (100.0 - botMargin).toFixed(2);
    playerMarginInput.value = parseFloat(playerMargin);
}

/**
 * تفعيل وضع التعديل وتفعيل حقل إدخال نسبة البوت
 */
function enableMarginEdit() {
    const targetMarginInput = document.getElementById('bot-margin-input') || document.getElementById('targetMarginInput');
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
async function loadDashboardStats() {
    initEvents();
    
    const botProfitEl = document.getElementById('bot-profit-val');
    const userProfitEl = document.getElementById('user-profit-val');
    const actualMarginEl = document.getElementById('actual-profit-pct');
    
    const targetMarginInput = document.getElementById('bot-margin-input') || document.getElementById('targetMarginInput');
    const playerMarginInput = document.getElementById('user-margin-input') || document.getElementById('playerMarginInput');
    
    const btnEditMargin = document.getElementById('btnEditMargin');
    const btnPublishMargin = document.getElementById('btnPublishMargin');

    try {
        let response = await fetch(`${API_BASE}/admin/dashboard-stats`, {
            method: 'GET',
            headers: getAuthHeaders()
        });

        if (!response.ok) {
            response = await fetch(`${API_BASE}/admin/stats`, {
                method: 'GET',
                headers: getAuthHeaders()
            });
        }

        if (!response.ok) {
            response = await fetch(`${API_BASE}/game-settings`, {
                method: 'GET',
                headers: getAuthHeaders()
            });
        }

        const result = await response.json();

        if (result.status === 'success' || result.success) {
            const stats = result.stats || result.data || {};
            
            const botProfit = stats.total_bot_profit !== undefined ? stats.total_bot_profit : (result.total_bot_profit || 0);
            const userProfit = stats.total_wins !== undefined ? stats.total_wins : (stats.total_user_profit !== undefined ? stats.total_user_profit : (result.total_user_profit || 0));
            const actualMargin = stats.actual_bot_percent !== undefined ? stats.actual_bot_percent : (stats.actual_margin !== undefined ? stats.actual_margin : (result.actual_margin || 0));
            
            const targetMargin = stats.target_margin_percent !== undefined ? stats.target_margin_percent : (result.target_margin !== undefined ? result.target_margin : (result.bot_margin || 70));

            if (botProfitEl) botProfitEl.innerText = Number(botProfit).toLocaleString('ar-EG');
            if (userProfitEl) userProfitEl.innerText = Number(userProfit).toLocaleString('ar-EG');
            if (actualMarginEl) actualMarginEl.innerText = `${actualMargin}%`;

            if (targetMarginInput) {
                targetMarginInput.value = targetMargin;
            }
            if (playerMarginInput) {
                playerMarginInput.value = parseFloat((100.0 - targetMargin).toFixed(2));
            }

            if (btnEditMargin) btnEditMargin.style.display = 'block';
            if (btnPublishMargin) btnPublishMargin.style.display = 'none';
        } else {
            console.warn("تعذر جلب الإحصائيات:", result.message || result.error);
            if (botProfitEl) botProfitEl.innerText = "0";
            if (userProfitEl) userProfitEl.innerText = "0";
            if (actualMarginEl) actualMarginEl.innerText = "0%";
        }
    } catch (error) {
        console.error("خطأ في جلب بيانات لوحة التحكم:", error);
        if (botProfitEl) botProfitEl.innerText = "0";
        if (userProfitEl) userProfitEl.innerText = "0";
        if (actualMarginEl) actualMarginEl.innerText = "0%";
    }
}

async function loadGameSettings() {
    return await loadDashboardStats();
}

/**
 * تحديث نسبة أرباح البوت المستهدفة ونشرها فوراً إلى قاعدة البيانات
 */
async function updateGameSettings() {
    const input = document.getElementById('bot-margin-input') || document.getElementById('targetMarginInput');
    if (!input) return;

    const targetMarginVal = parseFloat(input.value);

    if (isNaN(targetMarginVal) || targetMarginVal < 0 || targetMarginVal > 100) {
        alert("⚠️ يرجى إدخال نسبة مئوية صحيحة بين 0 و 100!");
        return;
    }

    const payload = {
        bot_margin: targetMarginVal,
        target_margin: targetMarginVal,
        player_margin: parseFloat((100.0 - targetMarginVal).toFixed(2)),
        updatedBy: "المدير العام"
    };

    try {
        let response = await fetch(`${API_BASE}/admin/update-margin`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            response = await fetch(`${API_BASE}/admin/settings`, {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify(payload)
            });
        }

        if (!response.ok) {
            response = await fetch(`${API_BASE}/game-settings`, {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify(payload)
            });
        }

        const result = await response.json();

        if (result.status === 'success' || result.success) {
            alert(`✅ ${result.message || 'تم تحديث ونشر النسب بنجاح!'}`);
            input.disabled = true;
            await loadDashboardStats();
            loadAdminLogs();
        } else {
            alert(`❌ خطأ: ${result.message || result.error || 'حدث خطأ أثناء حفظ الإعدادات'}`);
        }
    } catch (error) {
        console.error("خطأ أثناء تحديث النسب:", error);
        alert("⚠️ فشل الاتصال بالسيرفر أثناء عملية الحفظ!");
    }
}

function loadHouseEdge() { loadDashboardStats(); }
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
            headers: getAuthHeaders(),
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
        const response = await fetch(`${API_BASE}/moderators`, {
            method: 'GET',
            headers: getAuthHeaders()
        });

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
            method: 'DELETE',
            headers: getAuthHeaders()
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
        const response = await fetch(`${API_BASE}/admin-logs`, {
            method: 'GET',
            headers: getAuthHeaders()
        });

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
