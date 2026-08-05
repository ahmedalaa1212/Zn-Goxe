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

    function updateStatsFromLocalData() {
        const state = window.userState || window.PlayerData || window.GameState;
        if (state) {
            const totalMiningEl = document.getElementById('stat-total-mining');
            const totalStorageEl = document.getElementById('stat-total-storage');
            
            let totalUpgradesCount = 0;
            if (state.upgrades) {
                for (let i = 1; i <= 9; i++) {
                    totalUpgradesCount += parseInt(state.upgrades[`lvl${i}`] || 0);
                }
            }
            let storageLevelsCount = parseInt(state.storage_level || 0);

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
            avatarEl.innerHTML = `<img src="${user.photo_url}" style="width:100%; height:100%; object-fit:cover; border-radius:50%;">`;
        }

        updateStatsFromLocalData();

        try {
            let data;
            if (typeof window.fetchAPI === 'function') {
                data = await window.fetchAPI('/api/settings/stats');
            } else {
                const initData = window.Telegram?.WebApp?.initData || "";
                const res = await fetch('/api/settings/stats', {
                    headers: { 
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${initData}`
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
    // 🎧 نظام الدعم الفني الاحترافي المزود بالوضع المحلي الاحتياطي
    // ==========================================
    let supportTicketId = null;
    let isSupportClosed = false;
    let supportPollInterval = null;
    let supportLastMsgCount = -1;
    let isFetchingTicket = false;
    let localMessagesList = [];

    const chatBox = document.getElementById('support-chat-box');
    const msgInput = document.getElementById('support-msg-input');
    const sendBtn = document.getElementById('support-send-btn');
    const inputSection = document.getElementById('support-input-section');
    const ticketDisplay = document.getElementById('ticket-id-display');

    // إنشاء رقم مرجعي محلي سريعات عند الانقطاع
    function generateLocalTicketId() {
        const uid = getTgId();
        const shortUid = uid.slice(-4);
        const randSec = Math.floor(Math.random() * 90000) + 10000;
        return `TK-${shortUid}-${randSec}`;
    }

    // حفظ وقراءة المحادثة محلياً للحفاظ على الاستمرارية
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
            document.body.style.overflow = 'hidden'; // منع التمرير للخلفية
        }
        
        // جلب البيانات من الكاش المحلي أولاً لاستجابة فورية بدون شاشة معطلة
        const cached = getStoredSupportData();
        if (cached && cached.ticket_id) {
            supportTicketId = cached.ticket_id;
            isSupportClosed = (cached.status === 'closed');
            localMessagesList = cached.messages || [];
            if (ticketDisplay) ticketDisplay.innerHTML = `تذكرة #${supportTicketId} 📋`;
            renderMessages(localMessagesList);
            enableSupportInput();
        } else {
            // كود افتراضي مؤقت في حال فتح لأول مرة بدون شبكة
            supportTicketId = generateLocalTicketId();
            localMessagesList = [{
                sender: 'admin',
                text: `مرحباً بك! كود المحادثة المرجعي الخاص بك هو: [ ${supportTicketId} ]. اكتب استفسارك وسنجيبك فوراً.`,
                timestamp: new Date().toISOString()
            }];
            if (ticketDisplay) ticketDisplay.innerHTML = `تذكرة #${supportTicketId} 📋`;
            renderMessages(localMessagesList);
            enableSupportInput();
            saveSupportDataLocally(supportTicketId, localMessagesList, 'open');
        }

        supportLastMsgCount = -1;
        fetchTicketData();
    };

    window.closeSupportModal = function() {
        const modal = document.getElementById('support-modal');
        if (modal) {
            modal.style.display = 'none';
            document.body.style.overflow = 'auto';
        }
        if (supportPollInterval) {
            clearInterval(supportPollInterval);
            supportPollInterval = null;
        }
    };

    window.fetchTicketData = async function() {
        if (isFetchingTicket) return;
        isFetchingTicket = true;

        try {
            let data;
            if (typeof window.fetchAPI === 'function') {
                data = await window.fetchAPI('/api/support/ticket');
            } else {
                const initData = window.Telegram?.WebApp?.initData || "";
                const response = await fetch('/api/support/ticket', {
                    method: 'GET',
                    headers: { 
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${initData}`
                    }
                });
                data = await response.json();
            }

            if (data && data.success) {
                supportTicketId = data.ticket_id || supportTicketId;
                isSupportClosed = (data.status === 'closed');
                localMessagesList = data.messages || [];
                
                if (ticketDisplay) ticketDisplay.innerHTML = `تذكرة #${supportTicketId} 📋`;
                renderMessages(localMessagesList);
                saveSupportDataLocally(supportTicketId, localMessagesList, data.status);
                
                if (isSupportClosed) {
                    disableSupportInput("تم إنهاء هذه المحادثة.");
                } else {
                    enableSupportInput();
                    startSupportPolling();
                }
            } else {
                // استخدام البيانات المحلية بدلاً من إغلاق الشات
                console.warn("تنبيه الخادم: يتم استعراض البيانات محلياً.");
            }
        } catch (error) {
            console.warn("وضع العمل بدون اتصال بالشبكة مفعل محلياً.");
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

    function renderMessages(messages) {
        messages = messages || [];
        if (!chatBox) return;

        if (messages.length === supportLastMsgCount && !isSupportClosed) return;
        supportLastMsgCount = messages.length;

        chatBox.innerHTML = ''; 

        if (messages.length === 0) {
            chatBox.innerHTML = `
                <div class="msg-system">
                    👋 <b>مرحباً بك في الدعم الفني المباشر!</b><br>
                    الكود المرجعي: <b>${supportTicketId || ''}</b><br>
                    اكتب استفسارك وسيقوم فريق الدعم بالرد عليك في أقرب وقت.
                </div>`;
        } else {
            messages.forEach(msg => {
                const div = document.createElement('div');
                const isUser = (msg.sender === 'user');
                div.className = `chat-msg ${isUser ? 'msg-user' : 'msg-admin'}`;
                
                const timeStr = formatTime(msg.timestamp);
                div.innerHTML = `
                    <div>${escapeHTML(msg.text)}</div>
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
        return String(str).replace(/[&<>"']/g, function(m) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m];
        });
    }

    window.sendQuickQuery = function(text) {
        if (!msgInput) return;
        msgInput.value = text;
        sendSupportMessage();
    };

    window.startNewTicket = async function() {
        if (chatBox) chatBox.innerHTML = '<div class="msg-system">جاري تفعيل محادثة جديدة... ⏳</div>';
        
        // توليد كود محلي جديد فوراً
        const newLocalId = generateLocalTicketId();
        supportTicketId = newLocalId;
        isSupportClosed = false;
        localMessagesList = [{
            sender: 'admin',
            text: `تم فتح تذكرة محادثة جديدة برقم مرجعي: [ ${newLocalId} ]. تفضل بكتابة سؤالك.`,
            timestamp: new Date().toISOString()
        }];
        
        if (ticketDisplay) ticketDisplay.innerHTML = `تذكرة #${supportTicketId} 📋`;
        enableSupportInput();
        renderMessages(localMessagesList);
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
                        'Content-Type': 'application/json'
                    }
                });
                data = await response.json();
            }

            if (data && data.success) {
                supportTicketId = data.ticket_id;
                localMessagesList = data.messages || localMessagesList;
                if (ticketDisplay) ticketDisplay.innerHTML = `تذكرة #${supportTicketId} 📋`;
                renderMessages(localMessagesList);
                saveSupportDataLocally(supportTicketId, localMessagesList, 'open');
                startSupportPolling();
            }
        } catch (e) {
            console.warn("تم إنشاء التذكرة محلياً وسيتم مزامنتها مع الخادم عند توفره.");
        }
    };

    window.sendSupportMessage = async function() {
        if (!msgInput) return;
        const text = msgInput.value.trim();
        if (!text || isSupportClosed) return;

        if (!supportTicketId) {
            supportTicketId = generateLocalTicketId();
        }

        const newMsgObj = {
            sender: 'user',
            text: text,
            timestamp: new Date().toISOString()
        };

        // إضافة الرسالة في واجهة المستخدم وحفظها فوراً
        localMessagesList.push(newMsgObj);
        renderMessages(localMessagesList);
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
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ ticket_id: supportTicketId, text: text })
                });
                data = await response.json();
            }

            if (data && data.success) {
                fetchTicketData();
            } else if (data?.message && data.message.includes("إنهاء")) {
                isSupportClosed = true;
                fetchTicketData();
            }
        } catch (error) {
            console.warn("تعذر الإرسال الفوري للسيرفر، التذكرة محفوظة محلياً.");
        } finally {
            if (sendBtn) sendBtn.disabled = false;
        }
    };

    function disableSupportInput(reason) {
        if (msgInput) {
            msgInput.disabled = true;
            msgInput.placeholder = reason;
        }
        if (sendBtn) sendBtn.disabled = true;
        if (inputSection) inputSection.style.opacity = '0.5';
        if (supportPollInterval) {
            clearInterval(supportPollInterval);
            supportPollInterval = null;
        }
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
        if (supportPollInterval) clearInterval(supportPollInterval);
        supportPollInterval = setInterval(() => {
            const modal = document.getElementById('support-modal');
            if (!isSupportClosed && modal && modal.style.display === 'flex' && document.visibilityState === 'visible') {
                fetchTicketData();
            }
        }, 10000); // استعلام كل 10 ثوانٍ لحفظ الموارد
    }

    if (msgInput) {
        msgInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter') sendSupportMessage();
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
        }
    });

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        fetchAndRenderData();
    } else {
        document.addEventListener('DOMContentLoaded', fetchAndRenderData);
    }
})();
