// settings/settings.js
(function initSettingsSystem() {
    
    function getStoredBalance() {
        if (window.userState && window.userState.balance !== undefined) {
            return parseFloat(window.userState.balance);
        }
        if (window.GameState && window.GameState.balance !== undefined) {
            return parseFloat(window.GameState.balance);
        }
        const bal = localStorage.getItem('zn_balance') || localStorage.getItem('user_balance');
        return bal !== null ? parseFloat(bal) : 0;
    }

    function syncTopBalance() {
        const stored = getStoredBalance();
        const topBalEl = document.getElementById('top-balance-settings');
        if (topBalEl) {
            topBalEl.innerText = `ZN: ${Math.floor(stored).toLocaleString('en-US')}`;
        }
    }

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
        syncTopBalance();

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
                if (data.balance !== undefined && window.userState) {
                    window.userState.balance = data.balance;
                }
                const miningEl = document.getElementById('stat-total-mining');
                const storageEl = document.getElementById('stat-total-storage');
                if (miningEl) miningEl.innerText = `${data.farm_levels_count || 0} مستويات`;
                if (storageEl) storageEl.innerText = `${data.storage_levels_count || 0} مستويات`;
                syncTopBalance();
            }
        } catch (error) {
            console.warn("Settings stats info:", error);
        }
    }

    // ==========================================
    // 🎧 وظائف الشات والدعم الفني (المحسّنة بالكامل)
    // ==========================================
    let supportTicketId = null;
    let isSupportClosed = false;
    let supportPollInterval = null;
    let supportLastMsgCount = -1;
    let isFetchingTicket = false;

    const chatBox = document.getElementById('support-chat-box');
    const msgInput = document.getElementById('support-msg-input');
    const sendBtn = document.getElementById('support-send-btn');
    const inputSection = document.getElementById('support-input-section');
    const ticketDisplay = document.getElementById('ticket-id-display');

    window.openSupportModal = function() {
        const modal = document.getElementById('support-modal');
        if (modal) modal.style.display = 'flex';
        
        if (chatBox) chatBox.innerHTML = '<div class="msg-system">جاري جلب المحادثة...</div>';
        supportLastMsgCount = -1;
        fetchTicketData();
    };

    window.closeSupportModal = function() {
        const modal = document.getElementById('support-modal');
        if (modal) modal.style.display = 'none';
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
                supportTicketId = data.ticket_id;
                isSupportClosed = (data.status === 'closed');
                
                if (ticketDisplay) ticketDisplay.innerText = `رقم التذكرة: #${supportTicketId}`;
                renderMessages(data.messages);
                
                if (isSupportClosed) {
                    disableSupportInput("تم إنهاء هذه المحادثة. يمكنك بدء محادثة جديدة.");
                } else {
                    enableSupportInput();
                    startSupportPolling();
                }
            } else {
                showChatError(data?.message || "فشل جلب التذكرة من السيرفر.");
            }
        } catch (error) {
            showChatError("حدث خطأ في الاتصال بالشبكة.");
        } finally {
            isFetchingTicket = false;
        }
    };

    function showChatError(errMsg) {
        if (ticketDisplay) ticketDisplay.innerText = "تنبيه: " + errMsg;
        if (chatBox) {
            chatBox.innerHTML = `
                <div class="msg-system" style="color: #ff5252; padding: 15px; text-align: center;">
                    ⚠️ ${errMsg}<br><br>
                    <button onclick="fetchTicketData()" style="padding: 8px 16px; background: #ff9800; border: none; border-radius: 8px; color: #fff; font-weight: bold; cursor: pointer;">
                        إعادة المحاولة 🔄
                    </button>
                </div>`;
        }
    }

    function renderMessages(messages) {
        messages = messages || [];
        if (!chatBox) return;

        if (messages.length === supportLastMsgCount && !isSupportClosed) return;
        supportLastMsgCount = messages.length;

        chatBox.innerHTML = ''; 

        if (messages.length === 0) {
            chatBox.innerHTML = '<div class="msg-system">مرحباً بك! اكتب استفسارك وسيرد عليك فريق الدعم.</div>';
        } else {
            messages.forEach(msg => {
                const div = document.createElement('div');
                div.className = `chat-msg ${msg.sender === 'user' ? 'msg-user' : 'msg-admin'}`;
                div.innerText = msg.text;
                chatBox.appendChild(div);
            });
        }

        // إذا كانت التذكرة مغلقة: إظهار الرسالة والزر التفاعلي
        if (isSupportClosed) {
            const closedBox = document.createElement('div');
            closedBox.className = 'msg-system';
            closedBox.style.cssText = 'background: rgba(255, 82, 82, 0.15); border: 1px solid #ff5252; color: #ff5252; margin-top: 15px; padding: 12px; border-radius: 10px; text-align: center;';
            closedBox.innerHTML = `
                🔒 تم إنهاء هذه المحادثة من قبل الدعم الفني.<br>يرجى بدء محادثة جديدة لإرسال استفسار جديد.<br><br>
                <button onclick="startNewTicket()" style="padding: 10px 20px; background: #2196F3; border: none; border-radius: 8px; color: #fff; font-weight: bold; cursor: pointer; font-size: 14px;">
                    ➕ بدء محادثة جديدة
                </button>
            `;
            chatBox.appendChild(closedBox);
            disableSupportInput("تم إنهاء المحادثة. انقر فوق 'بدء محادثة جديدة'");
        }

        chatBox.scrollTop = chatBox.scrollHeight;
    }

    window.startNewTicket = async function() {
        if (chatBox) chatBox.innerHTML = '<div class="msg-system">جاري إنشاء محادثة جديدة...</div>';
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
                isSupportClosed = false;
                if (ticketDisplay) ticketDisplay.innerText = `رقم التذكرة: #${supportTicketId}`;
                enableSupportInput();
                renderMessages([]);
                startSupportPolling();
            } else {
                alert("فشل إنشاء تذكرة جديدة: " + (data?.message || "خطأ غير معروف"));
                fetchTicketData();
            }
        } catch (e) {
            alert("خطأ في الاتصال بالسيرفر.");
            fetchTicketData();
        }
    };

    window.sendSupportMessage = async function() {
        if (!msgInput) return;
        const text = msgInput.value.trim();
        if (!text || isSupportClosed || !supportTicketId) return;

        const tempDiv = document.createElement('div');
        tempDiv.className = 'chat-msg msg-user';
        tempDiv.innerText = text;
        tempDiv.style.opacity = '0.5'; 
        
        if (chatBox) {
            chatBox.appendChild(tempDiv);
            chatBox.scrollTop = chatBox.scrollHeight;
        }
        
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
            } else {
                tempDiv.remove();
                alert("فشل الإرسال: " + (data?.message || "حدث خطأ"));
                if (data?.message && data.message.includes("إنهاء")) {
                    isSupportClosed = true;
                    fetchTicketData();
                }
            }
        } catch (error) {
            tempDiv.remove();
            alert("خطأ في الاتصال بالشبكة.");
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
            msgInput.placeholder = "اكتب رسالتك هنا...";
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
        }, 15000);
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
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(idText).then(() => showToast("تم نسخ الـ ID بنجاح!")).catch(() => fallbackCopy(idText));
        } else {
            fallbackCopy(idText);
        }
    };

    function fallbackCopy(text) {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        try { document.execCommand('copy'); showToast("تم نسخ الـ ID بنجاح!"); } catch (err) {}
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
        setTimeout(() => toast.style.display = 'none', 2000);
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
