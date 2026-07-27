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
        return user ? String(user.id) : "5102387551"; // Fallback for testing
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

    // ==========================================
    // ⚙️ وظائف الإعدادات العامة
    // ==========================================
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
                totalMiningEl.style.color = "#00cc66"; 
            }
            if (totalStorageEl) {
                totalStorageEl.innerText = `${storageLevelsCount} مستويات`;
                totalStorageEl.style.color = "#0088cc"; 
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
            // جلب احتياطي من السيرفر
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
    // 🎧 وظائف الدعم الفني (الشات العائم)
    // ==========================================
    let supportTicketId = null;
    let isSupportClosed = false;
    let supportPollInterval = null;
    let supportLastMessageCount = 0;

    const chatBox = document.getElementById('support-chat-box');
    const msgInput = document.getElementById('support-msg-input');
    const sendBtn = document.getElementById('support-send-btn');
    const inputSection = document.getElementById('support-input-section');
    const ticketDisplay = document.getElementById('ticket-id-display');

    window.openSupportModal = function() {
        document.getElementById('support-modal').style.display = 'flex';
        fetchTicketData(); // جلب المحادثة أو إنشاء تذكرة جديدة عند الفتح
    };

    window.closeSupportModal = function() {
        document.getElementById('support-modal').style.display = 'none';
        if(supportPollInterval) clearInterval(supportPollInterval);
    };

    async function fetchTicketData() {
        const initData = getInitData();
        if (!initData) return;

        ticketDisplay.innerHTML = `جاري الاتصال... <div class="spinner"></div>`;

        try {
            const response = await fetch('/api/support/ticket', {
                method: 'GET',
                headers: { 'X-Telegram-Init-Data': initData }
            });
            const data = await response.json();

            if (data.success) {
                supportTicketId = data.ticket_id;
                isSupportClosed = data.status === 'closed';
                
                ticketDisplay.innerText = `رقم التذكرة: ${supportTicketId}`;
                renderMessages(data.messages);
                
                if (isSupportClosed) {
                    disableSupportInput("تم إنهاء هذه المحادثة من الدعم الفني.");
                } else {
                    enableSupportInput();
                    startSupportPolling();
                }
            }
        } catch (error) {
            ticketDisplay.innerText = "خطأ في الاتصال بالخادم";
        }
    }

    function renderMessages(messages) {
        if (!messages || messages.length === 0) {
            chatBox.innerHTML = '<div class="msg-system">نحن هنا لمساعدتك، ارسل استفسارك الآن.</div>';
            return;
        }

        if (messages.length === supportLastMessageCount) return; // لا تقم بالتحديث إذا لم تكن هناك رسائل جديدة
        supportLastMessageCount = messages.length;

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
            closedDiv.innerText = '🔒 تم إغلاق هذه التذكرة.';
            chatBox.appendChild(closedDiv);
        }

        chatBox.scrollTop = chatBox.scrollHeight;
    }

    window.sendSupportMessage = async function() {
        const text = msgInput.value.trim();
        if (!text || isSupportClosed || !supportTicketId) return;

        const initData = getInitData();
        
        // عرض الرسالة مؤقتاً لتجربة سريعة
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
                alert("فشل الإرسال: " + data.message);
            }
        } catch (error) {
            tempDiv.remove();
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
        }, 3000); // تحديث كل 3 ثواني أثناء فتح الشاشة
    }

    msgInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') sendSupportMessage();
    });

    // ==========================================
    // دوال النسخ والمودال العام
    // ==========================================
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

    // التهيئة
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        setTimeout(fetchAndRenderData, 100);
    } else {
        document.addEventListener('DOMContentLoaded', () => setTimeout(fetchAndRenderData, 100));
    }
    setInterval(updateStatsFromLocalData, 1000);

})();
