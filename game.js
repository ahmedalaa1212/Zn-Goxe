// ==========================================
// 1. التهيئة والتخزين المحلي (Local-First Architecture)
// ==========================================
const tg = window.Telegram?.WebApp || null;

if (tg) {
    tg.ready();
    tg.expand();

    if (typeof tg.enableClosingConfirmation === "function") {
        tg.enableClosingConfirmation();
    }
}

window.currentTonPriceUSD =
    parseFloat(localStorage.getItem("last_ton_price")) || 6.5;
window.serverTimeOffset = 0;

window.formatTime = function (seconds) {
    if (isNaN(seconds) || seconds <= 0) return "0s";

    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);

    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
};

function hideLoadingScreen() {
    const appEl = document.getElementById("app");
    const navEl = document.getElementById("main-nav");

    if (appEl) appEl.style.display = "block";
    if (navEl) navEl.style.display = "flex";

    const loaders = document.querySelectorAll(
        "#loading-screen, .loading-screen, #loader"
    );

    loaders.forEach((el) => {
        el.style.opacity = "0";
        el.style.transition = "opacity 0.3s ease";
        setTimeout(() => el.remove(), 300);
    });
}

function getSavedState() {
    const startParam = tg?.initDataUnsafe?.start_param || null;

    const base = {
        tg_id: tg?.initDataUnsafe?.user?.id || null,
        first_name: tg?.initDataUnsafe?.user?.first_name || "لاعب",
        referred_by_param: startParam,
        balance: 0.0,
        usd_balance: 0.0,
        ad_balance: 0.0,
        hourly_rate: 0.0,
        energy: 100,
        storage_level: 0,
        extra_storage: 0.0,
        max_cap: 100.0,
        unclaimed: 0.0,
        daily_streak: 1,
        daily_day: 1,
        last_daily_claim_date: null,
        upgrades: {},
        wallet_address: null,
        boost_multiplier: 1,
        boost_active: false,
        boost_expires_at: null,
        last_claim_time: null,
        last_sync_time: Date.now(),
    };

    try {
        const saved = localStorage.getItem("app_user_state");
        if (saved) {
            const parsed = JSON.parse(saved);
            return { ...base, ...parsed };
        }
    } catch (error) {
        console.warn("فشل قراءة app_user_state:", error);
    }

    return base;
}

let isFirebaseUpdating = false;
let saveDebounceTimer = null;

function persistUserStateToLocalStorage(state) {
    try {
        localStorage.setItem("app_user_state", JSON.stringify(state));
    } catch (error) {
        console.warn("فشل الحفظ في localStorage:", error);
    }
}

window.userState = new Proxy(getSavedState(), {
    set(target, prop, value) {
        if (
            [
                "balance",
                "usd_balance",
                "ad_balance",
                "hourly_rate",
                "extra_storage",
                "max_cap",
                "unclaimed",
            ].includes(prop)
        ) {
            const num = parseFloat(value);
            target[prop] = Number.isNaN(num) ? 0.0 : num;
        } else {
            target[prop] = value;
        }

        if (!window.PlayerData) {
            window.PlayerData = {};
        }

        window.PlayerData[prop] = target[prop];

        if (
            [
                "balance",
                "usd_balance",
                "ad_balance",
                "hourly_rate",
                "energy",
                "storage_level",
                "extra_storage",
                "max_cap",
                "daily_streak",
                "daily_day",
                "upgrades",
                "last_claim_time",
                "unclaimed",
                "boost_multiplier",
                "boost_active",
                "boost_expires_at",
            ].includes(prop)
        ) {
            if (!isFirebaseUpdating) {
                if (saveDebounceTimer) {
                    clearTimeout(saveDebounceTimer);
                }

                saveDebounceTimer = setTimeout(() => {
                    persistUserStateToLocalStorage(target);
                }, 500);
            }

            if (typeof window.updateUI === "function") {
                window.updateUI();
            }

            if (typeof window.updateFarmUI === "function") {
                window.updateFarmUI();
            }

            window.dispatchEvent(
                new CustomEvent("userStateUpdated", { detail: target })
            );
        }

        return true;
    },
});

window.addEventListener("beforeunload", () => {
    persistUserStateToLocalStorage(window.userState);
});


// ==========================================
// 2. الاتصال بالسيرفر ومعالجة الاستجابة
// ==========================================
window.fetchAPI = async function (endpoint, method = "GET", bodyData = null) {
    const headers = {};

    if (bodyData !== null && method !== "GET" && method !== "HEAD") {
        headers["Content-Type"] = "application/json";
    }

    if (tg?.initData) {
        headers["X-Telegram-Init-Data"] = tg.initData;
        headers["Authorization"] = `Bearer ${tg.initData}`;
    }

    try {
        const fetchOptions = {
            method,
            headers,
        };

        if (method !== "GET" && method !== "HEAD" && bodyData !== null) {
            fetchOptions.body = JSON.stringify(bodyData);
        }

        const res = await fetch(endpoint, fetchOptions);

        let data = {};
        const contentType = res.headers.get("content-type") || "";

        if (contentType.includes("application/json")) {
            data = await res.json();
        } else {
            const text = await res.text();
            data = {
                success: false,
                error: text || `HTTP ${res.status}`,
            };
        }

        if (!res.ok) {
            if (
                res.status === 403 &&
                String(data.error || "").includes("محظور")
            ) {
                alert("حسابك محظور.");
                tg?.close();
            }

            throw new Error(data.error || `HTTP ${res.status}`);
        }

        if (data.server_time) {
            const serverMs = new Date(data.server_time).getTime();

            if (!Number.isNaN(serverMs)) {
                window.serverTimeOffset = serverMs - Date.now();
            }
        }

        const targetObj =
            data.player ||
            data.user ||
            data.data ||
            (data.balance !== undefined ? data : null);

        if (targetObj) {
            isFirebaseUpdating = true;

            try {
                if (targetObj.balance !== undefined && targetObj.balance !== null) {
                    const balance = parseFloat(targetObj.balance);
                    if (!Number.isNaN(balance)) {
                        window.userState.balance = balance;
                    }
                }

                if (
                    targetObj.usd_balance !== undefined &&
                    targetObj.usd_balance !== null
                ) {
                    const usd = parseFloat(targetObj.usd_balance);
                    if (!Number.isNaN(usd)) {
                        window.userState.usd_balance = usd;
                    }
                }

                if (
                    targetObj.ad_balance !== undefined &&
                    targetObj.ad_balance !== null
                ) {
                    const ad = parseFloat(targetObj.ad_balance);
                    if (!Number.isNaN(ad)) {
                        window.userState.ad_balance = ad;
                    }
                }

                if (targetObj.hourly_rate !== undefined) {
                    window.userState.hourly_rate =
                        parseFloat(targetObj.hourly_rate) || 0;
                }

                if (targetObj.storage_level !== undefined) {
                    window.userState.storage_level =
                        parseInt(targetObj.storage_level, 10) || 0;
                }

                if (targetObj.extra_storage !== undefined) {
                    window.userState.extra_storage =
                        parseFloat(targetObj.extra_storage) || 0;
                }

                if (targetObj.max_cap !== undefined) {
                    window.userState.max_cap =
                        parseFloat(targetObj.max_cap) || 100;
                }

                if (targetObj.daily_streak !== undefined) {
                    window.userState.daily_streak =
                        parseInt(targetObj.daily_streak, 10) || 1;
                }

                if (targetObj.daily_day !== undefined) {
                    window.userState.daily_day =
                        parseInt(targetObj.daily_day, 10) || 1;
                }

                if (targetObj.last_daily_claim_date !== undefined) {
                    window.userState.last_daily_claim_date =
                        targetObj.last_daily_claim_date;
                }

                if (targetObj.last_claim_time !== undefined) {
                    window.userState.last_claim_time = targetObj.last_claim_time;
                }

                if (targetObj.upgrades !== undefined) {
                    window.userState.upgrades = targetObj.upgrades;
                }

                if (targetObj.unclaimed !== undefined) {
                    window.userState.unclaimed =
                        parseFloat(targetObj.unclaimed) || 0;
                }

                if (targetObj.boost_multiplier !== undefined) {
                    window.userState.boost_multiplier =
                        parseInt(targetObj.boost_multiplier, 10) || 1;
                }

                if (targetObj.boost_active !== undefined) {
                    window.userState.boost_active = Boolean(
                        targetObj.boost_active
                    );
                }

                if (targetObj.boost_expires_at !== undefined) {
                    window.userState.boost_expires_at =
                        targetObj.boost_expires_at;
                }
            } finally {
                isFirebaseUpdating = false;
                persistUserStateToLocalStorage(window.userState);
            }
        }

        return data;
    } catch (err) {
        console.error(`API Error [${endpoint}]:`, err);
        throw err;
    }
};


// ==========================================
// 3. جلب سعر TON المباشر
// ==========================================
window.fetchTonPrice = async function () {
    try {
        const res = await fetch(
            "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd"
        );

        if (res.ok) {
            const data = await res.json();

            if (data["the-open-network"]?.usd) {
                const price = parseFloat(data["the-open-network"].usd);

                if (!Number.isNaN(price)) {
                    window.currentTonPriceUSD = price;
                    localStorage.setItem("last_ton_price", price);
                }
            }
        }
    } catch (err) {
        console.warn(
            "⚠️ لم يتم جلب سعر TON من CoinGecko، تم استخدام السعر المحلي:",
            window.currentTonPriceUSD
        );
    } finally {
        window.updateTonPriceUI();
    }
};

window.updateTonPriceUI = function () {
    const formattedPrice = `$${window.currentTonPriceUSD.toFixed(2)}`;

    document
        .querySelectorAll(
            '#ton-price-display, .ton-price-val, [data-bind="ton_price"]'
        )
        .forEach((el) => {
            el.innerHTML = `<span dir="ltr" style="white-space:nowrap; font-weight:bold; color:#0088cc;">${formattedPrice}</span>`;
        });

    document
        .querySelectorAll("#packages-loading-status, .packages-status")
        .forEach((el) => {
            el.style.display = "none";
        });
};


// ==========================================
// 4. مشاهدة الإعلانات والمكافآت
// ==========================================
window.watchMonetagAd = async function () {
    if (typeof window.show_11322720 !== "function") {
        alert("جاري تحميل مكتبة الإعلانات، يرجى المحاولة بعد قليل...");
        return;
    }

    try {
        await window.show_11322720();

        const res = await window.fetchAPI("/api/farm/daily_boost", "POST");

        if (res.success) {
            alert("🎉 تم زيادة سرعة التعدين بنجاح!");
        } else {
            alert(res.error || "حدث خطأ أثناء إضافة المكافأة.");
        }
    } catch (err) {
        console.error("Ad cancelled or error:", err);
        alert("يجب إكمال الإعلان للنهاية للحصول على المكافأة.");
    }
};

window.claimDailyReward = async function () {
    try {
        const res = await window.fetchAPI("/api/farm/daily_claim", "POST");

        if (res.success) {
            if (res.new_balance !== undefined) {
                window.userState.balance = parseFloat(res.new_balance);
            }

            if (res.daily_day !== undefined) {
                window.userState.daily_day = res.daily_day;
                window.userState.daily_streak = res.daily_day;
            }

            alert(
                `🎁 مبروك! استلمت مكافأة اليوم. اليوم الحالي: ${res.daily_day}`
            );

            if (typeof window.onFarmTabOpen === "function") {
                window.onFarmTabOpen();
            }
        } else {
            alert(res.error || "لا يمكنك الاستلام الآن.");
        }
    } catch (err) {
        alert(err.message || "حدث خطأ أثناء استلام المكافأة.");
    }
};

window.activateTenXBoost = async function (durationHours = 1) {
    try {
        const res = await window.fetchAPI(
            "/api/farm/activate_boost",
            "POST",
            { duration_hours: durationHours }
        );

        if (res.success || res.status === "success") {
            alert(
                `🚀 تم تفعيل مضاعف الأرباح 10x بنجاح لمدة ${durationHours}h!`
            );

            if (typeof window.loadUserData === "function") {
                await window.loadUserData();
            }

            return true;
        }

        alert(res.error || res.message || "حدث خطأ أثناء تفعيل البوست.");
        return false;
    } catch (err) {
        console.error("Boost activation error:", err);
        alert("حدث خطأ أثناء الاتصال بالسيرفر لتفعيل البوست.");
        return false;
    }
};


// ==========================================
// 5. Firestore Realtime Sync
// ==========================================
window.initFirebaseRealtimeSync = function (userId) {
    if (!window.db || !userId || typeof window.db.collection !== "function") {
        return;
    }

    try {
        window.db
            .collection("users")
            .doc(String(userId))
            .onSnapshot(
                (doc) => {
                    if (!doc.exists) {
                        return;
                    }

                    const d = doc.data() || {};

                    try {
                        isFirebaseUpdating = true;

                        if (!window.PlayerData) {
                            window.PlayerData = {};
                        }

                        Object.assign(window.PlayerData, d);

                        if (d.balance !== undefined && d.balance !== null) {
                            const balance = parseFloat(d.balance);
                            if (!Number.isNaN(balance)) {
                                window.userState.balance = balance;
                            }
                        }

                        if (d.usd_balance !== undefined) {
                            window.userState.usd_balance =
                                parseFloat(d.usd_balance) || 0;
                        }

                        [
                            "ad_balance",
                            "hourly_rate",
                            "energy",
                            "storage_level",
                            "extra_storage",
                            "max_cap",
                            "daily_streak",
                            "daily_day",
                            "last_daily_claim_date",
                            "upgrades",
                            "last_claim_time",
                            "unclaimed",
                            "boost_multiplier",
                            "boost_active",
                            "boost_expires_at",
                        ].forEach((key) => {
                            if (d[key] !== undefined) {
                                window.userState[key] = d[key];
                            }
                        });

                        window.userState.last_sync_time = Date.now();
                    } finally {
                        isFirebaseUpdating = false;
                        persistUserStateToLocalStorage(window.userState);

                        window.updateUI();

                        if (typeof window.updateFarmUI === "function") {
                            window.updateFarmUI();
                        }

                        window.dispatchEvent(
                            new CustomEvent("userStateUpdated", {
                                detail: window.userState,
                            })
                        );
                    }
                },
                (error) => {
                    console.error("Firebase Sync Error:", error);
                }
            );
    } catch (error) {
        console.warn("Realtime sync omitted:", error);
    }
};


// ==========================================
// 6. دالة إدارة عداد التجميع
// ==========================================
let claimCooldownTimer = null;

window.updateClaimButtonState = function () {
    const claimButtons = document.querySelectorAll(
        '#claim-btn, .claim-btn, [data-action="claim"]'
    );

    if (!claimButtons.length) {
        return;
    }

    const COOLDOWN_SECONDS = 15;
    const lastClaimStr = window.userState.last_claim_time;
    const unclaimed = parseFloat(window.userState?.unclaimed || 0);
    const isFarmTab = document
        .getElementById("view-farm")
        ?.classList.contains("active");

    function renderButton(btn, disabled, text, className) {
        btn.disabled = disabled;
        btn.innerHTML = text;

        if (className) {
            btn.className = className;
        }
    }

    if (!lastClaimStr) {
        claimButtons.forEach((btn) => {
            if (isFarmTab && unclaimed <= 0) {
                renderButton(
                    btn,
                    true,
                    "المخزن فارغ ⏳",
                    "claim-action-btn btn-disabled"
                );
            } else {
                renderButton(
                    btn,
                    false,
                    "تجميع الرصيد 💰",
                    "claim-action-btn btn-ready"
                );
            }
        });

        if (claimCooldownTimer) {
            clearInterval(claimCooldownTimer);
            claimCooldownTimer = null;
        }

        return;
    }

    const lastClaimMs = new Date(lastClaimStr).getTime();

    if (Number.isNaN(lastClaimMs)) {
        claimButtons.forEach((btn) =>
            renderButton(
                btn,
                false,
                "تجميع الرصيد 💰",
                "claim-action-btn btn-ready"
            )
        );

        if (claimCooldownTimer) {
            clearInterval(claimCooldownTimer);
            claimCooldownTimer = null;
        }

        return;
    }

    const currentServerMs = Date.now() + (window.serverTimeOffset || 0);
    const secondsPassed = Math.floor(
        (currentServerMs - lastClaimMs) / 1000
    );
    const remainingSeconds = COOLDOWN_SECONDS - secondsPassed;

    if (remainingSeconds <= 0) {
        if (claimCooldownTimer) {
            clearInterval(claimCooldownTimer);
            claimCooldownTimer = null;
        }

        claimButtons.forEach((btn) => {
            if (isFarmTab && unclaimed <= 0) {
                renderButton(
                    btn,
                    true,
                    "المخزن فارغ ⏳",
                    "claim-action-btn btn-disabled"
                );
            } else {
                renderButton(
                    btn,
                    false,
                    "تجميع الرصيد 💰",
                    "claim-action-btn btn-ready"
                );
            }
        });

        return;
    }

    if (!claimCooldownTimer) {
        claimCooldownTimer = setInterval(() => {
            const nowMs = Date.now() + (window.serverTimeOffset || 0);
            const passed = Math.floor((nowMs - lastClaimMs) / 1000);
            const remaining = COOLDOWN_SECONDS - passed;

            if (remaining > 0) {
                claimButtons.forEach((btn) => {
                    renderButton(
                        btn,
                        true,
                        `انتظر ${window.formatTime(remaining)} ⏳`,
                        "claim-action-btn btn-disabled"
                    );
                });
            } else {
                clearInterval(claimCooldownTimer);
                claimCooldownTimer = null;

                const latestUnclaimed = parseFloat(
                    window.userState?.unclaimed || 0
                );

                claimButtons.forEach((btn) => {
                    if (isFarmTab && latestUnclaimed <= 0) {
                        renderButton(
                            btn,
                            true,
                            "المخزن فارغ ⏳",
                            "claim-action-btn btn-disabled"
                        );
                    } else {
                        renderButton(
                            btn,
                            false,
                            "تجميع الرصيد 💰",
                            "claim-action-btn btn-ready"
                        );
                    }
                });
            }
        }, 1000);
    }
};


// ==========================================
// 7. تنسيق وعرض الرصيد
// ==========================================
window.formatBalance = function (val) {
    if (val === undefined || val === null || Number.isNaN(Number(val))) {
        return "0.00";
    }

    const num = parseFloat(val);

    return num.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 6,
    });
};

window.formatNumberHTML = function (val) {
    if (val === undefined || val === null || Number.isNaN(Number(val))) {
        return "0.00";
    }

    let num = parseFloat(val);
    let suffix = "";

    if (Math.abs(num) >= 1e9) {
        num /= 1e9;
        suffix = "B";
    } else if (Math.abs(num) >= 1e6) {
        num /= 1e6;
        suffix = "M";
    }

    const formattedStr = num.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 6,
    });

    return `${formattedStr}${suffix}`;
};

let visualBalance = null;
let animationFrameId = null;

function startLocalMiningSimulator() {
    if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
    }

    function tick() {
        const targetVal = parseFloat(window.userState?.balance || 0);
        renderSmoothBalance(targetVal);
        animationFrameId = requestAnimationFrame(tick);
    }

    animationFrameId = requestAnimationFrame(tick);
}

function renderSmoothBalance(targetVal) {
    if (Number.isNaN(targetVal)) {
        targetVal = 0;
    }

    if (visualBalance === null || Number.isNaN(visualBalance)) {
        visualBalance = targetVal;
        applyBalanceToUI(visualBalance);
        return;
    }

    const diff = targetVal - visualBalance;

    if (Math.abs(diff) > 10) {
        visualBalance = targetVal;
    } else if (Math.abs(diff) < 0.000001) {
        visualBalance = targetVal;
    } else {
        visualBalance += diff * 0.08;
    }

    applyBalanceToUI(visualBalance);
}

function applyBalanceToUI(val) {
    const formatted = window.formatNumberHTML(val);
    const rawFormatted = window.formatBalance(val);

    const selectors =
        '[data-bind="balance"], .user-balance, #farm-balance, #user-balance, #main-balance, #balance, .sync-balance, #top-balance-tasks, .user-balance-val, [data-bind="user_balance"]';

    document.querySelectorAll(selectors).forEach((el) => {
        if (el.id === "shop-balance-text" || el.id === "top-balance-games") {
            return;
        }

        if (el.tagName === "INPUT") {
            el.value = rawFormatted;
        } else if (el.id === "top-balance-tasks") {
            el.innerText = `ZN ${rawFormatted}`;
        } else if (el.classList.contains("plain-text")) {
            el.innerText = `${rawFormatted} ZN`;
        } else {
            el.innerHTML = `<span dir="ltr" style="white-space:nowrap;">${formatted} ZN</span>`;
        }
    });
}

window.updateUI = function () {
    window.updateClaimButtonState();
    window.updateTonPriceUI();

    const currentMaxCap = parseFloat(window.userState.max_cap ?? 100);

    document
        .querySelectorAll(
            '#storage-max, .max-storage-val, [data-bind="max_cap"], #farm-storage-max'
        )
        .forEach((el) => {
            if (el.tagName === "INPUT") {
                el.value = currentMaxCap.toFixed(2);
            } else {
                el.innerHTML = `<span dir="ltr" style="white-space:nowrap;">${window.formatBalance(
                    currentMaxCap
                )}</span>`;
            }
        });

    const adBal = parseFloat(window.userState.ad_balance || 0);
    const formattedAd = window.formatBalance(adBal);

    document
        .querySelectorAll(
            '#ad-balance-display, .ad-balance-val, [data-bind="ad_balance"]'
        )
        .forEach((el) => {
            if (el.id === "ad-balance-display") {
                el.innerHTML = `<span dir="ltr" style="white-space:nowrap;">AdZN ${formattedAd}</span>`;
            } else {
                el.innerHTML = `<span dir="ltr" style="white-space:nowrap;">${formattedAd}</span>`;
            }
        });

    const usdBal = parseFloat(window.userState.usd_balance || 0);
    const formattedUsd = window.formatBalance(usdBal);

    document
        .querySelectorAll(
            '.usd-balance-val, [data-bind="usd_balance"]'
        )
        .forEach((el) => {
            if (el.id === "shop-usd-text") {
                return;
            }

            el.innerHTML = `<span dir="ltr" style="white-space:nowrap;">$${formattedUsd}</span>`;
        });

    if (
        visualBalance === null &&
        window.userState?.balance !== undefined
    ) {
        visualBalance = parseFloat(window.userState.balance) || 0;
        applyBalanceToUI(visualBalance);
    }
};


// ==========================================
// 8. التنقل بين القوائم وتنزيل الموديولات
// ==========================================
const loadedModules = new Set();
const moduleLoadPromises = new Map();
const moduleStyleHrefs = new Set();

function resolveModuleUrl(pathValue) {
    return new URL(pathValue, window.location.origin + "/").href;
}

function injectModuleStyles(doc, moduleName, htmlUrl) {
    const nodes = [
        ...Array.from(doc.querySelectorAll("head link[rel='stylesheet']")),
        ...Array.from(doc.querySelectorAll("head style, body style"))
    ];

    for (const node of nodes) {
        if (node.tagName === "STYLE") {
            const marker = `${moduleName}:${node.textContent || ""}`;
            const existing = Array.from(
                document.head.querySelectorAll("style[data-module-inline-style]")
            ).some((style) => style.dataset.moduleInlineStyle === marker);

            if (!existing) {
                const style = document.createElement("style");
                style.dataset.moduleInlineStyle = marker;
                style.textContent = node.textContent || "";
                document.head.appendChild(style);
            }
            continue;
        }

        const href = node.getAttribute("href");
        if (!href) continue;

        const absoluteHref = new URL(
            href,
            new URL(htmlUrl, window.location.origin)
        ).href;

        if (moduleStyleHrefs.has(absoluteHref)) continue;

        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = absoluteHref;
        link.dataset.moduleStylesheet = moduleName;
        document.head.appendChild(link);
        moduleStyleHrefs.add(absoluteHref);
    }
}

function extractModuleFragment(htmlContent, moduleName, htmlUrl) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(htmlContent, "text/html");

    if (!doc || !doc.body) {
        throw new Error(`MODULE HTML PARSE FAILED: ${htmlUrl}`);
    }

    injectModuleStyles(doc, moduleName, htmlUrl);

    // Embedded module scripts are deliberately removed. The main loader
    // loads exactly one JS file for the module after HTML insertion.
    doc.body.querySelectorAll("script").forEach((node) => node.remove());

    // The main page owns the global bottom navigation.
    doc.body.querySelectorAll(
        "nav.bottom-nav, nav#main-nav, .bottom-nav, #bottom-nav, .nav-bar, .bottom-menu, .footer-nav"
    ).forEach((node) => node.remove());

    const fragment = doc.body.innerHTML.trim();

    if (!fragment) {
        throw new Error(`MODULE HTML EMPTY BODY: ${htmlUrl}`);
    }

    return fragment;
}

window.switchView = async function (viewName) {
    document.querySelectorAll(".nav-item").forEach((btn) => {
        btn.classList.remove("active");
    });

    const targetNav = document.getElementById(`nav-${viewName}`);
    if (targetNav) targetNav.classList.add("active");

    document.querySelectorAll(".game-view").forEach((view) => {
        view.classList.remove("active");
    });

    let targetView = document.getElementById(`view-${viewName}`);

    if (!targetView && (viewName === "games" || viewName === "game")) {
        targetView =
            document.getElementById("view-games") ||
            document.getElementById("view-game");
    }

    if (!targetView) {
        console.error(`❌ لم يتم العثور على view-${viewName}`);
        return;
    }

    targetView.classList.add("active");

    if (!loadedModules.has(viewName)) {
        if (!moduleLoadPromises.has(viewName)) {
            moduleLoadPromises.set(
                viewName,
                (async () => {
                    const cacheBuster = `?v=${Date.now()}`;
                    const encodedViewName = encodeURIComponent(viewName);

                    // Try the normal module path first, then common Flask/static
                    // locations. This keeps the existing layout untouched while
                    // allowing modules such as wallet to load when served from
                    // Flask's static directory instead of the web root.
                    const moduleCandidates = [
                        {
                            htmlPath: `/${encodedViewName}/${encodedViewName}.html${cacheBuster}`,
                            jsPath: `/${encodedViewName}/${encodedViewName}.js${cacheBuster}`
                        },
                        {
                            htmlPath: `/${encodedViewName}.html${cacheBuster}`,
                            jsPath: `/${encodedViewName}.js${cacheBuster}`
                        },
                        {
                            htmlPath: `/static/${encodedViewName}/${encodedViewName}.html${cacheBuster}`,
                            jsPath: `/static/${encodedViewName}/${encodedViewName}.js${cacheBuster}`
                        },
                        {
                            htmlPath: `/static/${encodedViewName}.html${cacheBuster}`,
                            jsPath: `/static/${encodedViewName}.js${cacheBuster}`
                        }
                    ];

                    let htmlContent = "";
                    let htmlPath = "";
                    let jsPath = "";
                    let htmlUrl = "";
                    let lastHtmlStatus = null;

                    for (const candidate of moduleCandidates) {
                        const candidateUrl = resolveModuleUrl(candidate.htmlPath);

                        try {
                            const response = await fetch(candidateUrl, {
                                method: "GET",
                                headers: { Accept: "text/html" },
                                cache: "no-store",
                                credentials: "same-origin"
                            });

                            lastHtmlStatus = response.status;

                            if (!response.ok) {
                                continue;
                            }

                            const content = await response.text();

                            if (!content.trim()) {
                                continue;
                            }

                            htmlContent = content;
                            htmlPath = candidate.htmlPath;
                            jsPath = candidate.jsPath;
                            htmlUrl = candidateUrl;
                            break;
                        } catch (error) {
                            console.warn(
                                `⚠️ تعذر تحميل ${candidate.htmlPath}:`,
                                error
                            );
                        }
                    }

                    if (!htmlContent.trim()) {
                        throw new Error(
                            `HTML LOAD FAILED: ${htmlPath || `/${encodedViewName}/${encodedViewName}.html`} → HTTP ${lastHtmlStatus ?? "NETWORK"}`
                        );
                    }

                    const fragment = extractModuleFragment(
                        htmlContent,
                        viewName,
                        htmlUrl
                    );

                    targetView.innerHTML = fragment;

                    await loadModuleScript(jsPath, viewName);

                    loadedModules.add(viewName);
                })().catch((error) => {
                    moduleLoadPromises.delete(viewName);
                    throw error;
                })
            );
        }

        try {
            await moduleLoadPromises.get(viewName);
        } catch (err) {
            console.error(`❌ خطأ تحميل ${viewName}:`, err);

            const safeMessage = String(err?.message || err || "Unknown error")
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;");

            targetView.innerHTML = `
                <div style="
                    display:flex;
                    flex-direction:column;
                    align-items:center;
                    justify-content:center;
                    min-height:40vh;
                    color:#fff;
                    padding:20px;
                    text-align:center;
                ">
                    <div style="font-size:42px;margin-bottom:12px;">⚠️</div>
                    <h2 style="margin-bottom:8px;">تعذر تحميل صفحة ${viewName}</h2>
                    <p style="color:#8b949e;max-width:520px;line-height:1.8;">
                        حدث خطأ أثناء تحميل ملفات الصفحة.
                    </p>
                    <code style="
                        display:block;
                        direction:ltr;
                        text-align:left;
                        margin-top:12px;
                        padding:10px;
                        max-width:520px;
                        width:100%;
                        overflow:auto;
                        background:#0b1220;
                        border:1px solid #263244;
                        border-radius:8px;
                        color:#fca5a5;
                        font-size:11px;
                    ">${safeMessage}</code>
                </div>
            `;
        }
    }

    if (viewName === "farm" && typeof window.onFarmTabOpen === "function") {
        window.onFarmTabOpen();
    }

    if (viewName === "shop" && typeof window.updateShopUI === "function") {
        window.updateShopUI();
    }

    if (
        (viewName === "games" || viewName === "game") &&
        typeof window.onGamesTabOpen === "function"
    ) {
        window.onGamesTabOpen();
    }

    const initFuncName =
        `init${viewName.charAt(0).toUpperCase()}${viewName.slice(1)}View`;

    if (typeof window[initFuncName] === "function") {
        try {
            await Promise.resolve(window[initFuncName]());
        } catch (error) {
            console.error(`❌ خطأ تهيئة ${viewName}:`, error);
        }
    }

    window.updateUI();
};

function loadModuleScript(scriptUrl, moduleName = "module") {
    return new Promise((resolve, reject) => {
        document
            .querySelectorAll(`script[data-module-script="${CSS.escape(moduleName)}"]`)
            .forEach((node) => node.remove());

        const script = document.createElement("script");
        script.src = scriptUrl;
        script.async = false;
        script.dataset.moduleScript = moduleName;

        script.onload = () => resolve();
        script.onerror = () =>
            reject(new Error(`JAVASCRIPT LOAD FAILED: ${scriptUrl.split("?")[0]}`));

        document.body.appendChild(script);
    });
}


// ==========================================
// 9. بدء التطبيق
// ==========================================
window.loadUserData = async function () {
    try {
        const startParam = tg?.initDataUnsafe?.start_param || null;

        const d = await window.fetchAPI(
            "/api/farm/player_data",
            "POST",
            {
                referrer_id: startParam,
                first_name:
                    tg?.initDataUnsafe?.user?.first_name || "لاعب",
            }
        );

        if (d?.success) {
            const u = d.player || d.user || d.data || {};
            Object.assign(window.userState, u);
        }
    } catch (err) {
        console.error("Error player_data:", err);
    } finally {
        window.updateUI();

        if (typeof window.updateFarmUI === "function") {
            window.updateFarmUI();
        }

        hideLoadingScreen();
    }
};

function initApp() {
    window.updateUI();
    window.fetchTonPrice();
    window.switchView("farm");

    window.loadUserData().then(() => {
        const uid =
            window.userState.tg_id ||
            tg?.initDataUnsafe?.user?.id;

        if (uid) {
            window.initFirebaseRealtimeSync(uid);
        }
    });

    startLocalMiningSimulator();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initApp, {
        once: true,
    });
} else {
    initApp();
}
