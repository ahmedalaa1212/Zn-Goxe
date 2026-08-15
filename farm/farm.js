window.initFarmView = function () {
    if (typeof window.onFarmTabOpen === "function") {
        window.onFarmTabOpen();
    }
};

window.closeWelcomeModal = function () {
    const modal = document.getElementById("welcome-modal");

    if (modal) {
        modal.style.display = "none";
        modal.classList.remove("active", "show");
    }

    if (!window.userState) window.userState = {};
    if (!window.PlayerData) window.PlayerData = {};

    window.userState.is_new_user = false;
    window.PlayerData.is_new_user = false;
    window.userState.welcome_seen = true;
    window.PlayerData.welcome_seen = true;

    try {
        const tele = window.Telegram?.WebApp;
        const userId =
            tele?.initDataUnsafe?.user?.id ||
            window.userState?.tg_id ||
            window.userState?.telegram_id ||
            window.PlayerData?.tg_id ||
            window.PlayerData?.telegram_id;

        if (userId) {
            localStorage.setItem(`zn_welcome_seen_${userId}`, "true");
        }

        if (typeof window.fetchAPI === "function") {
            window.fetchAPI("/api/farm/dismiss_welcome", "POST", {}).catch(() => {});
        }
    } catch (e) {
        console.error("خطأ حفظ حالة النافذة الترحيبية:", e);
    }
};

(function initFarm() {
    const tele = window.Telegram?.WebApp;
    const START_PARAM = tele?.initDataUnsafe?.start_param || "";

    const GAME_CONFIG = {
        maxUpgradesPerLevel: 15,
        dailyBoostReward: 0.15,
        maxDailyBoostRate: 4.5,
        boostMaxRewardCoins: 35.0,

        upgradeCosts: {
            1: { cost_zn: 600, cost_usd: 0.0, rate: 1.0 },
            2: { cost_zn: 1500, cost_usd: 0.10, rate: 2.5 },
            3: { cost_zn: 3800, cost_usd: 0.15, rate: 6.0 },
            4: { cost_zn: 10000, cost_usd: 0.20, rate: 15.0 },
            5: { cost_zn: 28000, cost_usd: 0.25, rate: 40.0 },
            6: { cost_zn: 75000, cost_usd: 0.30, rate: 100.0 },
            7: { cost_zn: 200000, cost_usd: 0.35, rate: 250.0 },
            8: { cost_zn: 500000, cost_usd: 0.40, rate: 600.0 },
            9: { cost_zn: 1400000, cost_usd: 0.50, rate: 1500.0 }
        },

        storageConfig: {
            "0": { capacity: 30.0, cost_zn: 0, cost_usd: 0.0 },
            "1": { capacity: 150.0, cost_zn: 400, cost_usd: 0.0 },
            "2": { capacity: 500.0, cost_zn: 1200, cost_usd: 0.05 },
            "3": { capacity: 1500.0, cost_zn: 3500, cost_usd: 0.10 },
            "4": { capacity: 4000.0, cost_zn: 10000, cost_usd: 0.15 },
            "5": { capacity: 10000.0, cost_zn: 25000, cost_usd: 0.20 },
            "6": { capacity: 25000.0, cost_zn: 65000, cost_usd: 0.25 },
            "7": { capacity: 70000.0, cost_zn: 180000, cost_usd: 0.30 },
            "8": { capacity: 200000.0, cost_zn: 500000, cost_usd: 0.35 },
            "9": { capacity: 600000.0, cost_zn: 1500000, cost_usd: 0.40 }
        },

        dailyRewards: [
            5, 10, 15, 20, 25, 30, 40, 45, 50, 60,
            65, 70, 75, 90, 100, 110, 120, 130, 140, 160,
            180, 200, 220, 240, 270, 300, 330, 360, 400, 450
        ]
    };

    let MIN_CLAIM_INTERVAL = 15;

    let isClaimingDaily = false;
    let isBoosting = false;
    let isFetching = false;
    let isClaimingMain = false;
    let isUpgrading = false;
    let isUpgradingStorage = false;

    let lastFetchTime = 0;
    const FETCH_THROTTLE_MS = 3000;
    let lastCheckedDate = "";

    function getCacheKey() {
        const userId =
            tele?.initDataUnsafe?.user?.id ||
            window.userState?.tg_id ||
            window.userState?.telegram_id ||
            window.PlayerData?.tg_id ||
            window.PlayerData?.telegram_id;

        return userId
            ? `zn_farm_cache_${userId}`
            : "zn_farm_cache_global";
    }

    function saveCachedData(data) {
        try {
            if (!data || typeof data !== "object") return;
            localStorage.setItem(getCacheKey(), JSON.stringify(data));
        } catch (e) {
            console.error("خطأ حفظ الكاش المحلي:", e);
        }
    }

    function loadCachedData() {
        try {
            const cached = localStorage.getItem(getCacheKey());
            if (!cached) return false;

            const parsed = JSON.parse(cached);

            if (!parsed || typeof parsed !== "object") {
                return false;
            }

            if (!window.userState) window.userState = {};
            if (!window.PlayerData) window.PlayerData = {};

            Object.assign(window.userState, parsed);
            Object.assign(window.PlayerData, parsed);

            return true;
        } catch (e) {
            console.error("خطأ قراءة الكاش المحلي:", e);
            return false;
        }
    }

    function showToast(message) {
        if (tele && typeof tele.showAlert === "function") {
            tele.showAlert(message);
        } else {
            alert(message);
        }
    }

    function getAdjustedNowMs() {
        return Date.now() + (window.serverTimeOffset || 0);
    }

    function syncServerTime(serverTimeStr) {
        if (!serverTimeStr) return;

        try {
            const serverMs = new Date(serverTimeStr).getTime();

            if (!Number.isNaN(serverMs)) {
                window.serverTimeOffset = serverMs - Date.now();
            }
        } catch (e) {
            console.error("خطأ مزامنة وقت السيرفر:", e);
        }
    }

    function formatUsdBalance(value) {
        const num = Number.parseFloat(value);

        if (!Number.isFinite(num) || Math.abs(num) < 0.0000005) {
            return "$0.00";
        }

        return `$${num.toFixed(6).replace(/\.?0+$/, "")}`;
    }

    /*
     * العرض: 4 منازل عشرية دائماً.
     * التخزين والحساب في الخادم أعلى دقة من ذلك.
     */
    function formatZnBalance(value) {
        const num = Number.parseFloat(value);

        if (!Number.isFinite(num)) {
            return "0.0000";
        }

        return num.toFixed(4);
    }

    function formatZnAmount(value) {
        return formatZnBalance(value);
    }

    function getStoredBalance() {
        if (
            window.userState &&
            window.userState.balance !== undefined &&
            window.userState.balance !== null
        ) {
            return Number.parseFloat(window.userState.balance) || 0;
        }

        return Number.parseFloat(window.PlayerData?.balance) || 0;
    }

    function getStoredUsdBalance() {
        if (
            window.userState &&
            window.userState.usd_balance !== undefined &&
            window.userState.usd_balance !== null
        ) {
            return Number.parseFloat(window.userState.usd_balance) || 0;
        }

        return Number.parseFloat(window.PlayerData?.usd_balance) || 0;
    }

    function setStoredBalance(newBalance, newUsdBalance) {
        if (!window.userState) window.userState = {};
        if (!window.PlayerData) window.PlayerData = {};

        if (newBalance !== undefined && newBalance !== null) {
            const value = Number.parseFloat(newBalance);

            if (Number.isFinite(value)) {
                window.userState.balance = value;
                window.PlayerData.balance = value;

                const element = document.getElementById("farm-balance");

                if (element) {
                    element.innerText = `${formatZnBalance(value)} ZN`;
                }
            }
        }

        if (newUsdBalance !== undefined && newUsdBalance !== null) {
            const value = Number.parseFloat(newUsdBalance);

            if (Number.isFinite(value)) {
                window.userState.usd_balance = value;
                window.PlayerData.usd_balance = value;

                const element = document.getElementById("farm-usd-balance");

                if (element) {
                    element.innerText = formatUsdBalance(value);
                }
            }
        }

        saveCachedData(window.userState);
    }

    function getTodayUTCStr() {
        return new Date(getAdjustedNowMs()).toISOString().split("T")[0];
    }

    function getTimeUntilUTCMidnight() {
        const now = new Date(getAdjustedNowMs());

        const nextMidnight = new Date(
            Date.UTC(
                now.getUTCFullYear(),
                now.getUTCMonth(),
                now.getUTCDate() + 1
            )
        );

        const diff = Math.max(0, nextMidnight.getTime() - now.getTime());

        let seconds = Math.floor(diff / 1000);
        const hours = Math.floor(seconds / 3600);
        seconds %= 3600;

        const minutes = Math.floor(seconds / 60);
        const secs = seconds % 60;

        return [
            String(hours).padStart(2, "0"),
            String(minutes).padStart(2, "0"),
            String(secs).padStart(2, "0")
        ].join(":");
    }

    function formatCompactCost(num) {
        const value = Number.parseFloat(num) || 0;

        if (value >= 1000000) {
            const formatted = (value / 1000000).toFixed(1);
            return formatted.endsWith(".0")
                ? `${(value / 1000000).toFixed(0)}M`
                : `${formatted}M`;
        }

        if (value >= 1000) {
            const formatted = (value / 1000).toFixed(1);
            return formatted.endsWith(".0")
                ? `${(value / 1000).toFixed(0)}K`
                : `${formatted}K`;
        }

        return value.toString();
    }

    function formatCompactNumber(num) {
        const value = Number.parseFloat(num) || 0;

        if (value >= 1000000) {
            return `${(value / 1000000).toFixed(1)}M`;
        }

        if (value >= 1000 && value % 1000 === 0) {
            return `${value / 1000}K`;
        }

        return value.toString();
    }

    window.fetchPlayerDataFromServer = async function (force = false) {
        const now = Date.now();

        if (isFetching) return;

        if (
            !force &&
            now - lastFetchTime < FETCH_THROTTLE_MS
        ) {
            window.updateFarmUI();
            return;
        }

        isFetching = true;

        try {
            const resData = await window.fetchAPI(
                "/api/farm/player_data",
                "POST",
                { start_param: START_PARAM }
            );

            if (resData && resData.success) {
                lastFetchTime = Date.now();

                if (resData.server_time) {
                    syncServerTime(resData.server_time);
                }

                if (
                    resData.cooldown_seconds !== undefined &&
                    resData.cooldown_seconds !== null
                ) {
                    MIN_CLAIM_INTERVAL = Math.max(
                        0,
                        Number.parseInt(resData.cooldown_seconds, 10) || 0
                    );
                }

                if (resData.game_config) {
                    const cfg = resData.game_config;

                    if (Array.isArray(cfg.daily_rewards)) {
                        GAME_CONFIG.dailyRewards = cfg.daily_rewards;
                    }

                    if (cfg.upgrade_costs) {
                        GAME_CONFIG.upgradeCosts = cfg.upgrade_costs;
                    }

                    if (cfg.storage_config) {
                        GAME_CONFIG.storageConfig = cfg.storage_config;
                    }

                    if (cfg.max_upgrades_per_level !== undefined) {
                        GAME_CONFIG.maxUpgradesPerLevel =
                            Number.parseInt(
                                cfg.max_upgrades_per_level,
                                10
                            ) || 15;
                    }

                    if (cfg.daily_boost_reward !== undefined) {
                        GAME_CONFIG.dailyBoostReward =
                            Number.parseFloat(
                                cfg.daily_boost_reward
                            ) || 0.15;
                    }

                    if (cfg.max_daily_boost_rate !== undefined) {
                        GAME_CONFIG.maxDailyBoostRate =
                            Number.parseFloat(
                                cfg.max_daily_boost_rate
                            ) || 4.5;
                    }

                    if (cfg.boost_max_reward_coins !== undefined) {
                        GAME_CONFIG.boostMaxRewardCoins =
                            Number.parseFloat(
                                cfg.boost_max_reward_coins
                            ) || 35.0;
                    }
                }

                if (!window.PlayerData) window.PlayerData = {};
                if (!window.userState) window.userState = {};

                if (resData.player) {
                    Object.assign(window.PlayerData, resData.player);
                    Object.assign(window.userState, resData.player);

                    saveCachedData(resData.player);

                    setStoredBalance(
                        resData.player.balance,
                        resData.player.usd_balance
                    );

                    const isNew =
                        resData.player.is_new_user === true ||
                        resData.player.welcome_seen === false;

                    const modal =
                        document.getElementById("welcome-modal");

                    if (modal) {
                        if (isNew) {
                            modal.style.display = "flex";
                            modal.classList.add("show", "active");
                        } else {
                            modal.style.display = "none";
                            modal.classList.remove("show", "active");
                        }
                    }
                }

                window.updateFarmUI();
            }
        } catch (e) {
            console.error("خطأ مزامنة المزرعة:", e);
        } finally {
            isFetching = false;
        }
    };

    window.updateFarmUI = function () {
        const pData = window.userState || window.PlayerData || {};

        const balance = getStoredBalance();
        const usdBalance = getStoredUsdBalance();

        const hourlyRate =
            Number.parseFloat(
                pData.hourly_rate ?? 0.05
            ) || 0.05;

        const balanceElement =
            document.getElementById("farm-balance");

        if (balanceElement) {
            balanceElement.innerText =
                `${formatZnBalance(balance)} ZN`;
        }

        const usdElement =
            document.getElementById("farm-usd-balance");

        if (usdElement) {
            usdElement.innerText =
                formatUsdBalance(usdBalance);
        }

        const rateElement =
            document.getElementById("farm-rate");

        if (rateElement) {
            const formattedRate =
                Number.isInteger(hourlyRate)
                    ? hourlyRate.toString()
                    : Number(hourlyRate.toFixed(2)).toString();

            rateElement.innerHTML =
                `<span dir="ltr">${formattedRate} /h</span> ⚡`;
        }

        const storageLevel =
            Number.parseInt(
                pData.storage_level ?? 0,
                10
            ) || 0;

        const storageLevelElement =
            document.getElementById("storage-level-num");

        if (storageLevelElement) {
            storageLevelElement.innerText = storageLevel;
        }

        const upgradeStorageButton =
            document.getElementById("upgrade-storage-btn");

        if (upgradeStorageButton) {
            upgradeStorageButton.onclick =
                window.handleStorageUpgrade;

            const nextLevel = storageLevel + 1;
            const nextConfig =
                GAME_CONFIG.storageConfig[
                    String(nextLevel)
                ];

            if (storageLevel >= 9 || !nextConfig) {
                upgradeStorageButton.innerText =
                    "المخزن في المستوى الأقصى (MAX) 🏆";
                upgradeStorageButton.disabled = true;
                upgradeStorageButton.className =
                    "storage-upgrade-btn btn-disabled";
            } else {
                const costZn =
                    typeof nextConfig === "object"
                        ? Number.parseFloat(
                              nextConfig.cost_zn ??
                              nextConfig.cost ??
                              0
                          ) || 0
                        : 0;

                const costUsd =
                    typeof nextConfig === "object"
                        ? Number.parseFloat(
                              nextConfig.cost_usd ?? 0
                          ) || 0
                        : 0;

                const costStrZn =
                    formatCompactCost(costZn);

                const costStrUsd =
                    costUsd > 0
                        ? ` + $${costUsd.toFixed(2)}`
                        : "";

                const canAfford =
                    balance + 1e-12 >= costZn &&
                    usdBalance + 1e-12 >= costUsd;

                upgradeStorageButton.innerText =
                    `ترقية المخزن Lvl ${nextLevel} (${costStrZn} ZN${costStrUsd}) 📦`;

                upgradeStorageButton.disabled =
                    !canAfford || isUpgradingStorage;

                upgradeStorageButton.className =
                    canAfford
                        ? "storage-upgrade-btn btn-ready-yellow"
                        : "storage-upgrade-btn btn-disabled";
            }
        }

        const fieldsContainer =
            document.getElementById("mining-fields");

        if (fieldsContainer) {
            const currentUpgrades =
                pData.upgrades &&
                typeof pData.upgrades === "object"
                    ? pData.upgrades
                    : {};

            let fieldsHTML = "";

            for (let i = 1; i <= 9; i++) {
                const count =
                    Number.parseInt(
                        currentUpgrades[`lvl${i}`] || 0,
                        10
                    ) || 0;

                const prevCount =
                    Number.parseInt(
                        currentUpgrades[`lvl${i - 1}`] || 0,
                        10
                    ) || 0;

                const isUnlocked =
                    i === 1 || prevCount > 0;

                const isMax =
                    count >= GAME_CONFIG.maxUpgradesPerLevel;

                const levelConfig =
                    GAME_CONFIG.upgradeCosts[i] || {};

                const costZn =
                    Number.parseFloat(
                        levelConfig.cost_zn ??
                        levelConfig.base_cost ??
                        levelConfig.price ??
                        0
                    ) || 0;

                const costUsd =
                    Number.parseFloat(
                        levelConfig.cost_usd ??
                        levelConfig.base_cost_usd ??
                        0
                    ) || 0;

                const costStrZn =
                    formatCompactCost(costZn);

                const costStrUsd =
                    costUsd > 0
                        ? `+$${costUsd.toFixed(2)}`
                        : "";

                const canAfford =
                    balance + 1e-12 >= costZn &&
                    usdBalance + 1e-12 >= costUsd;

                if (isMax) {
                    fieldsHTML += `
                    <div class="mining-card">
                        <div class="mining-card-icon">🏛️</div>
                        <div class="mining-card-title">مستوى ${i} (MAX)</div>
                        <button class="mining-card-btn" disabled>
                            ${GAME_CONFIG.maxUpgradesPerLevel}/${GAME_CONFIG.maxUpgradesPerLevel} MAX
                        </button>
                    </div>`;
                } else if (count > 0) {
                    fieldsHTML += `
                    <div class="mining-card"
                         onclick="window.handleUpgrade(${i})">
                        <div class="mining-card-icon">🏛️</div>
                        <div class="mining-card-title">
                            مستوى ${i} (x${count})
                        </div>
                        <button class="mining-card-btn"
                                ${!canAfford || isUpgrading ? "disabled" : ""}>
                            ترقية (${costStrZn}${costStrUsd})
                        </button>
                    </div>`;
                } else if (isUnlocked) {
                    fieldsHTML += `
                    <div class="mining-card"
                         onclick="window.handleUpgrade(${i})">
                        <div class="mining-card-icon">🏛️</div>
                        <div class="mining-card-title">
                            مستوى ${i}
                        </div>
                        <button class="mining-card-btn"
                                ${!canAfford || isUpgrading ? "disabled" : ""}>
                            شراء (${costStrZn}${costStrUsd})
                        </button>
                    </div>`;
                } else {
                    fieldsHTML += `
                    <div class="mining-card" style="opacity: 0.4;">
                        <div class="mining-card-icon">🔒</div>
                        <div class="mining-card-title">
                            مستوى ${i}
                        </div>
                        <button class="mining-card-btn" disabled>
                            مغلق
                        </button>
                    </div>`;
                }
            }

            fieldsContainer.innerHTML = fieldsHTML;
        }

        const boostButton =
            document.getElementById("boost-btn");

        if (boostButton) {
            const todayStr = getTodayUTCStr();
            const lastBoost = pData.last_boost_date;

            const currentDailyBoostRate =
                Number.parseFloat(
                    pData.daily_boost_rate || 0
                ) || 0;

            if (lastBoost === todayStr) {
                boostButton.className =
                    "boost-btn btn-disabled";
                boostButton.disabled = true;

                boostButton.innerHTML =
                    `<span style="font-size: 12px;">⏳</span>
                     <span style="font-size: 8px;">
                         ${getTimeUntilUTCMidnight()}
                     </span>`;
            } else if (!isBoosting) {
                boostButton.className = "boost-btn";
                boostButton.disabled = false;

                const boostText =
                    currentDailyBoostRate + 1e-9 >=
                    GAME_CONFIG.maxDailyBoostRate
                        ? `+${formatZnAmount(
                              GAME_CONFIG.boostMaxRewardCoins
                          )} ZN`
                        : `+${GAME_CONFIG.dailyBoostReward}/h`;

                boostButton.innerHTML =
                    `<span id="boost-icon">🚀</span>
                     <span id="boost-text">${boostText}</span>`;
            }
        }

        renderDailyRewards();
    };

    window.onFarmTabOpen = async function () {
        if (typeof window.fetchPlayerDataFromServer === "function") {
            await window.fetchPlayerDataFromServer(true);
        } else {
            window.updateFarmUI();
        }
    };

    function getRewardForDayIndex(index) {
        const rewards = GAME_CONFIG.dailyRewards;

        if (!Array.isArray(rewards) || rewards.length === 0) {
            return 5;
        }

        return rewards[index] ?? 450;
    }

    function renderDailyRewards() {
        const container =
            document.getElementById(
                "daily-rewards-container"
            );

        const pData =
            window.userState ||
            window.PlayerData ||
            {};

        if (!container) return;

        let html = "";

        const todayStr = getTodayUTCStr();
        const lastClaimDate =
            pData.last_daily_claim_date;

        const claimedToday =
            lastClaimDate === todayStr;

        let currentDailyDay =
            Number.parseInt(
                pData.daily_day || 1,
                10
            ) || 1;

        currentDailyDay =
            Math.max(
                1,
                Math.min(currentDailyDay, 30)
            );

        const timeLeftStr =
            getTimeUntilUTCMidnight();

        for (let i = 0; i < 30; i++) {
            const dayNum = i + 1;

            const rawReward =
                getRewardForDayIndex(i);

            const displayReward =
                formatCompactNumber(rawReward);

            if (claimedToday) {
                if (dayNum <= currentDailyDay) {
                    html += `
                    <div class="reward-day-card claimed">
                        <div class="day-title">
                            يوم ${dayNum}
                        </div>
                        <div style="font-size:14px;font-weight:bold;color:#10b981;">
                            ✓
                        </div>
                    </div>`;
                } else if (
                    dayNum === currentDailyDay + 1
                ) {
                    html += `
                    <div class="reward-day-card active"
                         style="border:1px dashed #ef4444;">
                        <div class="day-title">
                            يوم ${dayNum}
                        </div>
                        <div class="day-amount">
                            ${displayReward}
                        </div>
                        <div id="daily-timer"
                             style="color:#ef4444;font-size:8px;font-weight:bold;">
                            ⏳ ${timeLeftStr}
                        </div>
                    </div>`;
                } else {
                    html += `
                    <div class="reward-day-card"
                         style="opacity:0.4;">
                        <div class="day-title">
                            يوم ${dayNum}
                        </div>
                        <div class="day-amount">
                            ${displayReward}
                        </div>
                    </div>`;
                }
            } else if (dayNum < currentDailyDay) {
                html += `
                <div class="reward-day-card claimed">
                    <div class="day-title">
                        يوم ${dayNum}
                    </div>
                    <div style="font-size:14px;font-weight:bold;color:#10b981;">
                        ✓
                    </div>
                </div>`;
            } else if (dayNum === currentDailyDay) {
                html += `
                <div class="reward-day-card active">
                    <div class="day-title">
                        يوم ${dayNum}
                    </div>
                    <div class="day-amount">
                        ${displayReward}
                    </div>
                    <button id="daily-btn-${dayNum}"
                            onclick="window.handleDailyClaim(${currentDailyDay})"
                            style="background:#10b981;color:white;border:none;border-radius:4px;padding:2px 0;font-size:9px;width:100%;cursor:pointer;"
                            ${isClaimingDaily ? "disabled" : ""}>
                        استلام
                    </button>
                </div>`;
            } else {
                html += `
                <div class="reward-day-card"
                     style="opacity:0.4;">
                    <div class="day-title">
                        يوم ${dayNum}
                    </div>
                    <div class="day-amount">
                        ${displayReward}
                    </div>
                </div>`;
            }
        }

        container.innerHTML = html;
    }

    loadCachedData();
    window.updateFarmUI();

    if (window.farmIntervalId) {
        clearInterval(window.farmIntervalId);
    }

    window.farmIntervalId = setInterval(() => {
        const pData =
            window.userState ||
            window.PlayerData;

        if (!pData) return;

        const todayStr = getTodayUTCStr();

        if (
            lastCheckedDate &&
            lastCheckedDate !== todayStr
        ) {
            lastCheckedDate = todayStr;

            if (
                typeof window.fetchPlayerDataFromServer ===
                "function"
            ) {
                window.fetchPlayerDataFromServer(true);
            }
        }

        lastCheckedDate = todayStr;

        const maxCap =
            Number.parseFloat(
                pData.max_cap ?? 30.0
            ) || 30.0;

        const hourlyRate =
            Number.parseFloat(
                pData.hourly_rate ?? 0.05
            ) || 0.05;

        const lastClaimStr =
            pData.last_claim_time;

        let lastClaimTimeMs =
            lastClaimStr
                ? new Date(lastClaimStr).getTime()
                : getAdjustedNowMs();

        if (!Number.isFinite(lastClaimTimeMs)) {
            lastClaimTimeMs = getAdjustedNowMs();
        }

        const secondsPassed =
            Math.max(
                0,
                (getAdjustedNowMs() - lastClaimTimeMs) / 1000
            );

        let unclaimed =
            (hourlyRate / 3600.0) *
            secondsPassed;

        unclaimed =
            Math.min(
                Math.max(0, unclaimed),
                Math.max(0, maxCap)
            );

        pData.unclaimed = unclaimed;

        const progressElement =
            document.getElementById(
                "storage-progress"
            );

        const storageTextElement =
            document.getElementById(
                "storage-text"
            );

        if (
            progressElement &&
            storageTextElement
        ) {
            let percentage =
                maxCap > 0
                    ? (unclaimed / maxCap) * 100
                    : 0;

            percentage =
                Math.max(
                    0,
                    Math.min(percentage, 100)
                );

            progressElement.style.width =
                `${percentage}%`;

            storageTextElement.innerText =
                `${formatZnBalance(unclaimed)} / ${
                    maxCap.toLocaleString("en-US", {
                        maximumFractionDigits: 2
                    })
                }`;
        }

        const claimButton =
            document.getElementById("claim-btn");

        if (claimButton) {
            claimButton.onclick =
                window.handleMainClaim;

            const remainingCooldown =
                Math.max(
                    0,
                    Math.ceil(
                        MIN_CLAIM_INTERVAL -
                        secondsPassed
                    )
                );

            if (isClaimingMain) {
                claimButton.innerText =
                    "جاري الحفظ... 💾";

                claimButton.className =
                    "claim-action-btn btn-disabled";

                claimButton.disabled = true;
            } else if (
                remainingCooldown > 0 &&
                unclaimed > 0
            ) {
                claimButton.innerText =
                    `انتظر ${remainingCooldown} ثانية ⏳`;

                claimButton.className =
                    "claim-action-btn btn-disabled";

                claimButton.disabled = true;
            } else if (unclaimed > 0) {
                claimButton.innerText =
                    "تجميع الرصيد 💰";

                claimButton.className =
                    "claim-action-btn btn-ready";

                claimButton.disabled = false;
            } else {
                claimButton.innerText =
                    "المخزن فارغ ⏳";

                claimButton.className =
                    "claim-action-btn btn-disabled";

                claimButton.disabled = true;
            }
        }

        const timeLeftStr =
            getTimeUntilUTCMidnight();

        const boostButton =
            document.getElementById(
                "boost-btn"
            );

        if (boostButton) {
            boostButton.onclick =
                window.handleDailyBoost;

            const lastBoost =
                pData.last_boost_date;

            const currentDailyBoostRate =
                Number.parseFloat(
                    pData.daily_boost_rate || 0
                ) || 0;

            if (lastBoost === todayStr) {
                boostButton.className =
                    "boost-btn btn-disabled";

                boostButton.disabled = true;

                boostButton.innerHTML =
                    `<span style="font-size:12px;">⏳</span>
                     <span style="font-size:8px;">
                         ${timeLeftStr}
                     </span>`;
            } else if (!isBoosting) {
                boostButton.className =
                    "boost-btn";

                boostButton.disabled = false;

                const boostText =
                    currentDailyBoostRate + 1e-9 >=
                    GAME_CONFIG.maxDailyBoostRate
                        ? `+${formatZnAmount(
                              GAME_CONFIG.boostMaxRewardCoins
                          )} ZN`
                        : `+${GAME_CONFIG.dailyBoostReward}/h`;

                boostButton.innerHTML =
                    `<span id="boost-icon">🚀</span>
                     <span id="boost-text">
                         ${boostText}
                     </span>`;
            }
        }

        const dailyTimerElement =
            document.getElementById(
                "daily-timer"
            );

        if (
            dailyTimerElement &&
            pData.last_daily_claim_date === todayStr
        ) {
            dailyTimerElement.innerText =
                `⏳ ${timeLeftStr}`;
        }
    }, 1000);

    function syncOnVisibility() {
        if (document.visibilityState === "visible") {
            window.fetchPlayerDataFromServer(true);
        }
    }

    window.addEventListener(
        "pageshow",
        syncOnVisibility
    );

    document.addEventListener(
        "visibilitychange",
        syncOnVisibility
    );

    function showTelegramAd() {
        return new Promise((resolve) => {
            if (
                typeof window.show_11322720 ===
                "function"
            ) {
                try {
                    window
                        .show_11322720()
                        .then(() => resolve(true))
                        .catch((err) => {
                            console.warn(
                                "فشل أو تم إغلاق الإعلان:",
                                err
                            );

                            showToast(
                                "⚠️ يجب مشاهدة الإعلان حتى النهاية للحصول على المكافأة!"
                            );

                            resolve(false);
                        });
                } catch (e) {
                    console.error(
                        "استثناء في الإعلانات:",
                        e
                    );

                    showToast(
                        "❌ تعذر عرض الإعلان. حاول مرة أخرى."
                    );

                    resolve(false);
                }
            } else {
                showToast(
                    "⚠️ الإعلانات غير متوفرة حالياً، يرجى إعادة المحاولة لاحقاً."
                );

                resolve(false);
            }
        });
    }

    window.handleStorageUpgrade = async function () {
        if (isUpgradingStorage) return;

        isUpgradingStorage = true;

        try {
            const resData =
                await window.fetchAPI(
                    "/api/farm/upgrade_storage",
                    "POST",
                    {}
                );

            if (resData && resData.success) {
                if (resData.server_time) {
                    syncServerTime(
                        resData.server_time
                    );
                }

                setStoredBalance(
                    resData.new_balance,
                    resData.new_usd_balance
                );

                if (!window.userState) {
                    window.userState = {};
                }

                if (!window.PlayerData) {
                    window.PlayerData = {};
                }

                if (
                    resData.storage_level !==
                    undefined
                ) {
                    window.userState.storage_level =
                        resData.storage_level;

                    window.PlayerData.storage_level =
                        resData.storage_level;
                }

                if (
                    resData.max_cap !== undefined
                ) {
                    window.userState.max_cap =
                        resData.max_cap;

                    window.PlayerData.max_cap =
                        resData.max_cap;
                }

                if (
                    resData.last_claim_time
                ) {
                    window.userState.last_claim_time =
                        resData.last_claim_time;

                    window.PlayerData.last_claim_time =
                        resData.last_claim_time;
                }

                if (
                    resData.unclaimed !==
                    undefined
                ) {
                    window.userState.unclaimed =
                        resData.unclaimed;

                    window.PlayerData.unclaimed =
                        resData.unclaimed;
                }

                saveCachedData(
                    window.userState
                );

                showToast(
                    `📦 تم ترقية سعة المخزن بنجاح إلى Level ${resData.storage_level}!`
                );

                window.updateFarmUI();
            } else {
                showToast(
                    resData?.error ||
                    "❌ تعذر ترقية المخزن"
                );
            }
        } catch (e) {
            console.error(
                "خطأ ترقية المخزن:",
                e
            );

            showToast(
                "❌ حدث خطأ أثناء ترقية المخزن"
            );
        } finally {
            isUpgradingStorage = false;
            window.updateFarmUI();
        }
    };

    window.handleUpgrade = async function (level) {
        if (isUpgrading) return;

        const levelConfig =
            GAME_CONFIG.upgradeCosts[level] ||
            {};

        const costZn =
            Number.parseFloat(
                levelConfig.cost_zn ??
                levelConfig.base_cost ??
                levelConfig.price ??
                0
            ) || 0;

        const costUsd =
            Number.parseFloat(
                levelConfig.cost_usd ??
                levelConfig.base_cost_usd ??
                0
            ) || 0;

        const currentBalance =
            getStoredBalance();

        const currentUsdBalance =
            getStoredUsdBalance();

        if (
            currentBalance + 1e-12 < costZn ||
            currentUsdBalance + 1e-12 < costUsd
        ) {
            let message =
                `❌ رصيدك غير كافٍ! سعر الترقية: ${costZn.toLocaleString()} ZN`;

            if (costUsd > 0) {
                message +=
                    ` + $${costUsd.toFixed(2)} USD`;
            }

            showToast(message);
            return;
        }

        isUpgrading = true;
        window.updateFarmUI();

        try {
            const resData =
                await window.fetchAPI(
                    "/api/farm/upgrade",
                    "POST",
                    { level }
                );

            if (resData && resData.success) {
                if (resData.server_time) {
                    syncServerTime(
                        resData.server_time
                    );
                }

                setStoredBalance(
                    resData.new_balance,
                    resData.new_usd_balance
                );

                if (!window.userState) {
                    window.userState = {};
                }

                if (!window.PlayerData) {
                    window.PlayerData = {};
                }

                if (
                    resData.new_hourly_rate !==
                    undefined
                ) {
                    window.userState.hourly_rate =
                        resData.new_hourly_rate;

                    window.PlayerData.hourly_rate =
                        resData.new_hourly_rate;
                }

                if (resData.upgrades) {
                    window.userState.upgrades =
                        resData.upgrades;

                    window.PlayerData.upgrades =
                        resData.upgrades;
                }

                if (
                    resData.last_claim_time
                ) {
                    window.userState.last_claim_time =
                        resData.last_claim_time;

                    window.PlayerData.last_claim_time =
                        resData.last_claim_time;
                }

                if (
                    resData.unclaimed !==
                    undefined
                ) {
                    window.userState.unclaimed =
                        resData.unclaimed;

                    window.PlayerData.unclaimed =
                        resData.unclaimed;
                }

                saveCachedData(
                    window.userState
                );

                showToast(
                    `🏛️ تم ترقية المستوى ${level} بنجاح!`
                );

                window.updateFarmUI();
            } else {
                showToast(
                    resData?.error ||
                    "❌ تعذر إتمام الترقية"
                );
            }
        } catch (e) {
            console.error(
                "خطأ الترقية:",
                e
            );

            showToast(
                "❌ حدث خطأ أثناء عملية الشراء"
            );
        } finally {
            isUpgrading = false;
            window.updateFarmUI();
        }
    };

    window.handleDailyClaim = async function (dayNum) {
        if (isClaimingDaily) return;

        isClaimingDaily = true;
        renderDailyRewards();

        try {
            const adWatched =
                await showTelegramAd();

            if (!adWatched) {
                return;
            }

            const resData =
                await window.fetchAPI(
                    "/api/farm/daily_claim",
                    "POST",
                    {}
                );

            if (resData && resData.success) {
                if (resData.server_time) {
                    syncServerTime(
                        resData.server_time
                    );
                }

                setStoredBalance(
                    resData.new_balance,
                    resData.new_usd_balance
                );

                if (!window.userState) {
                    window.userState = {};
                }

                if (!window.PlayerData) {
                    window.PlayerData = {};
                }

                if (
                    resData.daily_day !==
                    undefined
                ) {
                    window.userState.daily_day =
                        resData.daily_day;

                    window.PlayerData.daily_day =
                        resData.daily_day;
                }

                if (
                    resData.last_daily_claim_date
                ) {
                    window.userState.last_daily_claim_date =
                        resData.last_daily_claim_date;

                    window.PlayerData.last_daily_claim_date =
                        resData.last_daily_claim_date;
                }

                saveCachedData(
                    window.userState
                );

                showToast(
                    `🎉 تم استلام مكافأة اليوم ${resData.daily_day} بنجاح!`
                );

                window.updateFarmUI();
            } else {
                showToast(
                    resData?.error ||
                    "❌ تعذر استلام المكافأة"
                );
            }
        } catch (e) {
            console.error(
                "خطأ استلام المكافأة اليومية:",
                e
            );

            showToast(
                "❌ حدث خطأ أثناء استلام المكافأة اليومية"
            );
        } finally {
            isClaimingDaily = false;
            renderDailyRewards();
        }
    };

    window.handleDailyBoost = async function () {
        if (isBoosting) return;

        isBoosting = true;
        window.updateFarmUI();

        try {
            const adWatched =
                await showTelegramAd();

            if (!adWatched) {
                return;
            }

            const resData =
                await window.fetchAPI(
                    "/api/farm/daily_boost",
                    "POST",
                    {}
                );

            if (resData && resData.success) {
                if (resData.server_time) {
                    syncServerTime(
                        resData.server_time
                    );
                }

                setStoredBalance(
                    resData.new_balance,
                    resData.new_usd_balance
                );

                if (!window.userState) {
                    window.userState = {};
                }

                if (!window.PlayerData) {
                    window.PlayerData = {};
                }

                if (
                    resData.type === "speed"
                ) {
                    if (
                        resData.new_rate !==
                        undefined
                    ) {
                        window.userState.hourly_rate =
                            resData.new_rate;

                        window.PlayerData.hourly_rate =
                            resData.new_rate;
                    }

                    if (
                        resData.daily_boost_rate !==
                        undefined
                    ) {
                        window.userState.daily_boost_rate =
                            resData.daily_boost_rate;

                        window.PlayerData.daily_boost_rate =
                            resData.daily_boost_rate;
                    }

                    if (
                        resData.last_claim_time
                    ) {
                        window.userState.last_claim_time =
                            resData.last_claim_time;

                        window.PlayerData.last_claim_time =
                            resData.last_claim_time;
                    }

                    if (
                        resData.unclaimed !==
                        undefined
                    ) {
                        window.userState.unclaimed =
                            resData.unclaimed;

                        window.PlayerData.unclaimed =
                            resData.unclaimed;
                    }

                    showToast(
                        `⚡ تم زيادة سرعة التعدين بمقدار +${resData.boost_amount || GAME_CONFIG.dailyBoostReward}/h وحفظ المحصول المعدن!`
                    );
                } else if (
                    resData.type === "balance"
                ) {
                    showToast(
                        `💰 تهانينا! تمت إضافة ${formatZnAmount(
                            resData.reward_coins ||
                            GAME_CONFIG.boostMaxRewardCoins
                        )} ZN إلى رصيدك مباشرة!`
                    );
                }

                if (
                    resData.last_boost_date
                ) {
                    window.userState.last_boost_date =
                        resData.last_boost_date;

                    window.PlayerData.last_boost_date =
                        resData.last_boost_date;
                }

                saveCachedData(
                    window.userState
                );

                window.updateFarmUI();
            } else {
                showToast(
                    resData?.error ||
                    "❌ تعذر تفعيل التعزيز"
                );
            }
        } catch (e) {
            console.error(
                "خطأ التعزيز اليومي:",
                e
            );

            showToast(
                "❌ حدث خطأ أثناء تفعيل التعزيز"
            );
        } finally {
            isBoosting = false;
            window.updateFarmUI();
        }
    };

    window.handleMainClaim = async function () {
        if (isClaimingMain) return;

        isClaimingMain = true;
        window.updateFarmUI();

        try {
            const resData =
                await window.fetchAPI(
                    "/api/farm/claim",
                    "POST",
                    {}
                );

            if (resData && resData.success) {
                if (resData.server_time) {
                    syncServerTime(
                        resData.server_time
                    );
                }

                setStoredBalance(
                    resData.new_balance,
                    resData.new_usd_balance
                );

                if (!window.userState) {
                    window.userState = {};
                }

                if (!window.PlayerData) {
                    window.PlayerData = {};
                }

                if (
                    resData.last_claim_time
                ) {
                    window.userState.last_claim_time =
                        resData.last_claim_time;

                    window.PlayerData.last_claim_time =
                        resData.last_claim_time;
                }

                window.userState.unclaimed = 0.0;
                window.PlayerData.unclaimed = 0.0;

                saveCachedData(
                    window.userState
                );

                showToast(
                    `💰 تم تجميع ${formatZnAmount(
                        resData.claimed_amount
                    )} ZN بنجاح!`
                );

                window.updateFarmUI();
            } else {
                showToast(
                    resData?.error ||
                    "❌ تعذر تجميع الرصيد"
                );
            }
        } catch (e) {
            console.error(
                "خطأ التجميع الرئيسي:",
                e
            );

            showToast(
                "❌ حدث خطأ أثناء التجميع"
            );
        } finally {
            isClaimingMain = false;
            window.updateFarmUI();
        }
    };

    window.handleClaim =
        window.handleMainClaim;
})();
