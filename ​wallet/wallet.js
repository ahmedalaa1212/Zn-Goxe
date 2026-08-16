// wallet/wallet.js
const WalletModule = {
    async init() {
        await this.loadWalletData();
        this.bindEvents();
    },

    async loadWalletData() {
        const tgId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;
        if (!tgId) return;

        try {
            const response = await fetch(`/api/wallet/info?tg_id=${tgId}`);
            const result = await response.json();

            if (result.success && result.wallet) {
                this.updateUI(result.wallet);
            }
        } catch (error) {
            console.error("❌ Error loading wallet data:", error);
        }
    },

    updateUI(wallet) {
        const balanceEl = document.getElementById("wallet-main-balance");
        const usdBalanceEl = document.getElementById("wallet-usd-balance");

        if (balanceEl) balanceEl.textContent = wallet.balance.toLocaleString();
        if (usdBalanceEl) usdBalanceEl.textContent = `$${wallet.usd_balance.toFixed(2)}`;
    },

    bindEvents() {
        const depositBtn = document.getElementById("btn-wallet-deposit");
        const withdrawBtn = document.getElementById("btn-wallet-withdraw");
        const historyBtn = document.getElementById("btn-wallet-history");

        if (depositBtn) {
            depositBtn.onclick = () => this.switchTab("deposit");
        }
        if (withdrawBtn) {
            withdrawBtn.onclick = () => this.switchTab("withdraw");
        }
        if (historyBtn) {
            historyBtn.onclick = () => this.switchTab("history");
        }
    },

    switchTab(tabName) {
        document.querySelectorAll(".wallet-tab-content").forEach(el => el.style.display = "none");
        const target = document.getElementById(`wallet-tab-${tabName}`);
        if (target) target.style.display = "block";
    }
};

document.addEventListener("DOMContentLoaded", () => WalletModule.init());
