(function initSettingsSystem() {
    
    // دالة آمنة لجلب المعرف الحقيقي من تليجرام WebApp
    function getTgId() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser) return String(webAppUser.id);
        }
        // معرف افتراضي للاختبار محلياً فقط في حال عدم وجود بيئة التليجرام
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

    // الدالة الأساسية: تذهب للسيرفر وتجلب أرقام الـ Firebase الحقيقية وتعرضها فوراً
    async function fetchAndRenderData() {
        const telegramId = getTgId();
        
        // تعبئة البيانات المبدئية المتاحة من التليجرام قبل رد السيرفر
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
            // عمل طلب Fetch مباشر للسيرفر لقراءة حقول الفايربيس
            let response = await fetch(`/api/user_data?telegramId=${telegramId}`);
            let result = await response.json();

            if (result.success && result.data) {
                const userData = result.data;

                // حفظ نسخة احتياطية في كائن اللعبة العام
                window.PlayerData = userData;

                // 🔥 الإصلاح السحري: جمع كافة مستويات الكروت المفتوحة الفردية (lvl1_count إلى lvl10_count)
                let totalUpgradesCount = 0;
                for (let i = 1; i <= 10; i++) {
                    totalUpgradesCount += parseInt(userData[`lvl${i}_count`] || 0);
                }

                // قراءة مستوى المخزن الفعلي بشكل منفصل وخاص به
                let currentStorage = parseInt(userData.storage_level || 0);

                // ربط الأرقام الحقيقية المجمعة بعناصر واجهة الإعدادات
                const totalMiningEl = document.getElementById('stat-total-mining');
                const storageLevelEl = document.getElementById('stat-storage-level');

                // الآن ستعرض عدد الترقيات الفعلي (مثال: 5) بدلاً من مستوى المخزن
                if (totalMiningEl) totalMiningEl.innerText = `${totalUpgradesCount} ترقيات`;
                if (storageLevelEl) storageLevelEl.innerText = `مستوى ${currentStorage}`;
                
                console.log(`✅ المزامنة تمت بنجاح! إجمالي الترقيات: ${totalUpgradesCount} | المخزن: ${currentStorage}`);
            } else {
                console.error("⚠️ فشل في قراءة استجابة السيرفر");
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

    // زر تحديث اللعبة: يقوم بعمل ريفرش كامل وإعادة تحميل لحل مشاكل ضعف النت والتهنيج
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

    // فاحص صامت لتحديث الصفحة بشكل دوري لتفادي أي بطء في الشبكة عند الفتح لأول مرة
    setInterval(() => {
        const totalMiningEl = document.getElementById('stat-total-mining');
        if (totalMiningEl && totalMiningEl.innerText === "0 ترقيات") {
            fetchAndRenderData();
        }
    }, 2000);

})();
