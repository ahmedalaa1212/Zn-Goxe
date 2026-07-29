// ==========================================
// 💳 ZN Goxe - Wallet Module (wallet.js)
// ==========================================

let playerData = {
    znBalance: 0,
    usdBalance: 0.00000,
    tgId: null 
};

let isWalletConnected = false;
let userWalletAddress = null;
let currentTonPriceUSD = 0; 

let currentWalletTab = localStorage.getItem('lastWalletTab') || 'withdraw';
let tonConnectUI = null;

const tgApp = window.Telegram?.WebApp;
if (tgApp) tgApp.ready();

function showAppAlert(message) {
    if (tgApp && typeof tgApp.showAlert === 'function') {
        tgApp.showAlert(message);
    } else {
        alert(message);
    }
}

function triggerHapticFeedback(type = 'impact', style = 'medium') {
    if (tgApp && tgApp.HapticFeedback) {
        if (type === 'impact') tgApp.HapticFeedback.impactOccurred(style);
        else if (type === 'notification') tgApp.HapticFeedback.notificationOccurred(style);
    }
}

// 1. جلب سعر الـ TON اللحظي بأكثر من مصدر لضمان الاستقرار
async function fetchLiveTonPrice() {
    try {
        let res = await fetch('https://tonapi.io/v2/rates?tokens=ton&currencies=usd');
        let data = await res.json();
        if (data?.rates?.TON?.prices?.USD) {
            currentTonPriceUSD = data.rates.TON.prices.USD;
        } else throw new Error();
    } catch {
        try {
            let res2 = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT');
            let data2 = await res2.json();
            currentTonPriceUSD = parseFloat(data2.price);
        } catch {
            if (currentTonPriceUSD === 0) currentTonPriceUSD = 5.00;
        }
    } finally {
        const tonPriceElem = document.getElementById('current-ton-price');
        if (tonPriceElem) tonPriceElem.innerText = currentTonPriceUSD.toFixed(3);
        window.updateHeaderBalances();
    }
}

// 2. تهيئة TON Connect
function initTonConnect() {
    if (typeof window.TON_CONNECT_UI === 'undefined') {
        setTimeout(initTonConnect, 100);
        return;
    }

    if (!tonConnectUI) {
        tonConnectUI = new window.TON_CONNECT_UI.TonConnectUI({
            manifestUrl: 'https://zn-goxe-production.up.railway.app/tonconnect-manifest.json',
            buttonRootId: 'hidden-ton-root'
        });

        tonConnectUI.uiOptions = {
            theme: 'DARK',
            colorsSet: {
                DARK: {
                    connectButton: { background: '#0098ea', foreground: '#ffffff' },
                    accent: '#0098ea', 
                    background: { primary: '#0a0d14', secondary: '#161c27', qr: '#ffffff' },
                    text: { primary: '#ffffff', secondary: '#94a3b8' }
                }
            }
        };

        tonConnectUI.connectionRestored.then(restored => {
            if (restored && tonConnectUI.wallet) {
                isWalletConnected = true;
                userWalletAddress = window.TON_CONNECT_UI.toUserFriendlyAddress(tonConnectUI.wallet.account.address);
                window.renderWalletTab(currentWalletTab); 
            }
        });

        tonConnectUI.onStatusChange(wallet => {
            if (wallet && wallet.account) {
                isWalletConnected = true;
                userWalletAddress = window.TON_CONNECT_UI.toUserFriendlyAddress(wallet.account.address);
                triggerHapticFeedback('notification', 'success');
            } else {
                isWalletConnected = false;
                userWalletAddress = null;
            }
            window.renderWalletTab(currentWalletTab);
        });
    }
}

window.connectCustomWallet = async function() {
    triggerHapticFeedback('impact', 'light');
    try {
        await tonConnectUI.openModal();
    } catch (e) {
        console.log("تم إلغاء عملية الاتصال");
    }
};

window.disconnectCustomWallet = async function() {
    triggerHapticFeedback('impact', 'medium');
    if (tonConnectUI) {
        try { 
            await tonConnectUI.disconnect(); 
            showAppAlert("تم إلغاء ربط المحفظة بنجاح.");
        } catch (e) {}
    }
};

// 3. تحديث الأرصدة المعروضة
window.updateHeaderBalances = function() {
    const pData = window.GameState || window.PlayerData || playerData;
    const zn = parseFloat(pData.balance !== undefined ? pData.balance : pData.znBalance) || 0;
    const usd = parseFloat(pData.usd_balance !== undefined ? pData.usd_balance : pData.usdBalance) || 0;

    const znElem = document.getElementById('wallet-zn-balance');
    const usdElem = document.getElementById('wallet-usd-balance');
    const tonElem = document.getElementById('wallet-ton-estimate');

    if (znElem) znElem.innerText = Math.floor(zn).toLocaleString('ar-EG');
    
    if (usdElem) {
        // عرض الخانات العشرية بدقة حتى لا تظهر $0.00000 للأرصدة الصغرى
        usdElem.innerText = "$" + (usd > 0 && usd < 0.01 ? usd.toFixed(5) : usd.toFixed(4));
    }
    
    let estimateTon = currentTonPriceUSD > 0 ? (usd / currentTonPriceUSD) : 0;
    if (tonElem) tonElem.innerText = "≈ " + estimateTon.toFixed(4) + " TON";
};

// أزرار الاختيار السريع للكميات
window.setQuickZn = function(percent) {
    const pData = window.GameState || playerData;
    const zn = parseFloat(pData.balance !== undefined ? pData.balance : pData.znBalance) || 0;
    const amount = Math.floor((zn * percent) / 100);
    const input = document.getElementById('zn-input');
    if (input) {
        input.value = amount;
        window.calculateConversionPreview();
    }
};

window.setQuickUsd = function(percent) {
    const pData = window.GameState || playerData;
    const usd = parseFloat(pData.usd_balance !== undefined ? pData.usd_balance : pData.usdBalance) || 0;
    const amount = ((usd * percent) / 100).toFixed(4);
    const input = document.getElementById('usd-withdraw');
    if (input) {
        input.value = amount;
        window.calculateWithdrawTon();
    }
};

// 4. عرض محتوى التبويبات
window.renderWalletTab = function(tab) {
    currentWalletTab = tab;
    localStorage.setItem('lastWalletTab', tab);

    const content = document.getElementById('wallet-content');
    if (!content) return;
    
    ['withdraw', 'history', 'deposit'].forEach(t => {
        const btn = document.getElementById(`btn-${t}`);
        if (btn) btn.classList.toggle('active', t === tab);
    });

    if (tab === 'deposit') {
        if (!isWalletConnected) {
            content.innerHTML = `
                <div class="card locked-state">
                    <div style="font-size: 42px; margin-bottom: 10px;">🔒</div>
                    <p style="color:#ef4444; font-weight:700; margin-top:0;">قم بربط محفظة TON لإتمام الإيداع</p>
                    <button onclick="window.connectCustomWallet()" class="action-btn btn-blue" style="margin-top:10px;">ربط المحفظة الآن</button>
                </div>`;
        } else {
            content.innerHTML = `
                <div class="card">
                    <div class="connected-state">
                        <div class="wallet-address-text">
                            ✅ المحفظة المتصلة:<br><b style="color: #fff;">${userWalletAddress}</b>
                        </div>
                        <button onclick="window.disconnectCustomWallet()" class="disconnect-btn">فصل</button>
                    </div>
                    
                    <h3 style="margin-top:0; color:#fff; text-align:center; font-size:16px;">💎 إيداع لشراء رصيد USD</h3>
                    
                    <div class="input-group">
                        <label class="input-label">المبلغ المطلوب بالدولار ($)</label>
                        <input type="number" id="deposit-usd-input" class="input-field" placeholder="0.00" oninput="window.calculateDepositTon()">
                    </div>
                    
                    <div id="deposit-calc-info" style="display:none; padding:12px; margin-bottom:15px; border-radius:10px; text-align:center; background:rgba(0, 152, 234, 0.1); border:1px solid rgba(0, 152, 234, 0.2);">
                        المبلغ المطلوب بالـ TON: <b id="required-ton-amount" style="color:#0098ea;">0</b> TON
                    </div>
                    
                    <button id="deposit-btn" onclick="window.executeDeposit()" class="action-btn btn-blue">متابعة الدفع عبر TON</button>
                </div>`;
        }
    } 
    else if (tab === 'history') {
        content.innerHTML = `
            <div class="card" style="text-align:center; color:#94a3b8; padding:30px;">
                <div style="font-size:32px; margin-bottom:10px;">⏳</div>
                جاري جلب سجل المعاملات...
            </div>`;
        
        const initData = tgApp?.initData || '';
        fetch(`/api/wallet/get_history?initData=${encodeURIComponent(initData)}`)
            .then(res => res.json())
            .then(data => {
                if (currentWalletTab !== 'history') return;

                if (data.success && data.history && data.history.length > 0) {
                    let html = `<div class="card" style="padding: 16px;">
                        <h3 style="margin-top:0; color:#fff; text-align:center; font-size:16px; margin-bottom:15px;">📋 سجل المعاملات</h3>
                        <div style="display: flex; flex-direction: column; gap: 10px; max-height: 380px; overflow-y: auto;">`;
                    
                    data.history.forEach(item => {
                        const isDeposit = item.type === 'deposit';
                        const typeText = isDeposit ? '🟢 إيداع' : '🔴 سحب';
                        let statusText = 'قيد المراجعة ⏳';
                        let statusColor = '#f59e0b';
                        if (item.status === 'completed' || item.status === 'approved') {
                            statusText = 'مكتمل ✅';
                            statusColor = '#10b981';
                        } else if (item.status === 'rejected' || item.status === 'cancelled') {
                            statusText = 'مرفوض ❌';
                            statusColor = '#ef4444';
                        }

                        const dateStr = item.created_at ? new Date(item.created_at).toLocaleString('ar-EG', {
                            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                        }) : '';

                        // تنسيق مرن للمبلغ ليعرض المبالغ الصغيرة بدون تقريب لـ 0.00
                        const rawAmount = parseFloat(item.amount_usd || item.amount || 0);
                        const displayAmount = (rawAmount > 0 && rawAmount < 0.01) ? rawAmount.toFixed(4) : rawAmount.toFixed(2);
                        
                        html += `
                            <div style="background: rgba(10, 13, 20, 0.5); padding: 12px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; border: 1px solid rgba(255,255,255,0.05);">
                                <div>
                                    <div style="font-weight: bold; color: #fff; font-size: 14px;">${typeText}</div>
                                    <div style="font-size: 11px; color: #94a3b8; margin-top: 3px;">${dateStr}</div>
                                </div>
                                <div style="text-align: left;">
                                    <div style="color: ${isDeposit ? '#10b981' : '#ef4444'}; font-weight: 800; font-size: 15px;">$${displayAmount}</div>
                                    <div style="font-size: 11px; color: ${statusColor}; font-weight:600; margin-top: 3px;">${statusText}</div>
                                </div>
                            </div>`;
                    });
                    html += `</div></div>`;
                    content.innerHTML = html;
                } else {
                    content.innerHTML = `
                        <div class="card" style="text-align:center; color:#94a3b8; padding:40px 20px;">
                            <div style="font-size:40px; margin-bottom:10px;">📥</div>
                            لا توجد عمليات سحب أو إيداع سابقة
                        </div>`;
                }
            })
            .catch(() => {
                if (currentWalletTab !== 'history') return;
                content.innerHTML = `<div class="card" style="text-align:center; color:#ef4444; padding:30px;">⚠️ تعذر تحميل السجل.</div>`;
            });
    }
    else if (tab === 'withdraw') {
        let withdrawHtml = `
            <div class="card">
                <h3 style="margin-top:0; color:#fff; text-align:center; font-size:16px;">🔄 تحويل ZN إلى USD</h3>
                <label class="input-label" style="text-align:center;">(1,000,000 ZN = $1.00 USD)</label>
                
                <div class="input-group">
                    <input type="number" id="zn-input" class="input-field" placeholder="أدخل كمية النقاط" oninput="window.calculateConversionPreview()">
                    <div class="quick-chips">
                        <button class="chip-btn" onclick="window.setQuickZn(25)">25%</button>
                        <button class="chip-btn" onclick="window.setQuickZn(50)">50%</button>
                        <button class="chip-btn" onclick="window.setQuickZn(75)">75%</button>
                        <button class="chip-btn" onclick="window.setQuickZn(100)">الكل</button>
                    </div>
                </div>
                
                <div id="conversion-calc-info" style="display:none; padding:10px; margin-bottom:15px; text-align:center; color:#10b981; background:rgba(16, 185, 129, 0.1); border:1px solid rgba(16, 185, 129, 0.2); border-radius:10px; font-weight:700;">
                    ستحصل على: <b id="expected-usd-amount">$0.00000</b>
                </div>

                <button id="convert-btn" onclick="window.convertManualPoints()" class="action-btn btn-green">تحويل النقاط الآن</button>
            </div>`;

        if (!isWalletConnected) {
            withdrawHtml += `
                <div class="card locked-state">
                    <div style="font-size: 42px; margin-bottom: 10px;">🔒</div>
                    <p style="color:#ef4444; font-weight:700; margin-top:0;">قم بربط محفظتك لتتمكن من سحب الأرباح</p>
                    <button onclick="window.connectCustomWallet()" class="action-btn btn-blue" style="margin-top:10px;">ربط المحفظة الآن</button>
                </div>`;
        } else {
            withdrawHtml += `
                <div class="card">
                    <div class="connected-state">
                        <div class="wallet-address-text">
                            ✅ المحفظة المتصلة:<br><b style="color: #fff;">${userWalletAddress}</b>
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
                        ستستلم على محفظتك: <b id="receive-ton-amount" style="color:#0098ea;">0</b> TON
                    </div>
                    
                    <button id="withdraw-btn" onclick="window.submitWithdrawal()" class="action-btn btn-blue">تقديم طلب السحب</button>
                </div>`;
        }
        content.innerHTML = withdrawHtml;
    }
};

// 5. الحسابات التفاعلية للنماذج
window.calculateConversionPreview = function() {
    let inputElem = document.getElementById('zn-input');
    let infoDiv = document.getElementById('conversion-calc-info');
    let expectedElem = document.getElementById('expected-usd-amount');
    
    let amount = parseFloat(inputElem?.value);
    if (amount > 0) {
        let usdExpected = (amount / 1000000).toFixed(5);
        if (expectedElem) expectedElem.innerText = "$" + usdExpected;
        infoDiv.style.display = 'block';
    } else { 
        if (infoDiv) infoDiv.style.display = 'none'; 
    }
};

window.calculateDepositTon = function() {
    let inputElem = document.getElementById('deposit-usd-input');
    let infoDiv = document.getElementById('deposit-calc-info');
    let requiredElem = document.getElementById('required-ton-amount');

    let usd = parseFloat(inputElem?.value);
    if (usd > 0 && currentTonPriceUSD > 0) {
        let tonRequired = (usd / currentTonPriceUSD).toFixed(4);
        if (requiredElem) requiredElem.innerText = tonRequired;
        infoDiv.style.display = 'block';
    } else { 
        if (infoDiv) infoDiv.style.display = 'none'; 
    }
};

window.calculateWithdrawTon = function() {
    let inputElem = document.getElementById('usd-withdraw');
    let infoDiv = document.getElementById('withdraw-calc-info');
    let receiveElem = document.getElementById('receive-ton-amount');

    let usd = parseFloat(inputElem?.value);
    if (usd > 0 && currentTonPriceUSD > 0) {
        let tonReceive = (usd / currentTonPriceUSD).toFixed(4);
        if (receiveElem) receiveElem.innerText = tonReceive;
        infoDiv.style.display = 'block';
    } else { 
        if (infoDiv) infoDiv.style.display = 'none'; 
    }
};

// 6. تنفيذ العمليات المخاطبة للباك إيند
window.executeDeposit = async function() {
    triggerHapticFeedback('impact', 'medium');
    let depositBtn = document.getElementById('deposit-btn');
    let usdInput = document.getElementById('deposit-usd-input');
    
    let usdAmount = parseFloat(usdInput?.value);
    if (!usdAmount || usdAmount <= 0) {
        return showAppAlert("⚠️ يرجى إدخال مبلغ صحيح للإيداع ($)");
    }

    let tonAmount = usdAmount / currentTonPriceUSD;
    let nanoTon = Math.floor(tonAmount * 1e9).toString(); 
    let projectWallet = "UQCkqSqgiw80Qz7ljESrhHppPAZU-lcTrmxyELN1Y-syVGtc"; 
    
    const transaction = {
        validUntil: Math.floor(Date.now() / 1000) + 360,
        messages: [{ address: projectWallet, amount: nanoTon }]
    };

    try {
        if (depositBtn) { depositBtn.disabled = true; depositBtn.innerText = "⏳ جاري فتح المحفظة..."; }
        const txResult = await tonConnectUI.sendTransaction(transaction);
        triggerHapticFeedback('notification', 'success');

        const initData = tgApp?.initData || null;
        if (initData) {
            let response = await fetch('/api/wallet/wallet_deposit_report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: initData, usdAmount: usdAmount, tonAmount: tonAmount, boc: txResult.boc })
            });
            let result = await response.json();
            
            if (result.success) {
                // تحديث الرصيد المحلي فوراً في الـ GameState والـ PlayerData
                const targetUsd = result.new_usd_balance !== undefined ? result.new_usd_balance : null;
                
                if (window.GameState) {
                    window.GameState.usd_balance = targetUsd !== null ? targetUsd : ((window.GameState.usd_balance || 0) + usdAmount);
                }
                if (window.PlayerData) {
                    window.PlayerData.usdBalance = targetUsd !== null ? targetUsd : ((window.PlayerData.usdBalance || 0) + usdAmount);
                    window.PlayerData.usd_balance = window.PlayerData.usdBalance;
                }
                playerData.usdBalance = targetUsd !== null ? targetUsd : (playerData.usdBalance + usdAmount);

                // تحديث واجهة الرصيد العلوية فوراً
                window.updateHeaderBalances();

                showAppAlert(`✅ تم الإيداع بنجاح!\nتمت إضافة $${usdAmount} لرصيدك.`);
                if (typeof window.fetchPlayerDataFromServer === 'function') await window.fetchPlayerDataFromServer();
            } else {
                showAppAlert("⚠️ فشل تأكيد الإيداع في السيرفر: " + (result.error || result.message));
            }
        }
        if (usdInput) usdInput.value = '';
    } catch (e) {
        triggerHapticFeedback('notification', 'warning');
        if (e && e.message !== "User rejected the transaction") {
            showAppAlert("⚠️ تم إلغاء المعاملة أو حدث خطأ أثناء الدفع.");
        }
    } finally {
        if (depositBtn) { depositBtn.disabled = false; depositBtn.innerText = "متابعة الدفع عبر TON"; }
    }
};

window.convertManualPoints = async function() {
    triggerHapticFeedback('impact', 'medium');
    let convertBtn = document.getElementById('convert-btn');
    let znInput = document.getElementById('zn-input');

    let amount = parseFloat(znInput?.value);
    if (!amount || isNaN(amount) || amount < 1000000) {
        return showAppAlert("⚠️ الحد الأدنى للتحويل هو 1,000,000 ZN");
    }
    
    const initData = tgApp?.initData || null;
    if (!initData) return showAppAlert("⚠️ يجب فتح التطبيق من داخل التليجرام.");

    try {
        if (convertBtn) { convertBtn.disabled = true; convertBtn.innerText = "⏳ جاري التحويل..."; }
        let response = await fetch('/api/wallet/wallet_convert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData, amount: amount })
        });
        let result = await response.json();
        
        if (result.success) {
            triggerHapticFeedback('notification', 'success');
            const usdGained = result.usd_gained;
            
            if (window.GameState) {
                window.GameState.balance -= amount;
                window.GameState.usd_balance = result.new_usd_balance !== undefined ? result.new_usd_balance : ((window.GameState.usd_balance || 0) + usdGained);
            }
            if (window.PlayerData) {
                window.PlayerData.balance -= amount;
                window.PlayerData.usdBalance = result.new_usd_balance !== undefined ? result.new_usd_balance : ((window.PlayerData.usdBalance || 0) + usdGained);
            }
            
            window.updateHeaderBalances();
            showAppAlert(`🎉 تم تحويل النقاط بنجاح!\nأضيف لرصيدك $${usdGained.toFixed(5)} USD`);
            if (znInput) znInput.value = '';
            const convInfo = document.getElementById('conversion-calc-info');
            if (convInfo) convInfo.style.display = 'none';
        } else {
            showAppAlert("⚠️ فشل التحويل: " + (result.error || result.message));
        }
    } catch (e) { 
        showAppAlert("⚠️ خطأ في الاتصال بالسيرفر."); 
    } finally {
        if (convertBtn) { convertBtn.disabled = false; convertBtn.innerText = "تحويل النقاط الآن"; }
    }
};

window.submitWithdrawal = async function() {
    triggerHapticFeedback('impact', 'medium');
    let withdrawBtn = document.getElementById('withdraw-btn');
    let usdInput = document.getElementById('usd-withdraw');

    let usdAmount = parseFloat(usdInput?.value);
    if (!usdAmount || usdAmount <= 0) {
        return showAppAlert("⚠️ يرجى إدخال مبلغ صحيح للسحب ($)");
    }

    if (!userWalletAddress) {
        return showAppAlert("⚠️ يرجى ربط المحفظة أولاً.");
    }

    const initData = tgApp?.initData || null;
    if (!initData) return showAppAlert("⚠️ غير مصرح بالعملية خارج التليجرام.");

    try {
        if (withdrawBtn) { withdrawBtn.disabled = true; withdrawBtn.innerText = "⏳ جاري الإرسال..."; }

        let response = await fetch('/api/wallet/wallet_withdraw', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData, amount: usdAmount, walletAddress: userWalletAddress })
        });
        let result = await response.json();
        
        if (result.success) {
            triggerHapticFeedback('notification', 'success');
            
            if (window.GameState) {
                window.GameState.usd_balance = result.new_usd_balance !== undefined ? result.new_usd_balance : Math.max(0, (window.GameState.usd_balance || 0) - usdAmount);
            }
            if (window.PlayerData) {
                window.PlayerData.usdBalance = result.new_usd_balance !== undefined ? result.new_usd_balance : Math.max(0, (window.PlayerData.usdBalance || 0) - usdAmount);
            }
            
            let expectedTon = (usdAmount / currentTonPriceUSD).toFixed(4);
            window.updateHeaderBalances();
            
            showAppAlert(`✅ تم تقديم طلب السحب بقيمة $${usdAmount}.\nستصلك (≈ ${expectedTon} TON) بعد المراجعة.`);
            if (usdInput) usdInput.value = '';
            const wInfo = document.getElementById('withdraw-calc-info');
            if (wInfo) wInfo.style.display = 'none';
        } else {
            showAppAlert("⚠️ " + (result.error || result.message));
        }
    } catch (e) { 
        showAppAlert("⚠️ خطأ أثناء معالجة الطلب."); 
    } finally {
        if (withdrawBtn) { withdrawBtn.disabled = false; withdrawBtn.innerText = "تقديم طلب السحب"; }
    }
};

// بدء التهيئة والتشغيل
fetchLiveTonPrice();
setInterval(fetchLiveTonPrice, 60000);

window.renderWalletTab(currentWalletTab);
window.updateHeaderBalances();
initTonConnect();
