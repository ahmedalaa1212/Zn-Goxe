// ==================== قسم الإضافات - Addons Module ====================

function getAddonsAuthHeaders() {
    const initData = window.Telegram?.WebApp?.initData || "";
    return {
        'Content-Type': 'application/json',
        'X-Telegram-Init-Data': initData,
        'Authorization': `Bearer ${initData}`
    };
}

async function loadAddonsSection(btnElement) {
    if (btnElement) {
        document.querySelectorAll('.sidebar button').forEach(b => b.classList.remove('active'));
        btnElement.classList.add('active');
    }

    const contentArea = document.getElementById('contentArea');
    
    try {
        const response = await fetch('addons/addons.html');
        if (!response.ok) throw new Error("تعذر تحميل ملف addons.html");
        const htmlContent = await response.text();
        contentArea.innerHTML = htmlContent;

        await fetchAndRenderPromoCodes();
    } catch (err) {
        console.error("خطأ تحميل قسم الإضافات:", err);
        contentArea.innerHTML = `<div class="content-card"><p style="color:#ef4444;">❌ حدث خطأ أثناء تحميل واجهة الإضافات.</p></div>`;
    }
}

async function submitCreatePromoCode() {
    const code = document.getElementById('promo_code_input').value.trim();
    const coins = document.getElementById('promo_coins_input').value;
    const duration_val = document.getElementById('promo_duration_val').value;
    const duration_type = document.getElementById('promo_duration_type').value;
    const max_uses = document.getElementById('promo_max_uses').value || 0;

    if (!code || !coins || !duration_val) {
        alert("⚠️ يرجى ملء جميع الحقول الأساسية!");
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

        tbody.innerHTML = data.codes.map(c => `
            <tr>
                <td style="font-weight:bold; color:#f59e0b;">${c.code}</td>
                <td><span class="badge-balance">${c.reward_coins} 🟡</span></td>
                <td>${c.used_count} / ${c.max_uses == 0 ? '∞' : c.max_uses}</td>
                <td>${c.is_active ? '🟢 نشط' : '🔴 معطل'}</td>
                <td>
                    <div class="action-buttons">
                        <button class="btn-action ${c.is_active ? 'btn-deduct' : 'btn-add'}" onclick="togglePromoStatus('${c.code}', ${!c.is_active})">
                            ${c.is_active ? 'تعطيل' : 'تفعيل'}
                        </button>
                        <button class="btn-action btn-ban" onclick="deletePromoCode('${c.code}')">حذف</button>
                    </div>
                </td>
            </tr>
        `).join('');
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
    if (!confirm(`هل أنت تأكد من حذف الكود ${code}؟`)) return;
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
