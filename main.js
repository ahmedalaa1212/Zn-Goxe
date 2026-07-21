// =========================================
// main.js - نظام التنقل الذكي والحركات
// =========================================

async function loadSection(section, btnElement) {
    const contentArea = document.getElementById('contentArea');
    
    // 1. تحديث شكل الزر النشط في القائمة الجانبية
    const allButtons = document.querySelectorAll('.sidebar button');
    allButtons.forEach(btn => btn.classList.remove('active'));
    
    if (btnElement) {
        btnElement.classList.add('active');
    }

    // 2. مؤشر تحميل شيك ومؤقت
    contentArea.innerHTML = `
        <div class="content-card animate-fade-in">
            <h3 style="color: #f59e0b; font-size: 16px;">⏳ جاري التحميل...</h3>
        </div>
    `;

    try {
        // 3. جلب ملف الـ HTML الخاص بالقائمة
        const response = await fetch(`./${section}/${section}.html`);
        
        if (!response.ok) {
            throw new Error(`الملف غير موجود: ${section}/${section}.html`);
        }
        
        const htmlText = await response.text();
        
        // 4. عرض المحتوى مع تأثير حركة الدخول الناعمة
        contentArea.innerHTML = `<div class="animate-fade-in" style="width: 100%;">${htmlText}</div>`;

        // 5. استدعاء ملف الـ JS الفرعي
        loadSectionScript(`./${section}/${section}.js`);

    } catch (error) {
        contentArea.innerHTML = `
            <div class="content-card animate-fade-in">
                <span style="font-size: 32px; display: block; margin-bottom: 8px;">⚠️</span>
                <h3 style="color: #ef4444; font-size: 16px; margin-bottom: 8px;">القائمة قيد التطوير</h3>
                <p style="color: #94a3b8; font-size: 12px; line-height: 1.5;">
                    قم بإنشاء مجلد باسم <b style="color:#f59e0b;">${section}</b><br>وبداخله ملف <b style="color:#f59e0b;">${section}.html</b>
                </p>
            </div>
        `;
    }
}

function loadSectionScript(scriptPath) {
    const oldScript = document.getElementById('activeSectionScript');
    if (oldScript) oldScript.remove();

    const script = document.createElement('script');
    script.id = 'activeSectionScript';
    script.src = scriptPath + '?v=' + new Date().getTime();
    document.body.appendChild(script);
}
