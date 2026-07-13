// دالة التنقل السريع بين القوائم وتغيير ألوان شريط الأزرار السفلي فوراً
function switchView(viewName) {
    // 1. جلب كافة شاشات اللعبة وإخفائها عبر الـ class فقط بدون إجبار الـ style
    const views = document.querySelectorAll('.game-view');
    views.forEach(view => {
        view.classList.remove('active');
    });

    // 2. إظهار الشاشة التي ضغط عليها اللاعب فوراً عبر إضافة الـ class
    const targetView = document.getElementById(`view-${viewName}`);
    if (targetView) {
        targetView.classList.add('active');
    }

    // 3. تحديث ألوان أزرار القائمة السفلية بشكل فوري وسلس
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.classList.remove('active');
    });

    const activeNav = document.getElementById(`nav-${viewName}`);
    if (activeNav) {
        activeNav.classList.add('active');
    }
}

// تشغيل شاشة المزرعة كشاشة افتراضية أول ما البوت يفتح
document.addEventListener('DOMContentLoaded', () => {
    switchView('farm');
});
