// =========================================
// super_admin.js - الربط التفاعلي المستقر للوحة الإدارة العليا (ZN Go & Big Arena)
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
    loadZnGoSettings();
    loadBigArenaSettings();
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
    // 1. ربط حقول لعبة شبكة ZN Go
    const grid36BotInput = document.getElementById('grid36-bot-margin');
    if (grid36BotInput && !grid36BotInput.dataset.bound) {
        grid36BotInput.dataset.bound = "true";
        grid36BotInput.addEventListener('input', calculateZnGoMargins);
    }

    // 2. ربط حقول لعبة الساحة الكبرى
    const bigArenaBotInput = document.getElementById('big-arena-bot-margin');
    if (bigArenaBotInput && !bigArenaBotInput.dataset.bound) {
        bigArenaBotInput.dataset.bound = "true";
        bigArenaBotInput.addEventListener('input', calculateBigArenaMargins);
    }
}
window.initEvents = initEvents;

/**
 * حساب نسبة اللاعبين تلقائياً (100 - نسبة البوت) لشبكة ZN Go
 */
function calculateZnGoMargins() {
    const botInput = document.getElementById('grid36-bot-margin');
    const userInput = document.getElementById('grid36-user-margin');
    
    if (!botInput || !userInput) return;

    let botMargin = parseFloat(botInput.value);
    if (isNaN(botMargin)) { userInput.value = ''; return; }
    if (botMargin < 0) botMargin = 0;
    if (botMargin > 100) botMargin = 100;

    userInput.value = parseFloat((100.0 - botMargin).toFixed(2));
}
window.calculateZnGoMargins = calculateZnGoMargins;

/**
 * حساب نسبة اللاعبين تلقائياً (100 - نسبة البوت) للساحة الكبرى
 */
function calculateBigArenaMargins() {
    const botInput = document.getElementById('big-arena-bot-margin');
    const userInput = document.getElementById('big-arena-user-margin');
    
    if (!botInput || !userInput) return;

    let botMargin = parseFloat(botInput.value);
    if (isNaN(botMargin)) { userInput.value = ''; return; }
    if (botMargin < 0) botMargin = 0;
    if (botMargin > 100) botMargin = 100;

    userInput.value = parseFloat((100.0 - botMargin).toFixed(2));
}
window.calculateBigArenaMargins = calculateBigArenaMargins;

/**
 * زر التحديث الشامل لجلب أحدث الأرقام والإعدادات من السيرفر
 */
async function refreshDashboard() {
    await loadDashboardStats();
    await loadZnGoSettings();
    await loadBigArenaSettings();
    await loadModerators();
    await loadAdminLogs();
    alert("🔄 تم تحديث البيانات بنجاح من الفايربيس!");
}
window.refreshDashboard = refreshDashboard;

// ==========================================
// 1. جلب وحفظ إعدادات الألعاب بشكل منفصل (ZN Go & Big Arena)
// ==========================================

async function loadDashboardStats() {
    const botProfitEl = document.getElementById('bot-profit-val');
    const userProfitEl = document.getElementById('user-profit-val');
    const actualMarginEl = document.getElementById('actual-profit-pct');

    try {
        const response = await apiFetch(`${API_BASE}/admin/dashboard-stats`, { method: 'GET' });
        const result = await response.json();

        if (response.ok && (result.status === 'success' || result.success)) {
            const stats = result.stats || {};
            
            const botProfit = stats.total_bot_profit || 0;
            const userProfit = stats.total_user_profit || stats.total_wins || 0;
            const actualMargin = stats.actual_bot_percent || stats.actual_margin || 0;

            if (botProfitEl) botProfitEl.innerText = Number(botProfit).toLocaleString('ar-EG');
            if (userProfitEl) userProfitEl.innerText = Number(userProfit).toLocaleString('ar-EG');
            if (actualMarginEl) actualMarginEl.innerText = `${actualMargin}%`;

            if (result.zn_go_config || result.grid_36) {
                populateZnGoUI(result.zn_go_config || result.grid_36);
            }
            if (result.big_arena) {
                populateBigArenaUI(result.big_arena);
            }
        }
    } catch (error) {
        console.error("❌ خطأ في جلب إحصائيات لوحة التحكم:", error);
    }
}
window.loadDashboardStats = loadDashboardStats;

/**
 * جلب إعدادات لعبة شبكة ZN Go حصرياً المربوطة بـ Firestore
 */
async function loadZnGoSettings() {
    try {
        const response = await apiFetch(`${API_BASE}/admin/zn-go-settings`, { method: 'GET' });
        const result = await response.json();
        if (response.ok && result.success && result.config) {
            populateZnGoUI(result.config);
            if (result.stats && result.stats.actual_bot_percent !== undefined) {
                const actualMarginEl = document.getElementById('actual-profit-pct');
                if (actualMarginEl) actualMarginEl.innerText = `${result.stats.actual_bot_percent}%`;
            }
        }
    } catch (error) {
        console.error("❌ خطأ في جلب إعدادات شبكة ZN Go:", error);
    }
}
window.loadZnGoSettings = loadZnGoSettings;
window.loadGrid36Settings = loadZnGoSettings; // الحفاظ على توافق الأسماء القديمة

function populateZnGoUI(cfg) {
    const botInput = document.getElementById('grid36-bot-margin');
    const userInput = document.getElementById('grid36-user-margin');
    const minBetInput = document.getElementById('grid36-min-bet');

    const botMargin = cfg.bot_profit ?? cfg.bot_margin ?? 70;
    const playerMargin = cfg.player_profit ?? cfg.player_margin ?? (100 - botMargin);

    if (botInput) botInput.value = botMargin;
    if (userInput) userInput.value = playerMargin;
    if (minBetInput) minBetInput.value = cfg.min_bet ?? 10;
}

/**
 * حفظ إعدادات لعبة شبكة ZN Go دون إرسال خيار التفعيل/الإيقاف
 */
async function saveZnGoSettings() {
    const botInput = document.getElementById('grid36-bot-margin');
    const minBetInput = document.getElementById('grid36-min-bet');

    if (!botInput || !minBetInput) return;

    const botProfit = parseFloat(botInput.value);
    const minBet = parseFloat(minBetInput.value);
    const playerProfit = parseFloat((100.0 - botProfit).toFixed(2));

    if (isNaN(botProfit) || botProfit < 0 || botProfit > 100) {
        alert("⚠️ نسبة أرباح البوت لشبكة ZN Go يجب أن تكون بين 0 و 100!");
        return;
    }

    if (isNaN(minBet) || minBet < 0) {
        alert("⚠️ يرجى إدخال حد أدنى صحيح للرهان لشبكة ZN Go!");
        return;
    }

    const payload = {
        initData: getTelegramInitData(),
        bot_profit: botProfit,
        bot_margin: botProfit,
        player_profit: playerProfit,
        player_margin: playerProfit,
        min_bet: minBet
    };

    try {
        const response = await apiFetch(`${API_BASE}/admin/zn-go-settings`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        const result = await response.json();

        if (response.ok && result.success) {
            alert(`✅ ${result.message || 'تم حفظ إعدادات شبكة ZN Go بنجاح!'}`);
            loadZnGoSettings();
            loadAdminLogs();
        } else {
            alert(`❌ خطأ: ${result.message || result.error || 'حدث خطأ أثناء الحفظ'}`);
        }
    } catch (error) {
        console.error("❌ خطأ أثناء حفظ إعدادات شبكة ZN Go:", error);
    }
}
window.saveZnGoSettings = saveZnGoSettings;
window.saveGrid36Settings = saveZnGoSettings; // التوافق مع الاستدعاء من HTML

/**
 * جلب إعدادات لعبة الساحة الكبرى
 */
async function loadBigArenaSettings() {
    try {
        const response = await apiFetch(`${API_BASE}/admin/settings/big_arena`, { method: 'GET' });
        const result = await response.json();
        if (response.ok && result.success && result.config) {
            populateBigArenaUI(result.config);
        }
    } catch (error) {
        console.error("❌ خطأ في جلب إعدادات الساحة الكبرى:", error);
    }
}
window.loadBigArenaSettings = loadBigArenaSettings;

function populateBigArenaUI(cfg) {
    const botInput = document.getElementById('big-arena-bot-margin');
    const userInput = document.getElementById('big-arena-user-margin');
    const minBetInput = document.getElementById('big-arena-min-bet');
    const enabledToggle = document.getElementById('big-arena-enabled');

    if (botInput) botInput.value = cfg.bot_margin ?? 70;
    if (userInput) userInput.value = cfg.player_margin ?? (100 - (cfg.bot_margin ?? 70));
    if (minBetInput) minBetInput.value = cfg.min_bet ?? 10;
    if (enabledToggle) enabledToggle.checked = cfg.enabled ?? true;
}

/**
 * حفظ إعدادات لعبة الساحة الكبرى
 */
async function saveBigArenaSettings() {
    const botInput = document.getElementById('big-arena-bot-margin');
    const minBetInput = document.getElementById('big-arena-min-bet');
    const enabledToggle = document.getElementById('big-arena-enabled');

    if (!botInput || !minBetInput) return;

    const botMargin = parseFloat(botInput.value);
    const minBet = parseFloat(minBetInput.value);
    const enabled = enabledToggle ? enabledToggle.checked : true;

    if (isNaN(botMargin) || botMargin < 0 || botMargin > 100) {
        alert("⚠️ نسبة أرباح البوت للساحة الكبرى يجب أن تكون بين 0 و 100!");
        return;
    }

    if (isNaN(minBet) || minBet < 0) {
        alert("⚠️ يرجى إدخال حد أدنى صحيح للرهان للساحة الكبرى!");
        return;
    }

    const payload = {
        initData: getTelegramInitData(),
        bot_margin: botMargin,
        min_bet: minBet,
        enabled: enabled
    };

    try {
        const response = await apiFetch(`${API_BASE}/admin/settings/big_arena`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        const result = await response.json();

        if (response.ok && result.success) {
            alert(`✅ ${result.message || 'تم حفظ إعدادات الساحة الكبرى بنجاح!'}`);
            loadBigArenaSettings();
            loadAdminLogs();
        } else {
            alert(`❌ خطأ: ${result.message || result.error || 'حدث خطأ أثناء الحفظ'}`);
        }
    } catch (error) {
        console.error("❌ خطأ أثناء حفظ إعدادات الساحة الكبرى:", error);
    }
}
window.saveBigArenaSettings = saveBigArenaSettings;

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
