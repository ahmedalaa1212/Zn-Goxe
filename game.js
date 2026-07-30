// =================================================================
// 🎮 ZN Goxe - Core Game Engine & Universal Realtime State Manager
// =================================================================

(function initGameEngine() {
    'use strict';

    // 1. تهيئة تطبيق التليجرام Mini App
    const tg = window.Telegram?.WebApp;
    if (tg) {
        tg.ready();
        tg.expand();
    }

    // 2. الحجم والبيانات الافتراضية
    const rawUser = tg?.initDataUnsafe?.user;
    const defaultUserId = rawUser?.id ? String(rawUser.id) : '';
    const defaultUsername = rawUser?.username || rawUser?.first_name || 'Goxe User';

    // 3. الحالة الكلية للعبة (Internal Raw Target)
    const rawState = {
        user_id: defaultUserId,
        username: defaultUsername,
        balance: 0,
        usd_balance: 0,
        ad_balance: 0,
        hourly_rate: 0,
        energy: 1000,
        max_energy: 1000,
        is_syncing: false,
        is_initialized: false
    };

    // 4. دالة المصادقة الآمنة لجلب الـ Payload
    window.getAuthPayload = function(extraData = {}) {
        const initData = window.Telegram?.WebApp?.initData || '';
        const currentUserId = window.GameState?.user_id || defaultUserId;
        return {
            initData: initData,
            tg_id: String(currentUserId),
            ...extraData
        };
    };

    // 5. محرك التحديث الموحد لجميع واجهات التطبيق (Universal UI Updater)
    window.updateGlobalUI = function() {
        if (!window.GameState) return;

        const zn = Number(window.GameState.balance) || 0;
        const usd = Number(window.GameState.usd_balance) || 0;
        const speed = Number(window.GameState.hourly_rate) || 0;

        // تنسيق الأرقام
        const formattedZN = Math.floor(zn).toLocaleString('en-US');
        const formattedUSD = "$" + (usd > 0 && usd < 0.01 ? usd.toFixed(5) : usd.toFixed(4));
        const formattedSpeed = "h/" + Math.floor(speed).toLocaleString('en-US');

        // قائمة بجميع الـ IDs المحتملة لرصيد النقاط ZN عبر كل الصفحات (المهمات، المتجر، المحفظة، المزرعة)
        const znSelectors = [
            '#user-zn-balance', '#zn-balance', '#wallet-zn-balance', 
            '#top-zn-balance', '#farm-zn-balance', '#task-zn-balance',
            '#store-zn-balance', '.zn-balance-value', '.global-zn-display'
        ];

        // قائمة بجميع الـ IDs المحتملة لرصيد الدولار USD
        const usdSelectors = [
            '#user-usd-balance', '#usd-balance', '#wallet-usd-balance', 
            '#store-usd-balance', '#top-usd-balance', '.usd-balance-value', 
            '.global-usd-display'
        ];

        // قائمة بجميع الـ IDs المحتملة للسرعة hourly_rate
        const speedSelectors = [
            '#user-hourly-rate', '#hourly-rate', '#store-hourly-rate', 
            '#farm-speed-rate', '.speed-rate-value'
        ];

        // تحديث عناصر ZN
        znSelectors.forEach(selector => {
            document.querySelectorAll(selector).forEach(el => {
                if (el.tagName === 'INPUT') {
                    el.value = formattedZN;
                } else {
                    // إذا كان العنصر يحتوى على نص داخلي مثل ZN 0
                    if (el.classList.contains('text-formatted') || el.dataset.prefix) {
                        el.innerText = (el.dataset.prefix || '') + formattedZN + (el.dataset.suffix || '');
                    } else {
                        el.innerText = formattedZN;
                    }
                }
            });
        });

        // تحديث عناصر USD
        usdSelectors.forEach(selector => {
            document.querySelectorAll(selector).forEach(el => {
                if (el.tagName === 'INPUT') el.value = formattedUSD;
                else el.innerText = formattedUSD;
            });
        });

        // تحديث عناصر السرعة
        speedSelectors.forEach(selector => {
            document.querySelectorAll(selector).forEach(el => {
                if (el.tagName === 'INPUT') el.value = formattedSpeed;
                else el.innerText = formattedSpeed;
            });
        });

        // استدعاء تحديث المحفظة إذا كانت دالتها محملة
        if (typeof window.updateWalletHeaderUI === 'function') {
            window.updateWalletHeaderUI();
        }
    };

    // 6. إنشاء Proxy ذكي لمراقبة أي تغيير في GameState وتحديث الشاشات فوراً
    window.GameState = new Proxy(rawState, {
        set(target, prop, value) {
            target[prop] = value;
            
            // عند تعديل أي قيمة مالية أو رئيسية، يتم استدعاء التحديث اللحظي للـ UI فوراً
            if (['balance', 'usd_balance', 'ad_balance', 'hourly_rate', 'energy'].includes(prop)) {
                window.updateGlobalUI();
            }
            return true;
        }
    });

    // 7. دالة المزامنة المباشرة مع سيرفر Flask / Firestore
    window.syncGameState = async function() {
        if (!window.apiCall || rawState.is_syncing) return;
        rawState.is_syncing = true;

        try {
            const payload = window.getAuthPayload();
            const res = await window.apiCall('/api/farm/sync', 'POST', payload);

            if (res && res.success && res.data) {
                const data = res.data;
                if (data.balance !== undefined) window.GameState.balance = Number(data.balance);
                if (data.usd_balance !== undefined) window.GameState.usd_balance = Number(data.usd_balance);
                if (data.ad_balance !== undefined) window.GameState.ad_balance = Number(data.ad_balance);
                if (data.hourly_rate !== undefined) window.GameState.hourly_rate = Number(data.hourly_rate);
                if (data.energy !== undefined) window.GameState.energy = Number(data.energy);
                if (data.max_energy !== undefined) window.GameState.max_energy = Number(data.max_energy);
                
                window.GameState.is_initialized = true;
                window.updateGlobalUI();
            }
        } catch (err) {
            console.error("Game state sync error:", err);
        } finally {
            rawState.is_syncing = false;
        }
    };

    // 8. التنقل الموحد بين القوائم والمجلدات
    window.switchTab = function(tabName) {
        if (tg && tg.HapticFeedback) {
            tg.HapticFeedback.impactOccurred('light');
        }

        const navBtns = document.querySelectorAll('.nav-btn, .footer-btn, [data-tab]');
        navBtns.forEach(btn => {
            if (btn.dataset.tab === tabName || btn.id === `nav-${tabName}`) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        const sections = document.querySelectorAll('.tab-content, .page-section');
        sections.forEach(sec => {
            if (sec.id === `tab-${tabName}` || sec.id === `${tabName}-section`) {
                sec.style.display = 'block';
            } else {
                sec.style.display = 'none';
            }
        });

        // مزامنة فورية عند تغيير التبويب لتأكيد ظهور الرصيد الصحيح
        window.updateGlobalUI();
    };

    // 9. تشغيل المزامنة التلقائية عند التحميل ودورياً كل 10 ثوانٍ
    document.addEventListener('DOMContentLoaded', () => {
        window.updateGlobalUI();
        window.syncGameState();
        
        // مزامنة خلفية كل 10 ثوانٍ لضمان استقرار الأرصدة
        setInterval(() => {
            window.syncGameState();
        }, 10000);
    });

    // تشغيل فوري في حال تم تحميل Script بعد DOMContentLoaded
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        window.updateGlobalUI();
        window.syncGameState();
    }

})();
