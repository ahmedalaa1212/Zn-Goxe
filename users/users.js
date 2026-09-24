// =========================================
// ملف إدارة وعرض بيانات المستخدمين Muted & Filtered
// users/users.js
// =========================================

let uDataList = []; // البيانات الكاملة القادمة من السيرفر

// 1. جلب البيانات المباشرة من السيرفر
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
            uUpdateQuickStats(uDataList);
            uApplyFilters();
        } else {
            container.innerHTML = `<div class="u-error">❌ فشل الجلب: ${json.message || 'خطأ غير معروف'}</div>`;
        }
    } catch (err) {
        console.error("Fetch error:", err);
        container.innerHTML = `<div class="u-error">❌ تعذر الاتصال بالسيرفر! تأكد من تشغيل السيرفر ورابط users_bp.</div>`;
    }
}

// 2. تحديث شريط الإحصائيات التحليلي السريع
function uUpdateQuickStats(list) {
    let total = list.length;
    let active = list.filter(u => u.bot_active === true || u.bot_active === 'true' || String(u.bot_active).toLowerCase() === 'true').length;
    let totalRefs = list.reduce((acc, u) => acc + (Number(u.invited_friends_count) || 0), 0);
    let totalAds = list.reduce((acc, u) => acc + (Number(u.ads_watched) || 0), 0);

    const elTotal = document.getElementById('statTotalUsers');
    const elActive = document.getElementById('statActiveUsers');
    const elRefs = document.getElementById('statTotalRefs');
    const elAds = document.getElementById('statTotalAds');

    if (elTotal) elTotal.innerText = total.toLocaleString('ar-EG');
    if (elActive) elActive.innerText = active.toLocaleString('ar-EG');
    if (elRefs) elRefs.innerText = totalRefs.toLocaleString('ar-EG');
    if (elAds) elAds.innerText = totalAds.toLocaleString('ar-EG');
}

// 3. دالة تحويل وتحليل التاريخ لغرض التصفية الفعالة بكل الصيغ
function parseUserDate(dateStr) {
    if (!dateStr) return null;

    // إذا كانت القيمة بالفعل رقم timestamp (مثل epoch)
    if (typeof dateStr === 'number') {
        let num = dateStr;
        if (num < 10000000000) num *= 1000;
        let d = new Date(num);
        return !isNaN(d.getTime()) ? d : null;
    }

    let str = String(dateStr).trim();
    if (!str) return null;

    // محاولة تحويل مباشر
    let d = new Date(str);
    if (!isNaN(d.getTime())) return d;

    // معالجة المسافات والصيغ الخاصة (ISO with space or Sept)
    let ISOstr = str.replace(' ', 'T').replace('Sept', 'Sep');
    d = new Date(ISOstr);
    if (!isNaN(d.getTime())) return d;

    return null;
}

// 4. تطبيق جميع الفلاتر والفرز بالتفصيل الحقيقي
function uApplyFilters() {
    if (!uDataList || uDataList.length === 0) return;

    let sortBy = document.getElementById('uSortBy')?.value || 'invited_friends_count';
    let limitVal = document.getElementById('uLimit')?.value || '5';
    let statusFilter = document.getElementById('uStatusFilter')?.value || 'all';
    let dateFromStr = document.getElementById('uDateFrom')?.value || '';
    let dateToStr = document.getElementById('uDateTo')?.value || '';
    let searchTerm = document.getElementById('uSearchInput')?.value.trim().toLowerCase() || '';

    let filtered = [...uDataList];

    // أ) تصفية حسب نص البحث (ID, Name, Wallet, Device ID)
    if (searchTerm) {
        filtered = filtered.filter(u => 
            String(u.tg_id || '').toLowerCase().includes(searchTerm) || 
            String(u.document_id || '').toLowerCase().includes(searchTerm) || 
            String(u.first_name || '').toLowerCase().includes(searchTerm) ||
            String(u.wallet_address || '').toLowerCase().includes(searchTerm) ||
            String(u.device_id || '').toLowerCase().includes(searchTerm)
        );
    }

    // ب) تصفية حسب حالة الحساب
    if (statusFilter === 'active') {
        filtered = filtered.filter(u => u.bot_active === true || u.bot_active === 'true' || String(u.bot_active).toLowerCase() === 'true');
    } else if (statusFilter === 'banned') {
        filtered = filtered.filter(u => u.banned === true || u.banned === 'true' || String(u.banned).toLowerCase() === 'true');
    } else if (statusFilter === 'unbanned') {
        filtered = filtered.filter(u => !u.banned || u.banned === 'false' || String(u.banned).toLowerCase() === 'false');
    } else if (statusFilter === 'wallet') {
        filtered = filtered.filter(u => u.wallet_address && String(u.wallet_address).trim() !== '');
    }

    // ج) تجهيز نطاق التاريخ بالمللي ثانية لضمان الدقة
    let hasDateFilter = Boolean(dateFromStr || dateToStr);
    let fromTime = null;
    let toTime = null;

    if (dateFromStr) {
        let [y, m, d] = dateFromStr.split('-').map(Number);
        fromTime = new Date(y, m - 1, d, 0, 0, 0, 0).getTime();
    }
    if (dateToStr) {
        let [y, m, d] = dateToStr.split('-').map(Number);
        toTime = new Date(y, m - 1, d, 23, 59, 59, 999).getTime();
    }

    // د) حساب إحالات كل مستخدم المقبولة ضمن نطاق التاريخ المحدد
    filtered.forEach(u => {
        if (Array.isArray(u.referrals_list) && u.referrals_list.length > 0) {
            let refsInPeriod = u.referrals_list.filter(ref => {
                if (!hasDateFilter) return true;
                let refDate = parseUserDate(ref.joined_at);
                if (!refDate) return false;
                let t = refDate.getTime();
                if (fromTime !== null && t < fromTime) return false;
                if (toTime !== null && t > toTime) return false;
                return true;
            });
            u._period_refs = refsInPeriod.length;
        } else {
            // إذا لم تكن هناك قائمة إحالات مفصلة
            u._period_refs = hasDateFilter ? 0 : (Number(u.invited_friends_count) || 0);
        }
    });

    // هـ) إذا تم تحديد تاريخ ومعيار العرض ليس الإحالات -> يتم فلترة تاريخ انضمام الحساب نفسه
    if (hasDateFilter && sortBy !== 'invited_friends_count') {
        filtered = filtered.filter(u => {
            let uDate = parseUserDate(u.joined_at || u.joinDate || u.created_at || u.last_active_at);
            if (!uDate) return false;
            let t = uDate.getTime();
            if (fromTime !== null && t < fromTime) return false;
            if (toTime !== null && t > toTime) return false;
            return true;
        });
    }

    // و) ترتيب القائمة تنازلياً حسب المعيار المختار
    filtered.sort((a, b) => {
        let valA, valB;

        if (sortBy === 'invited_friends_count' && hasDateFilter) {
            valA = a._period_refs !== undefined ? a._period_refs : 0;
            valB = b._period_refs !== undefined ? b._period_refs : 0;
        } else {
            valA = a[sortBy];
            valB = b[sortBy];
        }

        if (Array.isArray(valA)) valA = valA.length;
        if (Array.isArray(valB)) valB = valB.length;

        let numA = Number(valA) || 0;
        let numB = Number(valB) || 0;

        return numB - numA;
    });

    // ز) تحديد عدد النتائج المعروضة (Top N)
    let displayList = filtered;
    if (limitVal !== 'all') {
        let lim = parseInt(limitVal, 10) || 5;
        displayList = filtered.slice(0, lim);
    }

    // ح) عرض القائمة المفلترة
    uRender(displayList, filtered.length, sortBy, limitVal, searchTerm !== '', hasDateFilter);
}

// 5. الاختصارات السريعة للتاريخ
function uSetQuickDate(preset, btnEl) {
    document.querySelectorAll('.u-btn-preset').forEach(b => b.classList.remove('active'));
    if (btnEl) btnEl.classList.add('active');

    let dateFromInput = document.getElementById('uDateFrom');
    let dateToInput = document.getElementById('uDateTo');

    if (!dateFromInput || !dateToInput) return;

    let now = new Date();

    if (preset === 'all') {
        dateFromInput.value = '';
        dateToInput.value = '';
    } else if (preset === 'today') {
        let yyyy = now.getFullYear();
        let mm = String(now.getMonth() + 1).padStart(2, '0');
        let dd = String(now.getDate()).padStart(2, '0');
        let todayStr = `${yyyy}-${mm}-${dd}`;
        dateFromInput.value = todayStr;
        dateToInput.value = todayStr;
    } else if (preset === '7days') {
        let past = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        dateFromInput.value = past.toISOString().split('T')[0];
        dateToInput.value = now.toISOString().split('T')[0];
    } else if (preset === '30days') {
        let past = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
        dateFromInput.value = past.toISOString().split('T')[0];
        dateToInput.value = now.toISOString().split('T')[0];
    }

    uApplyFilters();
}

// 6. إعادة ضبط جميع الفلاتر
function uResetFilters() {
    let sortSelect = document.getElementById('uSortBy');
    let limitSelect = document.getElementById('uLimit');
    let statusSelect = document.getElementById('uStatusFilter');
    let dateFrom = document.getElementById('uDateFrom');
    let dateTo = document.getElementById('uDateTo');
    let search = document.getElementById('uSearchInput');

    if (sortSelect) sortSelect.value = 'invited_friends_count';
    if (limitSelect) limitSelect.value = '5';
    if (statusSelect) statusSelect.value = 'all';
    if (dateFrom) dateFrom.value = '';
    if (dateTo) dateTo.value = '';
    if (search) search.value = '';

    document.querySelectorAll('.u-btn-preset').forEach(b => b.classList.remove('active'));
    let allBtn = document.querySelector('.u-btn-preset');
    if (allBtn) allBtn.classList.add('active');

    uApplyFilters();
}

// 7. تنسيق القيم والخصائص
function fmtVal(val) {
    if (val === undefined || val === null || val === '') return '<span class="u-null">غير محدد</span>';
    if (typeof val === 'boolean') return val ? '<span class="u-true">نعم (True)</span>' : '<span class="u-false">لا (False)</span>';
    if (typeof val === 'object') return `<pre class="u-json-val">${JSON.stringify(val, null, 1)}</pre>`;
    return val;
}

// 8. عنوان وصياغة معيار الفرز المختار
function getCriteriaTitle(sortBy) {
    const titles = {
        'invited_friends_count': 'إحالات الفترة / الإجمالي',
        'ads_watched': 'مشاهدة الإعلانات الإجمالية',
        'daily_streak': 'ستريك التسجيل اليومي',
        'daily_boost_rate': 'مكافأة/معدل التسريع',
        'balance': 'الرصيد الرئيسي',
        'mined_points': 'النقاط المعدنة',
        'usd_balance': 'رصيد الدولار USD',
        'znx_balance': 'رصيد ZNX',
        'completed_tasks': 'المهام المكتملة',
        'interactions': 'عدد التفاعلات',
        'total_wins': 'إجمالي الفوز بالألعاب'
    };
    return titles[sortBy] || 'المعيار المختار';
}

// 9. عرض الكروت والجداول الموحدة للمستخدمين
function uRender(usersList, totalFilteredCount, sortBy, limitVal, isSearch, hasDateFilter) {
    const container = document.getElementById('uResultsContainer');
    if (!container) return;
    container.innerHTML = '';

    if (!usersList || usersList.length === 0) {
        container.innerHTML = '<div class="u-empty">❌ لا يوجد مستخدمين يطابقون خيارات البحث أو التصفية الحالية.</div>';
        return;
    }

    const countHeader = document.createElement('div');
    countHeader.className = 'u-count-tag';
    
    let criteriaName = getCriteriaTitle(sortBy);
    let limitText = limitVal === 'all' ? 'جميع المستوفين' : `أفضل ${usersList.length}`;

    if (isSearch) {
        countHeader.innerHTML = `<span>🔍 نتائج البحث المباشر:</span> <span>عرض ${usersList.length} من إجمالي ${totalFilteredCount} مستخدم</span>`;
    } else {
        countHeader.innerHTML = `<span>🏆 ${limitText} في [${criteriaName}]:</span> <span>معروض ${usersList.length} من أصل ${totalFilteredCount} مستخدم مطابق</span>`;
    }
    container.appendChild(countHeader);

    usersList.forEach((u, index) => {
        let card = document.createElement('div');
        card.className = 'u-single-card';

        let mainVal = u[sortBy];
        if (sortBy === 'invited_friends_count' && hasDateFilter && u._period_refs !== undefined) {
            mainVal = `${u._period_refs} (إحالات الفترة) | ${u.invited_friends_count} (الإجمالي)`;
        } else {
            if (Array.isArray(mainVal)) mainVal = mainVal.length;
            if (mainVal === undefined || mainVal === null) mainVal = 0;
        }

        let rankBadge = isSearch 
            ? `${criteriaName}: ${mainVal}` 
            : `🏆 المركز #${index + 1} (${criteriaName}: ${mainVal})`;

        let refDisplayVal = u.invited_friends_count;
        if (hasDateFilter && u._period_refs !== undefined) {
            refDisplayVal = `${u.invited_friends_count} إجمالي (منها ${u._period_refs} إحالة خلال الفترة المحددة)`;
        }

        const fields = [
            { label: "🆔 ID المستخدم (Telegram ID):", value: u.tg_id || u.document_id },
            { label: "👤 اسم المستخدم (First Name):", value: u.first_name || "مستخدم" },
            { label: "📅 تاريخ الانضمام (Joined Date):", value: u.joined_at || u.joinDate },
            { label: "👥 عدد الإحالات (Invited Friends):", value: refDisplayVal },
            { label: "🔗 تم دعوته بواسطة (Referred By):", value: u.referred_by },
            { label: "💰 الرصيد الرئيسي (Balance):", value: u.balance },
            { label: "🪙 رصيد ZNX:", value: u.znx_balance },
            { label: "💵 رصيد الدولار (USD):", value: u.usd_balance ? `$${u.usd_balance}` : null },
            { label: "📢 رصيد الإعلانات (Ad Balance):", value: u.ad_balance },
            { label: "📺 الإعلانات المشاهدة (Ads Watched):", value: u.ads_watched },
            { label: "🔥 الستريك اليومي (Daily Streak):", value: u.daily_streak },
            { label: "📆 اليوم الحالي (Daily Day):", value: u.daily_day },
            { label: "🚀 معدل البوست اليومي (Daily Boost):", value: u.daily_boost_rate },
            { label: "⛏️ النقاط المعدنة (Mined Points):", value: u.mined_points },
            { label: "🎁 الأرباح غير المطالب بها (Unclaimed):", value: u.unclaimed },
            { label: "⚡ معدل التعدين / ساعة (Hourly Rate):", value: u.hourly_rate },
            { label: "📦 مستوى المخزن (Storage Level):", value: u.storage_level },
            { label: "➕ المخزن الإضافي (Extra Storage):", value: u.extra_storage },
            { label: "🔋 السعة القصوى (Max Cap):", value: u.max_cap },
            { label: "⚡ الطاقة الحالية (Energy):", value: u.energy },
            { label: "⌛ أرباح إحالة معلقة:", value: u.pending_ref_earnings },
            { label: "💎 إجمالي أرباح الإحالات:", value: u.total_ref_earnings },
            { label: "🌐 عنوان المحفظة (Wallet):", value: u.wallet_address ? `<span class="u-wallet-val">${u.wallet_address}</span>` : null, isRawHTML: true },
            { label: "🕒 آخر نشاط (Last Active):", value: u.last_active || u.last_active_at },
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

// تشغيل جلب البيانات تلقائياً عند فتح الصفحة
uFetch();
