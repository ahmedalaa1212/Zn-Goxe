// ==================== قسم الإضافات - أكواد المكافآت ====================

async function loadAddonsSection(btnElement) {
    if (btnElement) {
        document.querySelectorAll('.sidebar button').forEach(b => b.classList.remove('active'));
        btnElement.classList.add('active');
    }

    const contentArea = document.getElementById('contentArea');
    contentArea.innerHTML = `
        <div class="content-card animate-fade-in">
            <h3 style="color: #f59e0b; margin-bottom: 12px;">🎁 إنشاء كود مكافأة جديد (Promo Code)</h3>
            
            <div class="search-box-container">
                <input type="text" id="promo_code_input" class="search-input" placeholder="اسم الكود (مثال: BONUS2026)">
                <input type="number" id="promo_coins_input" class="search-input" placeholder="عدد العملات المكافأة لكل شخص">
                
                <div style="display: flex; gap: 8px;">
                    <input type="number" id="promo_duration_val" class="search-input" placeholder="المدة (مثال: 5)" style="flex: 2;">
                    <select id="promo_duration_type" class="search-input" style="flex: 1; background-color: #1f2330;">
                        <option value="minutes">دقائق</option>
                        <option value="hours" selected>ساعات</option>
                        <option value="days">أيام</option>
                    </select>
                </div>

                <input type="number" id="promo_max_uses" class="search-input" placeholder="أقصى عدد مستخدمين (0 تعني غير محدود)">
                
                <button class="btn-refresh" onclick="submitCreatePromoCode()">✨ إنشاء الكود الآن</button>
            </div>
        </div>

        <div class="content-card animate-fade-in">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <h3 style="color: #f59e0b;">📋 الأكواد النشطة والسابقة</h3>
                <button class="btn-action btn-add" onclick="fetchAndRenderPromoCodes()">تحديث 🔄</button>
            </div>
            <div class="table-responsive">
                <table class="users-table">
                    <thead>
                        <tr>
                            <th>الكود</th>
                            <th>العملات</th>
                            <th>الاستخدامات</th>
                            <th>الحالة</th>
                            <th>إجراءات</th>
                        </tr>
                    </thead>
                    <tbody id="promo_codes_table_body">
                        <tr><td colspan="5">جاري التحميل...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    `;

    await fetchAndRenderPromoCodes();
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
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, coins, duration_val, duration_type, max_uses })
        });
        const data = await res.json();
        alert(data.message);
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
        const res = await fetch('/api/admin/promo/list');
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
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, is_active: targetStatus })
        });
        const data = await res.json();
        alert(data.message);
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
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        const data = await res.json();
        alert(data.message);
        await fetchAndRenderPromoCodes();
    } catch (err) {
        alert("❌ خطأ في الاتصال!");
    }
}
