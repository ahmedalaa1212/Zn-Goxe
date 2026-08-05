(function initAdminChat() {
    let currentTicketId = null;
    let allTickets = [];
    let adminPollInterval = null;
    let isFetching = false;
    let lastMsgCount = 0;
    let tickCounter = 0;

    // جلب كل التذاكر (يستدعى فقط أثناء التواجد في الشاشة الرئيسية)
    window.fetchAdminTickets = async function() {
        if (isFetching || currentTicketId) return;
        isFetching = true;

        const container = document.getElementById('tickets-container');
        try {
            const response = await fetch('/api/admin/chat/tickets', {
                headers: { 'X-Telegram-Init-Data': window.Telegram?.WebApp?.initData || "" }
            });
            const data = await response.json();

            if (data.success) {
                allTickets = data.tickets || [];
                updateUnreadBadge(allTickets);
                filterTickets();
            } else if (container) {
                container.innerHTML = `<p style="color:#ef4444; text-align:center;">${data.message}</p>`;
            }
        } catch (e) {
            if (container && allTickets.length === 0) {
                container.innerHTML = '<p style="color:#ef4444; text-align:center;">فشل الاتصال بالسيرفر</p>';
            }
        } finally {
            isFetching = false;
        }
    };

    // جلب تذكرة واحدة فقط بطلب اقتصادي (1 Read) أثناء فتح المحادثة
    async function fetchSingleActiveTicket() {
        if (!currentTicketId || isFetching) return;
        isFetching = true;

        try {
            const response = await fetch(`/api/admin/chat/ticket/${currentTicketId}`, {
                headers: { 'X-Telegram-Init-Data': window.Telegram?.WebApp?.initData || "" }
            });
            const data = await response.json();

            if (data.success && data.ticket) {
                const ticket = data.ticket;
                const msgs = ticket.messages || [];

                if (msgs.length !== lastMsgCount) {
                    renderChatMessages(msgs);
                    if (ticket.has_unread_admin || ticket.last_sender === 'user') {
                        markTicketAsReadSilent(currentTicketId);
                    }
                }
            }
        } catch (e) {
        } finally {
            isFetching = false;
        }
    }

    async function markTicketAsReadSilent(ticketId) {
        try {
            await fetch('/api/admin/chat/mark_read', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': window.Telegram?.WebApp?.initData || ""
                },
                body: JSON.stringify({ ticket_id: ticketId })
            });
        } catch (e) {}
    }

    function updateUnreadBadge(tickets) {
        const badge = document.getElementById('unread-count-badge');
        if (!badge) return;
        
        const unreadCount = tickets.filter(t => t.has_unread_admin || t.last_sender === 'user').length;
        if (unreadCount > 0) {
            badge.innerText = `${unreadCount} غير مقروء`;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    }

    window.filterTickets = function() {
        const searchInput = document.getElementById('ticket-search-input');
        const query = searchInput ? searchInput.value.trim().toLowerCase() : '';

        if (!query) {
            renderTicketsList(allTickets);
            return;
        }

        const filtered = allTickets.filter(t => {
            const tId = (t.ticket_id || '').toLowerCase();
            const uInfo = t.user_info || {};
            const name = (uInfo.first_name || '').toLowerCase();
            const username = (uInfo.username || '').toLowerCase();
            const uId = String(t.user_id || uInfo.id || '');

            return tId.includes(query) || name.includes(query) || username.includes(query) || uId.includes(query);
        });

        renderTicketsList(filtered);
    };

    function renderTicketsList(tickets) {
        const container = document.getElementById('tickets-container');
        if (!container) return;

        if (tickets.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: #94a3b8; padding: 20px 0;">لا توجد أي محادثات مطابقة.</p>';
            return;
        }

        let html = '';
        tickets.forEach(t => {
            const info = t.user_info || {};
            const isClosed = t.status === 'closed';
            const hasUnread = (t.has_unread_admin || t.last_sender === 'user') && !isClosed;

            const statusBadge = isClosed 
                ? '<span style="color:#ef4444; font-size:11px; background:#ef44441a; padding:2px 6px; border-radius:4px;">[مغلقة]</span>' 
                : '<span style="color:#10b981; font-size:11px; background:#10b9811a; padding:2px 6px; border-radius:4px;">[مفتوحة]</span>';

            const unreadBadge = hasUnread 
                ? '<span style="background:#ef4444; color:#fff; font-size:10px; padding:2px 6px; border-radius:10px; margin-right:6px;">🔴 جديدة</span>' 
                : '';

            const cardBorder = hasUnread ? 'border: 1px solid #f59e0b;' : 'border: 1px solid #2d3345;';

            html += `
                <div onclick="openAdminChat('${t.ticket_id}')" style="background: #1f2330; ${cardBorder} padding: 12px; border-radius: 10px; margin-bottom: 8px; cursor: pointer; transition: all 0.2s;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong style="color:#fff; font-size:13px;">
                            ${unreadBadge} ${info.first_name || 'مستخدم'} (@${info.username || 'بدون'})
                        </strong>
                        ${statusBadge}
                    </div>
                    <div style="font-size: 11px; color:#94a3b8; margin-top:6px; display:flex; justify-content:space-between;">
                        <span>كود التذكرة: <b style="color:#f59e0b;">#${t.ticket_id}</b></span>
                        <span>الرسائل: ${(t.messages || []).length}</span>
                    </div>
                </div>
            `;
        });
        container.innerHTML = html;
    }

    window.openAdminChat = async function(ticketId) {
        currentTicketId = ticketId;
        const ticket = allTickets.find(t => t.ticket_id === ticketId);
        
        markTicketAsReadSilent(ticketId);
        if (ticket) ticket.has_unread_admin = false;
        updateUnreadBadge(allTickets);

        document.getElementById('tickets-list-section').style.display = 'none';
        document.getElementById('chat-view-section').style.display = 'block';

        if (ticket) {
            const info = ticket.user_info || {};
            document.getElementById('chat-user-name').innerText = `${info.first_name || 'مستخدم'} (@${info.username || 'بدون'})`;
            document.getElementById('chat-ticket-id').innerText = `رقم التذكرة: #${ticket.ticket_id}`;
            lastMsgCount = 0;
            renderChatMessages(ticket.messages || []);
        }

        fetchSingleActiveTicket();
    };

    function renderChatMessages(messages) {
        const box = document.getElementById('admin-chat-box');
        if (!box) return;

        lastMsgCount = messages.length;
        box.innerHTML = '';

        if (messages.length === 0) {
            box.innerHTML = '<p style="text-align:center; color:#64748b; font-size:12px;">لا توجد رسائل بعد</p>';
            return;
        }

        messages.forEach(m => {
            const div = document.createElement('div');
            const isAdmin = m.sender === 'admin';
            div.style.cssText = `
                max-width: 80%;
                padding: 10px 14px;
                border-radius: 12px;
                font-size: 13px;
                line-height: 1.4;
                align-self: ${isAdmin ? 'flex-end' : 'flex-start'};
                background: ${isAdmin ? '#f59e0b' : '#2d3345'};
                color: ${isAdmin ? '#000' : '#fff'};
                border-bottom-${isAdmin ? 'right' : 'left'}-radius: 2px;
                white-space: pre-wrap;
            `;
            div.innerText = m.text;
            box.appendChild(div);
        });
        box.scrollTop = box.scrollHeight;
    }

    window.closeChatView = function() {
        currentTicketId = null;
        lastMsgCount = 0;
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
                fetchSingleActiveTicket();
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

    // حلقة تحديث ذكية (3 ثوانٍ للمحادثة المفتوحة، و8 ثوانٍ للقائمة العامة)
    function startSmartPolling() {
        if (adminPollInterval) clearInterval(adminPollInterval);
        
        adminPollInterval = setInterval(() => {
            if (document.visibilityState !== 'visible') return;

            tickCounter++;
            if (currentTicketId) {
                // محادثة مفتوحة: جلب التذكرة المحددة فقط كل 3 ثوانٍ
                fetchSingleActiveTicket();
            } else {
                // القائمة الرئيسية: التحديث كل 9 ثوانٍ (كل 3 دورات)
                if (tickCounter % 3 === 0) {
                    fetchAdminTickets();
                }
            }
        }, 3000);
    }

    fetchAdminTickets();
    startSmartPolling();
})();
