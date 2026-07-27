(function initSettingsSystem() {
    
    function getTgUser() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            // التخلص من ?. لدعم الهواتف القديمة ومنع كسر الأكواد
            if (window.Telegram.WebApp.initDataUnsafe && window.Telegram.WebApp.initDataUnsafe.user) {
                return window.Telegram.WebApp.initDataUnsafe.user;
            }
        }
        return null;
    }

    function getTgId() {
        const user = getTgUser();
        return user ? String(user.id) : "5102387551"; // Fallback for testing
    }

    function getPlayerName() {
        const user = getTgUser();
        if (user) {
            return user.first_name + (user.last_name ? " " + user.last_name : "");
        }
        return "اللاعب المحترف";
    }

    // 🔒 تحديث الدالة لترسل البيانات في الـ Headers لضمان أقصى درجات الأمان
    async function fetchAndRenderData() {
        const telegramId = getTgId();
        let initData = "";
        
        // استخراج التوقيع بأمان بدون كسر المتصفحات القديمة
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            initData = window.Telegram.WebApp.initData;
        }
        
        const usernameEl = document.getElementById('player-username');
        const telegramIdEl = document.getElementById('player-telegram-id');
        const avatarEl = document.getElementById('player-avatar');
        const totalMiningEl = document.getElementById('stat-total-mining');
        const totalStorageEl = document.getElementById('stat-total-storage');

        // طباعة البيانات الشخصية مباشرة بدون سيرفر للسرعة
        if (usernameEl) usernameEl.innerText = getPlayerName();
        if (telegramIdEl) telegramIdEl.innerText = telegramId;

        const user = getTgUser();
        if (user && user.photo_url && avatarEl) {
            avatarEl.innerHTML = `<img src="${user.photo_url}" style="width:100%; height:100%; object-fit:cover; border-radius:50%;">`;
        }

        // جلب الإحصائيات (المزرعة والمخزن) من السيرفر حصراً لمنع التلاعب
        if (!initData) {
            console.error("⚠️ فشل: لا يوجد initData، تأكد من فتح اللعبة داخل تليجرام.");
            if (totalMiningEl) totalMiningEl.innerText = "0 مستويات (تجريبي)";
            if (totalStorageEl) totalStorageEl.innerText = "0 مستويات (تجريبي)";
            return;
        }

        try {
            // استدعاء الرابط المباشر الذي يدمجه السيرفر بنجاح الآن
            let response = await fetch('/api/settings/stats', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': initData // 🔒 إرسال التوقيع في الهيدر
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            let result = await response.json();

            if (result.success) {
                if (totalMiningEl) {
                    totalMiningEl.innerText = `${result.farm_levels_count} مستويات`;
                    totalMiningEl.style.color = "#00cc66"; // إعادة اللون للطبيعي
                }
                if (totalStorageEl) {
                    totalStorageEl.innerText = `${result.storage_levels_count} مستويات`;
                    totalStorageEl.style.color = "#0088cc"; // إعادة اللون للطبيعي
                }
                console.log("✅ تمت مزامنة الإحصائيات بأمان من السيرفر!");
            } else {
                console.error("⚠️ السيرفر رفض الطلب أو البيانات غير متاحة:", result.message);
                if (totalMiningEl) totalMiningEl.innerText = "0 مستويات";
                if (totalStorageEl) totalStorageEl.innerText = "0 مستويات";
            }
        } catch (error) {
            console.error("❌ خطأ أثناء جلب البيانات من السيرفر:", error);
            if (totalMiningEl) {
                totalMiningEl.innerText = "خطأ في الاتصال";
                totalMiningEl.style.color = "#ff4444";
            }
            if (totalStorageEl) {
                totalStorageEl.innerText = "خطأ في الاتصال";
                totalStorageEl.style.color = "#ff4444";
            }
        }
    }

    // دعم أقوى لعملية النسخ داخل متصفح تيليجرام
    window.copyPlayerId = function() {
        const idText = document.getElementById('player-telegram-id').innerText;
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(idText).then(() => {
                showToast("تم نسخ الـ ID بنجاح! 📋");
            }).catch(err => {
                console.error('فشل في نسخ النص: ', err);
                fallbackCopyTextToClipboard(idText);
            });
        } else {
            fallbackCopyTextToClipboard(idText);
        }
    };

    function fallbackCopyTextToClipboard(text) {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        textArea.style.position = "fixed"; 
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        try {
            document.execCommand('copy');
            showToast("تم نسخ الـ ID بنجاح! 📋");
        } catch (err) {
            console.error('Fallback: فشل النسخ', err);
        }
        document.body.removeChild(textArea);
    }

    window.showPrivacyModal = function() {
        const modal = document.getElementById('settings-modal');
        if (modal) modal.style.display = 'flex';
    };

    window.closeSettingsModal = function() {
        const modal = document.getElementById('settings-modal');
        if (modal) modal.style.display = 'none';
    };

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

    // لضمان استدعاء الدالة بعد اكتمال تحميل التليجرام ويب آب
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        setTimeout(fetchAndRenderData, 100);
    } else {
        document.addEventListener('DOMContentLoaded', () => {
            setTimeout(fetchAndRenderData, 100);
        });
    }

    // نظام Retry ذكي: سيحاول التحديث فقط إذا كانت النتيجة "جاري التحميل" أو "خطأ" 
    // للحفاظ على موارد الفايربيس من الطلبات الوهمية
    setInterval(() => {
        const totalMiningEl = document.getElementById('stat-total-mining');
        if (totalMiningEl && (totalMiningEl.innerText.includes("جاري") || totalMiningEl.innerText.includes("خطأ"))) {
            fetchAndRenderData();
        }
    }, 5000);

})();
