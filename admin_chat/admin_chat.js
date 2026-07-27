(function initAdminChat() {
    let currentTicketId = null;
    let allTickets = [];

    window.fetchAdminTickets = async function() {
        const container = document.getElementById('tickets-container');
        if (!container) return;
        container.innerHTML = '<p style="text-align: center; color: #94a3b8;">جاري جلب المحادثات...</p>';

        try {
            const response = await fetch('/api/admin/chat/tickets', {
                headers: { 'X-Telegram-Init-Data': window.Telegram?.WebApp?.initData || "" }
            });
            const data = await response.json();

            if (data.success) {
                allTickets = data.tickets || [];
                renderTicketsList(allTickets);
            } else {
                container.innerHTML = `<p style="color:#ef4444; text-align:center;">${data.message}</p>`;
            }
        } catch (e) {
            container.innerHTML = '<p style="color:#ef4444; text-align:center;">فشل الاتصال بالسيرفر</p>';
        }
    };

    function renderTicketsList(tickets) {
        const container = document.getElementById('tickets-container');
        if (tickets.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: #94a3b8;">لا توجد أي محادثات حالياً.</p>';
            return;
        }

        let html = '';
        tickets.forEach(t => {
            const info = t.user_info || {};
            const isClosed = t.status === 'closed';
            const statusBadge = isClosed 
                ? '<span style="color:#ef4444; font-size:11px;">[مغلقة]</span>' 
                : '<span style="color:#10b981; font-size:11px;">[مفتوحة]</span>';

            html += `
                <div onclick="openAdminChat('${t.ticket_id}')" style="background: #1f2330; border: 1px solid #2d3345; padding: 12px; border-radius: 10px; margin-bottom: 8px; cursor: pointer;">
                    <div style="display:flex; justify-between; align-items:center;">
                        <strong style="color:#fff;">${info.first_name || 'مستخدم'} (@${info.username || 'بدون'})</strong>
                        ${statusBadge}
                    </div>
                    <div style="font-size: 11px; color:#94a3b8; margin-top:4px;">تذكرة #${t.ticket_id} | عدد الرسائل: ${(t.messages || []).length}</div>
                </div>
            `;
        });
        container.innerHTML = html;
    }

    window.openAdminChat = function(ticketId) {
        currentTicketId = ticketId;
        const ticket = allTickets.find(t => t.ticket_id === ticketId);
        if (!ticket) return;

        document.getElementById('tickets-list-section').style.display = 'none';
        document.getElementById('chat-view-section').style.display = 'block';

        const info = ticket.user_info || {};
        document.getElementById('chat-user-name').innerText = `${info.first_name || 'مستخدم'} (@${info.username || 'بدون'})`;
        document.getElementById('chat-ticket-id').innerText = `رقم التذكرة: #${ticket.ticket_id}`;

        renderChatMessages(ticket.messages || []);
    };

    function renderChatMessages(messages) {
        const box = document.getElementById('admin-chat-box');
        box.innerHTML = '';

        messages.forEach(m => {
            const div = document.createElement('div');
            const isAdmin = m.sender === 'admin';
            div.style.cssText = `
                max-width: 80%;
                padding: 8px 12px;
                border-radius: 8px;
                font-size: 13px;
                align-self: ${isAdmin ? 'flex-end' : 'flex-start'};
                background: ${isAdmin ? '#f59e0b' : '#2d3345'};
                color: ${isAdmin ? '#000' : '#fff'};
            `;
            div.innerText = m.text;
            box.appendChild(div);
        });
        box.scrollTop = box.scrollHeight;
    }

    window.closeChatView = function() {
        document.getElementById('chat-view-section').style.display = 'none';
        document.getElementById('tickets-list-section').style.display = 'block';
        fetchAdminTickets();
    };

    window.sendAdminReply = async function() {
        const input = document.getElementById('admin-reply-input');
        const text = input.value.trim();
        if (!text || !currentTicketId) return;

        input.value = '';

        try {
            const res = await fetch('/api/admin/chat/reply', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': window.Telegram?.WebApp?.initData || ""
                },
                body: JSON.stringify({ ticket_id: currentTicketId, text: text })
            });
            const data = await res.json();
            if (data.success) {
                // إعادة جلب التذاكر وتحديث الرسائل
                const tRes = await fetch('/api/admin/chat/tickets', {
                    headers: { 'X-Telegram-Init-Data': window.Telegram?.WebApp?.initData || "" }
                });
                const tData = await tRes.json();
                if (tData.success) {
                    allTickets = tData.tickets;
                    const updatedTicket = allTickets.find(t => t.ticket_id === currentTicketId);
                    if (updatedTicket) renderChatMessages(updatedTicket.messages || []);
                }
            } else {
                alert("خطأ: " + data.message);
            }
        } catch (e) {
            alert("فشل الإرسال");
        }
    };

    window.closeCurrentTicket = async function() {
        if (!currentTicketId || !confirm("هل أنت تأكد من إغلاق التذكرة؟")) return;

        try {
            const res = await fetch('/api/admin/chat/close', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': window.Telegram?.WebApp?.initData || ""
                },
                body: JSON.stringify({ ticket_id: currentTicketId })
            });
            const data = await res.json();
            if (data.success) {
                closeChatView();
            } else {
                alert("خطأ: " + data.message);
            }
        } catch (e) {
            alert("فشل الإغلاق");
        }
    };

    // تشغيل القائمة تلقائياً عند الفتح
    fetchAdminTickets();
})();
