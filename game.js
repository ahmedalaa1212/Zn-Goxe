// المحرك الرئيسي للانتقالات (نظام المجلدات)
async function switchView(viewName) {
    // 1. تحديث الأزرار (تغيير لون الزر النشط)
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    const activeNav = document.getElementById('nav-' + viewName);
    if (activeNav) activeNav.classList.add('active');

    // 2. تحديد مكان العرض
    const container = document.getElementById('view-' + viewName);
    
    // 3. جلب محتوى القائمة من المجلد الخاص بها
    try {
        const res = await fetch(`${viewName}/${viewName}.html`);
        const html = await res.text();
        container.innerHTML = html;

        // 4. تنفيذ كود الـ JS الخاص بالقائمة (لضمان عمل كل شيء داخل مجلده)
        const script = document.createElement('script');
        script.src = `${viewName}/${viewName}.js`;
        document.body.appendChild(script);

        // 5. التبديل المرئي بين الصفحات
        document.querySelectorAll('.game-view').forEach(v => v.classList.remove('active'));
        container.classList.add('active');
    } catch (e) {
        console.error("خطأ في تحميل القائمة:", e);
        container.innerHTML = `<p style="text-align:center; padding:20px;">القائمة قيد التطوير...</p>`;
    }
}

// 6. تشغيل المزرعة تلقائياً عند فتح البوت لأول مرة
window.onload = () => {
    switchView('farm'); 
};
