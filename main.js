const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

let currentUserData = null;

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

            // إخفاء الإدارة العليا لو مش المدير الأساسي
            if (!data.is_admin) {
                const superAdminBtn = document.getElementById('btn_super_admin');
                if (superAdminBtn) {
                    superAdminBtn.style.opacity = '0.4';
                    superAdminBtn.style.cursor = 'not-allowed';
                }
            }
        } else {
            document.getElementById('accessDenied').innerHTML = "<h2>⛔ دخول غير مصرح به! أنت لست مسجلاً كأدمن.</h2>";
            setTimeout(() => { tg.close(); }, 3000);
        }
    } catch (error) {
        console.error("خطأ في التحقق:", error);
        document.getElementById('accessDenied').style.display = 'none';
        document.getElementById('adminPanel').style.display = 'flex';
    }
}

// دالة تحميل الأقسام من المجلدات الخاصة بها (السر كله هنا)
async function loadSection(sectionName, btnElement) {
    // تفعيل لون الزرار
    if (btnElement) {
        document.querySelectorAll('.sidebar button').forEach(b => b.classList.remove('active'));
        btnElement.classList.add('active');
    }

    const contentArea = document.getElementById('contentArea');
    contentArea.innerHTML = `<div style="text-align:center; padding:20px; color:#f59e0b;">⏳ جاري تحميل القسم...</div>`;

    try {
        // 1. جلب ملف الـ HTML من المجلد الخاص بالقسم
        let response = await fetch(`/${sectionName}/${sectionName}.html`);
        
        if (response.ok) {
            let html = await response.text();
            contentArea.innerHTML = html;

            // 2. تحميل ملف الـ JS الخاص بالقسم
            let scriptId = `script-${sectionName}`;
            // إزالة السكربت القديم لو موجود لمنع التداخل
            let oldScript = document.getElementById(scriptId);
            if (oldScript) oldScript.remove();

            let script = document.createElement('script');
            script.src = `/${sectionName}/${sectionName}.js`;
            script.id = scriptId;
            document.body.appendChild(script);
            
        } else {
            contentArea.innerHTML = `
                <div class="content-card" style="text-align:center; color:#ef4444;">
                    <h3>❌ لم يتم العثور على ملفات قسم ${sectionName}</h3>
                </div>`;
        }
    } catch (error) {
        console.error("خطأ:", error);
        contentArea.innerHTML = `<div class="content-card" style="text-align:center; color:#ef4444;"><h3>❌ حدث خطأ أثناء الاتصال.</h3></div>`;
    }
}

// حماية الإدارة العليا
function loadSuperAdminSection(btnElement) {
    if (currentUserData && !currentUserData.is_admin) {
        document.getElementById('contentArea').innerHTML = `
            <div class="content-card animate-fade-in" style="text-align: center; padding: 40px; color: #ff4444;">
                <span style="font-size: 40px;">⛔</span>
                <h3 style="margin-top: 15px; color: #f59e0b;">عذراً يا غالي، هذا القسم مخصص للمدير الأساسي فقط! 👑</h3>
            </div>
        `;
        return;
    }
    // لو مدير أساسي هيحمل مجلد super_admin
    loadSection('super_admin', btnElement);
}

verifyAccess();
