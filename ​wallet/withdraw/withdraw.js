// wallet/withdraw/withdraw.js
(function () {
    'use strict';

    window.setQuickZn = function(percent) {
        window.triggerHapticFeedback?.('impact', 'light');
        const zn = Number(window.GameState?.balance) || 0;
        const amount = Math.floor((zn * percent) / 100);
        const input = document.getElementById('zn-input');
        if (input) {
            input.value = amount;
            window.calculateConversionPreview();
        }
    };

    window.setQuickUsd = function(percent) {
        window.triggerHapticFeedback?.('impact', 'light');
        const usd = Number(window.GameState?.usd_balance) || 0;
        const amount = ((usd * percent) / 100).toFixed(2);
        const input = document.getElementById('usd-withdraw');
        if (input) {
            input.value = amount;
            window.calculateWithdrawTon();
        }
    };

    window.calculateConversionPreview = function() {
        let inputElem = document.getElementById('zn-input');
        let infoDiv = document.getElementById('conversion-calc-info');
        let expectedElem = document.getElementById('expected-usd-amount');
        
        let amount = parseFloat(inputElem?.value);
        if (amount > 0) {
            let usdExpected = (amount / 1000000).toFixed(2);
            if (expectedElem) expectedElem.innerText = "$" + usdExpected;
            if (infoDiv) infoDiv.style.display = 'block';
        } else { 
            if (infoDiv) infoDiv.style.display = 'none'; 
        }
    };

    window.calculateWithdrawTon = function() {
        let inputElem = document.getElementById('usd-withdraw');
        let infoDiv = document.getElementById('withdraw-calc-info');
        let receiveElem = document.getElementById('receive-ton-amount');

        let usd = parseFloat(inputElem?.value);
        if (usd > 0 && window.currentTonPriceUSD > 0) {
            let tonReceive = (usd / window.currentTonPriceUSD).toFixed(2);
            if (receiveElem) receiveElem.innerText = tonReceive;
            if (infoDiv) infoDiv.style.display = 'block';
        } else { 
            if (infoDiv) infoDiv.style.display = 'none'; 
        }
    };

    window.convertManualPoints = async function() {
        window.triggerHapticFeedback?.('impact', 'medium');
        let convertBtn = document.getElementById('convert-btn');
        let znInput = document.getElementById('zn-input');

        let amount = parseFloat(znInput?.value);
        if (!amount || isNaN(amount) || amount < 1000000) {
            return window.showAppAlert?.("⚠️ الحد الأدنى للتحويل هو 1,000,000 ZN");
        }

        if (amount > (window.GameState?.balance || 0)) {
            return window.showAppAlert?.("⚠️ رصيدك الحالي غير كافٍ لتحويل هذه الكمية.");
        }

        try {
            if (convertBtn) { convertBtn.disabled = true; convertBtn.innerText = "⏳ جاري التحويل..."; }
            
            const payload = window.getAuthPayload?.({ amount: amount });
            let result = await window.apiCall('/api/wallet/withdraw/convert', 'POST', payload);
            
            if (result && result.success) {
                window.triggerHapticFeedback?.('notification', 'success');
                
                if (!window.GameState) window.GameState = {};
                if (result.new_balance !== undefined) window.GameState.balance = result.new_balance;
                if (result.new_usd_balance !== undefined) window.GameState.usd_balance = result.new_usd_balance;

                window.clearHistoryCache?.();
                window.updateWalletHeaderUI?.();
                
                const usdAdded = (result.usd_gained || (amount / 1000000)).toFixed(2);
                window.showAppAlert?.(`🎉 تم تحويل النقاط بنجاح!\nأضيف لرصيدك $${usdAdded} USD`);
                
                if (znInput) znInput.value = '';
                const convInfo = document.getElementById('conversion-calc-info');
                if (convInfo) convInfo.style.display = 'none';
            } else {
                window.showAppAlert?.("⚠️ " + (result?.error || result?.message || "فشل التحويل."));
            }
        } catch (e) { 
            const serverError = e?.message || e?.error || "خطأ في الاتصال بالسيرفر.";
            window.showAppAlert?.("⚠️ " + serverError); 
        } finally {
            if (convertBtn) { convertBtn.disabled = false; convertBtn.innerText = "تحويل النقاط الآن"; }
        }
    };

    window.submitWithdrawal = async function() {
        window.triggerHapticFeedback?.('impact', 'medium');
        let withdrawBtn = document.getElementById('withdraw-btn');
        let usdInput = document.getElementById('usd-withdraw');

        let usdAmount = parseFloat(usdInput?.value);
        if (!usdAmount || usdAmount <= 0) {
            return window.showAppAlert?.("⚠️ يرجى إدخال مبلغ صحيح للسحب ($)");
        }

        if (usdAmount > (window.GameState?.usd_balance || 0)) {
            return window.showAppAlert?.("⚠️ رصيدك بالدولار غير كافٍ لعملية السحب هذه.");
        }

        if (!window.userWalletAddress) {
            return window.showAppAlert?.("⚠️ يرجى ربط المحفظة أولاً.");
        }

        try {
            if (withdrawBtn) { withdrawBtn.disabled = true; withdrawBtn.innerText = "⏳ جاري الإرسال..."; }

            const payload = window.getAuthPayload?.({
                amount: usdAmount,
                walletAddress: window.userWalletAddress
            });

            let result = await window.apiCall('/api/wallet/withdraw/request', 'POST', payload);
            
            if (result && result.success) {
                window.triggerHapticFeedback?.('notification', 'success');
                
                if (!window.GameState) window.GameState = {};
                if (result.new_usd_balance !== undefined) {
                    window.GameState.usd_balance = result.new_usd_balance;
                }

                window.clearHistoryCache?.();
                window.updateWalletHeaderUI?.();
                
                let expectedTon = (usdAmount / (window.currentTonPriceUSD || 1)).toFixed(2);
                window.showAppAlert?.(`✅ تم تقديم طلب السحب بقيمة $${usdAmount.toFixed(2)}.\nستصلك (≈ ${expectedTon} TON) بعد المراجعة.`);
                
                if (usdInput) usdInput.value = '';
                const wInfo = document.getElementById('withdraw-calc-info');
                if (wInfo) wInfo.style.display = 'none';
            } else {
                window.showAppAlert?.("⚠️ " + (result?.error || result?.message || "خطأ أثناء معالجة الطلب"));
            }
        } catch (e) { 
            const serverError = e?.message || e?.error || "خطأ في الاتصال بالسيرفر.";
            window.showAppAlert?.("⚠️ " + serverError); 
        } finally {
            if (withdrawBtn) { withdrawBtn.disabled = false; withdrawBtn.innerText = "تقديم طلب السحب"; }
        }
    };

    window.renderWithdrawUI = function() {
        const authContainer = document.getElementById('withdraw-wallet-auth-container');
        if (!authContainer) return;

        if (!window.isWalletConnected) {
            authContainer.innerHTML = `
                <div class="card locked-state">
                    <div style="font-size: 42px; margin-bottom: 10px;">🔒</div>
                    <p style="color:#ef4444; font-weight:700; margin-top:0;">قم بربط محفظتك لتتمكن من سحب الأرباح</p>
                    <button onclick="window.connectCustomWallet()" class="action-btn btn-blue" style="margin-top:10px;">ربط المحفظة الآن</button>
                </div>`;
        } else {
            authContainer.innerHTML = `
                <div class="card">
                    <div class="connected-state">
                        <div class="wallet-address-text">
                            ✅ المحفظة المتصلة:<br><b style="color: #fff;" class="num-en">${window.userWalletAddress}</b>
                        </div>
                        <button onclick="window.disconnectCustomWallet()" class="disconnect-btn">فصل</button>
                    </div>

                    <h3 style="margin-top:0; color:#fff; text-align:center; font-size:16px;">📤 طلب سحب الأرباح</h3>
                    
                    <div class="input-group">
                        <label class="input-label">المبلغ بالسحب ($)</label>
                        <input type="number" id="usd-withdraw" class="input-field" placeholder="0.00" oninput="window.calculateWithdrawTon()">
                        <div class="quick-chips">
                            <button class="chip-btn" onclick="window.setQuickUsd(25)">25%</button>
                            <button class="chip-btn" onclick="window.setQuickUsd(50)">50%</button>
                            <button class="chip-btn" onclick="window.setQuickUsd(75)">75%</button>
                            <button class="chip-btn" onclick="window.setQuickUsd(100)">الكل</button>
                        </div>
                    </div>
                    
                    <div id="withdraw-calc-info" style="display:none; padding:10px; margin-bottom:15px; text-align:center; color:#94a3b8; font-size:13px; background:rgba(255,255,255,0.03); border-radius:10px;">
                        ستستلم على محفظتك: <b id="receive-ton-amount" style="color:#0098ea;" class="num-en">0</b> TON
                    </div>
                    
                    <button id="withdraw-btn" onclick="window.submitWithdrawal()" class="action-btn btn-blue">تقديم طلب السحب</button>
                </div>`;
        }
    };
})();

