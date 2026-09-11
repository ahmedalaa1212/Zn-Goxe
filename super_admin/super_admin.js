// super_admin/super_admin.js
// JavaScript Controller for Super Admin WebApp Console

// استخراج رؤوس التوثيق الخاصة بـ Telegram WebApp لإرسالها مع جميع الطلبات
function getAdminHeaders() {
    const initData = window.Telegram?.WebApp?.initData || "";
    const adminId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || "";
    return {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": initData,
        "X-Admin-ID": adminId.toString(),
        "Authorization": `Bearer ${initData}`
    };
}

// تبديل إظهار/إخفاء حقل معرف المستخدم الفردي حسب الاختيار (جماعي / فردي)
function toggleTargetInput() {
    const targetTypeSelect = document.getElementById('msgTargetType');
    const singleTargetGroup = document.getElementById('singleTargetGroup');
    if (targetTypeSelect && singleTargetGroup) {
        if (targetTypeSelect.value === 'single') {
            singleTargetGroup.style.display = 'flex';
        } else {
            singleTargetGroup.style.display = 'none';
        }
    }
}

// إرسال الرسالة والإشعارات الإدارية (مباشرة أو جماعية)
async function sendAdminMessage() {
    const targetTypeSelect = document.getElementById('msgTargetType');
    const targetUserIdInput = document.getElementById('targetUserId');
    const msgContentInput = document.getElementById('msgContent');
    const msgImageUrlInput = document.getElementById('msgImageUrl');
    const msgBtnTextInput = document.getElementById('msgBtnText');
    const msgBtnUrlInput = document.getElementById('msgBtnUrl');
    const btnSend = document.getElementById('btnSendMessage');

    const targetType = targetTypeSelect ? targetTypeSelect.value : 'all';
    const targetId = targetUserIdInput ? targetUserIdInput.value.trim() : '';
    const message = msgContentInput ? msgContentInput.value.trim() : '';
    const imageUrl = msgImageUrlInput ? msgImageUrlInput.value.trim() : '';
    const btnText = msgBtnTextInput ? msgBtnTextInput.value.trim() : '';
    const btnUrl = msgBtnUrlInput ? msgBtnUrlInput.value.trim() : '';

    // التحقق المباشر من صحة المدخلات
    if (!message) {
        alert("⚠️ يرجى إدخال نص الرسالة المراد إرسالها.");
        if (msgContentInput) msgContentInput.focus();
        return;
    }

    if (targetType === 'single' && !targetId) {
        alert("⚠️ يرجى إدخال معرّف المستخدم (Telegram ID) المستهدف.");
        if (targetUserIdInput) targetUserIdInput.focus();
        return;
    }

    if (btnText && !btnUrl) {
        alert("⚠️ عند إضافة نص للزر التفاعلي، يجب إدخال رابط الزر (URL) أيضاً.");
        if (msgBtnUrlInput) msgBtnUrlInput.focus();
        return;
    }

    // تأكيد قبل الإرسال الجماعي لتجنب الأخطاء
    if (targetType === 'all') {
        const confirmBroadcast = confirm("⚠️ تنبيه: أنت على وشك إرسال هذه الرسالة كبث جماعي لكل مستخدمي البوت.\n\nهل أنت متأكد من الاستمرار؟");
        if (!confirmBroadcast) return;
    }

    // تعطيل الزر مؤقتاً لحين انتهاء العملية
    if (btnSend) {
        btnSend.disabled = true;
        btnSend.style.opacity = '0.6';
        btnSend.innerText = '⏳ جاري تنفيذ الإرسال...';
    }

    try {
        const response = await fetch('/api/super-admin/send-message', {
            method: 'POST',
            headers: getAdminHeaders(),
            body: JSON.stringify({
                target_type: targetType,
                target_id: targetType === 'single' ? targetId : null,
                message: message,
                image_url: imageUrl || null,
                button_text: btnText || null,
                button_url: btnUrl || null
            })
        });

        const data = await response.json();

        if (data.success) {
            alert("✅ " + data.message);
            if (msgContentInput) msgContentInput.value = '';
            if (msgImageUrlInput) msgImageUrlInput.value = '';
            if (msgBtnTextInput) msgBtnTextInput.value = '';
            if (msgBtnUrlInput) msgBtnUrlInput.value = '';
            if (targetUserIdInput && targetType === 'single') targetUserIdInput.value = '';
            
            // تحديث كارت الإحصائيات فور الإرسال
            fetchBroadcastStats();
        } else {
            alert("❌ فشل الإرسال: " + (data.message || "حدث خطأ غير معروف"));
        }
    } catch (error) {
        console.error("Error sending admin message:", error);
        alert("❌ تعذر الاتصال بالخادم: " + error.message);
    } finally {
        if (btnSend) {
            btnSend.disabled = false;
            btnSend.style.opacity = '1';
            btnSend.innerText = '🚀 إرسال الرسالة الآن';
        }
    }
}

// جلب وتحديث حالة الإرسال الجماعي الحية
async function fetchBroadcastStats() {
    const statusBox = document.getElementById('broadcastStatusBox');
    const detailsContainer = document.getElementById('broadcastProgressDetails');

    try {
        const response = await fetch('/api/super-admin/broadcast-stats', {
            method: 'GET',
            headers: getAdminHeaders()
        });

        const data = await response.json();

        if (data.success && statusBox && detailsContainer) {
            statusBox.style.display = 'block';
            const live = data.live_status || {};
            const latest = data.latest_campaign || null;

            if (live.is_running) {
                const percentage = live.total > 0 ? Math.round((live.sent / live.total) * 100) : 0;
                detailsContainer.innerHTML = `
                    <div style="color: var(--accent-gold); font-weight: bold; margin-bottom: 4px;">⚙️ حملة إرسال جارية حالياً (${percentage}%):</div>
                    <div>🟢 تم الإرسال بنجاح: <b>${live.sent}</b> / ${live.total}</div>
                    <div>🚫 حظروا البوت: <b>${live.blocked}</b></div>
                    <div>❌ فشل الإرسال: <b>${live.failed}</b></div>
                `;
            } else if (latest) {
                detailsContainer.innerHTML = `
                    <div style="color: var(--accent-green); font-weight: bold; margin-bottom: 4px;">✅ آخر حملة إرسال مكتملة (${latest.created_at_str || 'مؤخراً'}):</div>
                    <div>👤 المشرف المسؤول: <b>${latest.admin_name || 'الأدمن'}</b></div>
                    <div>🎯 إجمالي المستهدفين: <b>${latest.total_targets || 0}</b></div>
                    <div>🟢 تم التسليم بنجاح: <b>${latest.success_count || 0}</b></div>
                    <div>🚫 حظروا البوت: <b>${latest.blocked_count || 0}</b></div>
                    <div>❌ تعذر التسليم: <b>${latest.failed_count || 0}</b></div>
                `;
            } else {
                detailsContainer.innerHTML = '<div>ℹ️ لا توجد حملات إرسال جارية أو مسجلة مؤخراً.</div>';
            }
        }
    } catch (error) {
        console.error("Error fetching broadcast stats:", error);
    }
}

// تحميل التحليلات الكلية والإحصائيات لرأس اللوحة
async function loadGlobalAnalytics() {
    try {
        const response = await fetch('/api/super-admin/analytics', {
            method: 'GET',
            headers: getAdminHeaders()
        });
        const data = await response.json();
        if (data.success && data.analytics) {
            const stats = data.analytics.game_stats || {};
            const botProfitElem = document.getElementById('bot-profit-val');
            const userProfitElem = document.getElementById('user-profit-val');
            const actualProfitPctElem = document.getElementById('actual-profit-pct');

            if (botProfitElem) botProfitElem.innerText = (stats.total_house_profit || 0).toLocaleString();
            if (userProfitElem) userProfitElem.innerText = (stats.total_player_payout || 0).toLocaleString();
            if (actualProfitPctElem) actualProfitPctElem.innerText = (stats.actual_margin_pct || 0) + '%';
        }
    } catch (err) {
        console.error("Failed to load global analytics:", err);
    }
}

// إدارة إعدادات لعبة شبكة ZN Go
async function loadZnGoSettings() {
    try {
        const response = await fetch('/api/super-admin/zngo-settings', {
            method: 'GET',
            headers: getAdminHeaders()
        });
        const data = await response.json();
        if (data.success && data.settings) {
            const botMargin = document.getElementById('grid36-bot-margin');
            const userMargin = document.getElementById('grid36-user-margin');
            const minBet = document.getElementById('grid36-min-bet');

            if (botMargin) botMargin.value = data.settings.bot_margin || 70;
            if (userMargin) userMargin.value = (100 - (data.settings.bot_margin || 70)).toFixed(2);
            if (minBet) minBet.value = data.settings.min_bet || 10;
        }
    } catch (err) {
        console.error("Failed to load ZN Go settings:", err);
    }
}

async function saveZnGoSettings() {
    const botMargin = parseFloat(document.getElementById('grid36-bot-margin')?.value || 70);
    const minBet = parseFloat(document.getElementById('grid36-min-bet')?.value || 10);

    try {
        const response = await fetch('/api/super-admin/zngo-settings', {
            method: 'POST',
            headers: getAdminHeaders(),
            body: JSON.stringify({ bot_margin: botMargin, min_bet: minBet })
        });
        const data = await response.json();
        if (data.success) {
            alert("✅ تم حفظ إعدادات لعبة ZN Go بنجاح!");
        } else {
            alert("❌ " + (data.message || "فشل حفظ الإعدادات"));
        }
    } catch (err) {
        alert("❌ حدث خطأ أثناء الحفظ: " + err.message);
    }
}

// إدارة إعدادات لعبة الساحة الكبرى
async function loadBigArenaSettings() {
    try {
        const response = await fetch('/api/super-admin/big-arena-settings', {
            method: 'GET',
            headers: getAdminHeaders()
        });
        const data = await response.json();
        if (data.success && data.settings) {
            const botMargin = document.getElementById('big-arena-bot-margin');
            const userMargin = document.getElementById('big-arena-user-margin');
            const minBet = document.getElementById('big-arena-min-bet');
            const enabled = document.getElementById('big-arena-enabled');

            if (botMargin) botMargin.value = data.settings.bot_margin || 70;
            if (userMargin) userMargin.value = (100 - (data.settings.bot_margin || 70)).toFixed(2);
            if (minBet) minBet.value = data.settings.min_bet || 10;
            if (enabled) enabled.checked = !!data.settings.enabled;
        }
    } catch (err) {
        console.error("Failed to load Big Arena settings:", err);
    }
}

async function saveBigArenaSettings() {
    const botMargin = parseFloat(document.getElementById('big-arena-bot-margin')?.value || 70);
    const minBet = parseFloat(document.getElementById('big-arena-min-bet')?.value || 10);
    const enabled = document.getElementById('big-arena-enabled')?.checked || false;

    try {
        const response = await fetch('/api/super-admin/big-arena-settings', {
            method: 'POST',
            headers: getAdminHeaders(),
            body: JSON.stringify({ bot_margin: botMargin, min_bet: minBet, enabled: enabled })
        });
        const data = await response.json();
        if (data.success) {
            alert("✅ تم حفظ إعدادات الساحة الكبرى بنجاح!");
        } else {
            alert("❌ " + (data.message || "فشل حفظ الإعدادات"));
        }
    } catch (err) {
        alert("❌ حدث خطأ أثناء الحفظ: " + err.message);
    }
}

// إدارة المشرفين والصلاحيات
async function addNewModerator() {
    const modId = document.getElementById('modTelegramId')?.value.trim();
    const modName = document.getElementById('modName')?.value.trim();

    if (!modId || !modName) {
        alert("⚠️ يرجى إدخال معرّف التليجرام واسم المشرف.");
        return;
    }

    const permissions = {
        perm_users: document.getElementById('perm_users')?.checked || false,
        perm_support: document.getElementById('perm_support')?.checked || false,
        perm_settings: document.getElementById('perm_settings')?.checked || false,
        perm_transactions: document.getElementById('perm_transactions')?.checked || false,
        perm_security: document.getElementById('perm_security')?.checked || false,
        perm_ads: document.getElementById('perm_ads')?.checked || false
    };

    try {
        const response = await fetch('/api/super-admin/add-moderator', {
            method: 'POST',
            headers: getAdminHeaders(),
            body: JSON.stringify({ telegram_id: modId, name: modName, permissions: permissions })
        });
        const data = await response.json();
        if (data.success) {
            alert("✅ تمت إضافة المشرف بنجاح!");
            if (document.getElementById('modTelegramId')) document.getElementById('modTelegramId').value = '';
            if (document.getElementById('modName')) document.getElementById('modName').value = '';
            loadModerators();
        } else {
            alert("❌ " + (data.message || "فشل إضافة المشرف"));
        }
    } catch (err) {
        alert("❌ حدث خطأ أثناء إضافة المشرف: " + err.message);
    }
}

async function loadModerators() {
    const listElem = document.getElementById('moderatorsList');
    if (!listElem) return;

    try {
        const response = await fetch('/api/super-admin/list-moderators', {
            method: 'GET',
            headers: getAdminHeaders()
        });
        const data = await response.json();
        if (data.success && data.moderators) {
            if (data.moderators.length === 0) {
                listElem.innerHTML = '<p class="empty-msg">لا يوجد مشرفين مضافين حالياً.</p>';
                return;
            }
            listElem.innerHTML = data.moderators.map(mod => `
                <div class="mod-item">
                    <div class="mod-info">
                        <strong>${mod.name}</strong>
                        <span>ID: ${mod.telegram_id}</span>
                    </div>
                    <button class="btn-refresh" style="color: var(--accent-red); border-color: var(--accent-red);" onclick="removeModerator('${mod.telegram_id}')">🗑️ حذف</button>
                </div>
            `).join('');
        }
    } catch (err) {
        listElem.innerHTML = '<p class="empty-msg">تعذر تحميل قائمة المشرفين.</p>';
    }
}

async function removeModerator(telegramId) {
    if (!confirm(`هل أنت تأكد من رغبتك في حذف المشرف صاحب المعرف ${telegramId}؟`)) return;

    try {
        const response = await fetch('/api/super-admin/remove-moderator', {
            method: 'POST',
            headers: getAdminHeaders(),
            body: JSON.stringify({ telegram_id: telegramId })
        });
        const data = await response.json();
        if (data.success) {
            alert("✅ تم حذف المشرف بنجاح.");
            loadModerators();
        } else {
            alert("❌ " + (data.message || "فشل حذف المشرف"));
        }
    } catch (err) {
        alert("❌ حدث خطأ أثناء الحذف: " + err.message);
    }
}

// تحميل سجل النشاطات الإدارية
async function loadAdminLogs() {
    const logsElem = document.getElementById('adminLogs');
    if (!logsElem) return;

    try {
        const response = await fetch('/api/super-admin/logs', {
            method: 'GET',
            headers: getAdminHeaders()
        });
        const data = await response.json();
        if (data.success && data.logs) {
            if (data.logs.length === 0) {
                logsElem.innerHTML = '<p class="empty-msg">لا توجد سجلات إدارية حديثة.</p>';
                return;
            }
            logsElem.innerHTML = data.logs.map(log => `
                <div class="log-item">
                    <div class="mod-info">
                        <strong>${log.admin_name || 'مشرف'}</strong>
                        <span>${log.action || ''}</span>
                    </div>
                    <span style="color: var(--text-muted); font-size: 10px;">${log.timestamp || ''}</span>
                </div>
            `).join('');
        }
    } catch (err) {
        logsElem.innerHTML = '<p class="empty-msg">تعذر تحميل سجل النشاطات.</p>';
    }
}

// تهيئة الصفحة وتحميل البيانات أولياً فور اكتمال الجاهزية
document.addEventListener('DOMContentLoaded', () => {
    loadGlobalAnalytics();
    loadZnGoSettings();
    loadBigArenaSettings();
    loadModerators();
    loadAdminLogs();
    fetchBroadcastStats();
});
