// wallet/wallet.js
// =================================================================
// 💳 ZN Goxe - Wallet Module (Optimized, Animated & Secured)
// =================================================================

(function initWalletModule() {
    'use strict';

    let isWalletConnected = false;
    let userWalletAddress = null;
    let currentWalletTab = localStorage.getItem('lastWalletTab') || 'withdraw';
    let tonConnectUI = null;

    // 💾 ذاكرة مؤقتة لسجل المعاملات لتقليل طلبات السيرفر وقراءات الفايربيس
    let historyCache = null;
    let historyCacheTime = 0;
    const HISTORY_CACHE_TTL = 120000; // 2 دقيقة

    // 🛡️ تثبيت آمن لدالة apiCall
    if (typeof window.apiCall !== 'function') {
        window.apiCall = async function(url, method = 'POST', payload = {}) {
            try {
                const initData = window.Telegram?.WebApp?.initData || '';
                const response = await fetch(url, {
                    method: method,
                    headers: { 
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${initData}`
                    },
                    body: JSON.stringify(payload)
                });
                return await response.json();
            } catch (err) {
                return { success: false, error: "تعذر الاتصال بالسيرفر، تأكد من اتصال الإنترنت." };
            }
        };
    }

    window.currentTonPriceUSD = parseFloat(localStorage.getItem('last_ton_price')) || 0;
    let priceIntervalTimer = null;

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

    function getAuthPayload(extraData = {}) {
        const initData = window.Telegram?.WebApp?.initData || '';
        const rawUserId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || window.GameState?.user_id || '';
        
        return {
            initData: initData,
            tg_id: String(rawUserId),
            ...extraData
        };
    }

    // =================================================================
    // 🧮 0. دالة التحديث البصري التدريجي للأرقام (Smooth Counter Animation)
    // =================================================================
    function animateValue(element, start, end, duration = 800, decimals = 2, prefix = '', suffix = '') {
        if (!element) return;
        if (isNaN(start)) start = 0;
        if (isNaN(end)) end = 0;
        
        // إذا كان الفارق ضئيل جداً نحدّث مباشرة بدون أنيميشن
        if (Math.abs(start - end) < 0.001) {
            element.innerText = prefix + (decimals === 0 ? Math.floor(end).toLocaleString('en-US') : end.toFixed(decimals)) + suffix;
            element.dataset.currentVal = end;
            return;
        }

        let startTimestamp = null;
        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            const current = start + (end - start) * progress;
            
            if (decimals === 0) {
                element.innerText = prefix + Math.floor(current).toLocaleString('en-US') + suffix;
            } else {
                element.innerText = prefix + current.toFixed(decimals) + suffix;
            }

            if (progress < 1) {
                window.requestAnimationFrame(step);
            } else {
                element.dataset.currentVal = end;
            }
        };
        window.requestAnimationFrame(step);
    }

    // =================================================================
    // 📡 1. جلب سعر TON اللحظي
    // =================================================================
    function applyTonPrice(price) {
        let validPrice = parseFloat(price);
        if (isNaN(validPrice) || validPrice <= 0.1 || validPrice > 200) return;

        window.currentTonPriceUSD = validPrice;
        localStorage.setItem('last_ton_price', validPrice.toString());

        const tonPriceElem = document.getElementById('current-ton-price');
        if (tonPriceElem) {
            tonPriceElem.innerText = validPrice.toFixed(2);
        }

        if (typeof window.updateWalletHeaderUI === 'function') {
            window.updateWalletHeaderUI();
        }
    }

    async function fetchLiveTonPrice() {
        try {
            let res = await fetch('https://tonapi.io/v2/rates?tokens=ton&currencies=usd');
            if (res.ok) {
                let data = await res.json();
                let price = parseFloat(data?.rates?.TON?.prices?.USD);
                if (price > 0) return applyTonPrice(price);
            }
        } catch (e) {}

        try {
            let res = await fetch('https://www.okx.com/api/v5/market/ticker?instId=TON-USDT');
            if (res.ok) {
                let data = await res.json();
                let price = parseFloat(data?.data?.[0]?.last);
                if (price > 0) return applyTonPrice(price);
            }
        } catch (e) {}
    }

    function startTonPriceSync() {
        fetchLiveTonPrice();
        if (priceIntervalTimer) clearInterval(priceIntervalTimer);
        priceIntervalTimer = setInterval(fetchLiveTonPrice, 30000); // تحديث كل 30 ثانية لتخفيف الضغط
    }

    // =================================================================
    // 🔄 2. ربط ومزامنة المحفظة المباشرة
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

        // تطبيق الأنيميشن البصري والتأكد من تقييد الخانات العشرية إلى رقمين فقط للـ USD
        if (znElem) {
            const currentZn = parseFloat(znElem.dataset.currentVal || znElem.innerText.replace(/,/g, '')) || 0;
            animateValue(znElem, currentZn, zn, 600, 0);
        }
        
        if (usdElem) {
            const currentUsd = parseFloat(usdElem.dataset.currentVal || usdElem.innerText.replace('$', '')) || 0;
            animateValue(usdElem, currentUsd, usd, 600, 2, '$');
        }
        
        if (window.currentTonPriceUSD > 0) {
            let estimateTon = (usd / window.currentTonPriceUSD);
            if (tonElem) tonElem.innerText = "≈ " + estimateTon.toFixed(2) + " TON";
            if (tonPriceElem) tonPriceElem.innerText = window.currentTonPriceUSD.toFixed(2);
        }
    };

    // =================================================================
    // 🔗 3. تهيئة TON Connect
    // =================================================================
    function initTonConnect() {
        if (typeof window.TON_CONNECT_UI === 'undefined') {
            setTimeout(initTonConnect, 150);
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
                            background: { primary: '#0a0d14', secondary: '#161c27', qr: '#ffffff', tint: '#1e293b' },
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
    // 🎛️ 4. أزرار الاختيار السريع
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
        triggerHapticFeedback('impact', 'light');
        const zn = Number(window.GameState?.balance) || 0;
        const amount = Math.floor((zn * percent) / 100);
        const input = document.getElementById('zn-input');
        if (input) {
            input.value = amount;
            window.calculateConversionPreview();
        }
    };

    window.setQuickUsd = function(percent) {
        triggerHapticFeedback('impact', 'light');
        const usd = Number(window.GameState?.usd_balance) || 0;
        const amount = ((usd * percent) / 100).toFixed(2);
        const input = document.getElementById('usd-withdraw');
        if (input) {
            input.value = amount;
            window.calculateWithdrawTon();
        }
    };

    // =================================================================
    // 🖼️ 5. عرض محتوى التبويبات (بدون إعادة جلب البيانات بدون داعٍ)
    // =================================================================
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
                        <label class="input-label">أدخل مبلغ مخصص بالدولار ($)</label>
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
            const renderListUI = (rawList) => {
                if (currentWalletTab !== 'history') return;

                if (Array.isArray(rawList) && rawList.length > 0) {
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
                        } else if (itemType === 'convert' || itemType === 'conversion') {
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

                        const dateVal = item.created_at || item.date || item.timestamp;
                        const dateStr = dateVal ? new Date(dateVal).toLocaleString('en-US', {
                            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                        }) : '';

                        const rawAmount = parseFloat(item.amount_usd || item.amount || (item.amount_zn ? item.amount_zn / 1000000 : 0));
                        // 🔒 تقييد الخانات العشرية برقمين بحد أقصى (مثل 5.85)
                        const displayAmount = rawAmount.toFixed(2);
                        
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
            };

            // ⚡ استخدام الكاش لمنع استنزاف قراءات الفايربيس عند فتح السجل بانتظام
            const now = Date.now();
            if (historyCache && (now - historyCacheTime < HISTORY_CACHE_TTL)) {
                renderListUI(historyCache);
            } else {
                content.innerHTML = `
                    <div class="card" style="text-align:center; color:#94a3b8; padding:30px;">
                        <div style="font-size:32px; margin-bottom:10px;">⏳</div>
                        جاري جلب سجل المعاملات...
                    </div>`;

                const payload = getAuthPayload();
                window.apiCall('/api/wallet/get_history', 'POST', payload).then((data) => {
                    const rawList = data?.history || data?.transactions || data?.data || [];
                    historyCache = rawList;
                    historyCacheTime = Date.now();
                    renderListUI(rawList);
                }).catch(() => {
                    renderListUI([]);
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
                        ستحصل على: <b id="expected-usd-amount" class="num-en">$0.00</b>
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
            let usdExpected = (amount / 1000000).toFixed(2);
            if (expectedElem) expectedElem.innerText = "$" + usdExpected;
            if (infoDiv) infoDiv.style.display = 'block';
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
            let tonRequired = (usd / window.currentTonPriceUSD).toFixed(2);

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
            let tonReceive = (usd / window.currentTonPriceUSD).toFixed(2);
            if (receiveElem) receiveElem.innerText = tonReceive;
            if (infoDiv) infoDiv.style.display = 'block';
        } else { 
            if (infoDiv) infoDiv.style.display = 'none'; 
        }
    };

    // =================================================================
    // ⚡ 7. تنفيذ العمليات ومزامنة الرصيد فوراً (مبدأ الرد المباشر بدون إعادة جلب)
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

            const payload = getAuthPayload({
                usdAmount: usdAmount, 
                netUsdAmount: netCredited,
                tonAmount: tonAmount, 
                boc: txResult.boc 
            });

            let result = await window.apiCall('/api/wallet/wallet_deposit_report', 'POST', payload);
            
            if (result && result.success) {
                // ⚡ تحديث الـ State مباشرة
                if (!window.GameState) window.GameState = {};
                if (result.new_usd_balance !== undefined) {
                    window.GameState.usd_balance = result.new_usd_balance;
                } else {
                    window.GameState.usd_balance = (window.GameState.usd_balance || 0) + netCredited;
                }
                
                historyCache = null; // إبطال الكاش لإعادة جلب السجل مع العملية الجديدة عند فتح التبويب
                window.updateWalletHeaderUI();
                showAppAlert(`✅ تم الإيداع بنجاح!\nأضيفت $${netCredited.toFixed(2)} لرصيدك بعد خصم (3%).`);
                if (usdInput) usdInput.value = '';
            } else {
                showAppAlert("⚠️ " + (result?.error || result?.message || "فشل تأكيد الإيداع في السيرفر"));
            }
        } catch (e) {
            triggerHapticFeedback('notification', 'warning');
            if (e && e.message !== "User rejected the transaction") {
                const errMsg = e?.message || e?.error || "تم إلغاء المعاملة أو حدث خطأ أثناء الدفع.";
                showAppAlert("⚠️ " + errMsg);
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
            
            const payload = getAuthPayload({ amount: amount });
            let result = await window.apiCall('/api/wallet/wallet_convert', 'POST', payload);
            
            if (result && result.success) {
                triggerHapticFeedback('notification', 'success');
                
                // ⚡ تحديث مباشر للواجهة والعداد البصري
                if (!window.GameState) window.GameState = {};
                if (result.new_balance !== undefined) window.GameState.balance = result.new_balance;
                if (result.new_usd_balance !== undefined) window.GameState.usd_balance = result.new_usd_balance;

                historyCache = null; // تفريغ كاش السجل
                window.updateWalletHeaderUI();
                
                const usdAdded = (result.usd_gained || (amount / 1000000)).toFixed(2);
                showAppAlert(`🎉 تم تحويل النقاط بنجاح!\nأضيف لرصيدك $${usdAdded} USD`);
                
                if (znInput) znInput.value = '';
                const convInfo = document.getElementById('conversion-calc-info');
                if (convInfo) convInfo.style.display = 'none';
            } else {
                showAppAlert("⚠️ " + (result?.error || result?.message || "فشل التحويل."));
            }
        } catch (e) { 
            const serverError = e?.message || e?.error || "خطأ في الاتصال بالسيرفر.";
            showAppAlert("⚠️ " + serverError); 
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

            const payload = getAuthPayload({
                amount: usdAmount,
                walletAddress: userWalletAddress
            });

            let result = await window.apiCall('/api/wallet/wallet_withdraw', 'POST', payload);
            
            if (result && result.success) {
                triggerHapticFeedback('notification', 'success');
                
                // ⚡ تحديث مباشر بدون طلب بيانات شامل
                if (!window.GameState) window.GameState = {};
                if (result.new_usd_balance !== undefined) {
                    window.GameState.usd_balance = result.new_usd_balance;
                }

                historyCache = null;
                window.updateWalletHeaderUI();
                
                let expectedTon = (usdAmount / (window.currentTonPriceUSD || 1)).toFixed(2);
                showAppAlert(`✅ تم تقديم طلب السحب بقيمة $${usdAmount.toFixed(2)}.\nستصلك (≈ ${expectedTon} TON) بعد المراجعة.`);
                
                if (usdInput) usdInput.value = '';
                const wInfo = document.getElementById('withdraw-calc-info');
                if (wInfo) wInfo.style.display = 'none';
            } else {
                showAppAlert("⚠️ " + (result?.error || result?.message || "خطأ أثناء معالجة الطلب"));
            }
        } catch (e) { 
            const serverError = e?.message || e?.error || "خطأ في الاتصال بالسيرفر.";
            showAppAlert("⚠️ " + serverError); 
        } finally {
            if (withdrawBtn) { withdrawBtn.disabled = false; withdrawBtn.innerText = "تقديم طلب السحب"; }
        }
    };

    // =================================================================
    // 🚀 8. بدء التشغيل التلقائي
    // =================================================================
    startTonPriceSync();
    
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        window.renderWalletTab(currentWalletTab);
    } else {
        document.addEventListener('DOMContentLoaded', () => window.renderWalletTab(currentWalletTab));
    }

    initTonConnect();

})();
