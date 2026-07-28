// settings/settings.js
(function initSettingsSystem() {
    
    // --- أدوات المزامنة الموحدة مع جميع الشاشات ---
    function getStoredBalance() {
        if (window.GameState && window.GameState.balance !== undefined && window.GameState.balance !== null) {
            return parseFloat(window.GameState.balance);
        }
        const bal = localStorage.getItem('zn_balance') || localStorage.getItem('user_balance');
        return bal !== null ? parseFloat(bal) : 0;
    }

    function setStoredBalance(newBalance) {
        if (newBalance !== undefined && newBalance !== null) {
            const numVal = parseFloat(newBalance);
            if (typeof window.setBalance === 'function') {
                window.setBalance(numVal);
            } else {
                if (window.GameState) window.GameState.balance = numVal;
                localStorage.setItem('zn_balance', numVal.toString());
                localStorage.setItem('user_balance', numVal.toString());
            }
        }
    }

    function syncTopBalance() {
        const stored = getStoredBalance();
        const topBalEl = document.getElementById('top-balance-settings');
        if (topBalEl) {
            topBalEl.innerText = `ZN: ${Math.floor(stored).toLocaleString()}`;
        }
        if (typeof window.updateGlobalUI === 'function') {
            window.updateGlobalUI();
        }
    }

    function getTgUser() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            if (window.Telegram.WebApp.initDataUnsafe && window.Telegram.WebApp.initDataUnsafe.user) {
                return window.Telegram.WebApp.initDataUnsafe.user;
            }
        }
        return null;
    }

    function getTgId() {
        const user = getTgUser();
        return user ? String(user.id) : "5102387551"; 
    }

    function getPlayerName() {
        const user = getTgUser();
        if (user) {
            return user.first_name + (user.last_name ? " " + user.last_name : "");
        }
        return "اللاعب المحترف";
    }

    function getInitData() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            return window.Telegram.WebApp.initData || "";
        }
        return "";
    }

    function updateStatsFromLocalData() {
        syncTopBalance();

        if (window.PlayerData || window.GameState) {
            const data = window.PlayerData || window.GameState;
            const totalMiningEl = document.getElementById('stat-total-mining');
            const totalStorageEl = document.getElementById('stat-total-storage');
            
            let totalUpgradesCount = 0;
            if (data.upgrades) {
                for (let i = 1; i <= 9; i++) {
                    totalUpgradesCount += parseInt(data.upgrades[`lvl${i}`] || 0);
                }
            }
            let storageLevelsCount = parseInt(data.storage_level || 0);

            if (totalMiningEl) {
                totalMiningEl.innerText = `${totalUpgradesCount} مستويات`;
            }
            if (totalStorageEl) {
                totalStorageEl.innerText = `${storageLevelsCount} مستويات`;
            }
        }
    }

    async function fetchAndRenderData() {
        const telegramId = getTgId();
        const initData = getInitData();
        
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

        if (initData) {
            try {
                let response = await fetch('/api/settings/stats', {
                    headers: { 
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${initData}`
                    }
                });
                if (response.ok) {
                    let result = await response.json();
                    if (result.success) {
                        if (result.balance !== undefined) {
                            setStoredBalance(result.balance);
                            syncTopBalance();
                        }
                        const miningEl = document.getElementById('stat-total-mining');
                        const storageEl = document.getElementById('stat-total-storage');
                        if (miningEl) miningEl.innerText = `${result.farm_levels_count} مستويات`;
                        if (storageEl) storageEl.innerText = `${result.storage_levels_count} مستويات`;
                    }
                }
            } catch (error) {}
        }
    }

    // ==========================================
    // 🎧 وظائف الشات والدعم الفني
    // ==========================================
    let supportTicketId = null;
    let isSupportClosed = false;
    let supportPollInterval = null;
    let supportLastMsgCount = -1;

    const chatBox = document.getElementById('support-chat-box');
    const msgInput = document.getElementById('support-msg-input');
    const sendBtn = document.getElementById('support-send-btn');
    const inputSection = document.getElementById('support-input-section');
    const ticketDisplay = document.getElementById('ticket-id-display');

    window.openSupportModal = function() {
        const modal = document.getElementById('support-modal');
        if (modal) modal.style.display = 'flex';
        
        if (chatBox) chatBox.innerHTML = '';
        supportLastMsgCount = -1;
        fetchTicketData();
    };

    window.closeSupportModal = function() {
        const modal = document.getElementById('support-modal');
        if (modal) modal.style.display = 'none';
        if (supportPollInterval) clearInterval(supportPollInterval);
    };

    async function fetchTicketData() {
        const initData = getInitData();
        if (!initData) {
            if (ticketDisplay) ticketDisplay.innerText = "يرجى فتح التطبيق داخل تليجرام";
            return;
        }

        try {
            const response = await fetch('/api/support/ticket', {
                method: 'GET',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${initData}`
                }
            });
            const data = await response.json();

            if (data.success) {
                supportTicketId = data.ticket_id;
                isSupportClosed = data.status === 'closed';
                
                if (ticketDisplay) ticketDisplay.innerText = `رقم التذكرة: #${supportTicketId}`;
                renderMessages(data.messages);
                
                if (isSupportClosed) {
                    disableSupportInput("تم إغلاق هذه التذكرة من الدعم الفني.");
                } else {
                    enableSupportInput();
                    startSupportPolling();
                }
            } else {
                if (ticketDisplay) ticketDisplay.innerText = "خطأ: " + (data.message || "فشل الاتصال");
            }
        } catch (error) {
            if (ticketDisplay) ticketDisplay.innerText = "فشل الاتصال بالسيرفر";
        }
    }

    function renderMessages(messages) {
        messages = messages || [];
        if (!chatBox) return;

        if (messages.length === supportLastMsgCount) return;
        supportLastMsgCount = messages.length;

        chatBox.innerHTML = ''; 

        if (messages.length === 0) {
            chatBox.innerHTML = '<div class="msg-system">مرحباً بك! ارسل استفسارك وسيقوم فريق الدعم بالرد عليك.</div>';
        } else {
            messages.forEach(msg => {
                const div = document.createElement('div');
                div.className = `chat-msg ${msg.sender === 'user' ? 'msg-user' : 'msg-admin'}`;
                div.innerText = msg.text;
                chatBox.appendChild(div);
            });
        }

        if (isSupportClosed) {
            const closedDiv = document.createElement('div');
            closedDiv.className = 'msg-system';
            closedDiv.innerText = '🔒 تم إغلاق هذه المحادثة.';
            chatBox.appendChild(closedDiv);
            disableSupportInput("تم إغلاق هذه التذكرة من الدعم الفني.");
        }

        chatBox.scrollTop = chatBox.scrollHeight;
    }

    window.sendSupportMessage = async function() {
        if (!msgInput) return;
        const text = msgInput.value.trim();
        if (!text || isSupportClosed || !supportTicketId) return;

        const initData = getInitData();
        
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
            const response = await fetch('/api/support/message', {
                method: 'POST',
                headers: { 
                    'Authorization': `Bearer ${initData}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ ticket_id: supportTicketId, text: text })
            });
            const data = await response.json();

            if (data.success) {
                fetchTicketData();
            } else {
                tempDiv.remove();
                alert("فشل الإرسال: " + (data.message || "حدث خطأ"));
                if (data.message && data.message.includes("إغلاق")) {
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
        if (supportPollInterval) clearInterval(supportPollInterval);
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
            if (!isSupportClosed && modal && modal.style.display === 'flex') {
                fetchTicketData();
            }
        }, 3000);
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

    // --- مستمعات التنقل والمزامنة اللحظية ---
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
