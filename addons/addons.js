// ==================== قسم الإضافات والتحكم في البيانات - Addons Module ====================

// متغيرات حالة قسم التحكم في البيانات
let currentDataTargetMode = 'single'; // 'single' | 'all'
let inspectedUserData = null;
let systemDataLimits = {
    max_upgrade_per_lvl: 50,
    max_storage_level: 20
};

function getAddonsAuthHeaders() {
    const initData = window.Telegram?.WebApp?.initData || "";
    return {
        'Content-Type': 'application/json',
        'X-Telegram-Init-Data': initData,
        'Authorization': `Bearer ${initData}`
    };
}

function escapePromoHTML(str) {
    if (str === null || str === undefined) return '';
    return String(str).replace(/[&<>"'/]/g, function (m) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;', '/': '&#x2F;' }[m];
    });
}

async function loadAddonsSection(btnElement) {
    if (btnElement) {
        document.querySelectorAll('.sidebar button').forEach(b => b.classList.remove('active'));
        btnElement.classList.add('active');
    }

    const contentArea = document.getElementById('contentArea');
    
    try {
        const response = await fetch('addons/addons.html?_t=' + Date.now());
        if (!response.ok) throw new Error("تعذر تحميل ملف addons.html");
        const htmlContent = await response.text();
        contentArea.innerHTML = htmlContent;

        await fetchAndRenderPromoCodes();
    } catch (err) {
        console.error("خطأ تحميل قسم الإضافات:", err);
        contentArea.innerHTML = `<div class="content-card"><p style="color:#ef4444;">❌ حدث خطأ أثناء تحميل واجهة الإضافات.</p></div>`;
    }
}

// ==================== التبديل بين التبويبين (المكافآت / التحكم في البيانات) ====================

async function switchAddonsMainTab(tabName) {
    const promoTab = document.getElementById('addons_tab_promo');
    const dataTab = document.getElementById('addons_tab_datacontrol');
    const btnPromo = document.getElementById('tab_btn_promo');
    const btnData = document.getElementById('tab_btn_datacontrol');

    if (!promoTab || !dataTab) return;

    if (tabName === 'datacontrol') {
        promoTab.style.display = 'none';
        dataTab.style.display = 'block';

        if (btnData) {
            btnData.style.background = 'linear-gradient(135deg, #f59e0b, #d97706)';
            btnData.style.color = '#000';
            btnData.style.borderColor = '#f59e0b';
        }
        if (btnPromo) {
            btnPromo.style.background = '#1e293b';
            btnPromo.style.color = '#cbd5e1';
            btnPromo.style.borderColor = '#334155';
        }

        await fetchAndRenderAdminLogs();
    } else {
        promoTab.style.display = 'block';
        dataTab.style.display = 'none';

        if (btnPromo) {
            btnPromo.style.background = 'linear-gradient(135deg, #f59e0b, #d97706)';
            btnPromo.style.color = '#000';
            btnPromo.style.borderColor = '#f59e0b';
        }
        if (btnData) {
            btnData.style.background = '#1e293b';
            btnData.style.color = '#cbd5e1';
            btnData.style.borderColor = '#334155';
        }

        await fetchAndRenderPromoCodes();
    }
}

// ==================== دوال قسم أكواد المكافآت (Promo Codes) ====================

async function submitCreatePromoCode() {
    const code = document.getElementById('promo_code_input').value.trim().toUpperCase();
    const coins = document.getElementById('promo_coins_input').value;
    const duration_val = document.getElementById('promo_duration_val').value;
    const duration_type = document.getElementById('promo_duration_type').value;
    const max_uses = document.getElementById('promo_max_uses').value || 0;

    if (!code || !coins || !duration_val) {
        alert("⚠️ يرجى ملء جميع الحقول الأساسية!");
        return;
    }

    if (!/^[A-Z0-9_\-]{2,32}$/.test(code)) {
        alert("⚠️ اسم الكود يجب أن يحتوي على حروف إنجليزية وأرقام فقط (بدون مسافات)!");
        return;
    }

    try {
        const res = await fetch('/api/admin/promo/create', {
            method: 'POST',
            headers: getAddonsAuthHeaders(),
            body: JSON.stringify({ code, coins, duration_val, duration_type, max_uses })
        });
        const data = await res.json();
        alert(data.message || data.error);
        if (data.success) {
            document.getElementById('promo_code_input').value = '';
            document.getElementById('promo_coins_input').value = '';
            document.getElementById('promo_duration_val').value = '';
            document.getElementById('promo_max_uses').value = '';
            await fetchAndRenderPromoCodes();
        }
    } catch (err) {
        alert("❌ حدث خطأ أثناء الاتصال بالسيرفر!");
    }
}

async function fetchAndRenderPromoCodes() {
    const tbody = document.getElementById('promo_codes_table_body');
    if (!tbody) return;

    try {
        const res = await fetch('/api/admin/promo/list', {
            method: 'GET',
            headers: getAddonsAuthHeaders()
        });
        const data = await res.json();
        
        if (!data.success || !data.codes || data.codes.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="color:#94a3b8;">لا توجد أكواد مكافآت حتى الآن.</td></tr>`;
            return;
        }

        tbody.innerHTML = data.codes.map(c => {
            const safeCode = escapePromoHTML(c.code);
            let statusBadge = '🟢 نشط';
            if (!c.is_active) {
                statusBadge = '🔴 معطل';
            } else if (c.is_expired) {
                statusBadge = '⏰ منتهي';
            } else if (c.max_uses > 0 && c.used_count >= c.max_uses) {
                statusBadge = '🈵 مكتمل';
            }

            return `
            <tr>
                <td style="font-weight:bold; color:#f59e0b;">${safeCode}</td>
                <td><span class="badge-balance">${Number(c.reward_coins || 0)} 🟡</span></td>
                <td>${Number(c.used_count || 0)} / ${c.max_uses == 0 ? '∞' : Number(c.max_uses)}</td>
                <td>${statusBadge}</td>
                <td>
                    <div class="action-buttons">
                        <button class="btn-action ${c.is_active ? 'btn-deduct' : 'btn-add'}" onclick="togglePromoStatus('${safeCode}', ${!c.is_active})">
                            ${c.is_active ? 'تعطيل' : 'تفعيل'}
                        </button>
                        <button class="btn-action btn-ban" onclick="deletePromoCode('${safeCode}')">حذف</button>
                    </div>
                </td>
            </tr>
            `;
        }).join('');
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="5" style="color:#ef4444;">❌ فشل جلب البيانات</td></tr>`;
    }
}

async function togglePromoStatus(code, targetStatus) {
    try {
        const res = await fetch('/api/admin/promo/toggle', {
            method: 'POST',
            headers: getAddonsAuthHeaders(),
            body: JSON.stringify({ code, is_active: targetStatus })
        });
        const data = await res.json();
        alert(data.message || data.error);
        await fetchAndRenderPromoCodes();
    } catch (err) {
        alert("❌ خطأ في الاتصال!");
    }
}

async function deletePromoCode(code) {
    if (!confirm(`هل أنت متأكد من حذف الكود ${code}؟`)) return;
    try {
        const res = await fetch('/api/admin/promo/delete', {
            method: 'POST',
            headers: getAddonsAuthHeaders(),
            body: JSON.stringify({ code })
        });
        const data = await res.json();
        alert(data.message || data.error);
        await fetchAndRenderPromoCodes();
    } catch (err) {
        alert("❌ خطأ في الاتصال!");
    }
}

// ==================== دوال قسم التحكم الشامل في البيانات (Data Control) ====================

function switchDataTargetMode(mode) {
    currentDataTargetMode = (mode === 'all') ? 'all' : 'single';
    const singleBtn = document.getElementById('target_mode_single_btn');
    const allBtn = document.getElementById('target_mode_all_btn');
    const searchBox = document.getElementById('single_user_search_box');
    const warnBox = document.getElementById('all_users_warning_box');
    const userCard = document.getElementById('inspected_user_card');

    if (currentDataTargetMode === 'all') {
        if (allBtn) {
            allBtn.style.borderColor = '#f59e0b';
            allBtn.style.background = 'rgba(245, 158, 11, 0.2)';
            allBtn.style.color = '#fbbf24';
        }
        if (singleBtn) {
            singleBtn.style.borderColor = '#334155';
            singleBtn.style.background = '#1f2330';
            singleBtn.style.color = '#94a3b8';
        }
        if (searchBox) searchBox.style.display = 'none';
        if (warnBox) warnBox.style.display = 'block';
        if (userCard) userCard.style.display = 'none';
        updateUpgradeLevelHint();
        updateStorageLevelHint();
    } else {
        if (singleBtn) {
            singleBtn.style.borderColor = '#10b981';
            singleBtn.style.background = 'rgba(16, 185, 129, 0.2)';
            singleBtn.style.color = '#10b981';
        }
        if (allBtn) {
            allBtn.style.borderColor = '#334155';
            allBtn.style.background = '#1f2330';
            allBtn.style.color = '#94a3b8';
        }
        if (searchBox) searchBox.style.display = 'flex';
        if (warnBox) warnBox.style.display = 'none';
        if (inspectedUserData && userCard) {
            userCard.style.display = 'block';
        }
        updateUpgradeLevelHint();
        updateStorageLevelHint();
    }
}

async function inspectUserById(silent = false) {
    const idInput = document.getElementById('dc_target_telegram_id');
    if (!idInput) return;
    const telegramId = idInput.value.trim();

    if (!telegramId) {
        if (!silent) alert("⚠️ يرجى كتابة الـ ID الخاص باللاعب أولاً!");
        return;
    }

    try {
        const res = await fetch(`/api/admin/data/user-info?telegram_id=${encodeURIComponent(telegramId)}&_t=${Date.now()}`, {
            method: 'GET',
            headers: getAddonsAuthHeaders()
        });
        const data = await res.json();

        if (!data.success || !data.user) {
            inspectedUserData = null;
            const card = document.getElementById('inspected_user_card');
            if (card) card.style.display = 'none';
            if (!silent) alert(data.message || "❌ لم يتم العثور على هذا اللاعب في قاعدة البيانات!");
            return;
        }

        inspectedUserData = data.user;
        if (data.limits) {
            systemDataLimits = Object.assign(systemDataLimits, data.limits);
        }

        renderInspectedUserCard(inspectedUserData);
        updateUpgradeLevelHint();
        updateStorageLevelHint();
    } catch (err) {
        console.error("Error inspecting user:", err);
        if (!silent) alert("❌ حدث خطأ أثناء جلب بيانات اللاعب!");
    }
}

function renderInspectedUserCard(u) {
    const card = document.getElementById('inspected_user_card');
    if (!card || !u) return;

    card.style.display = (currentDataTargetMode === 'single') ? 'block' : 'none';

    const nameEl = document.getElementById('iu_name');
    const userEl = document.getElementById('iu_username');
    const statusBadge = document.getElementById('iu_status_badge');

    if (nameEl) nameEl.innerText = `${u.first_name || u.name || 'لاعب'} (#${u.tg_id})`;
    if (userEl) userEl.innerText = u.username ? `@${u.username}` : '';

    if (statusBadge) {
        if (u.is_banned) {
            statusBadge.innerText = '🚫 محظور';
            statusBadge.style.background = '#7f1d1d';
            statusBadge.style.color = '#fca5a5';
        } else {
            statusBadge.innerText = '🟢 نشط';
            statusBadge.style.background = '#065f46';
            statusBadge.style.color = '#6ee7b7';
        }
    }

    const fmt = (v) => Number(v || 0).toLocaleString('en-US', { maximumFractionDigits: 4 });

    const balEl = document.getElementById('iu_balance');
    const znxEl = document.getElementById('iu_znx');
    const usdEl = document.getElementById('iu_usd');
    const minedEl = document.getElementById('iu_mined');
    const storageEl = document.getElementById('iu_storage');
    const rateRefsEl = document.getElementById('iu_rate_refs');
    const vipEl = document.getElementById('iu_vip_info');
    const gridEl = document.getElementById('iu_upgrades_grid');

    if (balEl) balEl.innerText = `${fmt(u.balance)} ZN`;
    if (znxEl) znxEl.innerText = `${fmt(u.znx_balance)} ZNX`;
    if (usdEl) usdEl.innerText = `$${fmt(u.usd_balance)}`;
    if (minedEl) minedEl.innerText = `${fmt(u.mined_points)}`;

    const maxSt = systemDataLimits.max_storage_level || 20;
    if (storageEl) {
        storageEl.innerText = `مستوى ${u.storage_level || 1} / ${maxSt} (سعة: ${fmt(u.max_cap)})`;
    }

    if (rateRefsEl) {
        rateRefsEl.innerText = `⚡ ${fmt(u.mining_rate)}/س | 👥 ${u.referrals_count || 0}`;
    }

    if (vipEl) {
        if (u.is_vip || u.vip_active) {
            const pkg = u.vip_package || u.vip_status || 'VIP';
            const exp = u.vip_expires_at ? ` (ينتهي: ${u.vip_expires_at})` : '';
            vipEl.innerText = `🟢 مفعل - ${pkg}${exp}`;
            vipEl.style.color = '#4ade80';
        } else {
            vipEl.innerText = '⚪ غير مشترك حالياً';
            vipEl.style.color = '#94a3b8';
        }
    }

    if (gridEl) {
        const upg = u.upgrades || {};
        const maxUpg = systemDataLimits.max_upgrade_per_lvl || 50;
        let html = '';
        for (let i = 1; i <= 9; i++) {
            const key = `lvl${i}`;
            const count = parseInt(upg[key] || 0, 10) || 0;
            const isFull = count >= maxUpg;
            const borderColor = isFull ? '#f59e0b' : (count > 0 ? '#10b981' : '#262b38');
            html += `
                <div onclick="selectUpgradeLevelFromCard('${key}')" style="cursor:pointer; background:#1f2330; border:1px solid ${borderColor}; border-radius:6px; padding:6px; text-align:center;">
                    <div style="color:#94a3b8;">مستوى ${i}</div>
                    <div style="font-weight:bold; color:${isFull ? '#f59e0b' : '#fff'}; margin-top:2px;">
                        ${count} / ${maxUpg} ${isFull ? '🈵' : ''}
                    </div>
                </div>
            `;
        }
        gridEl.innerHTML = html;
    }
}

function selectUpgradeLevelFromCard(lvlKey) {
    const sel = document.getElementById('dc_upgrade_level_select');
    if (sel) {
        sel.value = lvlKey;
        updateUpgradeLevelHint();
    }
}

function updateUpgradeLevelHint() {
    const sel = document.getElementById('dc_upgrade_level_select');
    const hint = document.getElementById('dc_upgrade_limit_hint');
    const addBtn = document.getElementById('btn_upgrade_add');
    if (!sel || !hint) return;

    const lvlKey = sel.value;
    const maxUpg = systemDataLimits.max_upgrade_per_lvl || 50;

    if (currentDataTargetMode === 'single' && inspectedUserData) {
        const currentVal = parseInt((inspectedUserData.upgrades || {})[lvlKey] || 0, 10) || 0;
        const isMax = currentVal >= maxUpg;
        hint.innerText = `يمتلك اللاعب: ${currentVal} / ${maxUpg} ${isMax ? '(الحد الأقصى 🈵)' : ''}`;
        hint.style.color = isMax ? '#f87171' : '#38bdf8';
        if (addBtn) {
            addBtn.disabled = isMax;
            addBtn.style.opacity = isMax ? '0.5' : '1';
        }
    } else {
        hint.innerText = `الحد الأقصى للمستوى: ${maxUpg}`;
        hint.style.color = '#38bdf8';
        if (addBtn) {
            addBtn.disabled = false;
            addBtn.style.opacity = '1';
        }
    }
}

function updateStorageLevelHint() {
    const hint = document.getElementById('dc_storage_limit_hint');
    const addBtn = document.getElementById('btn_storage_add');
    if (!hint) return;

    const maxSt = systemDataLimits.max_storage_level || 20;

    if (currentDataTargetMode === 'single' && inspectedUserData) {
        const currentSt = parseInt(inspectedUserData.storage_level || 1, 10) || 1;
        const isMax = currentSt >= maxSt;
        hint.innerText = `مخزن اللاعب: ${currentSt} / ${maxSt} ${isMax ? '(الحد الأقصى 🈵)' : ''}`;
        hint.style.color = isMax ? '#f87171' : '#fbbf24';
        if (addBtn) {
            addBtn.disabled = isMax;
            addBtn.style.opacity = isMax ? '0.5' : '1';
        }
    } else {
        hint.innerText = `الحد الأقصى للمخزن: ${maxSt}`;
        hint.style.color = '#fbbf24';
        if (addBtn) {
            addBtn.disabled = false;
            addBtn.style.opacity = '1';
        }
    }
}

// ==================== تنفيذ عمليات الإضافة / الخصم / الترقيات / VIP ====================

async function executeAdminDataAction(category, action) {
    let telegramId = '';
    if (currentDataTargetMode === 'single') {
        const idEl = document.getElementById('dc_target_telegram_id');
        telegramId = idEl ? idEl.value.trim() : '';
        if (!telegramId) {
            alert("⚠️ يرجى إدخال ID اللاعب المستهدف أولاً في القسم رقم 1!");
            return;
        }
    }

    const payload = {
        target_type: currentDataTargetMode,
        telegram_id: telegramId,
        category: category,
        action: action
    };

    if (category === 'balance') {
        const field = document.getElementById('dc_balance_field').value;
        const amount = parseFloat(document.getElementById('dc_balance_amount').value);
        if (isNaN(amount) || amount <= 0) {
            alert("⚠️ يرجى إدخال كمية صحيحة أكبر من صفر!");
            return;
        }
        payload.field = field;
        payload.amount = amount;
    } else if (category === 'upgrade') {
        const levelKey = document.getElementById('dc_upgrade_level_select').value;
        const count = parseInt(document.getElementById('dc_upgrade_count').value, 10);
        if (isNaN(count) || count <= 0) {
            alert("⚠️ يرجى إدخال عدد ترقيات صحيح (1 أو أكثر)!");
            return;
        }
        payload.level_key = levelKey;
        payload.amount = count;
    } else if (category === 'storage') {
        const count = parseInt(document.getElementById('dc_storage_count').value, 10);
        if (isNaN(count) || count <= 0) {
            alert("⚠️ يرجى إدخال عدد مستويات مخزن صحيح (1 أو أكثر)!");
            return;
        }
        payload.amount = count;
    } else if (category === 'vip') {
        const pkg = document.getElementById('dc_vip_package').value;
        const durVal = parseFloat(document.getElementById('dc_vip_duration_val').value || 30);
        const durType = document.getElementById('dc_vip_duration_type').value;
        payload.vip_package = pkg;
        payload.duration_val = durVal;
        payload.duration_type = durType;
    }

    if (currentDataTargetMode === 'all') {
        const confirmAll = confirm("⚠️ تنبيه هام: أنت على وشك تطبيق هذا التعديل على (جميع المستخدمين) في البوت دفعة واحدة!\nهل أنت متأكد من المتابعة؟");
        if (!confirmAll) return;
    }

    try {
        const res = await fetch('/api/admin/data/execute', {
            method: 'POST',
            headers: getAddonsAuthHeaders(),
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        alert(data.message || data.error || "تمت العملية");

        if (data.success) {
            if (currentDataTargetMode === 'single' && telegramId) {
                await inspectUserById(true);
            }
            await fetchAndRenderAdminLogs();
        }
    } catch (err) {
        console.error("Execute admin action error:", err);
        alert("❌ حدث خطأ أثناء الاتصال بالسيرفر!");
    }
}

// ==================== الإرجاع الذكي (Undo) وإدارة السجلات ====================

async function undoLastAdminActions(specificLogId = null) {
    let count = 1;
    if (!specificLogId) {
        const countInput = document.getElementById('dc_undo_count_input');
        count = parseInt(countInput ? countInput.value : 1, 10);
        if (isNaN(count) || count <= 0) {
            alert("⚠️ يرجى تحديد عدد العمليات المراد إرجاعها (1 أو أكثر)!");
            return;
        }
        if (!confirm(`⏪ هل أنت متأكد من إرجاع آخر (${count}) عملية وإعادة بيانات الحسابات كما كانت قبلها تماماً؟`)) {
            return;
        }
    } else {
        if (!confirm(`⏪ هل أنت متأكد من التراجع عن العملية رقم #${specificLogId} وإعادة الحسابات المتأثرة لحالتها السابقة؟`)) {
            return;
        }
    }

    try {
        const res = await fetch('/api/admin/data/undo', {
            method: 'POST',
            headers: getAddonsAuthHeaders(),
            body: JSON.stringify({ count: count, log_id: specificLogId })
        });
        const data = await res.json();
        alert(data.message || data.error);

        if (data.success) {
            const idEl = document.getElementById('dc_target_telegram_id');
            if (currentDataTargetMode === 'single' && idEl && idEl.value.trim()) {
                await inspectUserById(true);
            }
            await fetchAndRenderAdminLogs();
        }
    } catch (err) {
        alert("❌ حدث خطأ أثناء الاتصال بالسيرفر!");
    }
}

async function fetchAndRenderAdminLogs() {
    const tbody = document.getElementById('admin_data_logs_tbody');
    if (!tbody) return;

    try {
        const res = await fetch('/api/admin/data/logs?_t=' + Date.now(), {
            method: 'GET',
            headers: getAddonsAuthHeaders()
        });
        const data = await res.json();

        if (!data.success || !data.logs || data.logs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="color:#94a3b8;">لا توجد سجلات عمليات حالياً.</td></tr>`;
            return;
        }

        tbody.innerHTML = data.logs.map(log => {
            const isUndone = Boolean(log.is_undone);
            const targetBadge = log.target_type === 'all'
                ? `<span style="color:#fbbf24; font-weight:bold;">🌍 الكل (${log.affected_count || 0})</span>`
                : `<span style="color:#38bdf8; font-family:monospace;">👤 ${escapePromoHTML(log.target_id)}</span>`;

            const statusOrUndoBtn = isUndone
                ? `<span style="color:#94a3b8; font-size:12px;">↩️ تم الإرجاع</span>`
                : `<button class="btn-action btn-ban" style="padding:4px 8px; font-size:11px;" onclick="undoLastAdminActions(${Number(log.id)})">⏪ إرجاع</button>`;

            return `
                <tr style="${isUndone ? 'opacity: 0.55;' : ''}">
                    <td style="font-family:monospace; color:#94a3b8;">#${Number(log.id)}</td>
                    <td style="font-weight:bold; color:#f59e0b;">${escapePromoHTML(log.action_title)}</td>
                    <td>${targetBadge}</td>
                    <td style="font-size:12px;">
                        <div>${escapePromoHTML(log.description)}</div>
                        <div style="color:#64748b; font-size:10px;">${escapePromoHTML(log.created_at || '')}</div>
                    </td>
                    <td>${statusOrUndoBtn}</td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="5" style="color:#ef4444;">❌ تعذر جلب سجل العمليات</td></tr>`;
    }
}

async function clearAdminLogsOnly() {
    if (!confirm("🗑️ هل تريد مسح سجل العمليات المعروض فقط؟\n(ملاحظة: مسح السجل لا ينقص ولا يغير أي رصيد لدى المستخدمين)")) {
        return;
    }

    try {
        const res = await fetch('/api/admin/data/clear-logs', {
            method: 'POST',
            headers: getAddonsAuthHeaders()
        });
        const data = await res.json();
        alert(data.message || data.error);
        await fetchAndRenderAdminLogs();
    } catch (err) {
        alert("❌ خطأ في الاتصال بالسيرفر!");
    }
}
