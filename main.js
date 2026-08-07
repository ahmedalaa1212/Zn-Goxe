// ==========================================
// 🛡️ نظام الحماية المتقدم للوحة التحكم
// ==========================================
const tg = window.Telegram?.WebApp;

// دالة جلب بيانات التوثيق من التليجرام
function getInitData() {
    return tg?.initData || window.Telegram?.WebApp?.initData || "";
}

document.addEventListener("DOMContentLoaded", async () => {
    if (tg) {
        tg.ready();
        tg.expand();
    }

    const initData = getInitData();

    // 1. فحص وجود بيانات التليجرام
    if (!initData) {
        showAccessDenied("⛔ تنبيه أمني: لا يمكنك فتح هذه اللوحة من المتصفح مباشرة! يجب فتحها من داخل بوت الأدمن.");
        return;
    }

    // 2. التحقق من الهوية والصلاحيات من الباك إند
    try {
        const response = await fetch('/api/verify_admin', {
            method: 'POST',
            headers: {
                'X-Telegram-Init-Data': initData,
                'Authorization': `Bearer ${initData}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ initData: initData })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // السماح بالدخول
            const accessDeniedEl = document.getElementById("accessDenied");
            const adminPanelEl = document.getElementById("adminPanel");

            if (accessDeniedEl) accessDeniedEl.style.display = "none";
            if (adminPanelEl) adminPanelEl.style.display = "flex";

            const user = tg?.initDataUnsafe?.user;
            const welcomeTitle = document.getElementById("welcomeTitle");
            if (welcomeTitle && user) {
                welcomeTitle.innerText = `مرحباً بك يا ${user.first_name || ''} 👋 (${data.role || 'مدير'})`;
            }
        } else {
            showAccessDenied(`⛔ وصول محظور: ${data.message || data.error || "ليس لديك صلاحية لوحة التحكم"}`);
        }
    } catch (error) {
        console.error("خطأ أثناء التحقق من هويّة المدير:", error);
        showAccessDenied("❌ خطأ في الاتصال بالسيرفر، تعذر التحقق من الهوية.");
    }
});

function showAccessDenied(message) {
    const screen = document.getElementById("accessDenied");
    const adminPanel = document.getElementById("adminPanel");

    if (screen) {
        screen.innerHTML = `<h2 style="color: #ef4444; padding: 20px; text-align: center; font-family: sans-serif;">${message}</h2>`;
        screen.style.display = "flex";
    }
    if (adminPanel) {
        adminPanel.style.display = "none";
    }
}

// ==========================================
// 🔄 دالة تحميل الأقسام (ترافقها الحماية للـ Headers)
// ==========================================
async function loadSection(sectionName, btnElement) {
    if (btnElement) {
        document.querySelectorAll('.sidebar button').forEach(btn => btn.classList.remove('active'));
        btnElement.classList.add('active');
    }

    const contentArea = document.getElementById("contentArea");
    if (!contentArea) return;

    contentArea.innerHTML = `
        <div class="content-card animate-fade-in" style="text-align: center; padding: 40px;">
            <h3 style="color: #f59e0b;">⏳ جاري تحميل قسم (${sectionName})...</h3>
        </div>
    `;

    try {
        const response = await fetch(`/${sectionName}/${sectionName}.html`);
        if (!response.ok) throw new Error("تعذر جلب الواجهة");
        
        const htmlContent = await response.text();
        contentArea.innerHTML = htmlContent;

        loadSectionScript(sectionName);
    } catch (error) {
        contentArea.innerHTML = `
            <div class="content-card animate-fade-in" style="text-align: center; border-color: #ef4444;">
                <h3 style="color: #ef4444;">❌ قسم تحت الإنشاء أو غير موجود</h3>
                <p style="color: #94a3b8; font-size: 13px; margin-top: 8px;">تأكد من وجود المجلد (${sectionName}) وبداخله الملفات المطلوبة.</p>
            </div>
        `;
    }
}

function loadSectionScript(sectionName) {
    const scriptId = `script_${sectionName}`;
    const oldScript = document.getElementById(scriptId);
    if (oldScript) oldScript.remove();

    const script = document.createElement("script");
    script.id = scriptId;
    script.src = `/${sectionName}/${sectionName}.js?v=${new Date().getTime()}`;
    
    script.onload = () => {
        if (sectionName === 'super_admin' && typeof window.initSuperAdmin === 'function') {
            window.initSuperAdmin();
        }
    };

    document.body.appendChild(script);
}

function loadSuperAdminSection(btnElement) {
    loadSection('super_admin', btnElement);
}
