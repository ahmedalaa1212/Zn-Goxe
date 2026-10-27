// =========================================================
// 👑 super_admin/super_admin.js
// Secured JavaScript Controller for Super Admin WebApp Console
// =========================================================

let broadcastPollTimer = null;

// استخراج معرّف الأدمن من بيئة تليجرام الرسمية للعرض فقط (بدون أي آيدي مكشوف أو قابل للتزوير)
function getAdminId() {
    const tgAdminId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;
    return tgAdminId ? String(tgAdminId) : "";
}

// جلب بيانات التوثيق المشفرة (initData) المعتمدة جنائياً في السيرفر
function getVerifiedInitData() {
    if (window.Telegram?.WebApp?.initData) {
        return window.Telegram.WebApp.initData;
    }
    if (typeof window.getInitData === "function") {
        return window.getInitData() || "";
    }
    return "";
}

// بناء هيدرات التوثيق الإداري المشفرة
function getAdminHeaders() {
    const initData = getVerifiedInitData();
    return {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": initData,
        "X-Init-Data": initData,
        "Authorization": initData ? `Bearer ${initData}` : ""
    };
}

// دالة مساعدة لتعقيم النصوص ومنع ثغرات XSS عند عرض أسماء المستخدمين أو الأسباب
function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// دالة موحدة لاستدعاء مسارات السوبر أدمن مع دمج الهيدرات المشفرة
async function requestApi(url, options = {}) {
    const adminHeaders = getAdminHeaders();
    const mergedHeaders = {
        ...adminHeaders,
        ...(options.headers || {})
    };

    const mergedOptions = {
        ...options,
        headers: mergedHeaders
    };

    if (typeof window.apiFetch === "function") {
        return window.apiFetch(url, mergedOptions);
    }
    return fetch(url, mergedOptions);
}

// =========================================================
// 📢 قسم الرسائل الإدارية والبث الجماعي
// =========================================================

function toggleTargetInput() {
    const targetTypeSelect = document.getElementById("msgTargetType");
    const singleTargetGroup = document.getElementById("singleTargetGroup");
    if (targetTypeSelect && singleTargetGroup) {
        singleTargetGroup.style.display = targetTypeSelect.value === "single" ? "flex" : "none";
    }
}

async function sendAdminMessage() {
    const targetTypeSelect = document.getElementById("msgTargetType");
    const targetUserIdInput = document.getElementById("targetUserId");
    const msgContentInput = document.getElementById("msgContent");
    const msgImageUrlInput = document.getElementById("msgImageUrl");
    const msgBtnTextInput = document.getElementById("msgBtnText");
    const msgBtnUrlInput = document.getElementById("msgBtnUrl");
    const btnSend = document.getElementById("btnSendMessage");

    const targetType = targetTypeSelect ? targetTypeSelect.value : "all";
    const targetId = targetUserIdInput ? targetUserIdInput.value.trim() : "";
    const message = msgContentInput ? msgContentInput.value.trim() : "";
    const imageUrl = msgImageUrlInput ? msgImageUrlInput.value.trim() : "";
    const btnText = msgBtnTextInput ? msgBtnTextInput.value.trim() : "";
    const btnUrl = msgBtnUrlInput ? msgBtnUrlInput.value.trim() : "";

    if (!message) {
        alert("⚠️ يرجى إدخال نص الرسالة المراد إرسالها.");
        if (msgContentInput) msgContentInput.focus();
        return;
    }

    if (targetType === "single" && !targetId) {
        alert("⚠️ يرجى إدخال معرّف المستخدم (Telegram ID) المستهدف.");
        if (targetUserIdInput) targetUserIdInput.focus();
        return;
    }

    if (btnText && !btnUrl) {
        alert("⚠️ عند إضافة نص للزر التفاعلي، يجب إدخال رابط الزر (URL) أيضاً.");
        if (msgBtnUrlInput) msgBtnUrlInput.focus();
        return;
    }

    if (targetType === "all") {
        const confirmBroadcast = confirm(
            "⚠️ تنبيه: أنت على وشك إرسال هذه الرسالة كبث جماعي لكل مستخدمي البوت عبر بوت المستخدمين الرئيسي.\n\nهل أنت متأكد من الاستمرار؟"
        );
        if (!confirmBroadcast) return;
    }

    if (btnSend) {
        btnSend.disabled = true;
        btnSend.style.opacity = "0.6";
        btnSend.innerText = "⏳ جاري تنفيذ الإرسال...";
    }

    try {
        const response = await requestApi("/api/super-admin/send-message", {
            method: "POST",
            body: JSON.stringify({
                target_type: targetType,
                target_id: targetType === "single" ? targetId : null,
                message: message,
                image_url: imageUrl || null,
                button_text: btnText || null,
                button_url: btnUrl || null
            })
        });

        const data = await response.json();

        if (data.success) {
            alert("✅ " + (data.message || "تم إرسال الرسالة بنجاح."));
            if (msgContentInput) msgContentInput.value = "";
            if (msgImageUrlInput) msgImageUrlInput.value = "";
            if (msgBtnTextInput) msgBtnTextInput.value = "";
            if (msgBtnUrlInput) msgBtnUrlInput.value = "";
            if (targetUserIdInput && targetType === "single") targetUserIdInput.value = "";

            fetchBroadcastStats();
            loadAdminLogs();
        } else {
            alert("❌ فشل الإرسال: " + (data.message || "حدث خطأ غير معروف"));
        }
    } catch (error) {
        console.error("Error sending admin message:", error);
        alert("❌ تعذر الاتصال بالخادم: " + error.message);
    } finally {
        if (btnSend) {
            btnSend.disabled = false;
            btnSend.style.opacity = "1";
            btnSend.innerText = "🚀 إرسال الرسالة الآن";
        }
    }
}

async function fetchBroadcastStats() {
    const statusBox = document.getElementById("broadcastStatusBox");
    const detailsContainer = document.getElementById("broadcastProgressDetails");

    try {
        const response = await requestApi("/api/super-admin/broadcast-stats", {
            method: "GET"
        });

        const data = await response.json();

        if (data.success && statusBox && detailsContainer) {
            statusBox.style.display = "block";
            const live = data.live_status || {};
            const latest = data.latest_campaign || null;

            if (live.is_running) {
                const processed = (live.sent || 0) + (live.blocked || 0) + (live.failed || 0);
                const percentage = live.total > 0 ? Math.round((processed / live.total) * 100) : 0;
                detailsContainer.innerHTML = `
                    <div style="color: var(--accent-gold, #f39c12); font-weight: bold; margin-bottom: 4px;">⚙️ حملة إرسال جارية حالياً (${percentage}%):</div>
                    <div>🟢 تم الإرسال بنجاح: <b>${live.sent || 0}</b> / ${live.total || 0}</div>
                    <div>🚫 حظروا البوت: <b>${live.blocked || 0}</b></div>
                    <div>❌ فشل الإرسال: <b>${live.failed || 0}</b></div>
                `;
                if (!broadcastPollTimer) {
                    broadcastPollTimer = setInterval(fetchBroadcastStats, 3000);
                }
            } else {
                if (broadcastPollTimer) {
                    clearInterval(broadcastPollTimer);
                    broadcastPollTimer = null;
                }
                if (latest) {
                    const failedCount = latest.failed_count !== undefined
                        ? latest.failed_count
                        : Math.max(0, (latest.total_targets || 0) - (latest.success_count || 0) - (latest.blocked_count || 0));
                    detailsContainer.innerHTML = `
                        <div style="color: var(--accent-green, #2ecc71); font-weight: bold; margin-bottom: 4px;">✅ آخر حملة إرسال مكتملة (${escapeHtml(latest.created_at_str || latest.created_at || "مؤخراً")}):</div>
                        <div>👤 المشرف المسؤول: <b>${escapeHtml(latest.admin_name || "الأدمن")}</b></div>
                        <div>🎯 إجمالي المستهدفين: <b>${latest.total_targets || 0}</b></div>
                        <div>🟢 تم التسليم بنجاح: <b>${latest.success_count || 0}</b></div>
                        <div>🚫 حظروا البوت: <b>${latest.blocked_count || 0}</b></div>
                        <div>❌ تعذر التسليم: <b>${failedCount}</b></div>
                    `;
                } else {
                    detailsContainer.innerHTML = "<div>ℹ️ لا توجد حملات إرسال جارية أو مسجلة مؤخراً.</div>";
                }
            }
        }
    } catch (error) {
        console.error("Error fetching broadcast stats:", error);
    }
}

// =========================================================
// 📈 قسم التحليلات العامة والأكثر تفاعلاً (Supabase)
// =========================================================

async function loadGlobalAnalytics() {
    try {
        const response = await requestApi("/api/super-admin/analytics", {
            method: "GET"
        });
        const data = await response.json();
        if (data.success && data.analytics) {
            const totalUsersElem = document.getElementById("total-users-val");
            const activeUsersElem = document.getElementById("active-users-val");
            const bannedUsersElem = document.getElementById("banned-users-val");
            const totalCoinsElem = document.getElementById("total-coins-val");

            if (totalUsersElem) totalUsersElem.innerText = Number(data.analytics.total_users || 0).toLocaleString();
            if (activeUsersElem) activeUsersElem.innerText = Number(data.analytics.active_today || 0).toLocaleString();
            if (bannedUsersElem) bannedUsersElem.innerText = Number(data.analytics.banned_users || 0).toLocaleString();
            if (totalCoinsElem && data.analytics.total_coins !== undefined) {
                totalCoinsElem.innerText = Number(data.analytics.total_coins || 0).toLocaleString();
            }

            const topUsers = data.analytics.top_active_users || data.analytics.top_users;
            if (topUsers) {
                renderTopActiveUsersList(topUsers);
            }
        }
    } catch (err) {
        console.error("Failed to load global analytics:", err);
    }
}

async function loadTopActiveUsers() {
    const listElem = document.getElementById("topActiveUsersList");
    if (!listElem) return;

    const startDateInput = document.getElementById("topActiveStartDate");
    const endDateInput = document.getElementById("topActiveEndDate");

    const startDate = startDateInput ? startDateInput.value.trim() : "";
    const endDate = endDateInput ? endDateInput.value.trim() : "";

    let endpoint = "/api/super-admin/analytics";
    const params = new URLSearchParams();
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);

    const queryString = params.toString();
    if (queryString) {
        endpoint += `?${queryString}`;
    }

    listElem.innerHTML = '<p class="empty-msg">⏳ جاري تحميل البيانات...</p>';

    try {
        const response = await requestApi(endpoint, {
            method: "GET"
        });
        const data = await response.json();
        const topUsers = data.analytics ? (data.analytics.top_active_users || data.analytics.top_users) : null;
        if (data.success && topUsers) {
            renderTopActiveUsersList(topUsers);
        } else {
            listElem.innerHTML = '<p class="empty-msg">لا توجد بيانات متاحة حالياً للفترة المحددة.</p>';
        }
    } catch (err) {
        console.error("Failed to load top active users:", err);
        listElem.innerHTML = '<p class="empty-msg">تعذر تحميل قائمة الأكثر نشاطاً.</p>';
    }
}

function resetTopActiveFilter() {
    const startDateInput = document.getElementById("topActiveStartDate");
    const endDateInput = document.getElementById("topActiveEndDate");

    if (startDateInput) startDateInput.value = "";
    if (endDateInput) endDateInput.value = "";

    loadTopActiveUsers();
}

function renderTopActiveUsersList(users) {
    const listElem = document.getElementById("topActiveUsersList");
    if (!listElem) return;

    if (!users || !Array.isArray(users) || users.length === 0) {
        listElem.innerHTML = '<p class="empty-msg">لا يوجد مستخدمون نشطون حالياً.</p>';
        return;
    }

    listElem.innerHTML = users.map((user, index) => {
        const uId = escapeHtml(user.telegram_id || user.user_id || user.tg_id || "—");
        const uName = escapeHtml(user.name || user.first_name || user.username || "مستخدم");

        const interactionsCount = (user.interactions !== undefined && user.interactions !== null)
            ? user.interactions
            : (user.activity_count ?? user.tap_count ?? user.total_mined ?? user.zn_balance ?? user.balance ?? 0);

        const znBalance = user.zn_balance !== undefined ? user.zn_balance : user.balance;
        const extraInfo = (znBalance !== undefined && znBalance !== null)
            ? ` | الرصيد: ${Number(znBalance).toLocaleString()}`
            : "";

        return `
            <div class="user-active-item" style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                <div class="user-info">
                    <strong>#${index + 1} ${uName}</strong>
                    <span>ID: ${uId}${extraInfo}</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span class="badge-count">${Number(interactionsCount).toLocaleString()} تفاعل</span>
                    <button class="btn-refresh" style="padding: 4px 8px; font-size: 11px;" onclick="inspectUserDetails('${uId}')" title="كشف الحساب">🔍</button>
                </div>
            </div>
        `;
    }).join("");
}

// =========================================================
// 🚫 قسم إدارة المحظورين والحظر وفك الحظر الشامل
// =========================================================

async function loadBannedUsers() {
    const listElem = document.getElementById("bannedUsersList");
    try {
        const response = await requestApi("/api/super-admin/banned-users", {
            method: "GET"
        });
        const data = await response.json();
        if (data.success) {
            const bannedUsersElem = document.getElementById("banned-users-val");
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

function renderBannedUsersList(users) {
    const listElem = document.getElementById("bannedUsersList");
    if (!listElem) return;

    if (!users || !Array.isArray(users) || users.length === 0) {
        listElem.innerHTML = '<p class="empty-msg">لا يوجد مستخدمون محظورون حالياً.</p>';
        return;
    }

    listElem.innerHTML = users.map(user => {
        const uId = escapeHtml(user.telegram_id || user.user_id || user.tg_id || "—");
        const uName = escapeHtml(user.name || user.first_name || user.username || "مستخدم محظور");
        const reason = escapeHtml(user.ban_reason || user.reason || "حظر أمني / تعدد حسابات");
        const bannedAt = escapeHtml(user.banned_at || user.date || user.updated_at || "—");
        const deviceInfo = user.device_id ? `<div>📱 <b>الجهاز:</b> <code>${escapeHtml(user.device_id)}</code></div>` : "";

        return `
            <div class="user-active-item" style="flex-direction: column; align-items: flex-start; gap: 8px; padding: 12px; background: rgba(231, 76, 60, 0.06); border: 1px solid rgba(231, 76, 60, 0.25); border-radius: 8px; margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; width: 100%; align-items: center;">
                    <div class="user-info">
                        <strong style="color: var(--accent-red, #e74c3c);">${uName}</strong>
                        <span>ID: ${uId}</span>
                    </div>
                    <div style="display: flex; gap: 6px;">
                        <button class="btn-refresh" style="padding: 4px 8px; font-size: 11px;" onclick="inspectUserDetails('${uId}')">🔍 كشف</button>
                        <button class="btn-refresh" style="color: var(--accent-green, #2ecc71); border-color: var(--accent-green, #2ecc71);" onclick="unbanUserDirect('${uId}')">🟢 فك الحظر</button>
                    </div>
                </div>
                <div style="font-size: 12px; color: var(--text-muted, #aaa); width: 100%; line-height: 1.5;">
                    <div>📌 <b>السبب:</b> ${reason}</div>
                    ${deviceInfo}
                    <div>📅 <b>التاريخ:</b> ${bannedAt}</div>
                </div>
            </div>
        `;
    }).join("");
}

async function unbanUserDirect(userId) {
    if (!userId || userId === "—") {
        alert("⚠️ معرّف المستخدم غير صالح.");
        return;
    }

    const confirmUnban = confirm(
        `🟢 هل أنت متأكد من فك الحظر الشامل عن المستخدم (${userId}) وتنظيف سجل أجهزته وبصمة متصفحه؟`
    );
    if (!confirmUnban) return;

    try {
        const response = await requestApi("/api/super-admin/unban-user", {
            method: "POST",
            body: JSON.stringify({
                telegram_id: String(userId).trim()
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

async function banUser() {
    const userIdInput =
        document.getElementById("banUserId") ||
        document.getElementById("unbanUserId") ||
        document.getElementById("targetUserId");
    const reasonInput = document.getElementById("banReason");

    const userId = userIdInput ? userIdInput.value.trim() : "";
    const reason = reasonInput ? reasonInput.value.trim() : "";

    if (!userId) {
        alert("⚠️ يرجى إدخال معرّف المستخدم (Telegram ID) المراد حظره.");
        if (userIdInput) userIdInput.focus();
        return;
    }

    const confirmBan = confirm(
        `🚫 هل أنت متأكد من حظر المستخدم (${userId}) وحظر جميع الأجهزة والبصمات والحسابات المرتبطة به؟`
    );
    if (!confirmBan) return;

    try {
        const response = await requestApi("/api/super-admin/ban-user", {
            method: "POST",
            body: JSON.stringify({
                telegram_id: userId,
                reason: reason || "تم الحظر من قبل الإدارة العليا"
            })
        });

        const data = await response.json();

        if (data.success) {
            alert("✅ " + (data.message || "تم حظر الحساب والأجهزة المربوطة به بنجاح."));
            if (document.getElementById("banUserId")) document.getElementById("banUserId").value = "";
            if (document.getElementById("unbanUserId")) document.getElementById("unbanUserId").value = "";
            if (reasonInput) reasonInput.value = "";
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

async function unbanUser() {
    const userIdInput =
        document.getElementById("unbanUserId") ||
        document.getElementById("banUserId") ||
        document.getElementById("targetUserId");
    const userId = userIdInput ? userIdInput.value.trim() : "";

    if (!userId) {
        alert("⚠️ يرجى إدخال معرّف المستخدم (Telegram ID) لفك الحظر عنه.");
        if (userIdInput) userIdInput.focus();
        return;
    }

    await unbanUserDirect(userId);
    if (document.getElementById("banUserId")) document.getElementById("banUserId").value = "";
    if (document.getElementById("unbanUserId")) document.getElementById("unbanUserId").value = "";
}

// =========================================================
// 🔍 قسم الكشف عن المستخدم وتعديل الأرصدة وتصفير الحسابات
// =========================================================

async function inspectUserDetails(passedUserId = null) {
    const inputElem =
        document.getElementById("inspectUserId") ||
        document.getElementById("banUserId") ||
        document.getElementById("targetUserId");

    const userId = (passedUserId || (inputElem ? inputElem.value.trim() : "")).trim();
    if (!userId) {
        alert("⚠️ يرجى إدخال معرّف المستخدم (Telegram ID) للكشف عنه.");
        return;
    }

    try {
        const response = await requestApi(`/api/super-admin/user-details?telegram_id=${encodeURIComponent(userId)}`, {
            method: "GET"
        });
        const data = await response.json();

        if (!data.success || !data.user) {
            alert("❌ " + (data.message || "لم يتم العثور على المستخدم."));
            return;
        }

        const u = data.user;
        const container = document.getElementById("userDetailsContainer");
        const balanceVal = u.zn_balance ?? u.balance ?? 0;
        const statusText = u.is_banned ? `🚫 محظور (${u.ban_reason || "بدون سبب"})` : "🟢 نشط وسليم";
        const linkedAccounts = Array.isArray(u.linked_accounts) && u.linked_accounts.length > 0
            ? u.linked_accounts.join(", ")
            : "لا توجد حسابات أخرى مشتركة";

        if (container) {
            container.style.display = "block";
            container.innerHTML = `
                <div style="padding: 12px; border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; background: rgba(0,0,0,0.25); font-size: 13px; line-height: 1.6;">
                    <div>👤 <b>الاسم:</b> ${escapeHtml(u.name || u.first_name || u.username || "غير معروف")} (<code>${escapeHtml(u.telegram_id || userId)}</code>)</div>
                    <div>🛡️ <b>الحالة:</b> ${escapeHtml(statusText)}</div>
                    <div>💰 <b>الرصيد الأساسي:</b> ${Number(balanceVal).toLocaleString()}</div>
                    <div>📱 <b>الجهاز:</b> <code>${escapeHtml(u.device_id || "غير مسجل")}</code></div>
                    <div>🧬 <b>البصمة:</b> <code>${escapeHtml(u.fingerprint_hash || "غير مسجلة")}</code></div>
                    <div>👥 <b>حسابات مشتركة بالجهاز:</b> ${escapeHtml(linkedAccounts)}</div>
                    <div style="display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap;">
                        <button class="btn-refresh" style="color: #e74c3c; border-color: #e74c3c;" onclick="unbanOrBanQuick('${escapeHtml(u.telegram_id || userId)}', ${Boolean(u.is_banned)})">
                            ${u.is_banned ? "🟢 فك الحظر" : "🚫 حظر شامل"}
                        </button>
                        <button class="btn-refresh" style="color: #f39c12; border-color: #f39c12;" onclick="resetUserAccount('${escapeHtml(u.telegram_id || userId)}')">
                            🔄 تصفير الحساب
                        </button>
                    </div>
                </div>
            `;
        } else {
            alert(
                `📋 بطاقة كشف المستخدم:\n` +
                `• الاسم: ${u.name || u.first_name || u.username || "غير معروف"}\n` +
                `• الآيدي: ${u.telegram_id || userId}\n` +
                `• الحالة: ${statusText}\n` +
                `• الرصيد: ${Number(balanceVal).toLocaleString()}\n` +
                `• الجهاز: ${u.device_id || "غير مسجل"}\n` +
                `• البصمة: ${u.fingerprint_hash || "غير مسجلة"}\n` +
                `• حسابات مشتركة: ${linkedAccounts}`
            );
        }
    } catch (err) {
        console.error("Error inspecting user:", err);
        alert("❌ تعذر جلب بيانات المستخدم: " + err.message);
    }
}

async function unbanOrBanQuick(userId, isCurrentlyBanned) {
    if (isCurrentlyBanned) {
        await unbanUserDirect(userId);
    } else {
        const reason = prompt("📌 أدخل سبب الحظر:", "مخالفة القوانين / تعدد حسابات");
        if (reason === null) return;
        const response = await requestApi("/api/super-admin/ban-user", {
            method: "POST",
            body: JSON.stringify({ telegram_id: userId, reason: reason || "حظر إداري" })
        });
        const data = await response.json();
        alert(data.success ? "✅ " + data.message : "❌ " + data.message);
        loadBannedUsers();
        loadGlobalAnalytics();
    }
    inspectUserDetails(userId);
}

async function modifyUserBalance(passedUserId = null, passedAction = null, passedAmount = null, passedCurrency = null) {
    const userId = passedUserId || document.getElementById("balanceUserId")?.value.trim() || "";
    const action = passedAction || document.getElementById("balanceAction")?.value || "add";
    const amountRaw = passedAmount !== null ? passedAmount : document.getElementById("balanceAmount")?.value.trim();
    const currency = passedCurrency || document.getElementById("balanceCurrency")?.value || "balance";

    if (!userId || amountRaw === "" || amountRaw === null || amountRaw === undefined) {
        alert("⚠️ يرجى إدخال معرّف المستخدم والمبلغ المطلوب.");
        return;
    }

    const amount = Number(amountRaw);
    if (isNaN(amount) || amount < 0) {
        alert("⚠️ يرجى إدخال مبلغ رقمي صحيح.");
        return;
    }

    const actionLabels = { add: "إضافة", deduct: "خصم", sub: "خصم", set: "تعيين" };
    const confirmMod = confirm(
        `💰 هل أنت متأكد من ${actionLabels[action] || action} مبلغ (${amount.toLocaleString()}) للمستخدم (${userId})؟`
    );
    if (!confirmMod) return;

    try {
        const response = await requestApi("/api/super-admin/modify-balance", {
            method: "POST",
            body: JSON.stringify({
                telegram_id: userId,
                action: action,
                amount: amount,
                currency: currency
            })
        });
        const data = await response.json();
        if (data.success) {
            alert("✅ " + (data.message || "تم تحديث رصيد المستخدم بنجاح."));
            if (document.getElementById("balanceAmount")) document.getElementById("balanceAmount").value = "";
            loadGlobalAnalytics();
            loadAdminLogs();
        } else {
            alert("❌ " + (data.message || "فشل تعديل الرصيد"));
        }
    } catch (err) {
        console.error("Error modifying balance:", err);
        alert("❌ حدث خطأ أثناء تعديل الرصيد: " + err.message);
    }
}

async function resetUserAccount(passedUserId = null) {
    const userId = (
        passedUserId ||
        document.getElementById("resetUserId")?.value.trim() ||
        document.getElementById("banUserId")?.value.trim() ||
        ""
    ).trim();

    if (!userId) {
        alert("⚠️ يرجى إدخال معرّف المستخدم (Telegram ID) المراد تصفير حسابه.");
        return;
    }

    const confirmReset = confirm(
        `⚠️ تحذير: هل أنت متأكد من تصفير حساب المستخدم (${userId}) وإعادة جميع أرصدته إلى الصفر؟ لا يمكن التراجع عن هذا الإجراء.`
    );
    if (!confirmReset) return;

    try {
        const response = await requestApi("/api/super-admin/reset-account", {
            method: "POST",
            body: JSON.stringify({ telegram_id: userId })
        });
        const data = await response.json();
        if (data.success) {
            alert("✅ " + (data.message || "تم تصفير حساب المستخدم بنجاح."));
            loadGlobalAnalytics();
            loadAdminLogs();
        } else {
            alert("❌ " + (data.message || "فشل تصفير الحساب"));
        }
    } catch (err) {
        console.error("Error resetting user account:", err);
        alert("❌ حدث خطأ أثناء تصفير الحساب: " + err.message);
    }
}

// =========================================================
// 🛡️ قسم إدارة المشرفين وسجل الحركات الإدارية
// =========================================================

async function addNewModerator() {
    const modId = document.getElementById("modTelegramId")?.value.trim();
    const modName = document.getElementById("modName")?.value.trim();

    if (!modId || !modName) {
        alert("⚠️ يرجى إدخال معرّف التليجرام واسم المشرف.");
        return;
    }

    const permissions = {
        perm_users: document.getElementById("perm_users")?.checked || false,
        perm_support: document.getElementById("perm_support")?.checked || false,
        perm_settings: document.getElementById("perm_settings")?.checked || false,
        perm_transactions: document.getElementById("perm_transactions")?.checked || false,
        perm_security: document.getElementById("perm_security")?.checked || false,
        perm_ads: document.getElementById("perm_ads")?.checked || false
    };

    try {
        const response = await requestApi("/api/super-admin/add-moderator", {
            method: "POST",
            body: JSON.stringify({
                telegram_id: modId,
                name: modName,
                permissions: permissions
            })
        });
        const data = await response.json();
        if (data.success) {
            alert("✅ تمت إضافة المشرف بنجاح!");
            if (document.getElementById("modTelegramId")) document.getElementById("modTelegramId").value = "";
            if (document.getElementById("modName")) document.getElementById("modName").value = "";
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
    const listElem = document.getElementById("moderatorsList");
    if (!listElem) return;

    try {
        const response = await requestApi("/api/super-admin/list-moderators", {
            method: "GET"
        });
        const data = await response.json();
        if (data.success && Array.isArray(data.moderators)) {
            if (data.moderators.length === 0) {
                listElem.innerHTML = '<p class="empty-msg">لا يوجد مشرفون مضافون حالياً.</p>';
                return;
            }
            const permLabels = {
                perm_users: "المستخدمين",
                perm_security: "الأمان والحظر",
                perm_ads: "الإعلانات والبث",
                perm_transactions: "المعاملات",
                perm_settings: "الإعدادات",
                perm_support: "الدعم"
            };

            listElem.innerHTML = data.moderators.map(mod => {
                const modId = escapeHtml(mod.telegram_id);
                const modName = escapeHtml(mod.name || "مشرف");
                const permsObj = mod.permissions || mod;
                const activePerms = Object.keys(permLabels)
                    .filter(k => Boolean(permsObj[k]))
                    .map(k => permLabels[k]);
                const permsText = activePerms.length > 0 ? activePerms.join(" • ") : "صلاحيات محدودة";

                return `
                    <div class="mod-item">
                        <div class="mod-info">
                            <strong>${modName}</strong>
                            <span>ID: ${modId}</span>
                            <small style="color: var(--accent-gold, #f39c12); font-size: 11px; display: block;">${escapeHtml(permsText)}</small>
                        </div>
                        <button class="btn-refresh" style="color: var(--accent-red, #e74c3c); border-color: var(--accent-red, #e74c3c);" onclick="removeModerator('${modId}')">🗑️ حذف</button>
                    </div>
                `;
            }).join("");
        }
    } catch (err) {
        listElem.innerHTML = '<p class="empty-msg">تعذر تحميل قائمة المشرفين.</p>';
    }
}

async function removeModerator(telegramId) {
    if (!confirm(`هل أنت متأكد من رغبتك في حذف المشرف صاحب المعرف (${telegramId})؟`)) return;

    try {
        const response = await requestApi("/api/super-admin/remove-moderator", {
            method: "POST",
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
    const logsElem = document.getElementById("adminLogs");
    if (!logsElem) return;

    try {
        const response = await requestApi("/api/super-admin/logs", {
            method: "GET"
        });
        const data = await response.json();
        if (data.success && Array.isArray(data.logs)) {
            if (data.logs.length === 0) {
                logsElem.innerHTML = '<p class="empty-msg">لا توجد سجلات إدارية حديثة.</p>';
                return;
            }
            logsElem.innerHTML = data.logs.map(log => `
                <div class="log-item">
                    <div class="mod-info">
                        <strong>${escapeHtml(log.admin || log.admin_name || "مشرف")}</strong>
                        <span>${escapeHtml(log.action || log.details || "")}</span>
                    </div>
                    <span style="color: var(--text-muted, #888); font-size: 10px;">${escapeHtml(log.timestamp || log.created_at || "")}</span>
                </div>
            `).join("");
        }
    } catch (err) {
        logsElem.innerHTML = '<p class="empty-msg">تعذر تحميل سجل النشاطات.</p>';
    }
}

// =========================================================
// 🚀 تهيئة موديول الإدارة العليا وتصدير الدوال
// =========================================================

function initSuperAdmin() {
    try {
        if (window.Telegram?.WebApp) {
            window.Telegram.WebApp.ready();
            window.Telegram.WebApp.expand();
        }
    } catch (e) {
        console.warn("Telegram WebApp init warning:", e);
    }

    loadGlobalAnalytics();
    loadTopActiveUsers();
    loadBannedUsers();
    loadModerators();
    loadAdminLogs();
    fetchBroadcastStats();
}

// تصدير جميع الدوال إلى النطاق العام window لضمان عمل كافة أزرار الواجهة
window.initSuperAdmin = initSuperAdmin;
window.getAdminHeaders = getAdminHeaders;
window.getAdminId = getAdminId;
window.banUser = banUser;
window.unbanUser = unbanUser;
window.unbanUserDirect = unbanUserDirect;
window.loadBannedUsers = loadBannedUsers;
window.renderBannedUsersList = renderBannedUsersList;
window.inspectUserDetails = inspectUserDetails;
window.unbanOrBanQuick = unbanOrBanQuick;
window.modifyUserBalance = modifyUserBalance;
window.resetUserAccount = resetUserAccount;
window.sendAdminMessage = sendAdminMessage;
window.fetchBroadcastStats = fetchBroadcastStats;
window.loadGlobalAnalytics = loadGlobalAnalytics;
window.loadTopActiveUsers = loadTopActiveUsers;
window.resetTopActiveFilter = resetTopActiveFilter;
window.renderTopActiveUsersList = renderTopActiveUsersList;
window.addNewModerator = addNewModerator;
window.loadModerators = loadModerators;
window.removeModerator = removeModerator;
window.loadAdminLogs = loadAdminLogs;
window.toggleTargetInput = toggleTargetInput;

document.addEventListener("DOMContentLoaded", () => {
    initSuperAdmin();
});
