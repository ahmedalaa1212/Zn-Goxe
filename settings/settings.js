(function initSettingsSystem() {
    
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
            return window.Telegram.WebApp.initData;
        }
        return "";
    }

    function updateStatsFromLocalData() {
        if (window.PlayerData) {
            const totalMiningEl = document.getElementById('stat-total-mining');
            const totalStorageEl = document.getElementById('stat-total-storage');
            
            let totalUpgradesCount = 0;
            if (window.PlayerData.upgrades) {
                for (let i = 1; i <= 9; i++) {
                    totalUpgradesCount += parseInt(window.PlayerData.upgrades[`lvl${i}`] || 0);
                }
            }
            let storageLevelsCount = parseInt(window.PlayerData.storage_level || 0);

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

        if (window.PlayerData) {
            updateStatsFromLocalData();
        } else if (initData) {
            try {
                let response = await fetch('/api/settings/stats', {
                    headers: { 'X-Telegram-Init-Data': initData }
                });
                if (response.ok) {
                    let result = await response.json();
                    if (result.success) {
                        document.getElementById('stat-total-mining').innerText = `${result.farm_levels_count} مستويات`;
                        document.getElementById('stat-total-storage').innerText = `${result.storage_levels_count} مستويات`;
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
        document.getElementById('support-modal').style.display = 'flex';
        fetchTicketData();
    };

    window.closeSupportModal = function() {
        document.getElementById('support-modal').style.display = 'none';
        if(supportPollInterval) clearInterval(supportPollInterval);
    };

    async function fetchTicketData() {
        const initData = getInitData();
        if (!initData) {
            ticketDisplay.innerText = "يرجى فتح التطبيق داخل تليجرام";
            return;
        }

        try {
            const response = await fetch('/api/support/ticket', {
                method: 'GET',
                headers: { 'X-Telegram-Init-Data': initData }
            });
            const data = await response.json();

            if (data.success) {
                supportTicketId = data.ticket_id;
                isSupportClosed = data.status === 'closed';
                
                ticketDisplay.innerText = `رقم التذكرة: #${supportTicketId}`;
                renderMessages(data.messages);
                
                if (isSupportClosed) {
                    disableSupportInput("تم إغلاق هذه التذكرة من قبل الدعم.");
                } else {
                    enableSupportInput();
                    startSupportPolling();
                }
            } else {
                ticketDisplay.innerText = "خطأ: " + (data.message || "فشل الاتصال");
            }
        } catch (error) {
            ticketDisplay.innerText = "فشل الاتصال بالسيرفر";
        }
    }

    function renderMessages(messages) {
        messages = messages || [];
        
        if (messages.length === supportLastMsgCount) return;
        supportLastMsgCount = messages.length;

        if (messages.length === 0) {
            chatBox.innerHTML = '<div class="msg-system">مرحباً بك! ارسل استفسارك وسيقوم فريق الدعم بالرد عليك.</div>';
            return;
        }

        chatBox.innerHTML = ''; 
        messages.forEach(msg => {
            const div = document.createElement('div');
            div.className = `chat-msg ${msg.sender === 'user' ? 'msg-user' : 'msg-admin'}`;
            div.innerText = msg.text;
            chatBox.appendChild(div);
        });

        if (isSupportClosed) {
            const closedDiv = document.createElement('div');
            closedDiv.className = 'msg-system';
            closedDiv.innerText = '🔒 هذه التذكرة مغلقة.';
            chatBox.appendChild(closedDiv);
        }

        chatBox.scrollTop = chatBox.scrollHeight;
    }

    window.sendSupportMessage = async function() {
        const text = msgInput.value.trim();
        if (!text || isSupportClosed || !supportTicketId) return;

        const initData = getInitData();
        
        const tempDiv = document.createElement('div');
        tempDiv.className = 'chat-msg msg-user';
        tempDiv.innerText = text;
        tempDiv.style.opacity = '0.5'; 
        chatBox.appendChild(tempDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
        
        msgInput.value = '';
        sendBtn.disabled = true;

        try {
            const response = await fetch('/api/support/message', {
                method: 'POST',
                headers: { 
                    'X-Telegram-Init-Data': initData,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ ticket_id: supportTicketId, text: text })
            });
            const data = await response.json();

            if (data.success) {
                fetchTicketData(); 
            } else {
                tempDiv.remove();
                alert("فشل الإرسال: " + (data.message || "خطأ غير معروف"));
            }
        } catch (error) {
            tempDiv.remove();
            alert("خطأ في الاتصال بالشبكة.");
        } finally {
            sendBtn.disabled = false;
        }
    };

    function disableSupportInput(reason) {
        msgInput.disabled = true;
        sendBtn.disabled = true;
        msgInput.placeholder = reason;
        inputSection.style.opacity = '0.5';
        if(supportPollInterval) clearInterval(supportPollInterval);
    }

    function enableSupportInput() {
        msgInput.disabled = false;
        sendBtn.disabled = false;
        msgInput.placeholder = "اكتب رسالتك هنا...";
        inputSection.style.opacity = '1';
    }

    function startSupportPolling() {
        if(supportPollInterval) clearInterval(supportPollInterval);
        supportPollInterval = setInterval(() => {
            if(!isSupportClosed && document.getElementById('support-modal').style.display === 'flex') {
                fetchTicketData();
            }
        }, 3000);
    }

    msgInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') sendSupportMessage();
    });

    window.copyPlayerId = function() {
        const idText = document.getElementById('player-telegram-id').innerText;
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(idText).then(() => showToast("تم النسخ!")).catch(() => fallbackCopy(idText));
        } else {
            fallbackCopy(idText);
        }
    };

    function fallbackCopy(text) {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        try { document.execCommand('copy'); showToast("تم النسخ!"); } catch (err) {}
        document.body.removeChild(textArea);
    }

    window.showPrivacyModal = function() { document.getElementById('settings-modal').style.display = 'flex'; };
    window.closeSettingsModal = function() { document.getElementById('settings-modal').style.display = 'none'; };
    
    function showToast(text) {
        const toast = document.getElementById('toast-msg');
        toast.innerText = text;
        toast.style.display = 'block';
        setTimeout(() => toast.style.display = 'none', 2000);
    }

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        setTimeout(fetchAndRenderData, 100);
    } else {
        document.addEventListener('DOMContentLoaded', () => setTimeout(fetchAndRenderData, 100));
    }
    setInterval(updateStatsFromLocalData, 1000);

})();
