// =========================================================
// 👑 super_admin/super_admin.js
// JavaScript Controller for Super Admin WebApp Console
// =========================================================

// دالة جلب هيدرات التوثيق الإداري مع الدعم الاحتياطي لـ URL Parameters
function getAdminHeaders() {
    const urlParams = new URLSearchParams(window.location.search);
    const urlAdminId = urlParams.get('admin_id') || urlParams.get('tg_id') || "";
    
    const initData = window.Telegram?.WebApp?.initData || window.getInitData?.() || "";
    const tgAdminId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || "";
    
    const finalAdminId = tgAdminId || urlAdminId || "5102387551";

    return {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": initData,
        "X-Init-Data": initData,
        "X-Admin-ID": finalAdminId.toString(),
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
            alert("✅ " + (data.message || "تم إرسال الرسالة بنجاح."));
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
                    <div style="color: var(--accent-gold, #f39c12); font-weight: bold; margin-bottom: 4px;">⚙️ حملة إرسال جارية حالياً (${percentage}%):</div>
                    <div>🟢 تم الإرسال بنجاح: <b>${live.sent}</b> /${live.total}</div>
                    <div>🚫 حظروا البوت: <b>${live.blocked}</b></div>
                    <div>❌ فشل الإرسال: <b>${live.failed}</b></div>
                `;
            } else if (latest) {
                detailsContainer.innerHTML = `
                    <div style="color: var(--accent-green, #2ecc71); font-weight: bold; margin-bottom: 4px;">✅ آخر حملة إرسال مكتملة (${latest.created_at_str || 'مؤخراً'}):</div>
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

            const topUsers = data.analytics.top_users || data.analytics.top_active_users;
            if (topUsers) {
                renderTopActiveUsersList(topUsers);
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
        const topUsers = data.analytics ? (data.analytics.top_users || data.analytics.top_active_users) : null;
        if (data.success && topUsers) {
            renderTopActiveUsersList(topUsers);
        } else {
            listElem.innerHTML = '<p class="empty-msg">لا توجد بيانات متاحة حالياً.</p>';
        }
    } catch (err) {
        console.error("Failed to load top active users:", err);
        listElem.innerHTML = '<p class="empty-msg">تعذر تحميل قائمة الأكثر نشاطاً.</p>';
    }
}

// 🎨 دالة عرض أكثر المستخدمين تفاعلاً ونشاطاً (تدعم حقول التفاعل التراكمية والتعدين ورصيد ZN)
function renderTopActiveUsersList(users) {
    const listElem = document.getElementById('topActiveUsersList');
    if (!listElem) return;

    if (!users || !Array.isArray(users) || users.length === 0) {
        listElem.innerHTML = '<p class="empty-msg">لا يوجد مستخدمون نشطون حالياً.</p>';
        return;
    }

    listElem.innerHTML = users.map((user, index) => {
        const uId = user.telegram_id || user.user_id || user.tg_id || '—';
        const uName = user.name || user.first_name || user.username || 'مستخدم';
        
        // استخراج تفاعلات المستخدم أو حقول التعدين والضغط المتاحة بمرونة
        const interactionsCount = (user.interactions !== undefined && user.interactions !== null)
            ? user.interactions
            : (user.activity_count ?? user.tap_count ?? user.total_mined ?? user.zn_balance ?? user.balance ?? 0);

        const znBalance = user.zn_balance !== undefined ? user.zn_balance : user.balance;
        const extraInfo = (znBalance !== undefined && znBalance !== null) ? ` | ZN: ${Number(znBalance).toLocaleString()}` : '';

        return `
            <div class="user-active-item">
                <div class="user-info">
                    <strong>#${index + 1}${uName}</strong>
                    <span>ID: ${uId}${extraInfo}</span>
                </div>
                <span class="badge-count">${Number(interactionsCount).toLocaleString()} تفاعل</span>
            </div>
        `;
    }).join('');
}

// 🚫 دالة جلب قائمة المحظورين وتحديث الواجهة والعداد
async function loadBannedUsers() {
    const listElem = document.getElementById('bannedUsersList');
    try {
        const response = await requestApi('/api/super-admin/banned-users', {
            method: 'GET'
        });
        const data = await response.json();
        if (data.success) {
            const bannedUsersElem = document.getElementById('banned-users-val');
            if (bannedUsersElem && data.total_banned !== undefined) {
                bannedUsersElem.innerText = Number(data.total_banned).toLocaleString();
            }
            if (listElem) {
                renderBannedUsersList(data.banned_users || []);
            }
        } else {
            if (listElem) {
                listElem.innerHTML = '<p class="empty-msg">فشل جلب قائمة المحظورين.</p>';
            }
        }
    } catch (err) {
        console.error("Failed to load banned users:", err);
        if (listElem) {
            listElem.innerHTML = '<p class="empty-msg">تعذر تحميل قائمة المحظورين.</p>';
        }
    }
}

// 🎨 دالة بناء وتصميم عناصر قائمة المحظورين
function renderBannedUsersList(users) {
    const listElem = document.getElementById('bannedUsersList');
    if (!listElem) return;

    if (!users || !Array.isArray(users) || users.length === 0) {
        listElem.innerHTML = '<p class="empty-msg">لا يوجد مستخدمون محظورون حالياً.</p>';
        return;
    }

    listElem.innerHTML = users.map(user => {
        const uId = user.telegram_id || user.user_id || user.tg_id || '—';
        const uName = user.name || user.first_name || user.username || 'مستخدم محظور';
        const reason = user.ban_reason || user.reason || 'لا يوجد سبب محدد';
        const bannedAt = user.banned_at || user.date || '—';

        return `
            <div class="user-active-item" style="flex-direction: column; align-items: flex-start; gap: 8px; padding: 12px; background: rgba(231, 76, 60, 0.05); border: 1px solid rgba(231, 76, 60, 0.2); border-radius: 8px; margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; width: 100%; align-items: center;">
                    <div class="user-info">
                        <strong style="color: var(--accent-red, #e74c3c);">${uName}</strong>
                        <span>ID: ${uId}</span>
                    </div>
                    <button class="btn-refresh" style="color: var(--accent-green, #2ecc71); border-color: var(--accent-green, #2ecc71);" onclick="unbanUserDirect('${uId}')">🟢 فك الحظر</button>
                </div>
                <div style="font-size: 12px; color: var(--text-muted, #aaa); width: 100%;">
                    <div>📌 <b>السبب:</b> ${reason}</div>
                    <div>📅 <b>التاريخ:</b> ${bannedAt}</div>
                </div>
            </div>
        `;
    }).join('');
}

// 🟢 دالة فك الحظر المباشر من قائمة المحظورين
async function unbanUserDirect(userId) {
    if (!userId || userId === '—') {
        alert("⚠️ معرّف المستخدم غير صالح.");
        return;
    }

    const confirmUnban = confirm(`🟢 هل أنت متأكد من فك الحظر عن المستخدم (${userId}) وجميع الأجهزة المربوطة به؟`);
    if (!confirmUnban) return;

    try {
        const response = await requestApi('/api/super-admin/unban-user', {
            method: 'POST',
            body: JSON.stringify({
                telegram_id: userId,
                tg_id: userId
            })
        });

        const data = await response.json();

        if (data.success) {
            alert("✅ " + (data.message || "تم فك حظر الحساب والأجهزة بنجاح."));
            loadBannedUsers();
            loadGlobalAnalytics();
            loadAdminLogs();
        } else {
            alert("❌ فشل فك الحظر: " + (data.message || "حدث خطأ غير معروف"));
        }
    } catch (err) {
        console.error("Error unbanning user directly:", err);
        alert("❌ حدث خطأ أثناء فك الحظر: " + err.message);
    }
}

// 🚫 دالة حظر مستخدم وحظر جهازه
async function banUser() {
    const userIdInput = document.getElementById('banUserId') || document.getElementById('unbanUserId') || document.getElementById('targetUserId');
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
                tg_id: userId,
                reason: reason || "تم الحظر من قبل الإدارة العليا"
            })
        });

        const data = await response.json();

        if (data.success) {
            alert("✅ " + (data.message || "تم حظر الحساب والأجهزة المربوطة به بنجاح."));
            if (document.getElementById('banUserId')) document.getElementById('banUserId').value = '';
            if (document.getElementById('unbanUserId')) document.getElementById('unbanUserId').value = '';
            if (reasonInput) reasonInput.value = '';
            loadGlobalAnalytics();
            loadBannedUsers();
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
    const userIdInput = document.getElementById('unbanUserId') || document.getElementById('banUserId') || document.getElementById('targetUserId');
    const userId = userIdInput ? userIdInput.value.trim() : '';

    if (!userId) {
        alert("⚠️ يرجى إدخال معرّف المستخدم (Telegram ID) لفك الحظر عنه.");
        if (userIdInput) userIdInput.focus();
        return;
    }

    try {
        const response = await requestApi('/api/super-admin/unban-user', {
            method: 'POST',
            body: JSON.stringify({
                telegram_id: userId,
                tg_id: userId
            })
        });

        const data = await response.json();

        if (data.success) {
            alert("✅ " + (data.message || "تم فك حظر حساب التليجرام وجميع الأجهزة المربوطة به بنجاح."));
            if (document.getElementById('banUserId')) document.getElementById('banUserId').value = '';
            if (document.getElementById('unbanUserId')) document.getElementById('unbanUserId').value = '';
            loadGlobalAnalytics();
            loadBannedUsers();
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
                    <button class="btn-refresh" style="color: var(--accent-red, #e74c3c); border-color: var(--accent-red, #e74c3c);" onclick="removeModerator('${mod.telegram_id}')">🗑️ حذف</button>
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
                        <strong>${log.admin || log.admin_name || 'مشرف'}</strong>
                        <span>${log.action || ''}</span>
                    </div>
                    <span style="color: var(--text-muted, #888); font-size: 10px;">${log.timestamp || ''}</span>
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
    loadBannedUsers();
    loadModerators();
    loadAdminLogs();
    fetchBroadcastStats();
}

// تصدير الدوال على مستوى النطاق العام window لعدم حدوث أخطاء Scope
window.initSuperAdmin = initSuperAdmin;
window.getAdminHeaders = getAdminHeaders;
window.banUser = banUser;
window.unbanUser = unbanUser;
window.unbanUserDirect = unbanUserDirect;
window.loadBannedUsers = loadBannedUsers;
window.renderBannedUsersList = renderBannedUsersList;
window.sendAdminMessage = sendAdminMessage;
window.fetchBroadcastStats = fetchBroadcastStats;
window.loadGlobalAnalytics = loadGlobalAnalytics;
window.loadTopActiveUsers = loadTopActiveUsers;
window.renderTopActiveUsersList = renderTopActiveUsersList;
window.addNewModerator = addNewModerator;
window.loadModerators = loadModerators;
window.removeModerator = removeModerator;
window.loadAdminLogs = loadAdminLogs;
window.toggleTargetInput = toggleTargetInput;

// تشغيل التهيئة عند اكتمال تحميل المستند
document.addEventListener('DOMContentLoaded', () => {
    initSuperAdmin();
});
