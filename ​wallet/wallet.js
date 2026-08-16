// wallet/wallet.js
const WalletModule = {
    loadedTabs: {},

    async init() {
        await this.loadWalletData();
        this.bindEvents();
        // فتح تبويب الإيداع تلقائياً عند الدخول
        this.switchTab('deposit');
    },

    async loadWalletData() {
        const tgId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;
        const url = tgId ? `/api/wallet/info?tg_id=${tgId}` : `/api/wallet/info`;

        try {
            const response = await fetch(url);
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

        if (balanceEl) balanceEl.textContent = Number(wallet.balance || 0).toLocaleString();
        if (usdBalanceEl) usdBalanceEl.textContent = `$${Number(wallet.usd_balance || 0).toFixed(2)}`;
    },

    bindEvents() {
        const depositBtn = document.getElementById("btn-wallet-deposit");
        const historyBtn = document.getElementById("btn-wallet-history");
        const withdrawBtn = document.getElementById("btn-wallet-withdraw");

        if (depositBtn) depositBtn.onclick = () => this.switchTab("deposit");
        if (historyBtn) historyBtn.onclick = () => this.switchTab("history");
        if (withdrawBtn) withdrawBtn.onclick = () => this.switchTab("withdraw");
    },

    async switchTab(tabName) {
        // إخفاء جميع محتويات التبويبات
        document.querySelectorAll(".wallet-tab-content").forEach(el => el.style.display = "none");
        
        // تحديث تنسيق الأزرار النشطة
        document.querySelectorAll(".wallet-actions .btn-action").forEach(btn => btn.classList.remove("active"));
        const activeBtn = document.getElementById(`btn-wallet-${tabName}`);
        if (activeBtn) activeBtn.classList.add("active");

        const target = document.getElementById(`wallet-tab-${tabName}`);
        if (target) {
            target.style.display = "block";
            
            // تحميل واجهة القسم الفرعي إذا لم تكن محملة سابقاً
            if (!this.loadedTabs[tabName]) {
                await this.loadSubTabContent(tabName, target);
            }
        }
    },

    async loadSubTabContent(tabName, targetEl) {
        try {
            const response = await fetch(`/wallet/${tabName}/${tabName}.html`);
            if (response.ok) {
                const html = await response.text();
                targetEl.innerHTML = html;
                this.loadedTabs[tabName] = true;

                // تشغيل ملف JS الفرعي لكل قسم إذا كان محظراً
                if (tabName === 'deposit' && window.DepositModule?.init) window.DepositModule.init();
                if (tabName === 'withdraw' && window.WithdrawModule?.init) window.WithdrawModule.init();
                if (tabName === 'history' && window.HistoryModule?.init) window.HistoryModule.init();
            }
        } catch (error) {
            console.error(`❌ Error loading ${tabName} sub-module:`, error);
        }
    }
};

document.addEventListener("DOMContentLoaded", () => WalletModule.init());
