// =========================================
// ملف main.js - محرك التنقل بين الـ 7 قوائم
// =========================================

/**
 * دالة جلب وعرض القوائم الفرعية ديناميكياً
 * @param {string} section - اسم القائمة (مثال: 'users', 'super_admin')
 */
async function loadSection(section) {
    const contentArea = document.getElementById('contentArea');
    
    // 1. عرض مؤشر التحميل حتى يجهز الملف
    contentArea.innerHTML = `
        <div style="text-align: center; margin-top: 50px;">
            <h3 style="color: #ffcc00; font-family: sans-serif;">⏳ جاري تحميل القائمة...</h3>
        </div>
    `;

    try {
        // 2. جلب ملف الـ HTML من داخل مجلد القائمة
        const response = await fetch(`./${section}/${section}.html`);
        
        if (!response.ok) {
            throw new Error(`تعذر العثور على الملف: ${section}/${section}.html`);
        }
        
        const htmlText = await response.text();
        
        // 3. طباعة محتوى الـ HTML داخل منطقة العرض الرئيسية
        contentArea.innerHTML = htmlText;

        // 4. استدعاء واستشعار ملف الـ JS الخاص بالقائمة ديناميكياً
        loadSectionScript(`./${section}/${section}.js`);

    } catch (error) {
        console.error("خطأ أثناء التحميل:", error);
        contentArea.innerHTML = `
            <div style="text-align: center; margin-top: 50px; color: #ff4444; font-family: sans-serif;">
                <h3>⚠️ القائمة قيد التطوير</h3>
                <p style="color: #bbb; margin-top: 10px;">تأكد من إنشاء المجلد <b>${section}</b> وبداخله الملف <b>${section}.html</b> في جيت هاب.</p>
            </div>
        `;
    }
}

/**
 * دالة تشغيل ملفات الـ JS الفرعية تلقائياً عند فتح القائمة
 * @param {string} scriptPath - مسار ملف الجافاسكريبت
 */
function loadSectionScript(scriptPath) {
    // إزالة أي سكربت قديم للقائمة السابقة لتجنب تضارب الأكواد
    const oldScript = document.getElementById('activeSectionScript');
    if (oldScript) {
        oldScript.remove();
    }

    // إنشاء عنصر script جديد وتفعيله
    const script = document.createElement('script');
    script.id = 'activeSectionScript';
    // إضافة متغيرة للوقت لمنع التخزين المؤقت (Cache) عند التعديل
    script.src = scriptPath + '?v=' + new Date().getTime(); 
    
    script.onload = () => {
        console.log(`✅ تم تحميل الكود بنجاح: ${scriptPath}`);
    };
    
    script.onerror = () => {
        console.log(`ℹ️ تنبيه: لا يوجد ملف JS منفصل لهذه القائمة بعد (${scriptPath}).`);
    };

    document.body.appendChild(script);
}
