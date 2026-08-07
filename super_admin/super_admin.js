// =========================================
// super_admin.js - الربط التفاعلي المستقر للوحة الإدارة العليا
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

/**
 * معالج موحد لطلبات الشبكة للتحقق من كود 403 وإغلاق التطبيق فوراً
 */
async function apiFetch(url, options = {}) {
    const defaultHeaders = getAuthHeaders();
    options.headers = { ...defaultHeaders, ...(options.headers || {}) };

    try {
        const response = await fetch(url, options);
        if (response.status === 403) {
            alert("⛔ عذراً، البوت مخصص للإدارة فقط!");
            if (window.Telegram && window.Telegram.WebApp) {
                window.Telegram.WebApp.close();
            }
            throw new Error("Unauthorized access (403)");
        }
        return response;
    } catch (err) {
        console.error("API Fetch Error:", err);
        throw err;
    }
}

/**
 * دالة الفحص الأولية للتأكد من هويّة الأدمن فور فتح الصفحة
 */
async function verifyAdminAccessOnLoad() {
    try {
        const res = await fetch(`${API_BASE}/verify_admin`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ initData: getTelegramInitData() })
        });

        if (res.status === 403 || !res.ok) {
            alert("⛔ عذراً، البوت مخصص للإدارة فقط!");
            if (window.Telegram && window.Telegram.WebApp) {
                window.Telegram.WebApp.close();
            }
            return false;
        }

        const data = await res.json();
        if (!data.success) {
            alert("⛔ عذراً، البوت مخصص للإدارة فقط!");
            if (window.Telegram && window.Telegram.WebApp) {
                window.Telegram.WebApp.close();
            }
            return false;
        }

        return true;
    } catch (err) {
        console.error("❌ Auth verification failed:", err);
        alert("⛔ عذراً، البوت مخصص للإدارة فقط!");
        if (window.Telegram && window.Telegram.WebApp) {
            window.Telegram.WebApp.close();
        }
        return false;
    }
}

/**
 * تهيئة القسم وتنفيذ جلب البيانات فور تحميل واجهة الإدارة العليا
 */
async function initSuperAdmin() {
    initEvents();
    const isAuthorized = await verifyAdminAccessOnLoad();
    if (!isAuthorized) return;

    loadDashboardStats();
    loadModerators();
    loadAdminLogs();
}

window.initSuperAdmin = initSuperAdmin;

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSuperAdmin);
} else {
    initSuperAdmin();
}

/**
 * ربط الأحداث التفاعلية لحقول الإدخال والنسب تلقائياً
 */
function initEvents() {
    // 1. ربط حقول الإعدادات العامة
    const targetMarginInput = document.getElementById('bot-margin-input') || document.getElementById('targetMarginInput');
    if (targetMarginInput && !targetMarginInput.dataset.bound) {
        targetMarginInput.dataset.bound = "true";
        targetMarginInput.addEventListener('input', calculateMargins);
    }

    const updateRatioBtn = document.getElementById('update-ratio-btn') || document.getElementById('btnPublishMargin');
    if (updateRatioBtn && !updateRatioBtn.dataset.bound) {
        updateRatioBtn.dataset.bound = "true";
        updateRatioBtn.addEventListener('click', updateGameSettings);
    }

    const btnEditMargin = document.getElementById('btnEditMargin');
    if (btnEditMargin && !btnEditMargin.dataset.bound) {
        btnEditMargin.dataset.bound = "true";
        btnEditMargin.addEventListener('click', enableMarginEdit);
    }

    // 2. ربط حقول الساحة الكبرى (شبكة الـ 36)
    const arenaBotMarginInput = document.getElementById('arena-bot-margin-input');
    if (arenaBotMarginInput && !arenaBotMarginInput.dataset.bound) {
        arenaBotMarginInput.dataset.bound = "true";
        arenaBotMarginInput.addEventListener('input', calculateArenaMargins);
    }

    const btnEditArena = document.getElementById('btnEditArena');
    if (btnEditArena && !btnEditArena.dataset.bound) {
        btnEditArena.dataset.bound = "true";
        btnEditArena.addEventListener('click', enableArena36Edit);
    }

    const btnPublishArena = document.getElementById('btnPublishArena');
    if (btnPublishArena && !btnPublishArena.dataset.bound) {
        btnPublishArena.dataset.bound = "true";
        btnPublishArena.addEventListener('click', updateArena36Settings);
    }
}
window.initEvents = initEvents;

/**
 * حساب نسبة اللاعبين تلقائياً (100 - نسبة البوت) للإعدادات العامة
 */
function calculateMargins() {
    const targetMarginInput = document.getElementById('bot-margin-input') || document.getElementById('targetMarginInput');
    const playerMarginInput = document.getElementById('user-margin-input') || document.getElementById('playerMarginInput');
    
    if (!targetMarginInput || !playerMarginInput) return;

    let botMargin = parseFloat(targetMarginInput.value);
    if (isNaN(botMargin)) { playerMarginInput.value = ''; return; }
    if (botMargin < 0) botMargin = 0;
    if (botMargin > 100) botMargin = 100;

    playerMarginInput.value = parseFloat((100.0 - botMargin).toFixed(2));
}
window.calculateMargins = calculateMargins;

/**
 * حساب نسبة اللاعبين تلقائياً للساحة الكبرى (شبكة الـ 36)
 */
function calculateArenaMargins() {
    const arenaBotMarginInput = document.getElementById('arena-bot-margin-input');
    const arenaUserMarginInput = document.getElementById('arena-user-margin-input');
    
    if (!arenaBotMarginInput || !arenaUserMarginInput) return;

    let botMargin = parseFloat(arenaBotMarginInput.value);
    if (isNaN(botMargin)) { arenaUserMarginInput.value = ''; return; }
    if (botMargin < 0) botMargin = 0;
    if (botMargin > 100) botMargin = 100;

    arenaUserMarginInput.value = parseFloat((100.0 - botMargin).toFixed(2));
}
window.calculateArenaMargins = calculateArenaMargins;

/**
 * تفعيل وضع التعديل وتفعيل حقول الإدخال للإعدادات العامة
 */
function enableMarginEdit() {
    const targetMarginInput = document.getElementById('bot-margin-input') || document.getElementById('targetMarginInput');
    const minBetInput = document.getElementById('min-bet-input');
    const btnEditMargin = document.getElementById('btnEditMargin');
    const btnPublishMargin = document.getElementById('btnPublishMargin') || document.getElementById('update-ratio-btn');

    if (targetMarginInput) {
        targetMarginInput.disabled = false;
        targetMarginInput.focus();
        targetMarginInput.select();
    }
    if (minBetInput) minBetInput.disabled = false;

    if (btnEditMargin) btnEditMargin.style.display = 'none';
    if (btnPublishMargin) btnPublishMargin.style.display = 'block';
}
window.enableMarginEdit = enableMarginEdit;

/**
 * تفعيل وضع التعديل للساحة الكبرى (شبكة الـ 36)
 */
function enableArena36Edit() {
    const arenaBotInput = document.getElementById('arena-bot-margin-input');
    const arenaMinBetInput = document.getElementById('arena-min-bet-input');
    const arenaToggle = document.getElementById('arena-status-toggle');
    const btnEditArena = document.getElementById('btnEditArena');
    const btnPublishArena = document.getElementById('btnPublishArena');

    if (arenaBotInput) {
        arenaBotInput.disabled = false;
        arenaBotInput.focus();
        arenaBotInput.select();
    }
    if (arenaMinBetInput) arenaMinBetInput.disabled = false;
    if (arenaToggle) arenaToggle.disabled = false;

    if (btnEditArena) btnEditArena.style.display = 'none';
    if (btnPublishArena) btnPublishArena.style.display = 'block';
}
window.enableArena36Edit = enableArena36Edit;

/**
 * زر التحديث (الريفرش) لجلب أحدث الأرقام من الفايربيس
 */
async function refreshDashboard() {
    await loadDashboardStats();
    await loadModerators();
    await loadAdminLogs();
    alert("🔄 تم تحديث البيانات بنجاح من الفايربيس!");
}
window.refreshDashboard = refreshDashboard;

// ==========================================
// 1. نظام التحكم بالألعاب وأرباح البوت (Game & Profit Control)
// ==========================================

/**
 * جلب إحصائيات الأرباح ونسبة أرباح البوت والساحة الكبرى من السيرفر والفايربيس
 */
async function loadDashboardStats() {
    initEvents();
    
    const botProfitEl = document.getElementById('bot-profit-val');
    const userProfitEl = document.getElementById('user-profit-val');
    const actualMarginEl = document.getElementById('actual-profit-pct');
    
    const targetMarginInput = document.getElementById('bot-margin-input') || document.getElementById('targetMarginInput');
    const playerMarginInput = document.getElementById('user-margin-input') || document.getElementById('playerMarginInput');
    const minBetInput = document.getElementById('min-bet-input');
    
    const arenaBotInput = document.getElementById('arena-bot-margin-input');
    const arenaUserInput = document.getElementById('arena-user-margin-input');
    const arenaMinBetInput = document.getElementById('arena-min-bet-input');
    const arenaToggle = document.getElementById('arena-status-toggle');

    const btnEditMargin = document.getElementById('btnEditMargin');
    const btnPublishMargin = document.getElementById('btnPublishMargin') || document.getElementById('update-ratio-btn');
    const btnEditArena = document.getElementById('btnEditArena');
    const btnPublishArena = document.getElementById('btnPublishArena');

    try {
        let response = await apiFetch(`${API_BASE}/game-settings`, { method: 'GET' });

        if (!response.ok) {
            response = await apiFetch(`${API_BASE}/admin/dashboard-stats`, { method: 'GET' });
        }

        const result = await response.json();

        if (response.ok && (result.status === 'success' || result.success)) {
            const stats = result.stats || result.data || {};
            
            const botProfit = stats.total_bot_profit !== undefined ? stats.total_bot_profit : (result.total_bot_profit || 0);
            const userProfit = stats.total_wins !== undefined ? stats.total_wins : (stats.total_user_profit !== undefined ? stats.total_user_profit : (result.total_user_profit || 0));
            const actualMargin = stats.actual_bot_percent !== undefined ? stats.actual_bot_percent : (stats.actual_margin !== undefined ? stats.actual_margin : (result.actual_margin || 0));
            const targetMargin = stats.target_margin_percent !== undefined ? stats.target_margin_percent : (result.target_margin !== undefined ? result.target_margin : (result.bot_margin || 70));
            
            const minBet = stats.min_bet !== undefined ? stats.min_bet : (result.min_bet !== undefined ? result.min_bet : (result.grid_game_config?.min_bet || 10));

            if (botProfitEl) botProfitEl.innerText = Number(botProfit).toLocaleString('ar-EG');
            if (userProfitEl) userProfitEl.innerText = Number(userProfit).toLocaleString('ar-EG');
            if (actualMarginEl) actualMarginEl.innerText = `${actualMargin}%`;

            // تحديث الحقول العامة
            if (targetMarginInput) targetMarginInput.value = targetMargin;
            if (playerMarginInput) playerMarginInput.value = parseFloat((100.0 - targetMargin).toFixed(2));
            if (minBetInput) minBetInput.value = minBet;

            if (targetMarginInput) targetMarginInput.disabled = true;
            if (minBetInput) minBetInput.disabled = true;
            if (btnEditMargin) btnEditMargin.style.display = 'block';
            if (btnPublishMargin) btnPublishMargin.style.display = 'none';

            // تحديث حقول الساحة الكبرى (شبكة الـ 36)
            if (result.arena_36) {
                const arenaData = result.arena_36;
                if (arenaBotInput) arenaBotInput.value = arenaData.target_margin;
                if (arenaUserInput) arenaUserInput.value = arenaData.player_margin;
                if (arenaMinBetInput) arenaMinBetInput.value = arenaData.min_bet;
                if (arenaToggle) arenaToggle.checked = arenaData.active;
            }

            if (arenaBotInput) arenaBotInput.disabled = true;
            if (arenaMinBetInput) arenaMinBetInput.disabled = true;
            if (arenaToggle) arenaToggle.disabled = true;
            if (btnEditArena) btnEditArena.style.display = 'block';
            if (btnPublishArena) btnPublishArena.style.display = 'none';

        } else {
            console.warn("⚠️ تعذر جلب الإحصائيات من السيرفر:", result.message || result.error);
        }
    } catch (error) {
        console.error("❌ خطأ في جلب بيانات لوحة التحكم:", error);
    }
}
window.loadDashboardStats = loadDashboardStats;

async function loadGameSettings() {
    return await loadDashboardStats();
}
window.loadGameSettings = loadGameSettings;

/**
 * تحديث نسبة أرباح البوت والحد الأدنى العامة ونشرها فوراً إلى قاعدة البيانات
 */
async function updateGameSettings() {
    const input = document.getElementById('bot-margin-input') || document.getElementById('targetMarginInput');
    const minBetInput = document.getElementById('min-bet-input');
    
    if (!input) return;

    const targetMarginVal = parseFloat(input.value);
    const minBetVal = minBetInput ? parseFloat(minBetInput.value) : undefined;

    if (isNaN(targetMarginVal) || targetMarginVal < 0 || targetMarginVal > 100) {
        alert("⚠️ يرجى إدخال نسبة مئوية صحيحة بين 0 و 100!");
        return;
    }

    if (minBetInput && (isNaN(minBetVal) || minBetVal < 0)) {
        alert("⚠️ يرجى إدخال حد أدنى صحيح للعب!");
        return;
    }

    const payload = {
        initData: getTelegramInitData(),
        bot_margin: targetMarginVal,
        target_margin: targetMarginVal,
        player_margin: parseFloat((100.0 - targetMarginVal).toFixed(2)),
        min_bet: minBetVal,
        updatedBy: "المدير العام"
    };

    try {
        let response = await apiFetch(`${API_BASE}/game-settings`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            response = await apiFetch(`${API_BASE}/admin/update-margin`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });
        }

        const result = await response.json();

        if (response.ok && (result.status === 'success' || result.success)) {
            alert(`✅ ${result.message || 'تم تحديث ونشر النسب والحد الأدنى بنجاح!'}`);
            input.disabled = true;
            if (minBetInput) minBetInput.disabled = true;
            
            const btnEditMargin = document.getElementById('btnEditMargin');
            const btnPublishMargin = document.getElementById('btnPublishMargin') || document.getElementById('update-ratio-btn');
            if (btnEditMargin) btnEditMargin.style.display = 'block';
            if (btnPublishMargin) btnPublishMargin.style.display = 'none';

            await loadDashboardStats();
            loadAdminLogs();
        } else {
            alert(`❌ خطأ (${response.status}): ${result.message || result.error || 'حدث خطأ أثناء حفظ الإعدادات'}`);
        }
    } catch (error) {
        console.error("❌ خطأ أثناء تحديث النسب:", error);
    }
}
window.updateGameSettings = updateGameSettings;

/**
 * تحديث إعدادات الساحة الكبرى (شبكة الـ 36) ونشرها فوراً إلى الفايربيس
 */
async function updateArena36Settings() {
    const arenaBotInput = document.getElementById('arena-bot-margin-input');
    const arenaMinBetInput = document.getElementById('arena-min-bet-input');
    const arenaToggle = document.getElementById('arena-status-toggle');

    if (!arenaBotInput) return;

    const targetMarginVal = parseFloat(arenaBotInput.value);
    const minBetVal = arenaMinBetInput ? parseFloat(arenaMinBetInput.value) : 10;
    const activeVal = arenaToggle ? arenaToggle.checked : true;

    if (isNaN(targetMarginVal) || targetMarginVal < 0 || targetMarginVal > 100) {
        alert("⚠️ يرجى إدخال نسبة مئوية صحيحة للساحة الكبرى بين 0 و 100!");
        return;
    }

    if (isNaN(minBetVal) || minBetVal < 0) {
        alert("⚠️ يرجى إدخال حد أدنى صحيح للرهان في الساحة الكبرى!");
        return;
    }

    const payload = {
        initData: getTelegramInitData(),
        bot_margin: targetMarginVal,
        target_margin: targetMarginVal,
        player_margin: parseFloat((100.0 - targetMarginVal).toFixed(2)),
        min_bet: minBetVal,
        active: activeVal,
        updatedBy: "المدير العام"
    };

    try {
        const response = await apiFetch(`${API_BASE}/admin/update-arena-36`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (response.ok && (result.status === 'success' || result.success)) {
            alert(`✅ ${result.message || 'تم تحديث ونشر إعدادات الساحة الكبرى بنجاح!'}`);
            
            arenaBotInput.disabled = true;
            if (arenaMinBetInput) arenaMinBetInput.disabled = true;
            if (arenaToggle) arenaToggle.disabled = true;

            const btnEditArena = document.getElementById('btnEditArena');
            const btnPublishArena = document.getElementById('btnPublishArena');
            if (btnEditArena) btnEditArena.style.display = 'block';
            if (btnPublishArena) btnPublishArena.style.display = 'none';

            await loadDashboardStats();
            loadAdminLogs();
        } else {
            alert(`❌ خطأ (${response.status}): ${result.message || result.error || 'حدث خطأ أثناء حفظ إعدادات الساحة'}`);
        }
    } catch (error) {
        console.error("❌ خطأ أثناء تحديث إعدادات الساحة الكبرى:", error);
    }
}
window.updateArena36Settings = updateArena36Settings;

function loadHouseEdge() { loadDashboardStats(); }
function updateHouseEdge() { updateGameSettings(); }
window.loadHouseEdge = loadHouseEdge;
window.updateHouseEdge = updateHouseEdge;

// ==========================================
// 2. إدارة المشرفين والصلاحيات والسجلات (Admin & Mod Management)
// ==========================================

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
        initData: getTelegramInitData(),
        id: modId,
        name: modName,
        permissions: permissions,
        addedBy: "المدير العام"
    };

    try {
        const response = await apiFetch(`${API_BASE}/moderators`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (response.ok && result.success) {
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
    }
}
window.addNewModerator = addNewModerator;

async function loadModerators() {
    const listContainer = document.getElementById('moderatorsList');
    if (!listContainer) return;

    try {
        const response = await apiFetch(`${API_BASE}/moderators`, { method: 'GET' });
        const result = await response.json();

        if (!response.ok || !result.success || !result.moderators || result.moderators.length === 0) {
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
window.loadModerators = loadModerators;

async function deleteModerator(modId, modName) {
    if (!confirm(`⚠️ هل أنت متأكد من حذف المشرف (${modName}) وسحب جميع صلاحياته؟`)) {
        return;
    }

    try {
        const response = await apiFetch(`${API_BASE}/moderators/${modId}?deletedBy=المدير العام`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (response.ok && result.success) {
            alert(`✅ ${result.message || 'تم حذف المشرف بنجاح'}`);
            loadModerators();
            loadAdminLogs();
        } else {
            alert(`❌ خطأ: ${result.message || result.error}`);
        }
    } catch (error) {
        console.error("خطأ أثناء الحذف:", error);
    }
}
window.deleteModerator = deleteModerator;

async function loadAdminLogs() {
    const logsContainer = document.getElementById('adminLogs');
    if (!logsContainer) return;

    try {
        const response = await apiFetch(`${API_BASE}/admin-logs`, { method: 'GET' });
        const result = await response.json();

        if (!response.ok || !result.success || !result.logs || result.logs.length === 0) {
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
window.loadAdminLogs = loadAdminLogs;
