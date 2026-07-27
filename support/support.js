(function initSupport() {
    let currentTicketId = null;
    let isTicketClosed = false;
    let pollInterval = null;
    let lastMessageCount = 0;

    function getInitData() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            return window.Telegram.WebApp.initData;
        }
        return "";
    }

    const chatBox = document.getElementById('chat-box');
    const msgInput = document.getElementById('msg-input');
    const sendBtn = document.getElementById('send-btn');
    const inputSection = document.getElementById('input-section');

    // 1. تهيئة المحادثة وجلب التذكرة
    async function fetchTicketData() {
        const initData = getInitData();
        if (!initData) {
            alert("يرجى فتح التطبيق من داخل تليجرام");
            return;
        }

        try {
            const response = await fetch('/api/support/ticket', {
                method: 'GET',
                headers: { 'X-Telegram-Init-Data': initData }
            });
            const data = await response.json();

            if (data.success) {
                currentTicketId = data.ticket_id;
                isTicketClosed = data.status === 'closed';
                
                document.getElementById('ticket-id-display').innerText = `رقم التذكرة: ${currentTicketId}`;
                document.getElementById('loading-overlay').style.display = 'none';

                renderMessages(data.messages);
                
                if (isTicketClosed) {
                    disableInput("تم إغلاق هذه التذكرة من قبل الدعم الفني.");
                } else {
                    // Start polling for new messages if open
                    startPolling();
                }
            } else {
                alert("حدث خطأ أثناء فتح المحادثة: " + data.message);
            }
        } catch (error) {
            console.error("Error fetching ticket:", error);
            alert("خطأ في الاتصال بالخادم.");
        }
    }

    // 2. عرض الرسائل في الشات
    function renderMessages(messages) {
        if (!messages || messages.length === 0) {
            chatBox.innerHTML = '<div class="msg-system">ابدأ المحادثة الآن، نحن هنا لمساعدتك.</div>';
            return;
        }

        // Only update if there are new messages
        if (messages.length === lastMessageCount) return;
        lastMessageCount = messages.length;

        chatBox.innerHTML = ''; // Clear current
        messages.forEach(msg => {
            const div = document.createElement('div');
            div.className = `message ${msg.sender === 'user' ? 'msg-user' : 'msg-admin'}`;
            div.innerText = msg.text;
            chatBox.appendChild(div);
        });

        if (isTicketClosed) {
            const closedDiv = document.createElement('div');
            closedDiv.className = 'msg-system';
            closedDiv.innerText = '🔒 تم إنهاء هذه المحادثة.';
            chatBox.appendChild(closedDiv);
        }

        // Auto scroll to bottom
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    // 3. إرسال رسالة
    window.sendMessage = async function() {
        const text = msgInput.value.trim();
        if (!text || isTicketClosed || !currentTicketId) return;

        const initData = getInitData();
        
        // Optimistic UI update
        const tempDiv = document.createElement('div');
        tempDiv.className = 'message msg-user';
        tempDiv.innerText = text;
        tempDiv.style.opacity = '0.5'; // indicate sending
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
                body: JSON.stringify({ ticket_id: currentTicketId, text: text })
            });
            const data = await response.json();

            if (data.success) {
                // Refresh full chat to get exact server state
                fetchTicketData(); 
            } else {
                tempDiv.remove();
                alert("فشل الإرسال: " + data.message);
            }
        } catch (error) {
            tempDiv.remove();
            alert("خطأ في الاتصال.");
        } finally {
            sendBtn.disabled = false;
        }
    }

    // 4. إغلاق حقل الإدخال
    function disableInput(reason) {
        msgInput.disabled = true;
        sendBtn.disabled = true;
        msgInput.placeholder = reason;
        inputSection.style.opacity = '0.5';
        if(pollInterval) clearInterval(pollInterval);
    }

    // 5. تحديث الشات تلقائياً (Polling every 3 seconds)
    function startPolling() {
        if(pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(() => {
            if(!isTicketClosed) fetchTicketData();
        }, 3000);
    }

    // Allow Enter key to send
    msgInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });

    // Start
    document.addEventListener('DOMContentLoaded', fetchTicketData);

})();

