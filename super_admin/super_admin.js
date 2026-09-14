// =========================================================
// 👑 super_admin/super_admin.js
// JavaScript Controller for Super Admin WebApp Console
// =========================================================

// دالة احتياطية لجلب هيدرات التوثيق الإداري عند عدم توفر apiFetch
function getAdminHeaders() {
    const initData = window.Telegram?.WebApp?.initData || window.getInitData?.() || "";
    const adminId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || "";
    return {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": initData,
        "X-Init-Data": initData,
        "X-Admin-ID": adminId.toString(),
        "Authorization": `Bearer ${initData}`
    };
}

// دالة مساعدة لاستدعاء API مع استخدام apiFetch الموحدة بمرونة
async function requestApi(url, options = {}) {
    if (typeof window.apiFetch === 'function') {
        return window.apiFetch(url, options);
    }
    const mergedOptions = {
        ...options,
        headers: {
            ...getAdminHeaders(),
            ...(options.headers || {})
        }
    };
    return fetch(url, mergedOptions);
}

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

    if (targetType === 'all') {
        const confirmBroadcast = confirm("⚠️ تنبيه: أنت على وشك إرسال هذه الرسالة كبث جماعي لكل مستخدمي البوت عبر بوت المستخدمين الرئيسي.\n\nهل أنت متأكد من الاستمرار؟");
        if (!confirmBroadcast) return;
    }

    if (btnSend) {
        btnSend.disabled = true;
        btnSend.style.opacity = '0.6';
        btnSend.innerText = '⏳ جاري تنفيذ الإرسال...';
    }

    try {
        const response = await requestApi('/api/super-admin/send-message', {
            method: 'POST',
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

async function fetchBroadcastStats() {
    const statusBox = document.getElementById('broadcastStatusBox');
    const detailsContainer = document.getElementById('broadcastProgressDetails');

    try {
        const response = await requestApi('/api/super-admin/broadcast-stats', {
            method: 'GET'
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

// 🔄 تحديث دالة التحليلات العامة لتعكس إحصائيات المستخدمين
async function loadGlobalAnalytics() {
    try {
        const response = await requestApi('/api/super-admin/analytics', {
            method: 'GET'
        });
        const data = await response.json();
        if (data.success && data.analytics) {
            const totalUsersElem = document.getElementById('total-users-val');
            const activeUsersElem = document.getElementById('active-users-val');
            const bannedUsersElem = document.getElementById('banned-users-val');

            if (totalUsersElem) totalUsersElem.innerText = (data.analytics.total_users || 0).toLocaleString();
            if (activeUsersElem) activeUsersElem.innerText = (data.analytics.active_today || 0).toLocaleString();
            if (bannedUsersElem) bannedUsersElem.innerText = (data.analytics.banned_users || 0).toLocaleString();

            if (data.analytics.top_users) {
                renderTopActiveUsersList(data.analytics.top_users);
            }
        }
    } catch (err) {
        console.error("Failed to load global analytics:", err);
    }
}

// 🏆 دالة جلب وقائمة أكثر المستخدمين تفاعلاً
async function loadTopActiveUsers() {
    const listElem = document.getElementById('topActiveUsersList');
    if (!listElem) return;

    try {
        const response = await requestApi('/api/super-admin/analytics', {
            method: 'GET'
        });
        const data = await response.json();
        if (data.success && data.analytics && data.analytics.top_users) {
            renderTopActiveUsersList(data.analytics.top_users);
        } else {
            listElem.innerHTML = '<p class="empty-msg">لا توجد بيانات متاحة حالياً.</p>';
        }
    } catch (err) {
        console.error("Failed to load top active users:", err);
        listElem.innerHTML = '<p class="empty-msg">تعذر تحميل قائمة الأكثر نشاطاً.</p>';
    }
}

function renderTopActiveUsersList(users) {
    const listElem = document.getElementById('topActiveUsersList');
    if (!listElem) return;

    if (!users || users.length === 0) {
        listElem.innerHTML = '<p class="empty-msg">لا يوجد مستخدمون نشطون حالياً.</p>';
        return;
    }

    listElem.innerHTML = users.map((user, index) => `
        <div class="user-active-item">
            <div class="user-info">
                <strong>#${index + 1} ${user.name || 'مستخدم'}</strong>
                <span>ID: ${user.telegram_id || user.user_id}</span>
            </div>
            <span class="badge-count">${(user.interactions || user.activity_count || 0).toLocaleString()} تفاعل</span>
        </div>
    `).join('');
}

// 🚫 دالة حظر مستخدم وحظر جهازه
async function banUser() {
    const userIdInput = document.getElementById('banUserId');
    const reasonInput = document.getElementById('banReason');

    const userId = userIdInput ? userIdInput.value.trim() : '';
    const reason = reasonInput ? reasonInput.value.trim() : '';

    if (!userId) {
        alert("⚠️ يرجى إدخال معرّف المستخدم (Telegram ID) المراد حظره.");
        if (userIdInput) userIdInput.focus();
        return;
    }

    const confirmBan = confirm(`🚫 هل أنت متأكد من حظر المستخدم (${userId}) وحظر الأجهزة المربوطة به؟`);
    if (!confirmBan) return;

    try {
        const response = await requestApi('/api/super-admin/ban-user', {
            method: 'POST',
            body: JSON.stringify({
                telegram_id: userId,
                reason: reason || "تم الحظر من قبل الإدارة العليا"
            })
        });

        const data = await response.json();

        if (data.success) {
            alert("✅ " + (data.message || "تم حظر الحساب والأجهزة المربوطة به بنجاح."));
            if (userIdInput) userIdInput.value = '';
            if (reasonInput) reasonInput.value = '';
            loadGlobalAnalytics();
            loadAdminLogs();
        } else {
            alert("❌ فشل عملية الحظر: " + (data.message || "حدث خطأ غير معروف"));
        }
    } catch (err) {
        console.error("Error banning user:", err);
        alert("❌ حدث خطأ أثناء تنفيذ الحظر: " + err.message);
    }
}

// 🟢 دالة فك الحظر عن حساب المستخدم وجميع الأجهزة المربوطة به
async function unbanUser() {
    const userIdInput = document.getElementById('banUserId');
    const userId = userIdInput ? userIdInput.value.trim() : '';

    if (!userId) {
        alert("⚠️ يرجى إدخال معرّف المستخدم (Telegram ID) لفك الحظر عنه.");
        if (userIdInput) userIdInput.focus();
        return;
    }

    try {
        const response = await requestApi('/api/super-admin/unban-user', {
            method: 'POST',
            body: JSON.stringify({ telegram_id: userId })
        });

        const data = await response.json();

        if (data.success) {
            alert("✅ " + (data.message || "تم فك حظر حساب التليجرام وجميع الأجهزة المربوطة به بنجاح."));
            if (userIdInput) userIdInput.value = '';
            loadGlobalAnalytics();
            loadAdminLogs();
        } else {
            alert("❌ فشل فك الحظر: " + (data.message || "حدث خطأ غير معروف"));
        }
    } catch (err) {
        console.error("Error unbanning user:", err);
        alert("❌ حدث خطأ أثناء فك الحظر: " + err.message);
    }
}

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
        const response = await requestApi('/api/super-admin/add-moderator', {
            method: 'POST',
            body: JSON.stringify({ telegram_id: modId, name: modName, permissions: permissions })
        });
        const data = await response.json();
        if (data.success) {
            alert("✅ تمت إضافة المشرف بنجاح!");
            if (document.getElementById('modTelegramId')) document.getElementById('modTelegramId').value = '';
            if (document.getElementById('modName')) document.getElementById('modName').value = '';
            loadModerators();
            loadAdminLogs();
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
        const response = await requestApi('/api/super-admin/list-moderators', {
            method: 'GET'
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
        const response = await requestApi('/api/super-admin/remove-moderator', {
            method: 'POST',
            body: JSON.stringify({ telegram_id: telegramId })
        });
        const data = await response.json();
        if (data.success) {
            alert("✅ تم حذف المشرف بنجاح.");
            loadModerators();
            loadAdminLogs();
        } else {
            alert("❌ " + (data.message || "فشل حذف المشرف"));
        }
    } catch (err) {
        alert("❌ حدث خطأ أثناء الحذف: " + err.message);
    }
}

async function loadAdminLogs() {
    const logsElem = document.getElementById('adminLogs');
    if (!logsElem) return;

    try {
        const response = await requestApi('/api/super-admin/logs', {
            method: 'GET'
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

// دالة تهيئة موديول الإدارة العليا
function initSuperAdmin() {
    loadGlobalAnalytics();
    loadTopActiveUsers();
    loadModerators();
    loadAdminLogs();
    fetchBroadcastStats();
}

// تصدير الدوال على مستوى النطاق العام window لعدم حدوث أخطاء Scope
window.initSuperAdmin = initSuperAdmin;
window.banUser = banUser;
window.unbanUser = unbanUser;
window.sendAdminMessage = sendAdminMessage;
window.fetchBroadcastStats = fetchBroadcastStats;
window.loadGlobalAnalytics = loadGlobalAnalytics;
window.loadTopActiveUsers = loadTopActiveUsers;
window.addNewModerator = addNewModerator;
window.loadModerators = loadModerators;
window.removeModerator = removeModerator;
window.loadAdminLogs = loadAdminLogs;
window.toggleTargetInput = toggleTargetInput;

// تشغيل التهيئة عند اكتمال تحميل المستند
document.addEventListener('DOMContentLoaded', () => {
    initSuperAdmin();
});
