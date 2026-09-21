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
            uSearch();
        } else {
            container.innerHTML = `<div class="u-error">❌ فشل الجلب: ${json.message || 'خطأ غير معروف'}</div>`;
        }
    } catch (err) {
        console.error("Fetch error:", err);
        container.innerHTML = `<div class="u-error">❌ تعذر الاتصال بالسيرفر! تأكد من ربط users_bp في سيرفر Flask.</div>`;
    }
}

// دالة مساعدة لتنسيق القيم المفقودة
function fmt(val) {
    if (val === undefined || val === null || val === '') return '<span class="u-null">غير محدد</span>';
    if (typeof val === 'boolean') return val ? '<span class="u-true">نعم (True)</span>' : '<span class="u-false">لا (False)</span>';
    if (typeof val === 'object') return `<pre class="u-json">${JSON.stringify(val, null, 1)}</pre>`;
    return val;
}

// عرض البيانات بأسلوب بطاقات وجداول تفصيلية شاملة
function uRender(usersList) {
    const container = document.getElementById('uResultsContainer');
    if (!container) return;
    container.innerHTML = '';

    if (!usersList || usersList.length === 0) {
        container.innerHTML = '<div class="u-empty">لا يوجد مستخدمين يطابقون كلمة البحث.</div>';
        return;
    }

    // إظهار عدد النتائج
    const countHeader = document.createElement('div');
    countHeader.className = 'u-count-tag';
    countHeader.innerHTML = `📊 إجمالي نتائج البحث: <strong>${usersList.length}</strong> مستخدم`;
    container.appendChild(countHeader);

    usersList.forEach(u => {
        let card = document.createElement('div');
        card.className = 'u-full-card';

        card.innerHTML = `
            <!-- الهيدر الخاص بالمستخدم -->
            <div class="u-card-header">
                <div class="u-user-title">
                    <span class="u-user-name">👤 ${u.first_name || 'مستخدم بدون اسم'}</span>
                    <span class="u-user-id">ID: ${u.tg_id || u.document_id}</span>
                </div>
                <div class="u-joined-date">
                    📅 الانضمام: ${u.joined_at || u.joinDate || 'غير مسجل'}
                </div>
            </div>

            <!-- شبكة البيانات المفصلة -->
            <div class="u-grid">
                <!-- قسم الأرصدة والعملات -->
                <div class="u-box u-box-gold">
                    <h4>💰 الأرصدة والعملات</h4>
                    <ul>
                        <li><span>الرصيد الرئيسي (Balance):</span> <strong>${fmt(u.balance)}</strong></li>
                        <li><span>رصيد ZNX:</span> <strong>${fmt(u.znx_balance)}</strong></li>
                        <li><span>رصيد الدولار (USD):</span> <strong>$${fmt(u.usd_balance)}</strong></li>
                        <li><span>رصيد الإعلانات:</span> <strong>${fmt(u.ad_balance)}</strong></li>
                        <li><span>النقاط المعدنة (Mined):</span> <strong>${fmt(u.mined_points)}</strong></li>
                        <li><span>غير المطالب به (Unclaimed):</span> <strong>${fmt(u.unclaimed)}</strong></li>
                    </ul>
                </div>

                <!-- قسم السرعات والمخازن والطاقة -->
                <div class="u-box u-box-blue">
                    <h4>⚡ السرعات والمخازن والتعدين</h4>
                    <ul>
                        <li><span>معدل التعدين/ساعة:</span> <strong>${fmt(u.hourly_rate)}</strong></li>
                        <li><span>معدل البوست اليومي:</span> <strong>${fmt(u.daily_boost_rate)}</strong></li>
                        <li><span>مستوى المخزن (Storage Level):</span> <strong>${fmt(u.storage_level)}</strong></li>
                        <li><span>المخزن الإضافي:</span> <strong>${fmt(u.extra_storage)}</strong></li>
                        <li><span>السعة القصوى (Max Cap):</span> <strong>${fmt(u.max_cap)}</strong></li>
                        <li><span>الطاقة (Energy):</span> <strong>${fmt(u.energy)}</strong></li>
                    </ul>
                </div>

                <!-- قسم الإحالات والنشاط -->
                <div class="u-box u-box-green">
                    <h4>👥 الإحالات والنشاط اليومي</h4>
                    <ul>
                        <li><span>عدد الأصدقاء المدعوين:</span> <strong>${fmt(u.invited_friends_count)}</strong></li>
                        <li><span>تمت دعوته بواسطة (Ref By):</span> <strong>${fmt(u.referred_by)}</strong></li>
                        <li><span>أرباح إحالة معلقة:</span> <strong>${fmt(u.pending_ref_earnings)}</strong></li>
                        <li><span>إجمالي أرباح الإحالات:</span> <strong>${fmt(u.total_ref_earnings)}</strong></li>
                        <li><span>الستريك اليومي (Streak):</span> <strong>${fmt(u.daily_streak)}</strong></li>
                        <li><span>اليوم الحالي (Daily Day):</span> <strong>${fmt(u.daily_day)}</strong></li>
                        <li><span>الإعلانات المشاهدة:</span> <strong>${fmt(u.ads_watched)}</strong></li>
                    </ul>
                </div>

                <!-- قسم الحساب والمحفظة والأوقات -->
                <div class="u-box u-box-purple">
                    <h4>🌐 الحساب والمحفظة والأوقات</h4>
                    <ul>
                        <li><span>عنوان المحفظة:</span> <strong class="u-wallet">${fmt(u.wallet_address)}</strong></li>
                        <li><span>آخر نشاط (Last Active):</span> <strong>${fmt(u.last_active)}</strong></li>
                        <li><span>آخر مطالبة (Last Claim):</span> <strong>${fmt(u.last_claim_time)}</strong></li>
                        <li><span>البوت نشط؟:</span> <strong>${fmt(u.bot_active)}</strong></li>
                        <li><span>حالة الحظر:</span> <strong>${fmt(u.banned)}</strong></li>
                        <li><span>معرف الجهاز (Device ID):</span> <strong>${fmt(u.device_id)}</strong></li>
                    </ul>
                </div>

                <!-- قسم الرهانات والألعاب -->
                <div class="u-box u-box-orange">
                    <h4>🎲 إحصائيات الرهانات والألعاب</h4>
                    <ul>
                        <li><span>إجمالي الرهانات (Bets):</span> <strong>${fmt(u.total_bets)}</strong></li>
                        <li><span>إجمالي الفوز (Wins):</span> <strong>${fmt(u.total_wins)}</strong></li>
                        <li><span>إجمالي الخسائر (Losses):</span> <strong>${fmt(u.total_losses)}</strong></li>
                        <li><span>التفاعلات (Interactions):</span> <strong>${fmt(u.interactions)}</strong></li>
                    </ul>
                </div>

                <!-- قسم التطويرات والمهام المكتملة -->
                <div class="u-box u-box-gray">
                    <h4>🛠️ الترقية والمهام (Upgrades & Tasks)</h4>
                    <ul>
                        <li><span>عدد الترقايات:</span> <strong>${fmt(u.upgrades_count)}</strong></li>
                        <li><span>قائمة الترقايات (Upgrades):</span> ${fmt(u.upgrades)}</li>
                        <li><span>المهام المكتملة (Completed Tasks):</span> ${fmt(u.completed_tasks)}</li>
                    </ul>
                </div>
            </div>
        `;

        container.appendChild(card);
    });
}

// البحث والفلترة الفورية بكل البيانات
function uSearch() {
    let input = document.getElementById('uSearchInput');
    let term = input ? input.value.trim().toLowerCase() : '';

    if (!term) {
        uRender(uDataList);
        return;
    }

    let filtered = uDataList.filter(u => 
        String(u.tg_id || '').toLowerCase().includes(term) || 
        String(u.document_id || '').toLowerCase().includes(term) || 
        String(u.first_name || '').toLowerCase().includes(term) ||
        String(u.wallet_address || '').toLowerCase().includes(term) ||
        String(u.referred_by || '').toLowerCase().includes(term)
    );

    uRender(filtered);
}

// بدء التشغيل عند تحميل الصفحة
uFetch();
