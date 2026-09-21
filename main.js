// ==========================================
// 🛡️ نظام الحماية المتقدم للوحة التحكم (main.js)
// ==========================================
const tg = window.Telegram?.WebApp;

// دالة جلب بيانات التوثيق من التليجرام
function getInitData() {
    return tg?.initData || window.Telegram?.WebApp?.initData || "";
}

// 🔐 دالة موحدة لإجراء طلبات الـ API مع إرفاق التوثيق التلقائي في الـ Headers
async function apiFetch(url, options = {}) {
    const initData = getInitData();
    const defaultHeaders = {
        'X-Telegram-Init-Data': initData,
        'X-Init-Data': initData,
        'Authorization': `Bearer ${initData}`,
        'Content-Type': 'application/json'
    };

    const mergedOptions = {
        ...options,
        headers: {
            ...defaultHeaders,
            ...(options.headers || {})
        }
    };

    return fetch(url, mergedOptions);
}

// تصدير الدوال للاستخدام العام في باقي الموديولات للحد من أخطاء الـ Scope
window.getInitData = getInitData;
window.apiFetch = apiFetch;

document.addEventListener("DOMContentLoaded", async () => {
    if (tg) {
        tg.ready();
        tg.expand();
    }

    const initData = getInitData();

    // 1. فحص وجود بيانات التليجرام ومنع المتصفحات الخارجية
    if (!initData) {
        showAccessDenied("⛔ تنبيه أمني: لا يمكنك فتح هذه اللوحة من المتصفح مباشرة! يجب فتحها حصرياً من داخل بوت الأدمن.");
        return;
    }

    // 2. التحقق من الهوية والصلاحيات من الباك إند
    try {
        const response = await apiFetch('/api/verify_admin', {
            method: 'POST',
            body: JSON.stringify({ initData: initData })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // السماح بالدخول وإظهار اللوحة
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

// دالة عرض شاشة رفض الوصول
function showAccessDenied(message) {
    const screen = document.getElementById("accessDenied");
    const adminPanel = document.getElementById("adminPanel");

    if (screen) {
        screen.innerHTML = `
            <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; background:#0d1117; color:#ef4444; font-family:sans-serif; text-align:center; padding:20px; direction:rtl;">
                <h1 style="font-size:56px; margin-bottom:10px;">⛔</h1>
                <h2 style="font-size:22px; color:#ef4444; margin-bottom:12px; font-weight:bold;">تم رفض الوصول!</h2>
                <p style="color:#94a3b8; font-size:14px; max-width:380px; line-height:1.6;">${message}</p>
            </div>
        `;
        screen.style.display = "flex";
    }
    if (adminPanel) {
        adminPanel.style.display = "none";
    }
}

// ==========================================
// 🔄 دالة تحميل الأقسام وتنسيق الشريط الجانبي
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

// ==========================================
// 📜 دالة تحميل وتنفيذ سكربتات الأقسام ديناميكياً
// ==========================================
function loadSectionScript(sectionName) {
    const scriptId = `script_${sectionName}`;
    const oldScript = document.getElementById(scriptId);
    if (oldScript) oldScript.remove();

    const script = document.createElement("script");
    script.id = scriptId;
    script.src = `/${sectionName}/${sectionName}.js?v=${new Date().getTime()}`;
    
    script.onload = () => {
        // 👥 تشغيل موديول بيانات المستخدمين تلقائياً
        if (sectionName === 'users') {
            if (typeof window.uFetch === 'function') {
                window.uFetch();
            }
        }
        
        // 👑 تشغيل دالة التهيئة لقسم super_admin والموديولات التابعة له
        else if (sectionName === 'super_admin') {
            if (typeof window.initSuperAdmin === 'function') {
                window.initSuperAdmin();
            } else {
                // 1️⃣ جلب التحليلات الحية للمستخدمين
                if (typeof loadGlobalAnalytics === 'function') loadGlobalAnalytics();
                
                // 2️⃣ جلب قائمة أكثر المستخدمين نشاطاً
                if (typeof loadTopActiveUsers === 'function') loadTopActiveUsers();
                
                // 3️⃣ جلب باقي الموديولات (المشرفين، السجلات، الإحصائيات)
                if (typeof loadModerators === 'function') loadModerators();
                if (typeof loadAdminLogs === 'function') loadAdminLogs();
                if (typeof fetchBroadcastStats === 'function') fetchBroadcastStats();
            }
        }
    };

    document.body.appendChild(script);
}

// تصدير دوال تحميل الأقسام إلى النافذة العامة
window.loadSection = loadSection;
window.loadSuperAdminSection = function(btnElement) {
    loadSection('super_admin', btnElement);
};
