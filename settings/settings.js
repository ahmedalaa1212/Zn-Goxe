(function initSettingsSystem() {
    // جلب الـ ID الحقيقي من النظام أو من تليجرام مباشرة
    function getTgId() {
        if (window.PlayerData && window.PlayerData.telegram_id) {
            return window.PlayerData.telegram_id;
        }
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser) return String(webAppUser.id);
        }
        return "5102387551"; // معرف افتراضي للاختبار في حال عدم توفر البيئة
    }

    // جلب اسم المستخدم الحقيقي
    function getPlayerName() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser) {
                return webAppUser.first_name + (webAppUser.last_name ? " " + webAppUser.last_name : "");
            }
        }
        return "اللاعب المحترف";
    }

    // دالة العرض الأساسية لبيانات الإعدادات
    window.renderSettingsPage = function() {
        const usernameEl = document.getElementById('player-username');
        const telegramIdEl = document.getElementById('player-telegram-id');
        const avatarEl = document.getElementById('player-avatar');

        if (usernameEl) usernameEl.innerText = getPlayerName();
        if (telegramIdEl) telegramIdEl.innerText = getTgId();
        
        // محاولة جلب الصورة الشخصية من تليجرام لو متاحة
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser && webAppUser.photo_url && avatarEl) {
                avatarEl.innerHTML = `<img src="${webAppUser.photo_url}" style="width:100%; height:100%; object-fit:cover;">`;
            }
        }

        // حساب وعرض الإحصائيات الحقيقية القادمة من السيرفر
        updateStatsDisplay();
    };

    // دالة حساب الإحصائيات من البيانات الحقيقية لـ PlayerData المربوطة بالسيرفر
    function updateStatsDisplay() {
        const totalMiningEl = document.getElementById('stat-total-mining');
        const storageLevelEl = document.getElementById('stat-storage-level');

        // قراءة البيانات الحقيقية المسحوبة من الـ Firebase
        const data = window.PlayerData || {};
        
        // حساب إجمالي مستويات ترقيات التعدين من lvl1 لـ lvl10
        let totalUpgradesCount = 0;
        for (let i = 1; i <= 10; i++) {
            totalUpgradesCount += parseInt(data[`lvl${i}_count`] || 0);
        }

        let currentStorage = parseInt(data.storage_level || 0);

        if (totalMiningEl) totalMiningEl.innerText = `${totalUpgradesCount} / 150`; // الحد الأقصى 15 لكل لفل * 10 لفلات = 150
        if (storageLevelEl) storageLevelEl.innerText = `مستوى ${currentStorage}`;
    }

    // دالة نسخ الـ ID الشيك والاحترافية مع إظهار توست تأكيدي
    window.copyPlayerId = function() {
        const idText = document.getElementById('player-telegram-id').innerText;
        navigator.clipboard.writeText(idText).then(() => {
            showToast("تم نسخ الـ ID بنجاح! 📋");
        }).catch(err => {
            console.error('فشل في نسخ النص: ', err);
        });
    };

    // دوال التحكم في النوافذ المنبثقة للسياسات والشروط
    window.showPrivacyModal = function() {
        const modal = document.getElementById('settings-modal');
        if (modal) modal.style.display = 'flex';
    };

    window.closeSettingsModal = function() {
        const modal = document.getElementById('settings-modal');
        if (modal) modal.style.display = 'none';
    };

    // دالة إظهار التوست بشكل مرن
    function showToast(text) {
        const toast = document.getElementById('toast-msg');
        if (toast) {
            toast.innerText = text;
            toast.style.display = 'block';
            setTimeout(() => {
                toast.style.display = 'none';
            }, 2000);
        }
    }

    // ميزة احترافية: إعادة تحميل البيانات ومزامنتها الفورية من السيرفر مباشرة دون الخروج من البوت
    window.refreshGameData = async function() {
        showToast("🔄 جاري تحديث البيانات من السيرفر...");
        
        try {
            // عمل طلب Fetch حقيقي للسيرفر لجلب أحدث البيانات المسجلة في Firebase
            let response = await fetch(`/api/user_data?telegramId=${getTgId()}`);
            let result = await response.json();

            if (result.success && result.data) {
                // تحديث البيانات على مستوى اللعبة بالكامل
                window.PlayerData = result.data;
                
                // إعادة رسم بيانات صفحة الإعدادات
                window.renderSettingsPage();
                
                // تحديث واجهة الرصيد الأساسية باللعبة لو كانت الدالة متوفرة
                if (typeof window.triggerAllUIUpdates === 'function') {
                    window.triggerAllUIUpdates();
                }
                
                showToast("🎮 تم تحديث البيانات بنجاح!");
            } else {
                showToast("⚠️ فشل تحديث البيانات من السيرفر");
            }
        } catch (e) {
            console.error("Error refreshing data:", e);
            showToast("❌ خطأ في الاتصال بالسيرفر!");
        }
    };

    // نظام المراقبة التلقائي للتأكد من تعبئة البيانات فور فتح القسم
    setInterval(() => {
        const settingsSection = document.getElementById('main-settings-section');
        const usernameEl = document.getElementById('player-username');
        
        if (settingsSection && usernameEl) {
            // لو القسم معروض ومكتوب جاري التحميل، نقوم بالرسم فوراً
            if (settingsSection.style.display !== 'none' && 
                window.getComputedStyle(settingsSection).display !== 'none' && 
                usernameEl.innerText === "جاري التحميل...") {
                window.renderSettingsPage();
            }
        }
    }, 300);

    // تشغيل مبدئي سريع
    setTimeout(window.renderSettingsPage, 500);
})();
