(function initSettingsSystem() {
    
    function getTgId() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser) return String(webAppUser.id);
        }
        return "5102387551"; 
    }

    function getPlayerName() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser) {
                return webAppUser.first_name + (webAppUser.last_name ? " " + webAppUser.last_name : "");
            }
        }
        return "اللاعب المحترف";
    }

    // 🔒 تحديث الدالة لترسل وتستعلم بالبيانات المشفرة حتماً
    async function fetchAndRenderData() {
        const telegramId = getTgId();
        const initData = window.Telegram?.WebApp?.initData; // 🔒
        
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
            let url = `/api/user_data`;
            if (initData) {
                url += `?initData=${encodeURIComponent(initData)}`;
            } else {
                url += `?telegramId=${telegramId}`; // فحص محلي
            }

            let response = await fetch(url);
            let result = await response.json();

            if (result.success && result.data) {
                const userData = result.data;
                window.PlayerData = userData;

                let totalUpgradesCount = 0;
                for (let i = 1; i <= 10; i++) {
                    totalUpgradesCount += parseInt(userData[`lvl${i}_count`] || 0);
                }

                const totalMiningEl = document.getElementById('stat-total-mining');
                if (totalMiningEl) {
                    totalMiningEl.innerText = `${totalUpgradesCount} مستويات`;
                }
                
                console.log(`✅ تمت المزامنة الآمنة! إجمالي مستويات الترقيات: ${totalUpgradesCount}`);
            } else {
                console.error("⚠️ فشل في قراءة استجابة السيرفر أو البيانات ناقصة");
            }
        } catch (error) {
            console.error("❌ خطأ أثناء جلب البيانات من الفايربيس:", error);
        }
    }

    window.copyPlayerId = function() {
        const idText = document.getElementById('player-telegram-id').innerText;
        navigator.clipboard.writeText(idText).then(() => {
            showToast("تم نسخ الـ ID بنجاح! 📋");
        }).catch(err => {
            console.error('فشل في نسخ النص: ', err);
        });
    };

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

    window.refreshGameData = function() {
        showToast("🔄 جاري إعادة تحميل وتحديث اللعبة بالكامل...");
        setTimeout(() => {
            window.location.reload(); 
        }, 800);
    };

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        fetchAndRenderData();
    } else {
        document.addEventListener('DOMContentLoaded', fetchAndRenderData);
    }

    setInterval(() => {
        const totalMiningEl = document.getElementById('stat-total-mining');
        if (totalMiningEl && totalMiningEl.innerText === "0 مستويات") {
            fetchAndRenderData();
        }
    }, 2000);

})();
