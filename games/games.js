/**
 * 🎮 Zn Goxe - نظام الألعاب والساحة الكبرى
 * Version: 15.2
 */

// ==========================================
// 🌐 المتغيرات العامة والحالة (State)
// ==========================================
let currentUid = "";
let userBalance = 0.0;
let currentTab = "arena";

// متغيرات الساحة (Arena)
let arenaTimerInterval = null;
let arenaEndTime = 0;
let hasJoinedArena = false;
let arenaEntryFee = 100.0;
let defaultPayoutPercentages = [40.0, 20.0, 10.0, 8.0, 6.0, 5.0, 4.0, 3.0, 2.0, 2.0];

// متغيرات لعبة الصناديق (Grid 36)
let brokenCount = 3;
let grid36SessionToken = null;
let isBoxesGameActive = false;
let openedBoxesCount = 0;
let currentBoxesPayout = 0.0;

// Telegram WebApp Initialization
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
}

// ==========================================
// 🚀 بدء التشغيل والتهيئة عند تحميل الصفحة
// ==========================================
document.addEventListener("DOMContentLoaded", async () => {
    extractUserUid();
    await fetchUserInfo();
    await checkNotifications();

    // تشغيل الساحة كافتراضي
    switchGameTab("arena");
    startArenaStatusPolling();

    // تهيئة شبكة الصناديق
    renderBoxesGrid();
    setupInputKeyboardHandlers();
});

// ==========================================
// 👤 1. استخراج ID وتحديث الرصيد
// ==========================================
function extractUserUid() {
    if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) {
        currentUid = String(tg.initDataUnsafe.user.id);
    } else {
        const urlParams = new URLSearchParams(window.location.search);
        currentUid = urlParams.get("tg_id") || urlParams.get("uid") || urlParams.get("user_id") || "123456789";
    }
}

async function fetchUserInfo() {
    if (!currentUid) return;
    try {
        const res = await fetch(`/api/user/info?tg_id=${currentUid}`);
        const data = await res.json();
        if (data.success) {
            userBalance = parseFloat(data.balance) || 0.0;
            updateBalanceUI(userBalance);
        }
    } catch (err) {
        console.error("فشل جلب بيانات المستخدم:", err);
    }
}

function updateBalanceUI(bal) {
    userBalance = parseFloat(bal) || 0.0;
    const balEl = document.getElementById("top-balance-games");
    if (balEl) {
        balEl.innerText = userBalance.toFixed(2) + " ZN";
    }
}

async function checkNotifications() {
    if (!currentUid) return;
    try {
        const res = await fetch(`/api/games/check_notifications`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tg_id: currentUid })
        });
        const data = await res.json();
        if (data.success && data.refund > 0) {
            updateBalanceUI(data.balance);
            alert(`🛡️ تم إرجاع مبلغ ${data.refund} ZN لحسابك لعدم اكتمال النصاب (10 لاعبين) في جولة الساحة السابقة.`);
        }
    } catch (err) {
        console.error("خطأ في فحص الإشعارات:", err);
    }
}

// ==========================================
// 🔄 2. التنقل بين التبويبات (Tabs)
// ==========================================
function switchGameTab(tab) {
    currentTab = tab;
    const arenaTab = document.getElementById("tab-arena");
    const boxesTab = document.getElementById("tab-boxes");
    const arenaContent = document.getElementById("content-arena");
    const boxesContent = document.getElementById("content-boxes");

    if (tab === "arena") {
        arenaTab.classList.add("active");
        boxesTab.classList.remove("active");
        arenaContent.style.display = "block";
        boxesContent.style.display = "none";
        fetchArenaStatus();
    } else {
        boxesTab.classList.add("active");
        arenaTab.classList.remove("active");
        boxesContent.style.display = "block";
        arenaContent.style.display = "none";
    }
}

// ==========================================
// ⚔️ 3. منطق الساحة الكبرى (Arena)
// ==========================================
let arenaPollInterval = null;

function startArenaStatusPolling() {
    fetchArenaStatus();
    if (arenaPollInterval) clearInterval(arenaPollInterval);
    arenaPollInterval = setInterval(fetchArenaStatus, 4000);
}

async function fetchArenaStatus() {
    if (!currentUid) return;
    try {
        const res = await fetch(`/api/games/status?tg_id=${currentUid}`);
        const data = await res.json();

        if (data.success) {
            arenaEndTime = data.end_time || 0;
            hasJoinedArena = data.has_joined || false;
            arenaEntryFee = data.entry_fee || 100.0;
            const prizePool = data.prize_pool || 0.0;
            const playersCount = data.participants_count || 0;
            const minPlayers = data.min_players || 10;
            const payoutPcts = data.payout_percentages || defaultPayoutPercentages;

            // تحديث الواجهة
            document.getElementById("prize-pool").innerText = prizePool.toFixed(2) + " ZN";
            document.getElementById("arena-players-count").innerText = `👥 ${playersCount}/${minPlayers} لاعبين`;

            if (data.balance !== undefined) {
                updateBalanceUI(data.balance);
            }

            // تحديث زر الاشتراك
            const joinBtn = document.getElementById("btn-join-arena");
            if (joinBtn) {
                if (hasJoinedArena) {
                    joinBtn.innerText = "✅ أنت مشترك في هذه الجولة";
                    joinBtn.disabled = true;
                    joinBtn.style.opacity = "0.75";
                    joinBtn.style.background = "linear-gradient(90deg, #10b981, #047857)";
                } else {
                    joinBtn.innerText = `دخول الساحة (${arenaEntryFee.toFixed(0)} ZN)`;
                    joinBtn.disabled = false;
                    joinBtn.style.opacity = "1";
                    joinBtn.style.background = "linear-gradient(90deg, #f39c12, #d35400)";
                }
            }

            // تحديث العداد التنازلي
            updateArenaTimerUI();

            // رسم جدول جوائز الساحة (Top 10)
            renderArenaPrizes(prizePool, payoutPcts);
        }
    } catch (err) {
        console.error("خطأ جلب حالة الساحة:", err);
    }
}

function updateArenaTimerUI() {
    if (arenaTimerInterval) clearInterval(arenaTimerInterval);

    const timerEl = document.getElementById("arena-timer");
    const update = () => {
        const now = Math.floor(Date.now() / 1000);
        const diff = arenaEndTime - now;

        if (diff <= 0) {
            timerEl.innerText = "00:00";
            timerEl.style.color = "#ef4444";
            fetchArenaStatus(); // إعادة تحميل الساحة عند انتهاء الجولة
            return;
        }

        const mins = Math.floor(diff / 60);
        const secs = diff % 60;
        timerEl.innerText = `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
        timerEl.style.color = diff <= 15 ? "#ef4444" : "#ffffff";
    };

    update();
    arenaTimerInterval = setInterval(update, 1000);
}

function renderArenaPrizes(prizePool, payoutPcts) {
    const listContainer = document.getElementById("arena-prizes-list");
    if (!listContainer) return;

    listContainer.innerHTML = "";
    const icons = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"];

    payoutPcts.forEach((pct, index) => {
        const rank = index + 1;
        const icon = icons[index] || `#${rank}`;
        const prizeAmount = (prizePool * (pct / 100.0)).toFixed(2);

        const itemHtml = `
            <div class="prize-rank-item">
                <div class="prize-rank-info">
                    <span class="prize-rank-icon">${icon}</span>
                    <span class="prize-rank-title">المركز ${rank}</span>
                </div>
                <div class="prize-rank-values">
                    <span class="prize-rank-pct">${pct}%</span>
                    <span class="prize-rank-amount">${prizeAmount} ZN</span>
                </div>
            </div>
        `;
        listContainer.insertAdjacentHTML("beforeend", itemHtml);
    });
}

function joinArena() {
    if (hasJoinedArena) return;
    if (userBalance < arenaEntryFee) {
        alert(`❌ رصيدك الحالي (${userBalance.toFixed(2)} ZN) لا يكفي لدخول الساحة (${arenaEntryFee} ZN).`);
        return;
    }

    const confirmModal = document.getElementById("confirm-modal");
    if (confirmModal) {
        confirmModal.style.display = "flex";
    } else {
        executeJoinArena();
    }
}

async function onConfirmJoin(confirmed) {
    document.getElementById("confirm-modal").style.display = "none";
    if (confirmed) {
        await executeJoinArena();
    }
}

async function executeJoinArena() {
    try {
        const res = await fetch(`/api/games/arena/enter`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tg_id: currentUid })
        });
        const data = await res.json();

        if (data.success) {
            if (data.new_balance !== undefined) {
                updateBalanceUI(data.new_balance);
            }
            alert(data.message || "⚔️ تم انضمامك للساحة بنجاح!");
            fetchArenaStatus();
        } else {
            alert(data.message || "❌ فشل الانضمام للساحة.");
        }
    } catch (err) {
        console.error("خطأ أثناء الدخول للساحة:", err);
        alert("⚠️ حدث خطأ في الاتصال بالسيرفر.");
    }
}

// ==========================================
// 📦 4. منطق لعبة ZN Go - شبكة الـ 36 صندوق
// ==========================================
function renderBoxesGrid() {
    const gridEl = document.getElementById("boxes-grid");
    if (!gridEl) return;

    gridEl.innerHTML = "";
    for (let i = 0; i < 36; i++) {
        const boxHtml = `
            <div class="box-card" id="box-${i}" onclick="onBoxClick(${i})">
                <div class="box-inner">
                    <div class="box-front">📦</div>
                    <div class="box-back" id="box-back-${i}">💎</div>
                </div>
            </div>
        `;
        gridEl.insertAdjacentHTML("beforeend", boxHtml);
    }
}

function openBoxesSettings() {
    if (isBoxesGameActive) {
        alert("⚠️ لا يمكنك تغيير الصعوبة أثناء الجولة النشطة!");
        return;
    }
    document.getElementById("boxes-settings-modal").style.display = "flex";
}

function closeBoxesSettings() {
    document.getElementById("boxes-settings-modal").style.display = "none";
}

function selectBrokenCount(count) {
    brokenCount = count;
    const textEl = document.getElementById("selected-broken-text");
    let maxMultiplier = count === 3 ? "20x" : count === 5 ? "40x" : "70x";
    if (textEl) {
        textEl.innerText = `${count} عملات مكسورة (سقف 🌟 ${maxMultiplier})`;
    }
    closeBoxesSettings();
}

function addBetBoxes(val) {
    if (isBoxesGameActive) return;
    const input = document.getElementById("boxes-bet-input");
    let curr = parseFloat(input.value) || 0;
    input.value = Math.max(100, curr + val);
}

function setBetMaxBoxes() {
    if (isBoxesGameActive) return;
    const input = document.getElementById("boxes-bet-input");
    input.value = Math.max(100, Math.floor(userBalance));
}

async function startBoxesGame() {
    if (isBoxesGameActive) return;

    const betInput = document.getElementById("boxes-bet-input");
    const betAmount = parseFloat(betInput.value) || 0;

    if (betAmount < 100) {
        alert("⚠️ الحد الأدنى للرهان هو 100 ZN");
        return;
    }

    if (betAmount > userBalance) {
        alert("❌ رصيدك الحالي لا يكفي لهذه القيمة.");
        return;
    }

    try {
        const res = await fetch(`/api/games/grid36/start`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                tg_id: currentUid,
                bet_amount: betAmount,
                broken_count: brokenCount
            })
        });
        const data = await res.json();

        if (data.success) {
            isBoxesGameActive = true;
            grid36SessionToken = data.session_token;
            openedBoxesCount = 0;
            currentBoxesPayout = 0;

            if (data.new_balance !== undefined) {
                updateBalanceUI(data.new_balance);
            }

            // إعادة تنشيط الواجهة الصناديق
            renderBoxesGrid();
            document.getElementById("btn-start-boxes").style.display = "none";
            document.getElementById("btn-cashout-boxes").style.display = "block";
            document.getElementById("btn-cashout-boxes").innerText = "سحب الأرباح (0.00 ZN)";
        } else {
            alert(data.message || "❌ فشل بدء اللعبة.");
        }
    } catch (err) {
        console.error("خطأ بدء لعبة الصناديق:", err);
        alert("⚠️ حدث خطأ في الاتصال بالخادم.");
    }
}

async function onBoxClick(index) {
    if (!isBoxesGameActive || !grid36SessionToken) return;

    const boxEl = document.getElementById(`box-${index}`);
    if (!boxEl || boxEl.classList.contains("flipped")) return;

    try {
        const res = await fetch(`/api/games/grid36/open`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                tg_id: currentUid,
                box_index: index,
                session_token: grid36SessionToken
            })
        });
        const data = await res.json();

        if (data.success) {
            const backEl = document.getElementById(`box-back-${index}`);

            if (data.is_bomb) {
                // اصطدام بعملة مكسورة (خسارة)
                boxEl.classList.add("flipped", "broken");
                if (backEl) backEl.innerText = "💥";
                isBoxesGameActive = false;

                setTimeout(() => {
                    alert("💥 للأسف! فتحت عملة مكسورة وانتهت الجولة.");
                    resetBoxesGameUI();
                    if (data.layout) revealAllBoxesLayout(data.layout);
                }, 500);
            } else {
                // صندوق رابح
                boxEl.classList.add("flipped");
                if (backEl) backEl.innerText = `✨ ${data.multiplier}x`;

                openedBoxesCount++;
                currentBoxesPayout = parseFloat(data.current_win) || 0;

                const cashoutBtn = document.getElementById("btn-cashout-boxes");
                if (cashoutBtn) {
                    cashoutBtn.innerText = `سحب الأرباح (${currentBoxesPayout.toFixed(2)} ZN)`;
                }
            }
        } else {
            alert(data.message || "❌ تعذر فتح الصندوق.");
        }
    } catch (err) {
        console.error("خطأ أثناء فتح الصندوق:", err);
    }
}

async function cashOutBoxes() {
    if (!isBoxesGameActive || openedBoxesCount === 0) {
        alert("⚠️ افتح صندوقاً واحداً على الأقل قبل السحب!");
        return;
    }

    try {
        const res = await fetch(`/api/games/grid36/cashout`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tg_id: currentUid })
        });
        const data = await res.json();

        if (data.success) {
            isBoxesGameActive = false;
            if (data.new_balance !== undefined) {
                updateBalanceUI(data.new_balance);
            }

            alert(`🎉 مبروك! تم سحب أرباحك بنجاح: +${parseFloat(data.payout).toFixed(2)} ZN`);
            resetBoxesGameUI();

            if (data.layout) {
                revealAllBoxesLayout(data.layout);
            }
        } else {
            alert(data.message || "❌ فشل سحب الأرباح.");
        }
    } catch (err) {
        console.error("خطأ عند سحب الأرباح:", err);
        alert("⚠️ تعذر الاتصال بالخادم.");
    }
}

function revealAllBoxesLayout(layout) {
    if (!layout || !Array.isArray(layout)) return;

    layout.forEach((item, i) => {
        const boxEl = document.getElementById(`box-${i}`);
        const backEl = document.getElementById(`box-back-${i}`);

        if (boxEl && !boxEl.classList.contains("flipped")) {
            if (item.type === "bomb") {
                boxEl.classList.add("flipped", "broken");
                if (backEl) backEl.innerText = "💥";
            } else {
                boxEl.classList.add("flipped");
                if (backEl) backEl.innerText = `${item.multiplier}x`;
            }
        }
    });
}

function resetBoxesGameUI() {
    isBoxesGameActive = false;
    grid36SessionToken = null;
    document.getElementById("btn-start-boxes").style.display = "block";
    document.getElementById("btn-cashout-boxes").style.display = "none";
}

// ==========================================
// ⌨️ 5. معالجة إخفاء القائمة عند الكتابة
// ==========================================
function setupInputKeyboardHandlers() {
    const inputs = document.querySelectorAll("input, select, textarea");
    inputs.forEach(input => {
        input.addEventListener("focus", () => document.body.classList.add("keyboard-open"));
        input.addEventListener("blur", () => document.body.classList.remove("keyboard-open"));
    });
}
