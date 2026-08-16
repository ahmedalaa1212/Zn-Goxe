// wallet/wallet.js
// هذا الملف يتم تحميله ديناميكياً بعد DOMContentLoaded، لذلك لا نعتمد
// على document.addEventListener('DOMContentLoaded', ...) هنا.

(function () {
    "use strict";

    const telegram = window.Telegram?.WebApp || null;

    function getInitData() {
        return telegram?.initData || "";
    }

    function showMessage(message) {
        if (telegram?.showAlert) {
            telegram.showAlert(String(message));
        } else {
            window.alert(String(message));
        }
    }

    let depositDataLoaded = false;
    let walletServerReadCompleted = false;
    let walletEventsBound = false;

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function getStateBalances(state = window.userState || {}) {
        const balance = Number(state?.balance);
        const usdBalance = Number(state?.usd_balance);

        return {
            balance: Number.isFinite(balance) ? balance : 0,
            usd_balance: Number.isFinite(usdBalance) ? usdBalance : 0,
        };
    }

    async function walletRequest(url, method = "GET", body = null) {
        // Use the common API helper when available so auth headers are consistent.
        if (typeof window.fetchAPI === "function") {
            return window.fetchAPI(url, method, body);
        }

        const headers = {
            "Content-Type": "application/json",
        };

        const initData = getInitData();
        if (initData) {
            headers["X-Telegram-Init-Data"] = initData;
            headers["Authorization"] = `Bearer ${initData}`;
        }

        const options = { method, headers };
        if (body !== null && method !== "GET" && method !== "HEAD") {
            options.body = JSON.stringify(body);
        }

        const response = await fetch(url, options);
        let data = {};
        try {
            data = await response.json();
        } catch {
            data = {};
        }

        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }

        return data;
    }

    function updateUIBalances(wallet) {
        const balances = getStateBalances(wallet);
        const coinElem = document.getElementById("coin-balance");
        const usdElem = document.getElementById("usd-balance");

        if (coinElem) {
            coinElem.textContent = balances.balance.toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 6,
            });
        }

        if (usdElem) {
            usdElem.textContent = balances.usd_balance.toLocaleString("en-US", {
                style: "currency",
                currency: "USD",
                minimumFractionDigits: 2,
                maximumFractionDigits: 6,
            });
        }
    }

    async function loadWalletData(force = false) {
        const state = window.userState || {};
        const balances = getStateBalances(state);

        // The main game already loads the authenticated user and keeps one
        // Firestore onSnapshot listener alive. Re-reading /api/wallet/info
        // every time the wallet tab opens only duplicates a database read.
        if (!force && window.__userStateHydrated === true) {
            updateUIBalances(balances);
            return balances;
        }

        if (!force && walletServerReadCompleted) {
            updateUIBalances(balances);
            return balances;
        }

        try {
            const result = await walletRequest("/api/wallet/info", "POST", {
                initData: getInitData(),
            });

            if (result?.success && result.wallet) {
                const serverBalance = Number(result.wallet.balance);
                const serverUsd = Number(result.wallet.usd_balance);

                if (window.userState) {
                    if (Number.isFinite(serverBalance)) {
                        window.userState.balance = serverBalance;
                    }
                    if (Number.isFinite(serverUsd)) {
                        window.userState.usd_balance = serverUsd;
                    }
                }

                walletServerReadCompleted = true;
                updateUIBalances(result.wallet);
                return getStateBalances(result.wallet);
            }

            console.warn(
                "⚠️ لم يتم استرجاع بيانات المحفظة:",
                result?.error || "Unknown error"
            );
        } catch (error) {
            console.error("❌ خطأ أثناء جلب رصيد المحفظة:", error);
        }

        updateUIBalances(balances);
        return balances;
    }

    function switchTab(tabName) {
        document
            .querySelectorAll(".wallet-btn-tab")
            .forEach((btn) => btn.classList.remove("active"));

        document
            .querySelectorAll(".wallet-content-section")
            .forEach((section) => section.classList.remove("active"));

        const activeBtn = Array.from(document.querySelectorAll(".wallet-btn-tab"))
            .find((btn) => btn.dataset.walletTab === tabName) || null;
        const activeSection = document.getElementById(`${tabName}-section`);

        if (activeBtn) {
            activeBtn.classList.add("active");
        }

        if (activeSection) {
            activeSection.classList.add("active");
        }

        if (tabName === "deposit") {
            loadDepositData();
        } else if (tabName === "withdraw") {
            loadWithdrawData();
        } else if (tabName === "history") {
            loadHistoryData();
        }
    }

    function initWalletTabs() {
        document.querySelectorAll(".wallet-btn-tab").forEach((button) => {
            if (button.dataset.walletBound === "1") {
                return;
            }

            button.dataset.walletBound = "1";
            button.addEventListener("click", () => {
                switchTab(button.dataset.walletTab);
            });
        });
    }

    async function loadDepositData(force = false) {
        const container = document.getElementById("deposit-options");
        if (!container) {
            return;
        }

        if (depositDataLoaded && !force) {
            return;
        }

        container.innerHTML =
            '<div class="wallet-loading">جاري تحميل وسائل الإيداع المتاحة...</div>';

        try {
            const data = await walletRequest("/api/wallet/deposit/", "GET");

            if (data?.success && Array.isArray(data.methods) && data.methods.length) {
                container.innerHTML = data.methods
                    .map((method) => {
                        const id = escapeHtml(method?.id || "");
                        const name = escapeHtml(method?.name || "طريقة إيداع");

                        return `
                            <div class="wallet-method-row">
                                <span>${name}</span>
                                <button
                                    type="button"
                                    class="wallet-inline-btn"
                                    style="background:#10b981;"
                                    data-deposit-id="${id}"
                                >شحن</button>
                            </div>
                        `;
                    })
                    .join("");

                container
                    .querySelectorAll("[data-deposit-id]")
                    .forEach((button) => {
                        button.addEventListener("click", () => {
                            const methodId = button.dataset.depositId || "";
                            if (typeof window.initDeposit === "function") {
                                window.initDeposit(methodId);
                            } else {
                                showMessage(
                                    "طريقة الإيداع جاهزة، لكن إجراء الدفع لم يتم ربطه بعد."
                                );
                            }
                        });
                    });
            } else {
                container.innerHTML =
                    '<div class="wallet-empty">وسائل الإيداع المتاحة ستظهر هنا قريباً.</div>';
            }

            depositDataLoaded = true;
        } catch (error) {
            console.error("❌ Deposit data error:", error);
            container.innerHTML =
                '<div class="wallet-empty">وسائل الشحن التلقائي قيد التجهيز.</div>';
        }
    }

    async function loadWithdrawData() {
        const container = document.getElementById("withdraw-form");
        if (!container) {
            return;
        }

        container.innerHTML = `
            <div class="wallet-withdraw-form">
                <input
                    type="number"
                    id="withdraw-amount"
                    class="wallet-input"
                    min="0"
                    step="0.01"
                    inputmode="decimal"
                    placeholder="المبلغ المراد سحبه ($)"
                >

                <input
                    type="text"
                    id="withdraw-address"
                    class="wallet-input"
                    maxlength="200"
                    autocomplete="off"
                    placeholder="عنوان المحفظة (TON / Wallet Address)"
                >

                <button
                    type="button"
                    id="wallet-submit-withdraw"
                    class="wallet-inline-btn"
                    style="background:#2563eb;padding:12px;font-size:14px;"
                >تأكيد طلب السحب</button>
            </div>
        `;

        document
            .getElementById("wallet-submit-withdraw")
            ?.addEventListener("click", submitWithdraw);
    }

    async function loadHistoryData() {
        const container = document.getElementById("history-list");
        if (!container) {
            return;
        }

        container.innerHTML =
            '<div class="wallet-loading">جاري تحميل السجل...</div>';

        try {
            const data = await walletRequest("/api/wallet/history/", "POST", {
                initData: getInitData(),
            });

            if (data?.success && Array.isArray(data.history) && data.history.length) {
                container.innerHTML = data.history
                    .map((item) => {
                        const type =
                            item?.type === "deposit" ? "📥 إيداع" : "📤 سحب";
                        const amount = escapeHtml(item?.amount ?? "");
                        const status = escapeHtml(item?.status ?? "");

                        return `
                            <div class="wallet-history-row">
                                <span>${type}</span>
                                <span style="font-weight:700;">${amount}</span>
                                <span>${status}</span>
                            </div>
                        `;
                    })
                    .join("");
            } else {
                container.innerHTML =
                    '<div class="wallet-empty">لا توجد سجلات عمليات سابقة.</div>';
            }
        } catch (error) {
            console.error("❌ History data error:", error);
            container.innerHTML =
                '<div class="wallet-empty">لا توجد عمليات سابقة حتى الآن.</div>';
        }
    }

    async function submitWithdraw() {
        const amountElement = document.getElementById("withdraw-amount");
        const addressElement = document.getElementById("withdraw-address");

        const amountText = amountElement?.value?.trim() || "";
        const address = addressElement?.value?.trim() || "";
        const amount = Number(amountText);

        if (!amountText || !Number.isFinite(amount) || amount <= 0 || !address) {
            showMessage("يرجى إدخال المبلغ وعنوان المحفظة بشكل صحيح.");
            return;
        }

        try {
            const result = await walletRequest(
                "/api/wallet/withdraw/request",
                "POST",
                {
                    initData: getInitData(),
                    amount,
                    address,
                }
            );

            if (result?.success) {
                if (window.userState) {
                    if (result.new_balance !== undefined) {
                        window.userState.balance = Number(result.new_balance) || 0;
                    }
                    if (result.new_usd_balance !== undefined) {
                        window.userState.usd_balance = Number(result.new_usd_balance) || 0;
                    }
                }

                updateUIBalances(window.userState);
                showMessage("تم تقديم طلب السحب بنجاح!");
            } else {
                showMessage(result?.error || "فشل إرسال طلب السحب");
            }
        } catch (error) {
            console.error("❌ Withdraw error:", error);
            showMessage(error?.message || "حدث خطأ أثناء إرسال طلب السحب.");
        }
    }

    let walletInitialized = false;

    function bindWalletBalanceSync() {
        if (walletEventsBound) {
            return;
        }

        walletEventsBound = true;

        const sync = (event) => {
            const state = event?.detail || window.userState || {};
            updateUIBalances(state);
        };

        window.addEventListener("userStateUpdated", sync);
        window.addEventListener("balanceUpdated", sync);

        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "visible") {
                updateUIBalances(window.userState || {});
            }
        });
    }

    function initWalletView() {
        if (walletInitialized) {
            updateUIBalances(window.userState || {});
            return;
        }

        if (!document.querySelector(".wallet-page")) {
            return;
        }

        walletInitialized = true;
        bindWalletBalanceSync();

        if (telegram) {
            telegram.ready();
            telegram.expand();
        }

        initWalletTabs();
        updateUIBalances(window.userState || {});

        // Normally this does zero database reads because game.js has already
        // hydrated userState. It is kept as a safe fallback for direct loads.
        void loadWalletData(false);
        void loadDepositData(false);
    }

    // Expose public functions for compatibility with the rest of the project.
    window.loadWalletData = loadWalletData;
    window.updateWalletUIBalances = updateUIBalances;
    window.switchWalletTab = switchTab;
    window.loadDepositData = loadDepositData;
    window.loadWithdrawData = loadWithdrawData;
    window.loadHistoryData = loadHistoryData;
    window.submitWithdraw = submitWithdraw;
    window.initWalletView = initWalletView;

    // game.js already calls init{view}View() after loading a module.
    // Calling this directly here makes the module safe even when loaded separately.
    initWalletView();
})();
