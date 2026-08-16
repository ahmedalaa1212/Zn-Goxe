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
        const coinElem = document.getElementById("coin-balance");
        const usdElem = document.getElementById("usd-balance");

        if (coinElem) {
            coinElem.textContent = Number(wallet?.balance || 0).toLocaleString(
                "en-US",
                { minimumFractionDigits: 2, maximumFractionDigits: 6 }
            );
        }

        if (usdElem) {
            usdElem.textContent = Number(wallet?.usd_balance || 0).toLocaleString(
                "en-US",
                { style: "currency", currency: "USD", minimumFractionDigits: 2 }
            );
        }
    }

    async function loadWalletData() {
        try {
            // Send initData both in the common helper and the JSON body
            // for backward compatibility with the wallet endpoint.
            const result = await walletRequest("/api/wallet/info", "POST", {
                initData: getInitData(),
            });

            if (result?.success && result.wallet) {
                updateUIBalances(result.wallet);

                if (window.userState) {
                    if (result.wallet.balance !== undefined) {
                        window.userState.balance = Number(result.wallet.balance) || 0;
                    }
                    if (result.wallet.usd_balance !== undefined) {
                        window.userState.usd_balance =
                            Number(result.wallet.usd_balance) || 0;
                    }
                }
            } else {
                console.warn(
                    "⚠️ لم يتم استرجاع بيانات المحفظة:",
                    result?.error || "Unknown error"
                );
            }
        } catch (error) {
            console.error("❌ خطأ أثناء جلب رصيد المحفظة:", error);
        }
    }

    function switchTab(tabName) {
        document
            .querySelectorAll(".wallet-btn-tab")
            .forEach((btn) => btn.classList.remove("active"));

        document
            .querySelectorAll(".wallet-content-section")
            .forEach((section) => section.classList.remove("active"));

        const activeBtn = document.querySelector(
            `.wallet-btn-tab[data-wallet-tab="${CSS.escape(tabName)}"]`
        );
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

    async function loadDepositData() {
        const container = document.getElementById("deposit-options");
        if (!container) {
            return;
        }

        container.innerHTML =
            '<div class="wallet-loading">جاري تحميل وسائل الإيداع المتاحة...</div>';

        try {
            const data = await walletRequest("/api/wallet/deposit/", "GET");

            if (data?.success && Array.isArray(data.methods) && data.methods.length) {
                container.innerHTML = data.methods
                    .map((method) => {
                        const id = String(method?.id || "").replace(/"/g, "&quot;");
                        const name = String(method?.name || "طريقة إيداع").replace(
                            /</g,
                            "&lt;"
                        );

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
                            const methodId = button.dataset.depositId;
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
                        const amount = String(item?.amount ?? "");
                        const status = String(item?.status ?? "");

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
                showMessage("تم تقديم طلب السحب بنجاح!");
                await loadWalletData();
            } else {
                showMessage(result?.error || "فشل إرسال طلب السحب");
            }
        } catch (error) {
            console.error("❌ Withdraw error:", error);
            showMessage(error?.message || "حدث خطأ أثناء إرسال طلب السحب.");
        }
    }

    function initWalletView() {
        if (telegram) {
            telegram.ready();
            telegram.expand();
        }

        initWalletTabs();
        updateUIBalances({
            balance: window.userState?.balance || 0,
            usd_balance: window.userState?.usd_balance || 0,
        });

        loadWalletData();
        loadDepositData();
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
