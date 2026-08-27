// settings/settings.js
(function initSettingsSystem() {
    
    function getTgUser() {
        if (window.Telegram?.WebApp?.initDataUnsafe?.user) {
            return window.Telegram.WebApp.initDataUnsafe.user;
        }
        return null;
    }

    function getTgId() {
        const user = getTgUser();
        return user ? String(user.id) : (window.userState?.tg_id || "5102387551"); 
    }

    function getPlayerName() {
        const user = getTgUser();
        if (user) {
            return user.first_name + (user.last_name ? " " + user.last_name : "");
        }
        return window.userState?.first_name || "اللاعب المحترف";
    }

    // 🎯 دالة إخفاء أرقام الـ ID للحفاظ على الخصوصية (أول 4 أرقام + ***** + باقي الأرقام)
    function maskTelegramId(uid) {
        if (!uid) return "*****";
        const str = String(uid).trim();
        if (str.length > 6) {
            return str.slice(0, 4) + "*****" + str.slice(8);
        } else if (str.length > 2) {
            return str.slice(0, 2) + "*****";
        }
        return "*****";
    }

    function updateStatsFromLocalData() {
        const state = window.userState || window.PlayerData || window.GameState;
        if (state) {
            const totalMiningEl = document.getElementById('stat-total-mining');
            const totalStorageEl = document.getElementById('stat-total-storage');
            
            let totalUpgradesCount = 0;
            if (state.upgrades && typeof state.upgrades === 'object') {
                for (let i = 1; i <= 9; i++) {
                    totalUpgradesCount += parseInt(state.upgrades[`lvl${i}`] || 0) || 0;
                }
            }
            let storageLevelsCount = parseInt(state.storage_level || 0) || 0;

            if (totalMiningEl) totalMiningEl.innerText = `${totalUpgradesCount} مستويات`;
            if (totalStorageEl) totalStorageEl.innerText = `${storageLevelsCount} مستويات`;
        }
    }

    async function fetchAndRenderData() {
        const telegramId = getTgId();
        const usernameEl = document.getElementById('player-username');
        const telegramIdEl = document.getElementById('player-telegram-id');
        const avatarEl = document.getElementById('player-avatar');

        if (usernameEl) usernameEl.innerText = getPlayerName();
        if (telegramIdEl) telegramIdEl.innerText = telegramId;

        const user = getTgUser();
        if (user && user.photo_url && avatarEl) {
            avatarEl.innerHTML = `<img src="${escapeHTML(user.photo_url)}" style="width:100%; height:100%; object-fit:cover; border-radius:50%;">`;
        }

        updateStatsFromLocalData();
        fetchLeaderboard();

        try {
            let data;
            if (typeof window.fetchAPI === 'function') {
                data = await window.fetchAPI('/api/settings/stats');
            } else {
                const initData = window.Telegram?.WebApp?.initData || "";
                const res = await fetch('/api/settings/stats', {
                    headers: { 
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${initData}`,
                        'X-Telegram-Init-Data': initData
                    }
                });
                data = await res.json();
            }

            if (data && data.success) {
                const miningEl = document.getElementById('stat-total-mining');
                const storageEl = document.getElementById('stat-total-storage');
                if (miningEl) miningEl.innerText = `${data.farm_levels_count || 0} مستويات`;
                if (storageEl) storageEl.innerText = `${data.storage_levels_count || 0} مستويات`;
            }
        } catch (error) {
            console.warn("Settings stats info:", error);
        }
    }

    // ==========================================
    // 🎁 نظام تفعيل أكواد الهدايا (Promo Codes)
    // ==========================================
    async function redeemPromoCode() {
        const inputEl = document.getElementById('promo-code-input');
        const btnEl = document.getElementById('redeem-code-btn');
        if (!inputEl) return;

        const code = inputEl.value.trim().toUpperCase();
        if (!code) {
            showToast("⚠️ يرجى إدخال الكود أولاً!");
            return;
        }

        if (btnEl) {
            btnEl.disabled = true;
            btnEl.innerText = "جاري التفعيل... ⏳";
            btnEl.style.opacity = '0.7';
        }

        try {
            let data = null;
            const initData = window.Telegram?.WebApp?.initData || "";

            if (typeof window.fetchAPI === 'function') {
                try {
                    data = await window.fetchAPI('/api/settings/redeem-code', 'POST', { code: code });
                } catch (e) {
                    console.warn("fetchAPI failed, falling back to fetch:", e);
                }
            }

            if (!data) {
                const res = await fetch('/api/settings/redeem-code', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${initData}`,
                        'X-Telegram-Init-Data': initData
                    },
                    body: JSON.stringify({ code: code })
                });
                data = await res.json();
            }

            if (data && data.success) {
                showToast(data.message || "🎉 تم تفعيل الكود بنجاح!");
                inputEl.value = '';
                fetchAndRenderData();
            } else if (data && data.message) {
                showToast(data.message);
            } else {
                showToast("❌ فشل تفعيل الكود!");
            }
        } catch (error) {
            console.error("Redeem code error:", error);
            showToast("❌ حدث خطأ أثناء الاتصال بالسيرفر!");
        } finally {
            if (btnEl) {
                btnEl.disabled = false;
                btnEl.innerText = "تفعيل ✨";
                btnEl.style.opacity = '1';
            }
        }
    }
    window.redeemPromoCode = redeemPromoCode;

    // ==========================================
    // 🏆 نظام المتصدرين في التعدين
    // ==========================================
    async function fetchLeaderboard() {
        const listEl = document.getElementById('leaderboard-list');
        if (!listEl) return;

        listEl.innerHTML = '<div style="text-align:center; color:var(--text-muted); font-size:12px; padding:10px;">جاري تحميل المتصدرين... ⏳</div>';

        try {
            let data;
            if (typeof window.fetchAPI === 'function') {
                data = await window.fetchAPI('/api/settings/leaderboard');
            } else {
                const initData = window.Telegram?.WebApp?.initData || "";
                const res = await fetch('/api/settings/leaderboard', {
                    headers: { 
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${initData}`,
                        'X-Telegram-Init-Data': initData
                    }
                });
                data = await res.json();
            }

            if (data && data.success && Array.isArray(data.leaderboard)) {
                if (data.leaderboard.length === 0) {
                    listEl.innerHTML = '<div style="text-align:center; color:var(--text-muted); font-size:12px; padding:10px;">لا يوجد متصدرين حالياً.</div>';
                    return;
                }

                let html = '';
                data.leaderboard.forEach((item, index) => {
                    const rank = index + 1;
                    let rankBadge = `${rank}#`;
                    let rankClass = '';
                    if (rank === 1) { rankBadge = '🥇'; rankClass = 'leader-rank-1'; }
                    else if (rank === 2) { rankBadge = '🥈'; rankClass = 'leader-rank-2'; }
                    else if (rank === 3) { rankBadge = '🥉'; rankClass = 'leader-rank-3'; }

                    const rawUid = item.uid || item.telegram_id || item.tg_id || '';
                    const maskedId = item.masked_id || maskTelegramId(rawUid);
                    const name = escapeHTML(item.first_name || item.username || `لاعب #${String(rawUid).slice(-4)}`);

                    const rawScore = (item.mined_points !== undefined && item.mined_points !== null) 
                        ? item.mined_points 
                        : (item.mining_points !== undefined && item.mining_points !== null)
                        ? item.mining_points
                        : item.total_mined || 0;
                    
                    const numScore = parseFloat(rawScore) || 0;
                    const strScore = numScore.toFixed(4).replace(/\.?0+$/, ''); 
                    const scoreParts = strScore.split('.');
                    const mainInt = parseInt(scoreParts[0], 10).toLocaleString('en-US');

                    let scoreHTML = mainInt;
                    if (scoreParts.length > 1 && scoreParts[1]) {
                        scoreHTML += `<span style="font-size:0.8em; opacity:0.65; font-weight:normal;">.${scoreParts[1]}</span>`;
                    }

                    html += `
                        <div class="leader-item" style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
                            <div style="display:flex; align-items:center; gap:6px; flex-shrink:0;">
                                <span class="leader-rank ${rankClass}">${rankBadge}</span>
                                <span style="font-size:11px; color:#aaa; font-family:monospace; direction:ltr; unicode-bidi:isolate;">ID: ${escapeHTML(maskedId)}</span>
                            </div>
                            <div style="flex:1; text-align:center; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding:0 6px;">
                                <span style="font-weight:600; color:#fff; font-size:13px;">${name}</span>
                            </div>
                            <span class="leader-score" style="flex-shrink:0;">⛏️ ${scoreHTML}</span>
                        </div>
                    `;
                });
                listEl.innerHTML = html;
            } else {
                listEl.innerHTML = '<div style="text-align:center; color:var(--text-muted); font-size:12px; padding:10px;">تعذر تحميل قائمة المتصدرين.</div>';
            }
        } catch (error) {
            console.warn("Leaderboard error:", error);
            if (listEl) {
                listEl.innerHTML = '<div style="text-align:center; color:var(--text-muted); font-size:12px; padding:10px;">خطأ في الاتصال بالشبكة.</div>';
            }
        }
    }
    window.fetchLeaderboard = fetchLeaderboard;

    // ==========================================
    // 🎧 نظام الدعم الفني المباشر
    // ==========================================
    let supportTicketId = null;
    let isSupportClosed = false;
    let supportPollInterval = null;
    let supportLastMsgCount = -1;
    let supportLastTimestamp = "";
    let isFetchingTicket = false;
    let isSendingMessage = false;
    let localMessagesList = [];

    const chatBox = document.getElementById('support-chat-box');
    const msgInput = document.getElementById('support-msg-input');
    const sendBtn = document.getElementById('support-send-btn');
    const inputSection = document.getElementById('support-input-section');
    const ticketDisplay = document.getElementById('ticket-id-display');

    function getWelcomeNoticeText(tId) {
        return `مرحباً بك في مركز الدعم الفني! 🎧\nكودك المرجعي للمحادثة: ${tId}\n\n⚠️ تنبيه هام لجميع المستخدمين:\nيرجى التكرم بالالتزام بآداب الحوار والتعامل اللائق مع فريق الدعم. المحادثات مخصصة فقط للاستفسارات الفنية والمشكلات. أي إساءة لفظية أو تجاوز قد يعرض حسابك للحظر النهائي والمنع من الخدمة فوراً.\n\nتفضل بكتابة استفسارك وسيقوم الفريق بالرد عليك في أقرب وقت.`;
    }

    function generateLocalTicketId() {
        const uid = getTgId();
        const shortUid = uid.slice(-4);
        const randSec = Math.floor(Math.random() * 90000) + 10000;
        return `TK-${shortUid}-${randSec}`;
    }

    function getStoredSupportData() {
        try {
            const uid = getTgId();
            const stored = localStorage.getItem(`support_cache_${uid}`);
            return stored ? JSON.parse(stored) : null;
        } catch (e) {
            return null;
        }
    }

    function saveSupportDataLocally(ticketId, msgs, status = 'open') {
        try {
            const uid = getTgId();
            localStorage.setItem(`support_cache_${uid}`, JSON.stringify({
                ticket_id: ticketId,
                messages: msgs,
                status: status,
                updated_at: new Date().toISOString()
            }));
        } catch (e) {}
    }

    window.openSupportModal = function() {
        const modal = document.getElementById('support-modal');
        if (modal) {
            modal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
        }
        
        const cached = getStoredSupportData();
        if (cached && cached.ticket_id) {
            supportTicketId = cached.ticket_id;
            isSupportClosed = (cached.status === 'closed');
            localMessagesList = cached.messages || [];
            if (ticketDisplay) ticketDisplay.innerText = `تذكرة #${supportTicketId} 📋`;
            renderMessages(localMessagesList, true);
            if (isSupportClosed) {
                disableSupportInput("تم إنهاء هذه المحادثة.");
            } else {
                enableSupportInput();
            }
        } else {
            supportTicketId = generateLocalTicketId();
            localMessagesList = [{
                sender: 'admin',
                text: getWelcomeNoticeText(supportTicketId),
                timestamp: new Date().toISOString()
            }];
            if (ticketDisplay) ticketDisplay.innerText = `تذكرة #${supportTicketId} 📋`;
            renderMessages(localMessagesList, true);
            enableSupportInput();
            saveSupportDataLocally(supportTicketId, localMessagesList, 'open');
        }

        supportLastMsgCount = -1;
        supportLastTimestamp = "";
        fetchTicketData();
        startSupportPolling();
    };

    window.closeSupportModal = function() {
        const modal = document.getElementById('support-modal');
        if (modal) {
            modal.style.display = 'none';
            document.body.style.overflow = 'auto';
        }
        stopSupportPolling();
    };

    window.fetchTicketData = async function() {
        if (isFetchingTicket) return;
        isFetchingTicket = true;

        try {
            let data;
            const endpoint = supportTicketId 
                ? `/api/support/ticket?ticket_id=${encodeURIComponent(supportTicketId)}`
                : '/api/support/ticket';

            if (typeof window.fetchAPI === 'function') {
                data = await window.fetchAPI(endpoint);
            } else {
                const initData = window.Telegram?.WebApp?.initData || "";
                const response = await fetch(endpoint, {
                    method: 'GET',
                    headers: { 
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${initData}`,
                        'X-Telegram-Init-Data': initData
                    }
                });
                data = await response.json();
            }

            if (data && data.success) {
                supportTicketId = data.ticket_id || supportTicketId;
                isSupportClosed = (data.status === 'closed');
                localMessagesList = data.messages || [];
                
                if (ticketDisplay) ticketDisplay.innerText = `تذكرة #${supportTicketId} 📋`;
                renderMessages(localMessagesList);
                saveSupportDataLocally(supportTicketId, localMessagesList, data.status);
                
                if (isSupportClosed) {
                    disableSupportInput("تم إنهاء هذه المحادثة.");
                } else {
                    enableSupportInput();
                }
            }
        } catch (error) {
            console.warn("تعذر الاتصال المباشر بالسيرفر حالياً.");
        } finally {
            isFetchingTicket = false;
        }
    };

    function formatTime(isoString) {
        if (!isoString) return '';
        try {
            const date = new Date(isoString);
            return date.toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' });
        } catch (e) {
            return '';
        }
    }

    function renderMessages(messages, forceRender = false) {
        messages = messages || [];
        if (!chatBox) return;

        const lastMsg = messages[messages.length - 1];
        const lastTs = lastMsg ? (lastMsg.timestamp || '') : '';

        if (!forceRender && messages.length === supportLastMsgCount && lastTs === supportLastTimestamp && !isSupportClosed) {
            return;
        }

        supportLastMsgCount = messages.length;
        supportLastTimestamp = lastTs;

        chatBox.innerHTML = ''; 

        if (messages.length === 0) {
            chatBox.innerHTML = `
                <div class="msg-system">
                    👋 <b>مرحباً بك في الدعم الفني المباشر!</b><br>
                    الكود المرجعي: <b>${escapeHTML(supportTicketId || '')}</b><br>
                    اكتب استفسارك وسيقوم فريق الدعم بالرد عليك في أقرب وقت.
                </div>`;
        } else {
            messages.forEach(msg => {
                const div = document.createElement('div');
                const isUser = (msg.sender === 'user');
                div.className = `chat-msg ${isUser ? 'msg-user' : 'msg-admin'}`;
                
                const timeStr = formatTime(msg.timestamp);
                div.innerHTML = `
                    <div style="white-space: pre-wrap;">${escapeHTML(msg.text)}</div>
                    ${timeStr ? `<span class="msg-time">${timeStr}</span>` : ''}
                `;
                chatBox.appendChild(div);
            });
        }

        if (isSupportClosed) {
            const closedBox = document.createElement('div');
            closedBox.className = 'msg-system';
            closedBox.style.cssText = 'background: rgba(231, 76, 60, 0.12); border: 1px solid #e74c3c; color: #ff6b6b; margin-top: 15px; padding: 14px; border-radius: 12px; text-align: center;';
            closedBox.innerHTML = `
                🔒 تم إنهاء هذه المحادثة من قبل الدعم الفني.<br><br>
                <button onclick="startNewTicket()" style="padding: 10px 20px; background: linear-gradient(135deg, var(--primary), #e67e22); border: none; border-radius: 10px; color: #000; font-weight: bold; cursor: pointer; font-size: 13px;">
                    ➕ بدء تذكرة محادثة جديدة
                </button>
            `;
            chatBox.appendChild(closedBox);
            disableSupportInput("المحادثة مغلقة.");
        }

        chatBox.scrollTo({ top: chatBox.scrollHeight, behavior: 'smooth' });
    }

    function escapeHTML(str) {
        if (!str) return '';
        return String(str).replace(/[&<>"'/]/g, function(m) {
            return {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;',
                '/': '&#x2F;'
            }[m];
        });
    }

    window.sendQuickQuery = function(text) {
        if (!msgInput) return;
        msgInput.value = text;
        sendSupportMessage();
    };

    window.startNewTicket = async function() {
        if (chatBox) chatBox.innerHTML = '<div class="msg-system">جاري تفعيل محادثة جديدة... ⏳</div>';
        
        const newLocalId = generateLocalTicketId();
        supportTicketId = newLocalId;
        isSupportClosed = false;
        localMessagesList = [{
            sender: 'admin',
            text: getWelcomeNoticeText(newLocalId),
            timestamp: new Date().toISOString()
        }];
        
        if (ticketDisplay) ticketDisplay.innerText = `تذكرة #${supportTicketId} 📋`;
        enableSupportInput();
        renderMessages(localMessagesList, true);
        saveSupportDataLocally(supportTicketId, localMessagesList, 'open');

        try {
            let data;
            if (typeof window.fetchAPI === 'function') {
                data = await window.fetchAPI('/api/support/new_ticket', 'POST', {});
            } else {
                const initData = window.Telegram?.WebApp?.initData || "";
                const response = await fetch('/api/support/new_ticket', {
                    method: 'POST',
                    headers: { 
                        'Authorization': `Bearer ${initData}`,
                        'X-Telegram-Init-Data': initData,
                        'Content-Type': 'application/json'
                    }
                });
                data = await response.json();
            }

            if (data && data.success) {
                supportTicketId = data.ticket_id;
                localMessagesList = data.messages || localMessagesList;
                if (ticketDisplay) ticketDisplay.innerText = `تذكرة #${supportTicketId} 📋`;
                renderMessages(localMessagesList, true);
                saveSupportDataLocally(supportTicketId, localMessagesList, 'open');
                startSupportPolling();
            }
        } catch (e) {
            console.warn("تم إنشاء التذكرة محلياً وسيتم المزامنة تلقائياً.");
        }
    };

    window.sendSupportMessage = async function() {
        if (!msgInput || isSendingMessage) return;
        const text = msgInput.value.trim();
        if (!text || isSupportClosed) return;

        isSendingMessage = true;

        if (!supportTicketId) {
            supportTicketId = generateLocalTicketId();
        }

        const newMsgObj = {
            sender: 'user',
            text: text,
            timestamp: new Date().toISOString()
        };

        localMessagesList.push(newMsgObj);
        renderMessages(localMessagesList, true);
        saveSupportDataLocally(supportTicketId, localMessagesList, 'open');

        msgInput.value = '';
        if (sendBtn) sendBtn.disabled = true;

        try {
            let data;
            if (typeof window.fetchAPI === 'function') {
                data = await window.fetchAPI('/api/support/message', 'POST', { ticket_id: supportTicketId, text: text });
            } else {
                const initData = window.Telegram?.WebApp?.initData || "";
                const response = await fetch('/api/support/message', {
                    method: 'POST',
                    headers: { 
                        'Authorization': `Bearer ${initData}`,
                        'X-Telegram-Init-Data': initData,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ ticket_id: supportTicketId, text: text })
                });
                data = await response.json();
            }

            if (data && data.success) {
                setTimeout(fetchTicketData, 300);
            } else if (data?.message && data.message.includes("إنهاء")) {
                isSupportClosed = true;
                fetchTicketData();
            }
        } catch (error) {
            console.warn("تعذر الإرسال الفوري للسيرفر، التذكرة محفوظة محلياً.");
        } finally {
            isSendingMessage = false;
            if (sendBtn && !isSupportClosed) sendBtn.disabled = false;
        }
    };

    function disableSupportInput(reason) {
        if (msgInput) {
            msgInput.disabled = true;
            msgInput.placeholder = reason;
        }
        if (sendBtn) sendBtn.disabled = true;
        if (inputSection) inputSection.style.opacity = '0.5';
        stopSupportPolling();
    }

    function enableSupportInput() {
        if (msgInput) {
            msgInput.disabled = false;
            msgInput.placeholder = "اكتب استفسارك هنا...";
        }
        if (sendBtn) sendBtn.disabled = false;
        if (inputSection) inputSection.style.opacity = '1';
    }

    function startSupportPolling() {
        stopSupportPolling();
        supportPollInterval = setInterval(() => {
            const modal = document.getElementById('support-modal');
            if (!isSupportClosed && modal && modal.style.display === 'flex' && document.visibilityState === 'visible') {
                fetchTicketData();
            }
        }, 3500);
    }

    function stopSupportPolling() {
        if (supportPollInterval) {
            clearInterval(supportPollInterval);
            supportPollInterval = null;
        }
    }

    if (msgInput) {
        msgInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                sendSupportMessage();
            }
        });
    }

    window.copyPlayerId = function() {
        const idEl = document.getElementById('player-telegram-id');
        if (!idEl) return;
        const idText = idEl.innerText;
        copyTextToClipboard(idText, "تم نسخ الـ ID بنجاح!");
    };

    window.copyTicketId = function() {
        if (!supportTicketId) return;
        copyTextToClipboard(supportTicketId, `تم نسخ رقم التذكرة المرجعي (${supportTicketId}) بنجاح!`);
    };

    function copyTextToClipboard(text, successMsg) {
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(text).then(() => showToast(successMsg)).catch(() => fallbackCopy(text, successMsg));
        } else {
            fallbackCopy(text, successMsg);
        }
    }

    function fallbackCopy(text, successMsg) {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        try { document.execCommand('copy'); showToast(successMsg); } catch (err) {}
        document.body.removeChild(textArea);
    }

    window.showPrivacyModal = function() { 
        const modal = document.getElementById('settings-modal');
        if (modal) modal.style.display = 'flex'; 
    };
    
    window.closeSettingsModal = function() { 
        const modal = document.getElementById('settings-modal');
        if (modal) modal.style.display = 'none'; 
    };
    
    function showToast(text) {
        const toast = document.getElementById('toast-msg');
        if (!toast) return;
        toast.innerText = text;
        toast.style.display = 'block';
        setTimeout(() => toast.style.display = 'none', 2200);
    }

    window.addEventListener('userStateUpdated', updateStatsFromLocalData);

    window.addEventListener('pageshow', () => {
        updateStatsFromLocalData();
        fetchAndRenderData();
    });

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            updateStatsFromLocalData();
            fetchAndRenderData();
        } else {
            stopSupportPolling();
        }
    });

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        fetchAndRenderData();
    } else {
        document.addEventListener('DOMContentLoaded', fetchAndRenderData);
    }
})();
