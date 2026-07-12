// game.js الرئيسي - مسؤول عن التنقل فقط
async function switchView(viewName) {
    // 1. تحديث الأزرار
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    document.getElementById('nav-' + viewName).classList.add('active');

    // 2. تحميل المحتوى من المجلد الخاص (مثلاً: farm/farm.html)
    const viewContainer = document.getElementById('view-' + viewName);
    
    try {
        const response = await fetch(`${viewName}/${viewName}.html`);
        const html = await response.text();
        viewContainer.innerHTML = html;

        // 3. تشغيل ملف الـ JS الخاص بالمجلد ده
        const script = document.createElement('script');
        script.src = `${viewName}/${viewName}.js`;
        document.body.appendChild(script);
        
        // إظهار القائمة
        document.querySelectorAll('.game-view').forEach(v => v.classList.remove('active'));
        viewContainer.classList.add('active');
        
    } catch (error) {
        console.error("خطأ في تحميل القائمة:", error);
    }
}
