// =========================================
// ملف عرض كافة بيانات المستخدمين (users/users.js)
// =========================================

let uDataList = [];

// جلب البيانات من السيرفر
async function uFetch() {
    const container = document.getElementById('uResultsContainer');
    if (!container) return;

    container.innerHTML = '<div class="u-loading">⏳ جاري جلب جميع البيانات الحية من الفايربيس...</div>';

    try {
        let res = await fetch('/api/users?t=' + new Date().getTime());
        
        if (!res.ok) {
            throw new Error(`خطأ في السيرفر برقم: ${res.status}`);
        }

        let json = await res.json();

        if (json.success) {
            uDataList = json.users || [];
            
            // ترتيب المستخدمين تنازلياً حسب عدد الإحالات
            uDataList.sort((a, b) => {
                let refA = Number(a.invited_friends_count) || 0;
                let refB = Number(b.invited_friends_count) || 0;
                return refB - refA;
            });

            uSearch();
        } else {
            container.innerHTML = `<div class="u-error">❌ فشل الجلب: ${json.message || 'خطأ غير معروف'}</div>`;
        }
    } catch (err) {
        console.error("Fetch error:", err);
        container.innerHTML = `<div class="u-error">❌ تعذر الاتصال بالسيرفر! تأكد من ربط users_bp في سيرفر Flask.</div>`;
    }
}

// دالة تنسيق القيم واللون الخاص بها
function fmtVal(val) {
    if (val === undefined || val === null || val === '') return '<span class="u-null">غير محدد</span>';
    if (typeof val === 'boolean') return val ? '<span class="u-true">نعم (True)</span>' : '<span class="u-false">لا (False)</span>';
    if (typeof val === 'object') return `<pre class="u-json-val">${JSON.stringify(val, null, 1)}</pre>`;
    return val;
}

// عرض البيانات في جدول واحد شامل لكل مستخدم
function uRender(usersList, isSearch = false) {
    const container = document.getElementById('uResultsContainer');
    if (!container) return;
    container.innerHTML = '';

    if (!usersList || usersList.length === 0) {
        container.innerHTML = '<div class="u-empty">❌ لا يوجد مستخدمين يطابقون ID أو كلمة البحث.</div>';
        return;
    }

    // شريط العنوان العلوي
    const countHeader = document.createElement('div');
    countHeader.className = 'u-count-tag';
    if (isSearch) {
        countHeader.innerHTML = `<span>🔍 نتائج البحث عن المستخدم:</span> <span>${usersList.length} مستخدم</span>`;
    } else {
        countHeader.innerHTML = `<span>🏆 أفضل 5 مستخدمين في عدد الإحالات:</span> <span>${usersList.length} من أصل ${uDataList.length}</span>`;
    }
    container.appendChild(countHeader);

    usersList.forEach((u, index) => {
        let card = document.createElement('div');
        card.className = 'u-single-card';

        let refCount = Number(u.invited_friends_count) || 0;
        let rankBadge = isSearch ? `عدد الإحالات: ${refCount}` : `🏆 المركز #${index + 1} (إحالات: ${refCount})`;

        // قائمة الحقول الشاملة مرتبة كـ (سؤال / جواب)
        const fields = [
            { label: "🆔 ID المستخدم (Telegram ID):", value: u.tg_id || u.document_id },
            { label: "👤 اسم المستخدم (First Name):", value: u.first_name || "مستخدم" },
            { label: "📅 تاريخ الانضمام (Joined Date):", value: u.joined_at || u.joinDate },
            { label: "👥 عدد الإحالات (Invited Friends):", value: u.invited_friends_count },
            { label: "🔗 تم دعوته بواسطة (Referred By):", value: u.referred_by },
            { label: "💰 الرصيد الرئيسي (Balance):", value: u.balance },
            { label: "🪙 رصيد ZNX:", value: u.znx_balance },
            { label: "💵 رصيد الدولار (USD):", value: u.usd_balance ? `$${u.usd_balance}` : null },
            { label: "📢 رصيد الإعلانات (Ad Balance):", value: u.ad_balance },
            { label: "⛏️ النقاط المعدنة (Mined Points):", value: u.mined_points },
            { label: "🎁 الأرباح غير المطالب بها (Unclaimed):", value: u.unclaimed },
            { label: "⚡ معدل التعدين / ساعة (Hourly Rate):", value: u.hourly_rate },
            { label: "🚀 معدل البوست اليومي (Daily Boost):", value: u.daily_boost_rate },
            { label: "📦 مستوى المخزن (Storage Level):", value: u.storage_level },
            { label: "➕ المخزن الإضافي (Extra Storage):", value: u.extra_storage },
            { label: "🔋 السعة القصوى (Max Cap):", value: u.max_cap },
            { label: "⚡ الطاقة الحالية (Energy):", value: u.energy },
            { label: "⌛ أرباح إحالة معلقة:", value: u.pending_ref_earnings },
            { label: "💎 إجمالي أرباح الإحالات:", value: u.total_ref_earnings },
            { label: "🔥 الستريك اليومي (Daily Streak):", value: u.daily_streak },
            { label: "📆 اليوم الحالي (Daily Day):", value: u.daily_day },
            { label: "📺 الإعلانات المشاهدة:", value: u.ads_watched },
            { label: "🌐 عنوان المحفظة (Wallet):", value: u.wallet_address ? `<span class="u-wallet-val">${u.wallet_address}</span>` : null, isRawHTML: true },
            { label: "🕒 آخر نشاط (Last Active):", value: u.last_active },
            { label: "⏱️ آخر مطالبة (Last Claim):", value: u.last_claim_time },
            { label: "🤖 البوت نشط؟ (Bot Active):", value: u.bot_active },
            { label: "🚫 حالة الحظر (Banned):", value: u.banned },
            { label: "📱 معرف الجهاز (Device ID):", value: u.device_id },
            { label: "🎲 إجمالي الرهانات (Total Bets):", value: u.total_bets },
            { label: "🏆 إجمالي الفوز (Total Wins):", value: u.total_wins },
            { label: "❌ إجمالي الخسائر (Total Losses):", value: u.total_losses },
            { label: "💬 عدد التفاعلات (Interactions):", value: u.interactions },
            { label: "🛠️ عدد الترقايات (Upgrades Count):", value: u.upgrades_count },
            { label: "📜 قائمة الترقايات (Upgrades):", value: u.upgrades },
            { label: "✅ المهام المكتملة (Completed Tasks):", value: u.completed_tasks }
        ];

        // بناء صفوف الجدول الموحد
        let rowsHtml = fields.map(f => {
            let valFormatted = f.isRawHTML ? (f.value || fmtVal(f.value)) : fmtVal(f.value);
            return `
                <tr>
                    <td class="u-label">${f.label}</td>
                    <td class="u-value">${valFormatted}</td>
                </tr>
            `;
        }).join('');

        card.innerHTML = `
            <div class="u-card-top">
                <div class="u-top-name">👤 ${u.first_name || 'مستخدم بدون اسم'}</div>
                <div class="u-top-badge">${rankBadge}</div>
            </div>

            <table class="u-data-table">
                <thead>
                    <tr>
                        <th>الخاصية / البيان</th>
                        <th>القيمة المسجلة</th>
                    </tr>
                </thead>
                <tbody>
                    ${rowsHtml}
                </tbody>
            </table>
        `;

        container.appendChild(card);
    });
}

// دالة البحث بالـ ID وعرض المستخدم المحدد فقط أو التكفّل بالأفضل 5
function uSearch() {
    let input = document.getElementById('uSearchInput');
    let term = input ? input.value.trim().toLowerCase() : '';

    if (!term) {
        // حالة عدم وجود كلمة بحث: إظهار أفضل 5 في الإحالات فقط
        let top5 = uDataList.slice(0, 5);
        uRender(top5, false);
        return;
    }

    // حالة وجود بحث: مطابقة الـ ID أو اسم المستخدم
    let filtered = uDataList.filter(u => 
        String(u.tg_id || '').toLowerCase().includes(term) || 
        String(u.document_id || '').toLowerCase().includes(term) || 
        String(u.first_name || '').toLowerCase().includes(term) ||
        String(u.wallet_address || '').toLowerCase().includes(term)
    );

    uRender(filtered, true);
}

// تشغيل جلب البيانات عند التحميل
uFetch();
