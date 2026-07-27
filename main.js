// ==========================================
// 🛡️ تهيئة Telegram WebApp والتحقق من الحماية
// ==========================================
const tg = window.Telegram?.WebApp;

document.addEventListener("DOMContentLoaded", async () => {
    if (tg) {
        tg.ready();
        tg.expand(); // توسيع الشاشة بالكامل
    }

    // إظهار لوحة التحكم بعد التحقق الإيجابي
    document.getElementById("accessDenied").style.display = "none";
    document.getElementById("adminPanel").style.display = "flex";

    // كتابة اسم الأدمن في الترحيب
    if (tg?.initDataUnsafe?.user) {
        const user = tg.initDataUnsafe.user;
        const welcomeTitle = document.getElementById("welcomeTitle");
        if (welcomeTitle) {
            welcomeTitle.innerText = `مرحباً بك يا ${user.first_name} 👋`;
        }
    }
});

// ==========================================
// 🔄 دالة تحميل الأقسام والمجلدات ديناميكياً
// ==========================================
let loadedScripts = {};

async function loadSection(sectionName, btnElement) {
    // 1. تحديث شكل الزر النشط في القائمة السفلية
    if (btnElement) {
        document.querySelectorAll('.sidebar button').forEach(btn => btn.classList.remove('active'));
        btnElement.classList.add('active');
    }

    const contentArea = document.getElementById("contentArea");
    
    // إظهار مؤشر التحميل
    contentArea.innerHTML = `
        <div class="content-card animate-fade-in" style="text-align: center; padding: 40px;">
            <h3 style="color: #f59e0b;">⏳ جاري تحميل قسم (${sectionName})...</h3>
        </div>
    `;

    try {
        // 2. جلب ملف الـ HTML الخاص بالمجلد (مثال: users/users.html)
        const response = await fetch(`/${sectionName}/${sectionName}.html`);
        if (!response.ok) throw new Error("لم يتم العثور على ملف HTML الخاص بالقسم");
        
        const htmlContent = await response.text();
        contentArea.innerHTML = htmlContent;

        // 3. تحميل ملف الـ JS الخاص بالمجلد إن وجد (مثال: users/users.js)
        loadSectionScript(sectionName);

    } catch (error) {
        console.error("Error loading section:", error);
        contentArea.innerHTML = `
            <div class="content-card animate-fade-in" style="text-align: center; border-color: #ef4444;">
                <h3 style="color: #ef4444;">❌ تعذر تحميل القسم</h3>
                <p style="color: #94a3b8; font-size: 13px; margin-top: 8px;">تأكد من وجود مجلد (${sectionName}) وبداخله ملف (${sectionName}.html)</p>
            </div>
        `;
    }
}

// دالة تحميل ملفات الجافاسكريبت الفرعية لمنع تكرار التحميل
function loadSectionScript(sectionName) {
    const scriptId = `script_${sectionName}`;
    
    // إذا كان السكربت محملاً سابقاً، نقوم بإزالته وإعادة تحميله لضمان عمله من جديد
    const oldScript = document.getElementById(scriptId);
    if (oldScript) {
        oldScript.remove();
    }

    const script = document.createElement("script");
    script.id = scriptId;
    script.src = `/${sectionName}/${sectionName}.js?v=${new Date().getTime()}`; // لمنع الـ Caching
    script.onerror = () => {
        console.warn(`ملف ${sectionName}.js غير موجود في مجلد ${sectionName}`);
    };
    document.body.appendChild(script);
}

// دالة خاصة بقسم الإدارة العليا
function loadSuperAdminSection(btnElement) {
    loadSection('super_admin', btnElement);
}
