// المحرك الرئيسي للانتقالات
async function switchView(viewName) {
    // 1. تحديث الأزرار (تغيير اللون)
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    document.getElementById('nav-' + viewName).classList.add('active');

    // 2. تحديد مكان العرض
    const container = document.getElementById('view-' + viewName);
    
    // 3. جلب محتوى القائمة من مجلدها
    try {
        const res = await fetch(`${viewName}/${viewName}.html`);
        const html = await res.text();
        container.innerHTML = html;

        // 4. تنفيذ كود الـ JS الخاص بالقائمة (لو موجود)
        const script = document.createElement('script');
        script.src = `${viewName}/${viewName}.js`;
        document.body.appendChild(script);

        // 5. التبديل المرئي
        document.querySelectorAll('.game-view').forEach(v => v.classList.remove('active'));
        container.classList.add('active');
    } catch (e) {
        container.innerHTML = `<p style="text-align:center; padding:20px;">القائمة قيد التطوير...</p>`;
    }
}
