(function initSettingsSystem() {
    
    // دالة لجلب المعرف الحقيقي من التليجرام أو الكائن العام للعبة فوراً
    function getTgId() {
        if (window.PlayerData && window.PlayerData.telegram_id) {
            return String(window.PlayerData.telegram_id);
        }
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser) return String(webAppUser.id);
        }
        return "00000000"; 
    }

    // دالة لجلب اسم المستخدم الحقيقي من تليجرام
    function getPlayerName() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser) {
                return webAppUser.first_name + (webAppUser.last_name ? " " + webAppUser.last_name : "");
            }
        }
        return "اللاعب المحترف";
    }

    // دالة العرض الأساسية لبيانات الإعدادات الحية (تعتمد على window.PlayerData المتاح فوراً)
    window.renderSettingsPage = function() {
        const usernameEl = document.getElementById('player-username');
        const telegramIdEl = document.getElementById('player-telegram-id');
        const avatarEl = document.getElementById('player-avatar');

        if (usernameEl) usernameEl.innerText = getPlayerName();
        if (telegramIdEl) telegramIdEl.innerText = getTgId();
        
        // جلب الصورة الشخصية من تليجرام لو كانت متوفرة في حساب المستخدم
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser && webAppUser.photo_url && avatarEl) {
                avatarEl.innerHTML = `<img src="${webAppUser.photo_url}" style="width:100%; height:100%; object-fit:cover;">`;
            }
        }

        // قراءة البيانات وعرض الإحصائيات فوراً
        updateStatsDisplay();
    };

    // دالة قراءة الإحصائيات الحقيقية من قاعدة البيانات المعروضة في window.PlayerData
    function updateStatsDisplay() {
        const totalMiningEl = document.getElementById('stat-total-mining');
        const storageLevelEl = document.getElementById('stat-storage-level');

        // سحب البيانات من الكائن الرئيسي الموحد المحمل في خلفية البوت
        const data = window.PlayerData || {};
        
        // حساب إجمالي مستويات ترقيات التعدين من lvl1 لـ lvl10 المخزنة في الـ Firebase
        let totalUpgradesCount = 0;
        for (let i = 1; i <= 10; i++) {
            totalUpgradesCount += parseInt(data[`lvl${i}_count`] || 0);
        }

        // جلب مستوى المخزن الفعلي
        let currentStorage = parseInt(data.storage_level || 0);

        // تحديث النصوص في الواجهة تلقائياً
        if (totalMiningEl) totalMiningEl.innerText = `${totalUpgradesCount} / 150`;
        if (storageLevelEl) storageLevelEl.innerText = `مستوى ${currentStorage}`;
    }

    // دالة نسخ الـ ID المطور مع إظهار توست تأكيدي سيعجب اللاعب
    window.copyPlayerId = function() {
        const idText = document.getElementById('player-telegram-id').innerText;
        navigator.clipboard.writeText(idText).then(() => {
            showToast("تم نسخ الـ ID بنجاح! 📋");
        }).catch(err => {
            console.error('فشل في نسخ النص: ', err);
        });
    };

    // دوال النوافذ المنبثقة لسياسة الاستخدام
    window.showPrivacyModal = function() {
        const modal = document.getElementById('settings-modal');
        if (modal) modal.style.display = 'flex';
    };

    window.closeSettingsModal = function() {
        const modal = document.getElementById('settings-modal');
        if (modal) modal.style.display = 'none';
    };

    // دالة إظهار رسائل التوست السريعة والاحترافية بالأسفل
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

    // تنفيذ طلبك بالظبط: زر التحديث يقوم بعمل ريفرش كامل للبوت وإعادة تحميل لتصحيح التهنيج وبطء النت
    window.refreshGameData = function() {
        showToast("🔄 جاري إعادة تحميل وتحديث اللعبة بالكامل...");
        setTimeout(() => {
            window.location.reload(); // عمل Refresh حقيقي وكامل لكل الملفات والبيانات من السيرفر
        }, 800);
    };

    // فاحص وتحديث صامت ذكي بمجرد تحول المستخدم لصفحة الإعدادات للتأكد من قراءة الأرقام الحقيقية فوراً
    setInterval(() => {
        const settingsSection = document.getElementById('main-settings-section');
        const usernameEl = document.getElementById('player-username');
        
        if (settingsSection && usernameEl) {
            // إذا كانت الصفحة ظاهرة أمام المستخدم والنص لا زال يعرض "جاري التحميل..."
            if (settingsSection.style.display !== 'none' && 
                window.getComputedStyle(settingsSection).display !== 'none' && 
                usernameEl.innerText === "جاري التحميل...") {
                window.renderSettingsPage();
            }
        }
    }, 200);

    // تشغيل فوري وتلقائي عند استدعاء الملف لعدم الانتظار
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        setTimeout(window.renderSettingsPage, 100);
    } else {
        document.addEventListener('DOMContentLoaded', window.renderSettingsPage);
    }

})();
