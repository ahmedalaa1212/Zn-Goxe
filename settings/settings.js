// قيم تكميلية افتراضية في حال عدم ربطها بملف الـ Core الرئيسي بعد
let tgUser = { id: 541982736, first_name: "اللاعب المحترف" }; 

// محاولة جلب بيانات المستخدم الحقيقية من بيئة تليجرام المتاحة بالـ WebApp
if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
    const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
    if (webAppUser) {
        tgUser = webAppUser;
    }
}

// دالة العرض الأساسية لبيانات الإعدادات
function renderSettingsPage() {
    const usernameEl = document.getElementById('player-username');
    const telegramIdEl = document.getElementById('player-telegram-id');
    const avatarEl = document.getElementById('player-avatar');

    if (usernameEl) usernameEl.innerText = tgUser.first_name || tgUser.username || "لاعب Zn Goxe";
    if (telegramIdEl) telegramIdEl.innerText = tgUser.id || "00000000";
    
    // إذا كان للمستخدم صورة حقيقية في تليجرام، يمكنك استبدال الأيقونة بها لاحقاً
    if (tgUser.photo_url && avatarEl) {
        avatarEl.innerHTML = `<img src="${tgUser.photo_url}" style="width:100%; height:100%; object-fit:cover;">`;
    }

    // حساب وعرض الإحصائيات الحسابية التكميلية لرفع الاحترافية
    updateStatsDisplay();
}

// دالة حساب الإحصائيات من الـ LocalStorage المحدث من المتجر والمزرعة
function updateStatsDisplay() {
    const totalMiningEl = document.getElementById('stat-total-mining');
    const storageLevelEl = document.getElementById('stat-storage-level');

    // افتراض وجود بيانات المتجر المخزنة مسبقاً، وإلا نضع صفر
    let currentStorage = typeof currentStorageLevel !== 'undefined' ? currentStorageLevel : 0;
    let totalUpgradesCount = 0;
    
    if (typeof miningUpgrades !== 'undefined') {
        Object.keys(miningUpgrades).forEach(lvl => {
            totalUpgradesCount += miningUpgrades[lvl];
        });
    }

    if (totalMiningEl) totalMiningEl.innerText = `${totalUpgradesCount} / 200`;
    if (storageLevelEl) storageLevelEl.innerText = `مستوى ${currentStorage}`;
}

// دالة نسخ الـ ID الشيك والاحترافية مع إظهار توست تأكيدي سيعجب اللاعب
function copyPlayerId() {
    const idText = document.getElementById('player-telegram-id').innerText;
    navigator.clipboard.writeText(idText).then(() => {
        const toast = document.getElementById('toast-msg');
        if (toast) {
            toast.style.display = 'block';
            setTimeout(() => {
                toast.style.display = 'none';
            }, 2000); // تختفي الرسالة تلقائياً بعد ثانيتين
        }
    }).catch(err => {
        console.error('فشل في نسخ النص: ', err);
    });
}

// دوال التحكم في النوافذ المنبثقة للسياسات والشروط
function showPrivacyModal() {
    const modal = document.getElementById('settings-modal');
    if (modal) modal.style.display = 'flex';
}

function closeSettingsModal() {
    const modal = document.getElementById('settings-modal');
    if (modal) modal.style.display = 'none';
}

// ميزة احترافية: إعادة تحميل البيانات ومزامنتها الفورية دون الخروج من البوت
function refreshGameData() {
    // تحديث الأرقام والبيانات
    renderSettingsPage();
    
    // إظهار توست سريع لتأكيد التحديث للاعب بنجاح
    const toast = document.getElementById('toast-msg');
    if (toast) {
        toast.innerText = "🎮 تم تحديث البيانات بنجاح!";
        toast.style.display = 'block';
        setTimeout(() => {
            toast.innerText = "تم نسخ الـ ID بنجاح!";
            toast.style.display = 'none';
        }, 1500);
    }
}

// الحارس الصامت لضمان ملء الصفحة بمجرد انتقال المستخدم إليها في الـ Single Page App
setInterval(() => {
    const settingsSection = document.getElementById('main-settings-section');
    const usernameEl = document.getElementById('player-username');
    
    if (settingsSection && usernameEl) {
        if (settingsSection.style.display !== 'none' && window.getComputedStyle(settingsSection).display !== 'none' && usernameEl.innerText === "جاري التحميل...") {
            renderSettingsPage();
        }
    }
}, 300);
