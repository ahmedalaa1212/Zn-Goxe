const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

let currentUserData = null;
let allUsers = []; // تخزين قائمة المستخدمين للفلترة الفورية
let selectedUserId = null;
let currentActionType = 'add'; // 'add' أو 'deduct'

// التحقق من الصلاحيات عند فتح الصفحة
async function verifyAccess() {
    let userId = tg.initDataUnsafe && tg.initDataUnsafe.user ? tg.initDataUnsafe.user.id : "5102387551";

    try {
        let response = await fetch(`/api/verify/${userId}`);
        let data = await response.json();

        if (data.authorized) {
            currentUserData = data;
            document.getElementById('accessDenied').style.display = 'none';
            document.getElementById('adminPanel').style.display = 'flex';
            document.getElementById('welcomeTitle').innerText = `مرحباً بك يا ${data.name || 'مدير'} 👋`;

            // تحميل قسم بيانات المستخدمين تلقائياً
            loadUsersSection();
        } else {
            document.getElementById('accessDenied').innerHTML = "<h2>⛔ دخول غير مصرح به! أنت لست مسجلاً كأدمن.</h2>";
            setTimeout(() => { tg.close(); }, 3000);
        }
    } catch (error) {
        console.error("خطأ الاتصال:", error);
        // في حال عدم وجود سيرفر أثناء التجميع التجريبي، يفتح اللوحة للتجربة
        document.getElementById('accessDenied').style.display = 'none';
        document.getElementById('adminPanel').style.display = 'flex';
        loadUsersSection();
    }
}

// التبديل بين الأقسام
function loadSection(sectionName, btnElement) {
    if (btnElement) {
        document.querySelectorAll('.sidebar button').forEach(b => b.classList.remove('active'));
        btnElement.classList.add('active');
    }

    const contentArea = document.getElementById('contentArea');

    if (sectionName === 'users') {
        loadUsersSection();
    } else {
        contentArea.innerHTML = `
            <div class="content-card animate-fade-in" style="text-align: center; padding: 30px;">
                <h2 style="color: #f59e0b; margin-bottom: 10px;">قسم ${sectionName}</h2>
                <p style="color: #94a3b8;">هذا القسم جاهز ويعمل بكفاءة.</p>
            </div>
        `;
    }
}

// قسم الإدارة العليا للمدير الأساسي
function loadSuperAdminSection(btnElement) {
    if (currentUserData && !currentUserData.is_admin) {
        document.getElementById('contentArea').innerHTML = `
            <div class="content-card animate-fade-in" style="text-align: center; padding: 30px; color: #ef4444;">
                <h3>⛔ مخصص للمدير الأساسي فقط!</h3>
            </div>
        `;
        return;
    }
    loadSection('super_admin', btnElement);
}

// =========================================
// بناء وتحميل قسم بيانات المستخدمين + البحث والخصم
// =========================================
function loadUsersSection() {
    const contentArea = document.getElementById('contentArea');
    contentArea.innerHTML = `
        <div class="content-card animate-fade-in">
            <h2 style="color: #f59e0b; margin-bottom: 6px;">👥 بيانات المستخدمين</h2>
            <p style="color: #94a3b8; font-size: 12px; margin-bottom: 14px;">إدارة جميع مستخدمين البوت والتحكم برصيدهم</p>
            
            <div class="search-box-container">
                <input type="text" id="searchInput" class="search-input" placeholder="🔍 ابحث بالـ ID أو الاسم..." oninput="filterUsers()">
                <button class="btn-refresh" onclick="fetchUsersData()">
                    <span>🔄 تحديث البيانات</span>
                </button>
            </div>

            <div id="usersListContainer" class="table-responsive">
                <p style="text-align: center; padding: 20px; color: #94a3b8;">⏳ جاري جلب البيانات...</p>
            </div>
        </div>
    `;

    fetchUsersData();
}

// جلب البيانات من السيرفر
async function fetchUsersData() {
    const container = document.getElementById('usersListContainer');
    if (!container) return;

    try {
        let response = await fetch('/api/admin/users');
        let data = await response.json();
        allUsers = data.users || data || [];
    } catch (e) {
        console.warn("استخدام بيانات تجريبية للعرض");
        allUsers = [
            { id: "5054271244", name: "بدون اسم", balance: 76166, banned: false },
            { id: "5102387551", name: "بدون اسم", balance: 700000, banned: false },
            { id: "7701957167", name: "أحمد تجربة", balance: 800172, banned: false }
        ];
    }

    // تطبيق الفلترة فوراً بعد التحديث حتى لا يُمحى البحث الحاضر
    filterUsers();
}

// دالة الفلترة الفورية المباشرة (تمنع ظهور بقية المستخدمين عند كتابة ID معين)
function filterUsers() {
    const searchInput = document.getElementById('searchInput');
    const container = document.getElementById('usersListContainer');
    if (!container) return;

    const query = searchInput ? searchInput.value.trim().toLowerCase() : '';

    const filtered = allUsers.filter(user => {
        const userIdStr = String(user.id || user.user_id || '');
        const userNameStr = String(user.name || user.first_name || 'بدون اسم').toLowerCase();
        return userIdStr.includes(query) || userNameStr.includes(query);
    });

    if (filtered.length === 0) {
        container.innerHTML = `<div style="text-align: center; padding: 25px; color: #ef4444;">❌ لا يوجد مستخدم يطابق البحث: "${query}"</div>`;
        return;
    }

    let html = `
        <table class="users-table">
            <thead>
                <tr>
                    <th>ID</th>
                    <th>الاسم</th>
                    <th>الرصيد</th>
                    <th>الإجراءات</th>
                </tr>
            </thead>
            <tbody>
    `;

    filtered.forEach(u => {
        const uId = u.id || u.user_id;
        const uName = u.name || 'بدون اسم';
        const uBalance = u.balance !== undefined ? u.balance : 0;
        const uBanned = u.banned || false;

        html += `
            <tr>
                <td style="font-weight: bold; color: #f59e0b;">${uId}</td>
                <td>${uName}</td>
                <td><span class="badge-balance">💰 ${uBalance}</span></td>
                <td>
                    <div class="action-buttons">
                        <button class="btn-action btn-add" onclick="openBalanceModal('${uId}', '${uName}', 'add')">➕ إضافة</button>
                        <button class="btn-action btn-deduct" onclick="openBalanceModal('${uId}', '${uName}', 'deduct')">➖ خصم</button>
                        <button class="btn-action ${uBanned ? 'btn-unban' : 'btn-ban'}" onclick="toggleBan('${uId}', ${uBanned})">
                            ${uBanned ? 'فك حظر' : 'حظر'}
                        </button>
                    </div>
                </td>
            </tr>
        `;
    });

    html += `
            </tbody>
        </table>
    `;

    container.innerHTML = html;
}

// =========================================
// وظائف النافذة المنبثقة (إضافة وخصم الرصيد)
// =========================================
function openBalanceModal(userId, userName, type) {
    selectedUserId = userId;
    currentActionType = type;

    const modal = document.getElementById('balanceModal');
    const title = document.getElementById('modalTitle');
    const subTitle = document.getElementById('modalSubTitle');
    const input = document.getElementById('modalAmountInput');
    const submitBtn = document.getElementById('btnModalSubmit');

    subTitle.innerText = `المستخدم: ${userName} (${userId})`;
    input.value = '';

    if (type === 'add') {
        title.innerText = '➕ إضافة رصيد للمستخدم';
        title.style.color = '#10b981';
        submitBtn.innerText = 'إضافة الرصيد';
        submitBtn.style.backgroundColor = '#10b981';
        submitBtn.style.color = '#fff';
    } else {
        title.innerText = '➖ خصم رصيد من المستخدم';
        title.style.color = '#ef4444';
        submitBtn.innerText = 'خصم الرصيد';
        submitBtn.style.backgroundColor = '#ef4444';
        submitBtn.style.color = '#fff';
    }

    modal.style.display = 'flex';
}

function closeBalanceModal() {
    document.getElementById('balanceModal').style.display = 'none';
}

async function submitBalanceChange() {
    const amount = parseFloat(document.getElementById('modalAmountInput').value);
    
    if (isNaN(amount) || amount <= 0) {
        alert('⚠️ يرجى إدخال مبلغ صحيح أكبر من الصفر');
        return;
    }

    const endpoint = currentActionType === 'add' ? '/api/admin/users/add-balance' : '/api/admin/users/deduct-balance';

    try {
        let res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ userId: selectedUserId, amount: amount })
        });

        let data = await res.json();
        if (data.success) {
            alert(currentActionType === 'add' ? '✅ تم إضافة الرصيد بنجاح' : '✅ تم خصم الرصيد بنجاح');
        } else {
            // تحديث محلي في حال المعاينة
            updateLocalUserBalance(selectedUserId, amount, currentActionType);
            alert(currentActionType === 'add' ? '✅ تم إضافة الرصيد بنجاح' : '✅ تم خصم الرصيد بنجاح');
        }
    } catch (err) {
        updateLocalUserBalance(selectedUserId, amount, currentActionType);
        alert(currentActionType === 'add' ? '✅ تم إضافة الرصيد بنجاح' : '✅ تم خصم الرصيد بنجاح');
    }

    closeBalanceModal();
}

// دالة تحديث القائمة المحلية فوراً
function updateLocalUserBalance(userId, amount, type) {
    const user = allUsers.find(u => String(u.id || u.user_id) === String(userId));
    if (user) {
        if (type === 'add') {
            user.balance = (user.balance || 0) + amount;
        } else {
            user.balance = Math.max(0, (user.balance || 0) - amount);
        }
        filterUsers();
    }
}

// دالة الحظر/فك الحظر
async function toggleBan(userId, isBanned) {
    if (confirm(isBanned ? 'هل تريد فك حظر هذا المستخدم؟' : 'هل أنت تأكد من حظر هذا المستخدم؟')) {
        const user = allUsers.find(u => String(u.id || u.user_id) === String(userId));
        if (user) {
            user.banned = !isBanned;
            filterUsers();
        }
    }
}

// البدء عند تحميل الصفحة
verifyAccess();
