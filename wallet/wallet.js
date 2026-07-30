// =================================================================
// 💳 ZN Goxe - Wallet Module (Fully Integrated & Realtime Updated)
// =================================================================

let isWalletConnected = false;
let userWalletAddress = null;
let currentWalletTab = localStorage.getItem('lastWalletTab') || 'withdraw';
let tonConnectUI = null;

// سعر TON المباشر المخزن
window.currentTonPriceUSD = parseFloat(localStorage.getItem('last_ton_price')) || 0;
let priceIntervalTimer = null;

// التهيئة الأولى لتطبيق التليجرام
const tgApp = window.Telegram?.WebApp;
if (tgApp) tgApp.ready();

// 🛠️ التنبيهات الهزاز والاشعارات
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

// =================================================================
// 📡 1. جلب سعر TON اللحظي المطابق لمحفظة تليجرام (TonAPI + OKX + CoinGecko)
// =================================================================

function applyTonPrice(price) {
    let validPrice = parseFloat(price);
    if (isNaN(validPrice) || validPrice <= 0.1 || validPrice > 200) return;

    window.currentTonPriceUSD = validPrice;
    localStorage.setItem('last_ton_price', validPrice);

    const tonPriceElem = document.getElementById('current-ton-price');
    if (tonPriceElem) {
        tonPriceElem.innerText = validPrice.toFixed(3);
    }

    if (typeof window.updateWalletHeaderUI === 'function') {
        window.updateWalletHeaderUI();
    }
}

async function fetchLiveTonPrice() {
    // 1. TonAPI.io (المصدر الرسمي)
    try {
        let res = await fetch('https://tonapi.io/v2/rates?tokens=ton&currencies=usd');
        if (res.ok) {
            let data = await res.json();
            let price = parseFloat(data?.rates?.TON?.prices?.USD);
            if (price > 0) {
                applyTonPrice(price);
                return;
            }
        }
    } catch (e) {}

    // 2. OKX Exchange API
    try {
        let res = await fetch('https://www.okx.com/api/v5/market/ticker?instId=TON-USDT');
        if (res.ok) {
            let data = await res.json();
            let price = parseFloat(data?.data?.[0]?.last);
            if (price > 0) {
                applyTonPrice(price);
                return;
            }
        }
    } catch (e) {}

    // 3. CoinGecko API
    try {
        let res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd');
        if (res.ok) {
            let data = await res.json();
            let price = parseFloat(data['the-open-network']?.usd);
            if (price > 0) {
                applyTonPrice(price);
                return;
            }
        }
    } catch (e) {}
}

function startTonPriceSync() {
    fetchLiveTonPrice();
    if (priceIntervalTimer) clearInterval(priceIntervalTimer);
    priceIntervalTimer = setInterval(fetchLiveTonPrice, 15000);
}

// =================================================================
// 🔄 2. ربط ومزامنة المحفظة المباشرة مع game.js
// =================================================================

const originalUpdateGlobalUI = window.updateGlobalUI;
window.updateGlobalUI = function() {
    if (typeof originalUpdateGlobalUI === 'function') {
        originalUpdateGlobalUI();
    }
    window.updateWalletHeaderUI();
};

window.updateWalletHeaderUI = function() {
    if (!window.GameState) return;

    const zn = Number(window.GameState.balance) || 0;
    const usd = Number(window.GameState.usd_balance) || 0;

    const znElem = document.getElementById('wallet-zn-balance');
    const usdElem = document.getElementById('wallet-usd-balance');
    const tonElem = document.getElementById('wallet-ton-estimate');
    const tonPriceElem = document.getElementById('current-ton-price');

    if (znElem) znElem.innerText = Math.floor(zn).toLocaleString('en-US');
    
    if (usdElem) {
        usdElem.innerText = "$" + (usd > 0 && usd < 0.01 ? usd.toFixed(5) : usd.toFixed(4));
    }
    
    if (window.currentTonPriceUSD > 0) {
        let estimateTon = (usd / window.currentTonPriceUSD);
        if (tonElem) tonElem.innerText = "≈ " + estimateTon.toFixed(4) + " TON";
        if (tonPriceElem) tonPriceElem.innerText = window.currentTonPriceUSD.toFixed(3);
    }
};

window.syncWalletData = async function() {
    if (typeof window.apiCall === 'function') {
        const res = await window.apiCall('/api/farm/sync', 'POST');
        if (res && res.success && res.data) {
            if (res.data.balance !== undefined) window.GameState.balance = res.data.balance;
            if (res.data.usd_balance !== undefined) window.GameState.usd_balance = res.data.usd_balance;
            if (res.data.ad_balance !== undefined) window.GameState.ad_balance = res.data.ad_balance;
            window.updateWalletHeaderUI();
        }
    }
};

// =================================================================
// 🔗 3. تهيئة TON Connect
// =================================================================

function initTonConnect() {
    if (typeof window.TON_CONNECT_UI === 'undefined') {
        setTimeout(initTonConnect, 100);
        return;
    }

    if (!tonConnectUI) {
        const themeDark = window.TON_CONNECT_UI.THEME ? window.TON_CONNECT_UI.THEME.DARK : 'DARK';

        tonConnectUI = new window.TON_CONNECT_UI.TonConnectUI({
            manifestUrl: 'https://zn-goxe-production.up.railway.app/tonconnect-manifest.json',
            buttonRootId: 'hidden-ton-root',
            uiPreferences: {
                theme: themeDark,
                colorsSet: {
                    [themeDark]: {
                        connectButton: { background: '#0098ea', foreground: '#ffffff' },
                        accent: '#0098ea',
                        iconOnAccent: '#ffffff',
                        background: { 
                            primary: '#0a0d14', 
                            secondary: '#161c27', 
                            qr: '#ffffff', 
                            tint: '#1e293b' 
                        },
                        text: { primary: '#ffffff', secondary: '#94a3b8' }
                    }
                }
            }
        });

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
        if (!tonConnectUI) initTonConnect();
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

// =================================================================
// 🎛️ 4. أزرار الاختيار السريع للكميات
// =================================================================

window.selectDepositPackage = function(amountUsd, element) {
    triggerHapticFeedback('impact', 'light');
    document.querySelectorAll('.package-card').forEach(card => card.classList.remove('selected'));
    if (element) element.classList.add('selected');

    const input = document.getElementById('deposit-usd-input');
    if (input) {
        input.value = amountUsd;
        window.calculateDepositTon();
    }
};

window.setQuickZn = function(percent) {
    const zn = Number(window.GameState?.balance) || 0;
    const amount = Math.floor((zn * percent) / 100);
    const input = document.getElementById('zn-input');
    if (input) {
        input.value = amount;
        window.calculateConversionPreview();
    }
};

window.setQuickUsd = function(percent) {
    const usd = Number(window.GameState?.usd_balance) || 0;
    const amount = ((usd * percent) / 100).toFixed(4);
    const input = document.getElementById('usd-withdraw');
    if (input) {
        input.value = amount;
        window.calculateWithdrawTon();
    }
};

// =================================================================
// 🖼️ 5. عرض محتوى التبويبات
// =================================================================

window.renderWalletTab = function(tab) {
    currentWalletTab = tab;
    localStorage.setItem('lastWalletTab', tab);

    window.syncWalletData();

    const content = document.getElementById('wallet-content');
    if (!content) return;
    
    ['withdraw', 'history', 'deposit'].forEach(t => {
        const btn = document.getElementById(`btn-${t}`);
        if (btn) btn.classList.toggle('active', t === tab);
    });

    if (tab === 'deposit') {
        let depositHtml = `
            <div class="card">
                <div class="deposit-notice-bar">
                    <span>📌 الحد الأدنى للإيداع: <b>$1.00</b></span>
                    <span>⚡ الخصم/الرسوم: <b>3%</b></span>
                </div>

                <div class="packages-section-title">
                    <span>💎 باقات الرصيد السريعة</span>
                </div>

                <div class="packages-grid">
                    <div class="package-card" onclick="window.selectDepositPackage(1, this)">
                        <div class="package-price">$1.00</div>
                        <div class="package-amount">تضاف $0.97</div>
                    </div>
                    <div class="package-card" onclick="window.selectDepositPackage(5, this)">
                        <div class="package-price">$5.00</div>
                        <div class="package-amount">تضاف $4.85</div>
                    </div>
                    <div class="package-card" onclick="window.selectDepositPackage(10, this)">
                        <span class="package-tag">شائع 🔥</span>
                        <div class="package-price">$10.00</div>
                        <div class="package-amount">تضاف $9.70</div>
                    </div>
                    <div class="package-card" onclick="window.selectDepositPackage(25, this)">
                        <span class="package-tag">الأفضل ⭐</span>
                        <div class="package-price">$25.00</div>
                        <div class="package-amount">تضاف $24.25</div>
                    </div>
                </div>`;

        if (!isWalletConnected) {
            depositHtml += `
                <div class="locked-state">
                    <div style="font-size: 38px; margin-bottom: 8px;">🔒</div>
                    <p style="color:#ef4444; font-weight:700; margin-top:0; font-size:13px;">قم بربط محفظة TON لإتمام الإيداع</p>
                    <button onclick="window.connectCustomWallet()" class="action-btn btn-blue" style="margin-top:6px;">ربط المحفظة الآن</button>
                </div></div>`;
        } else {
            depositHtml += `
                <div class="connected-state">
                    <div class="wallet-address-text">
                        ✅ المحفظة المتصلة:<br><b style="color: #fff;" class="num-en">${userWalletAddress}</b>
                    </div>
                    <button onclick="window.disconnectCustomWallet()" class="disconnect-btn">فصل</button>
                </div>
                
                <div class="input-group">
                    <label class="input-label">أو أدخل مبلغ مخصص بالدولار ($)</label>
                    <input type="number" id="deposit-usd-input" class="input-field" placeholder="1.00" min="1" step="0.5" oninput="window.calculateDepositTon()">
                </div>
                
                <div id="deposit-calc-info" style="display:none; padding:12px; margin-bottom:15px; border-radius:12px; text-align:center; background:rgba(0, 152, 234, 0.08); border:1px solid rgba(0, 152, 234, 0.2); font-size:13px;">
                    <div>الرصيد الصافي المضاف: <b id="net-credited-usd" style="color:#10b981;">$0.00</b></div>
                    <div style="margin-top:4px;">المبلغ المطلوب بالـ TON: <b id="required-ton-amount" style="color:#0098ea;" class="num-en">0</b> TON</div>
                </div>
                
                <button id="deposit-btn" onclick="window.executeDeposit()" class="action-btn btn-blue">متابعة الدفع عبر TON</button>
            </div>`;
        }
        content.innerHTML = depositHtml;
    } 
    else if (tab === 'history') {
        content.innerHTML = `
            <div class="card" style="text-align:center; color:#94a3b8; padding:30px;">
                <div style="font-size:32px; margin-bottom:10px;">⏳</div>
                جاري جلب سجل المعاملات...
            </div>`;
        
        if (typeof window.apiCall === 'function') {
            window.apiCall('/api/wallet/get_history', 'GET').then(data => {
                if (currentWalletTab !== 'history') return;

                const rawList = data?.history || data?.transactions || data?.data || data?.logs || [];

                if (data && data.success && Array.isArray(rawList) && rawList.length > 0) {
                    let html = `<div class="card" style="padding: 16px;">
                        <h3 style="margin-top:0; color:#fff; text-align:center; font-size:16px; margin-bottom:15px;">📋 سجل المعاملات</h3>
                        <div style="display: flex; flex-direction: column; gap: 10px; max-height: 380px; overflow-y: auto;">`;
                    
                    rawList.forEach(item => {
                        let typeText = '⚙️ عملية';
                        let amountColor = '#10b981';
                        
                        const itemType = String(item.type || '').toLowerCase();

                        if (itemType === 'deposit') {
                            typeText = '🟢 إيداع TON';
                            amountColor = '#10b981';
                        } else if (itemType === 'withdraw' || itemType === 'withdrawal') {
                            typeText = '🔴 سحب أرباح';
                            amountColor = '#ef4444';
                        } else if (itemType === 'convert' || itemType === 'conversion' || itemType === 'points_convert') {
                            typeText = '🔄 تحويل نقاط ZN';
                            amountColor = '#0098ea';
                        }

                        let statusText = 'مكتمل ✅';
                        let statusColor = '#10b981';
                        const status = String(item.status || '').toLowerCase();

                        if (status === 'pending' || status === 'processing') {
                            statusText = 'قيد المراجعة ⏳';
                            statusColor = '#f59e0b';
                        } else if (status === 'rejected' || status === 'cancelled' || status === 'failed') {
                            statusText = 'مرفوض ❌';
                            statusColor = '#ef4444';
                        }

                        const dateStr = (item.created_at || item.date || item.timestamp) ? new Date(item.created_at || item.date || item.timestamp).toLocaleString('en-US', {
                            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                        }) : '';

                        const rawAmount = parseFloat(item.amount_usd || item.amount || item.usd_amount || item.amount_zn / 1000000 || 0);
                        const displayAmount = (rawAmount > 0 && rawAmount < 0.01) ? rawAmount.toFixed(5) : rawAmount.toFixed(2);
                        
                        html += `
                            <div style="background: rgba(10, 13, 20, 0.5); padding: 12px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; border: 1px solid rgba(255,255,255,0.05);">
                                <div>
                                    <div style="font-weight: bold; color: #fff; font-size: 14px;">${typeText}</div>
                                    <div style="font-size: 11px; color: #94a3b8; margin-top: 3px;" class="num-en">${dateStr}</div>
                                </div>
                                <div style="text-align: left;">
                                    <div style="color: ${amountColor}; font-weight: 800; font-size: 15px;" class="num-en">$${displayAmount}</div>
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
                            لا توجد عمليات سابقة مسجلة
                        </div>`;
                }
            }).catch(() => {
                if (currentWalletTab !== 'history') return;
                content.innerHTML = `<div class="card" style="text-align:center; color:#ef4444; padding:30px;">⚠️ تعذر تحميل السجل حالياً.</div>`;
            });
        }
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
                    ستحصل على: <b id="expected-usd-amount" class="num-en">$0.00000</b>
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
                            ✅ المحفظة المتصلة:<br><b style="color: #fff;" class="num-en">${userWalletAddress}</b>
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
        content.innerHTML = withdrawHtml;
    }

    window.updateWalletHeaderUI();
};

// =================================================================
// 🧮 6. الحسابات التفاعلية
// =================================================================

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
    let netElem = document.getElementById('net-credited-usd');

    let usd = parseFloat(inputElem?.value);

    if (usd >= 1 && window.currentTonPriceUSD > 0) {
        let netUsd = usd * 0.97;
        let tonRequired = (usd / window.currentTonPriceUSD).toFixed(4);

        if (netElem) netElem.innerText = "$" + netUsd.toFixed(2);
        if (requiredElem) requiredElem.innerText = tonRequired;
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
        let tonReceive = (usd / window.currentTonPriceUSD).toFixed(4);
        if (receiveElem) receiveElem.innerText = tonReceive;
        infoDiv.style.display = 'block';
    } else { 
        if (infoDiv) infoDiv.style.display = 'none'; 
    }
};

// =================================================================
// ⚡ 7. تنفيذ العمليات ومزامنة الرصيد فوراً
// =================================================================

window.executeDeposit = async function() {
    triggerHapticFeedback('impact', 'medium');
    let depositBtn = document.getElementById('deposit-btn');
    let usdInput = document.getElementById('deposit-usd-input');
    
    let usdAmount = parseFloat(usdInput?.value);

    if (!usdAmount || usdAmount < 1.00) {
        return showAppAlert("⚠️ الحد الأدنى للإيداع هو $1.00 USD");
    }

    if (!window.currentTonPriceUSD || window.currentTonPriceUSD <= 0) {
        return showAppAlert("⚠️ جاري جلب سعر TON المباشر، يرجى الانتظار ثوانٍ والتجربة مجدداً.");
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
        const txResult = await tonConnectUI.sendTransaction(transaction);
        triggerHapticFeedback('notification', 'success');

        const netCredited = usdAmount * 0.97;

        if (typeof window.apiCall === 'function') {
            let result = await window.apiCall('/api/wallet/wallet_deposit_report', 'POST', {
                usdAmount: usdAmount, 
                netUsdAmount: netCredited,
                tonAmount: tonAmount, 
                boc: txResult.boc 
            });
            
            if (result.success) {
                if (result.new_usd_balance !== undefined) {
                    window.GameState.usd_balance = result.new_usd_balance;
                } else {
                    window.GameState.usd_balance = (window.GameState.usd_balance || 0) + netCredited;
                }
                
                window.updateWalletHeaderUI();
                showAppAlert(`✅ تم الإيداع بنجاح!\nأضيفت $${netCredited.toFixed(2)} لرصيدك بعد خصم (3%).`);
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

    if (amount > (window.GameState?.balance || 0)) {
        return showAppAlert("⚠️ رصيدك الحالي غير كافٍ لتحويل هذه الكمية.");
    }

    try {
        if (convertBtn) { convertBtn.disabled = true; convertBtn.innerText = "⏳ جاري التحويل..."; }
        
        let result = await window.apiCall('/api/wallet/wallet_convert', 'POST', { amount: amount });
        
        if (result.success) {
            triggerHapticFeedback('notification', 'success');
            
            window.GameState.balance -= amount;
            if (result.new_usd_balance !== undefined) {
                window.GameState.usd_balance = result.new_usd_balance;
            } else {
                window.GameState.usd_balance += (result.usd_gained || (amount / 1000000));
            }

            window.updateWalletHeaderUI();
            showAppAlert(`🎉 تم تحويل النقاط بنجاح!\nأضيف لرصيدك $${(result.usd_gained || (amount/1000000)).toFixed(5)} USD`);
            
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

    if (usdAmount > (window.GameState?.usd_balance || 0)) {
        return showAppAlert("⚠️ رصيدك بالدولار غير كافٍ لعملية السحب هذه.");
    }

    if (!userWalletAddress) {
        return showAppAlert("⚠️ يرجى ربط المحفظة أولاً.");
    }

    try {
        if (withdrawBtn) { withdrawBtn.disabled = true; withdrawBtn.innerText = "⏳ جاري الإرسال..."; }

        let result = await window.apiCall('/api/wallet/wallet_withdraw', 'POST', {
            amount: usdAmount,
            walletAddress: userWalletAddress
        });
        
        if (result.success) {
            triggerHapticFeedback('notification', 'success');
            
            if (result.new_usd_balance !== undefined) {
                window.GameState.usd_balance = result.new_usd_balance;
            } else {
                window.GameState.usd_balance -= usdAmount;
            }

            window.updateWalletHeaderUI();
            
            let expectedTon = (usdAmount / (window.currentTonPriceUSD || 1)).toFixed(4);
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

// =================================================================
// 🚀 8. بدء التشغيل التلقائي والمزامنة
// =================================================================

startTonPriceSync();
window.syncWalletData();
window.renderWalletTab(currentWalletTab);
initTonConnect();
