// settings/settings.js
(function initSettingsSystem() {
    
    // --- أدوات المزامنة الموحدة مع باقي الشاشات ---
    function getStoredBalance() {
        const bal = localStorage.getItem('user_balance') || localStorage.getItem('zn_balance');
        return bal !== null ? parseFloat(bal) : null;
    }

    function setStoredBalance(newBalance) {
        if (newBalance !== undefined && newBalance !== null) {
            const strVal = newBalance.toString();
            localStorage.setItem('user_balance', strVal);
            localStorage.setItem('zn_balance', strVal);
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
            return window.Telegram.WebApp.initData;
        }
        return "";
    }

    function updateStatsFromLocalData() {
        // تزامن الرصيد المخزن مع متغير اللاعب العام إذا كان موجواً
        const storedBal = getStoredBalance();
        if (storedBal !== null) {
            if (!window.PlayerData) window.PlayerData = {};
            window.PlayerData.balance = storedBal;
        }

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
        
        // تصفير البيانات عند فتح النافذة
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
                headers: { 'X-Telegram-Init-Data': initData }
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

        // إذا لم يكن هناك تغيير في عدد الرسائل، لا تقم بإعادة الرسم لتجنب الوميض
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
        
        // عرض الرسالة مؤقتاً للمستخدم
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
                    'X-Telegram-Init-Data': initData,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ ticket_id: supportTicketId, text: text })
            });
            const data = await response.json();

            if (data.success) {
                fetchTicketData(); // تحديث لجلب الرسالة بشكلها النهائي
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
        setTimeout(fetchAndRenderData, 100);
    } else {
        document.addEventListener('DOMContentLoaded', () => setTimeout(fetchAndRenderData, 100));
    }
    setInterval(updateStatsFromLocalData, 1000);

})();
