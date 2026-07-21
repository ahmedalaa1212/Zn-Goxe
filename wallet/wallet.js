// ==========================================
// 👛 ZN Goxe - Wallet System (wallet.js)
// ==========================================

window.userWalletAddress = null;

window.initWallet = function() {
    if (window.TonConnectUI) {
        try {
            window.tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
                manifestUrl: 'https://' + window.location.host + '/tonconnect-manifest.json',
                buttonRootId: 'ton-connect-btn'
            });

            window.tonConnectUI.onStatusChange(wallet => {
                if (wallet) {
                    window.userWalletAddress = wallet.account.address;
                    console.log("✅ المحفظة متصلة:", window.userWalletAddress);
                } else {
                    window.userWalletAddress = null;
                    console.log("🔌 المحفظة غير متصلة");
                }
            });
        } catch (e) {
            console.error("⚠️ خطأ في تهيئة TON Connect:", e);
        }
    }
};

window.renderWalletPage = function() {
    const container = document.getElementById('wallet-container');
    if (!container) return;

    const pData = window.PlayerData || {};
    const usdBal = (pData.usd_balance || 0).toFixed(5);
    const znBal = Math.floor(pData.balance || 0).toLocaleString();
    const tonApprox = ((pData.usd_balance || 0) / 1.60).toFixed(4);

    container.innerHTML = `
        <div class="wallet-card-main" style="background: linear-gradient(135deg, #1e1e24, #121215); border-radius: 16px; padding: 20px; text-align: center; border: 1px solid rgba(255,255,255,0.1); margin-bottom: 20px;">
            <div style="color: #888; font-size: 14px; margin-bottom: 5px;">رصيد ZN: ${znBal}</div>
            <div style="color: #00ff88; font-size: 32px; font-weight: bold; margin-bottom: 5px;">$ ${usdBal}</div>
            <div style="color: #0088cc; font-size: 14px; font-weight: 500;">≈ TON ${tonApprox}</div>
            <div id="ton-connect-btn" style="margin-top: 15px; display: flex; justify-content: center;"></div>
        </div>

        <!-- تبويبات المحفظة -->
        <div class="wallet-tabs" style="display: flex; gap: 10px; margin-bottom: 20px;">
            <button class="w-tab-btn" onclick="window.switchWalletTab('deposit')" id="w-tab-deposit" style="flex:1; padding: 12px; border-radius: 10px; border: none; background: #222; color: #fff; font-weight: bold; cursor: pointer;">إيداع</button>
            <button class="w-tab-btn" onclick="window.switchWalletTab('withdraw')" id="w-tab-withdraw" style="flex:1; padding: 12px; border-radius: 10px; border: none; background: #222; color: #fff; font-weight: bold; cursor: pointer;">سحب</button>
            <button class="w-tab-btn" onclick="window.switchWalletTab('history')" id="w-tab-history" style="flex:1; padding: 12px; border-radius: 10px; border: none; background: #0088cc; color: #fff; font-weight: bold; cursor: pointer;">سجلات</button>
        </div>

        <!-- محتوى التبويب -->
        <div id="wallet-tab-content"></div>
    `;

    window.switchWalletTab('history');
};

window.switchWalletTab = function(tabName) {
    document.querySelectorAll('.w-tab-btn').forEach(btn => {
        btn.style.background = '#222';
        btn.style.color = '#fff';
    });

    const activeBtn = document.getElementById(`w-tab-${tabName}`);
    if (activeBtn) {
        activeBtn.style.background = '#0088cc';
        activeBtn.style.color = '#fff';
    }

    const content = document.getElementById('wallet-tab-content');
    if (!content) return;

    if (tabName === 'withdraw') {
        content.innerHTML = `
            <div class="card" style="background: #18181c; border-radius: 14px; padding: 18px; border: 1px solid rgba(255,255,255,0.08);">
                <h3 style="color: #fff; margin-top: 0; font-size: 18px;">سحب الأرباح (USD / TON)</h3>
                <p style="color: #aaa; font-size: 13px;">سيتم تحويل المبلغ بالدولار إلى عملة TON وإرساله إلى محفظتك المربوطة فور موافقة الإدارة.</p>

                <!-- تحويل ZN إلى USD -->
                <div style="background: rgba(255,255,255,0.03); padding: 12px; border-radius: 10px; margin-bottom: 15px; border: 1px solid rgba(255,255,255,0.05);">
                    <div style="color: #ccc; font-size: 13px; margin-bottom: 8px;">تحويل ZN إلى USD (كل 1,000,000 ZN = $1)</div>
                    <input type="number" id="zn-to-convert" placeholder="أدخل كمية ZN" style="width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #111; color: #fff; box-sizing: border-box; margin-bottom: 8px;">
                    <button onclick="window.convertZnToUsd()" style="width: 100%; padding: 10px; background: #00cc66; color: #fff; border: none; border-radius: 8px; font-weight: bold; cursor: pointer;">تحويل النقاط</button>
                </div>

                <hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.1); margin: 15px 0;">

                <!-- طلب السحب -->
                <div style="margin-bottom: 15px;">
                    <label style="color: #ccc; font-size: 13px; display: block; margin-bottom: 5px;">المبلغ المراد سحبه ($ USD):</label>
                    <input type="number" step="0.01" id="usd-withdraw" placeholder="مثال: 0.11" oninput="window.calculateWithdrawTon()" style="width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #111; color: #fff; box-sizing: border-box;">
                </div>

                <div id="withdraw-calc-info" style="display: none; background: rgba(0, 136, 204, 0.1); border: 1px solid rgba(0, 136, 204, 0.3); padding: 10px; border-radius: 8px; color: #0088cc; font-size: 13px; margin-bottom: 15px;">
                    ستستلم على محفظتك: <span id="ton-estimate-val" style="font-weight: bold; color: #fff;">0</span> TON
                </div>

                <button onclick="window.submitWithdrawal()" style="width: 100%; padding: 12px; background: #0088cc; color: #fff; border: none; border-radius: 10px; font-weight: bold; font-size: 15px; cursor: pointer;">تقديم طلب سحب</button>
            </div>
        `;
    } else if (tabName === 'deposit') {
        content.innerHTML = `
            <div class="card" style="background: #18181c; border-radius: 14px; padding: 18px; border: 1px solid rgba(255,255,255,0.08);">
                <h3 style="color: #fff; margin-top: 0; font-size: 18px;">إيداع رصيد (TON)</h3>
                <p style="color: #aaa; font-size: 13px;">قم بإيداع عملة TON لشحن رصيد الإعلانات أو شراء الميزات.</p>

                <div style="margin-bottom: 15px;">
                    <label style="color: #ccc; font-size: 13px; display: block; margin-bottom: 5px;">مبلغ الإيداع ($ USD):</label>
                    <input type="number" step="0.1" id="usd-deposit" placeholder="مثال: 1.0" style="width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #111; color: #fff; box-sizing: border-box;">
                </div>

                <button onclick="window.submitDeposit()" style="width: 100%; padding: 12px; background: #00cc66; color: #fff; border: none; border-radius: 10px; font-weight: bold; font-size: 15px; cursor: pointer;">إتمام عملية الإيداع عبر المحفظة</button>
            </div>
        `;
    } else if (tabName === 'history') {
        content.innerHTML = `<div class="card" style="background:#18181c; border-radius:14px; padding:20px; text-align:center; color:#888;">⏳ جاري تحميل السجلات...</div>`;

        const initData = window.Telegram?.WebApp?.initData;
        if (!initData) {
            content.innerHTML = `<div class="card" style="background:#18181c; border-radius:14px; padding:20px; text-align:center; color:#ff4444;">⚠️ يرجى الدخول من تطبيق التليجرام لعرض السجلات.</div>`;
            return;
        }

        fetch(`/api/get_history?initData=${encodeURIComponent(initData)}&_t=${Date.now()}`)
            .then(res => res.json())
            .then(data => {
                if (data.success && data.history && data.history.length > 0) {
                    let html = `
                        <div class="card" style="background: #18181c; border-radius: 14px; padding: 18px; border: 1px solid rgba(255,255,255,0.08);">
                            <h3 style="color:#fff; text-align:center; margin-top:0; font-size:16px; margin-bottom:15px;">سجل المعاملات</h3>
                    `;
                    data.history.forEach(item => {
                        let statusText = '⏳ قيد المعالجة';
                        let statusColor = '#ffcc00';

                        if (item.status === 'approved' || item.status === 'completed') {
                            statusText = '✅ مكتملة';
                            statusColor = '#00cc66';
                        } else if (item.status === 'rejected' || item.status === 'cancelled') {
                            statusText = '❌ مرفوضة';
                            statusColor = '#ff4444';
                        }

                        let typeText = item.type === 'withdraw' ? 'سحب أرباح' : 'إيداع رصيد';
                        let typeIcon = item.type === 'withdraw' ? '📤' : '📥';
                        let dateStr = item.created_at ? new Date(item.created_at).toLocaleDateString('ar-EG', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' }) : '';

                        html += `
                            <div style="display:flex; justify-content:space-between; align-items:center; padding:12px 0; border-bottom:1px solid rgba(255,255,255,0.08);">
                                <div style="display:flex; align-items:center; gap:10px;">
                                    <span style="font-size:20px;">${typeIcon}</span>
                                    <div>
                                        <div style="color:#fff; font-weight:bold; font-size:14px;">${typeText}</div>
                                        <div style="color:#888; font-size:11px;">${dateStr}</div>
                                    </div>
                                </div>
                                <div style="text-align:left;">
                                    <div style="color:#fff; font-weight:bold; font-size:14px;">$${parseFloat(item.amount_usd || 0).toFixed(4)}</div>
                                    <div style="color:${statusColor}; font-size:12px; font-weight:bold; margin-top:2px;">${statusText}</div>
                                </div>
                            </div>
                        `;
                    });
                    html += `</div>`;
                    content.innerHTML = html;
                } else {
                    content.innerHTML = `
                        <div class="card" style="background:#18181c; border-radius:14px; padding:40px 20px; text-align:center; color:#777; border:1px solid rgba(255,255,255,0.08);">
                            <div style="font-size:48px; margin-bottom:10px;">📋</div>
                            <div style="color:#aaa; font-size:15px; font-weight:bold;">لا توجد سجلات سحب أو إيداع حالياً</div>
                        </div>`;
                }
            })
            .catch(err => {
                console.error("❌ خطأ في جلب السجلات:", err);
                content.innerHTML = `<div class="card" style="background:#18181c; border-radius:14px; padding:20px; text-align:center; color:#ff4444;">حدث خطأ أثناء تحميل السجلات من الخادم.</div>`;
            });
    }
};

window.calculateWithdrawTon = function() {
    const usdVal = parseFloat(document.getElementById('usd-withdraw').value) || 0;
    const infoDiv = document.getElementById('withdraw-calc-info');
    const estSpan = document.getElementById('ton-estimate-val');

    if (usdVal > 0) {
        const tonVal = (usdVal / 1.60).toFixed(4);
        if (estSpan) estSpan.innerText = tonVal;
        if (infoDiv) infoDiv.style.display = 'block';
    } else {
        if (infoDiv) infoDiv.style.display = 'none';
    }
};

window.convertZnToUsd = async function() {
    const znVal = parseFloat(document.getElementById('zn-to-convert').value);
    if (!znVal || znVal < 5000) return alert("⚠️ الحد الأدنى للتحويل هو 5000 ZN");

    const initData = window.Telegram?.WebApp?.initData;
    if (!initData) return alert("⚠️ يجب فتح التطبيق من تليجرام حصرياً.");

    try {
        let res = await fetch('/api/wallet_convert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData, amount: znVal })
        });
        let result = await res.json();

        if (result.success) {
            alert(`✅ تم تحويل ${znVal.toLocaleString()} ZN بنجاح إلى $${result.usd_gained.toFixed(5)}!`);
            document.getElementById('zn-to-convert').value = '';
            if (typeof window.fetchPlayerDataFromServer === 'function') {
                await window.fetchPlayerDataFromServer();
            }
            window.renderWalletPage();
        } else {
            alert("⚠️ فشل التحويل: " + (result.error || "خطأ غير معروف"));
        }
    } catch (e) {
        alert("❌ خطأ في الاتصال بالسيرفر.");
    }
};

window.submitWithdrawal = async function() {
    const usdAmount = parseFloat(document.getElementById('usd-withdraw').value);
    if (!usdAmount || usdAmount <= 0) return alert("⚠️ يرجى إدخال مبلغ صحيح للسحب");

    const pData = window.PlayerData || {};
    if ((pData.usd_balance || 0) < usdAmount) {
        return alert("⚠️ رصيدك الحالي بالدولار غير كافٍ لإتمام السحب!");
    }

    if (!window.userWalletAddress) {
        return alert("⚠️ يرجى ربط محفظة TON الخاصة بك أولاً قبل تقديم طلب السحب!");
    }

    const initData = window.Telegram?.WebApp?.initData;
    if (!initData) return alert("⚠️ غير مصرح بالعملية خارج تليجرام.");

    try {
        let response = await fetch('/api/wallet_withdraw', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                initData: initData,
                amount: usdAmount,
                walletAddress: window.userWalletAddress
            })
        });
        let result = await response.json();

        if (result.success) {
            if (typeof window.fetchPlayerDataFromServer === 'function') {
                await window.fetchPlayerDataFromServer();
            }

            alert(`✅ تم تقديم طلب السحب بنجاح بقيمة $${usdAmount}.\nتم خصم الرصيد والطلب قيد المعالجة الآن في السجلات!`);
            document.getElementById('usd-withdraw').value = '';

            window.switchWalletTab('history');
        } else {
            alert("⚠️ رفض السيرفر طلب السحب: " + (result.error || "خطأ غير معروف"));
        }
    } catch (e) {
        alert("❌ خطأ أثناء إرسال طلب السحب للخادم.");
    }
};

window.submitDeposit = async function() {
    const usdAmount = parseFloat(document.getElementById('usd-deposit').value);
    if (!usdAmount || usdAmount <= 0) return alert("⚠️ يرجى إدخال مبلغ إيداع صحيح.");

    if (!window.userWalletAddress || !window.tonConnectUI) {
        return alert("⚠️ يرجى ربط المحفظة أولاً لإجراء الإيداع.");
    }

    const tonAmount = (usdAmount / 1.60).toFixed(4);
    const nanoTon = Math.floor(tonAmount * 1e9);

    const transaction = {
        validUntil: Math.floor(Date.now() / 1000) + 600,
        messages: [
            {
                address: "EQB_YourProjectAdminTonWalletAddressHere",
                amount: nanoTon.toString()
            }
        ]
    };

    try {
        const result = await window.tonConnectUI.sendTransaction(transaction);
        const initData = window.Telegram?.WebApp?.initData;

        await fetch('/api/wallet_deposit_report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                initData: initData,
                usdAmount: usdAmount,
                tonAmount: parseFloat(tonAmount),
                boc: result.boc
            })
        });

        alert(`✅ تم إرسال الإيداع بنجاح بقيمة $${usdAmount}! الطلب قيد التأكيد.`);
        window.switchWalletTab('history');
    } catch (e) {
        console.error("❌ إلغاء أو فشل عملية الإيداع:", e);
        alert("⚠️ تم إلغاء عملية الإيداع أو حدث خطأ أثناء الدفع.");
    }
};
