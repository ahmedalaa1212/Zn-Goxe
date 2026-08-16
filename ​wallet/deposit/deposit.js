// wallet/deposit/deposit.js
(function () {
    'use strict';

    window.selectDepositPackage = function(amountUsd, element) {
        window.triggerHapticFeedback?.('impact', 'light');
        document.querySelectorAll('.package-card').forEach(card => card.classList.remove('selected'));
        if (element) element.classList.add('selected');

        const input = document.getElementById('deposit-usd-input');
        if (input) {
            input.value = amountUsd;
            window.calculateDepositTon();
        }
    };

    window.calculateDepositTon = function() {
        let inputElem = document.getElementById('deposit-usd-input');
        let infoDiv = document.getElementById('deposit-calc-info');
        let requiredElem = document.getElementById('required-ton-amount');
        let netElem = document.getElementById('net-credited-usd');

        let usd = parseFloat(inputElem?.value);

        if (usd >= 1 && window.currentTonPriceUSD > 0) {
            let netUsd = usd * 0.97;
            let tonRequired = (usd / window.currentTonPriceUSD).toFixed(2);

            if (netElem) netElem.innerText = "$" + netUsd.toFixed(2);
            if (requiredElem) requiredElem.innerText = tonRequired;
            if (infoDiv) infoDiv.style.display = 'block';
        } else { 
            if (infoDiv) infoDiv.style.display = 'none'; 
        }
    };

    window.executeDeposit = async function() {
        window.triggerHapticFeedback?.('impact', 'medium');
        let depositBtn = document.getElementById('deposit-btn');
        let usdInput = document.getElementById('deposit-usd-input');
        
        let usdAmount = parseFloat(usdInput?.value);

        if (!usdAmount || usdAmount < 1.00) {
            return window.showAppAlert?.("⚠️ الحد الأدنى للإيداع هو $1.00 USD");
        }

        if (!window.currentTonPriceUSD || window.currentTonPriceUSD <= 0) {
            return window.showAppAlert?.("⚠️ جاري جلب سعر TON المباشر، يرجى الانتظار ثوانٍ والتجربة مجدداً.");
        }

        let tonAmount = usdAmount / window.currentTonPriceUSD;
        let nanoTon = Math.floor(tonAmount * 1e9).toString(); 
        let projectWallet = "UQCkqSqgiw80Qz7ljESrhHppPAZU-lcTrmxyELN1Y-syVGtc"; 
        
        const transaction = {
            validUntil: Math.floor(Date.now() / 1000) + 360,
            messages: [{ address: projectWallet, amount: nanoTon }]
        };

        try {
            if (depositBtn) { depositBtn.disabled = true; depositBtn.innerText = "⏳ جاري فتح المحفظة..."; }
            const tonConnectUI = window.getTonConnectInstance?.();
            if (!tonConnectUI) throw new Error("تعذر الوصول إلى محفظة TON Connect");

            const txResult = await tonConnectUI.sendTransaction(transaction);
            window.triggerHapticFeedback?.('notification', 'success');

            const netCredited = usdAmount * 0.97;
            const payload = window.getAuthPayload?.({
                usdAmount: usdAmount, 
                netUsdAmount: netCredited,
                tonAmount: tonAmount, 
                boc: txResult.boc 
            });

            let result = await window.apiCall('/api/wallet/deposit/report', 'POST', payload);
            
            if (result && result.success) {
                if (!window.GameState) window.GameState = {};
                if (result.new_usd_balance !== undefined) {
                    window.GameState.usd_balance = result.new_usd_balance;
                } else {
                    window.GameState.usd_balance = (window.GameState.usd_balance || 0) + netCredited;
                }
                
                window.clearHistoryCache?.();
                window.updateWalletHeaderUI?.();
                window.showAppAlert?.(`✅ تم الإيداع بنجاح!\nأضيفت $${netCredited.toFixed(2)} لرصيدك بعد خصم (3%).`);
                if (usdInput) usdInput.value = '';
            } else {
                window.showAppAlert?.("⚠️ " + (result?.error || result?.message || "فشل تأكيد الإيداع في السيرفر"));
            }
        } catch (e) {
            window.triggerHapticFeedback?.('notification', 'warning');
            if (e && e.message !== "User rejected the transaction") {
                const errMsg = e?.message || e?.error || "تم إلغاء المعاملة أو حدث خطأ أثناء الدفع.";
                window.showAppAlert?.("⚠️ " + errMsg);
            }
        } finally {
            if (depositBtn) { depositBtn.disabled = false; depositBtn.innerText = "متابعة الدفع عبر TON"; }
        }
    };

    window.renderDepositUI = function() {
        const authContainer = document.getElementById('deposit-wallet-auth-container');
        if (!authContainer) return;

        if (!window.isWalletConnected) {
            authContainer.innerHTML = `
                <div class="locked-state">
                    <div style="font-size: 38px; margin-bottom: 8px;">🔒</div>
                    <p style="color:#ef4444; font-weight:700; margin-top:0; font-size:13px;">قم بربط محفظة TON لإتمام الإيداع</p>
                    <button onclick="window.connectCustomWallet()" class="action-btn btn-blue" style="margin-top:6px;">ربط المحفظة الآن</button>
                </div>`;
        } else {
            authContainer.innerHTML = `
                <div class="connected-state">
                    <div class="wallet-address-text">
                        ✅ المحفظة المتصلة:<br><b style="color: #fff;" class="num-en">${window.userWalletAddress}</b>
                    </div>
                    <button onclick="window.disconnectCustomWallet()" class="disconnect-btn">فصل</button>
                </div>
                
                <div class="input-group">
                    <label class="input-label">أدخل مبلغ مخصص بالدولار ($)</label>
                    <input type="number" id="deposit-usd-input" class="input-field" placeholder="1.00" min="1" step="0.5" oninput="window.calculateDepositTon()">
                </div>
                
                <div id="deposit-calc-info" style="display:none; padding:12px; margin-bottom:15px; border-radius:12px; text-align:center; background:rgba(0, 152, 234, 0.08); border:1px solid rgba(0, 152, 234, 0.2); font-size:13px;">
                    <div>الرصيد الصافي المضاف: <b id="net-credited-usd" style="color:#10b981;">$0.00</b></div>
                    <div style="margin-top:4px;">المبلغ المطلوب بالـ TON: <b id="required-ton-amount" style="color:#0098ea;" class="num-en">0</b> TON</div>
                </div>
                
                <button id="deposit-btn" onclick="window.executeDeposit()" class="action-btn btn-blue">متابعة الدفع عبر TON</button>`;
        }
    };
})();

