(function initSettingsSystem() {
    
    // دالة آمنة لجلب المعرف الحقيقي من تليجرام WebApp
    function getTgId() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser) return String(webAppUser.id);
        }
        // معرف افتراضي للاختبار محلياً في حال عدم وجود بيئة تليجرام حية
        return "5102387551"; 
    }

    // دالة لجلب اسم اللاعب الحقيقي من تليجرام
    function getPlayerName() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser) {
                return webAppUser.first_name + (webAppUser.last_name ? " " + webAppUser.last_name : "");
            }
        }
        return "اللاعب المحترف";
    }

    // الدالة الأساسية: تجلب البيانات وتجمع مستويات الترقيات فقط وتعرضها
    async function fetchAndRenderData() {
        const telegramId = getTgId();
        
        // تعبئة البيانات المبدئية المتاحة من التليجرام فوراً
        const usernameEl = document.getElementById('player-username');
        const telegramIdEl = document.getElementById('player-telegram-id');
        const avatarEl = document.getElementById('player-avatar');

        if (usernameEl) usernameEl.innerText = getPlayerName();
        if (telegramIdEl) telegramIdEl.innerText = telegramId;

        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser && webAppUser.photo_url && avatarEl) {
                avatarEl.innerHTML = `<img src="${webAppUser.photo_url}" style="width:100%; height:100%; object-fit:cover;">`;
            }
        }

        try {
            // طلب fetch مباشر للسيرفر لقراءة حقول الفايربيس
            let response = await fetch(`/api/user_data?telegramId=${telegramId}`);
            let result = await response.json();

            if (result.success && result.data) {
                const userData = result.data;

                // حفظ البيانات في الكائن العام للاحتياط
                window.PlayerData = userData;

                // حساب إجمالي مستويات الكروت والترقيات المفتوحة (من لفل 1 لـ لفل 10)
                let totalUpgradesCount = 0;
                for (let i = 1; i <= 10; i++) {
                    totalUpgradesCount += parseInt(userData[`lvl${i}_count`] || 0);
                }

                // ربط الرقم الحقيقي المجمع بعنصر الواجهة
                const totalMiningEl = document.getElementById('stat-total-mining');
                if (totalMiningEl) {
                    totalMiningEl.innerText = `${totalUpgradesCount} مستويات`;
                }
                
                console.log(`✅ تمت المزامنة! إجمالي المستويات والترقيات الفعلي: ${totalUpgradesCount}`);
            } else {
                console.error("⚠️ فشل في قراءة استجابة السيرفر أو البيانات ناقصة");
            }
        } catch (error) {
            console.error("❌ خطأ أثناء جلب البيانات من الفايربيس:", error);
        }
    }

    // دالة نسخ الـ ID وإظهار رسالة توست تأكيدية
    window.copyPlayerId = function() {
        const idText = document.getElementById('player-telegram-id').innerText;
        navigator.clipboard.writeText(idText).then(() => {
            showToast("تم نسخ الـ ID بنجاح! 📋");
        }).catch(err => {
            console.error('فشل في نسخ النص: ', err);
        });
    };

    // دوال النوافذ المنبثقة لشروط الاستخدام
    window.showPrivacyModal = function() {
        const modal = document.getElementById('settings-modal');
        if (modal) modal.style.display = 'flex';
    };

    window.closeSettingsModal = function() {
        const modal = document.getElementById('settings-modal');
        if (modal) modal.style.display = 'none';
    };

    // دالة إظهار رسائل التوست المنبثقة
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

    // زر التحديث: يعمل ريفرش كامل للبوت لحل مشاكل تهنيج وبطء النت
    window.refreshGameData = function() {
        showToast("🔄 جاري إعادة تحميل وتحديث اللعبة بالكامل...");
        setTimeout(() => {
            window.location.reload(); 
        }, 800);
    };

    // التشغيل التلقائي والمباشر فور تحميل الصفحة لضمان سحب البيانات فوراً
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        fetchAndRenderData();
    } else {
        document.addEventListener('DOMContentLoaded', fetchAndRenderData);
    }

    // فاحص صامت لتحديث الصفحة بشكل دوري في حال تأخر السيرفر
    setInterval(() => {
        const totalMiningEl = document.getElementById('stat-total-mining');
        if (totalMiningEl && totalMiningEl.innerText === "0 مستويات") {
            fetchAndRenderData();
        }
    }, 2000);

})();
