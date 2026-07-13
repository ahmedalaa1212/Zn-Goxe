// البيانات الافتراضية للمحفظة
let walletZnBalance = 15400;
const usdRate = 0.000002; // سعر تحويل العملة الافتراضي للـ ZN مقابل الدولار
let walletActiveTab = 'deposit'; // التبويب الافتراضي عند فتح المحفظة

// دالة عرض محتويات التبويب (إيداع - سجلات - سحب)
function renderWalletTab(tab) {
    walletActiveTab = tab;
    const content = document.getElementById('wallet-content');
    if (!content) return;

    content.innerHTML = '';
    
    // تحديث ألوان الأزرار بسرعة فائقة (تأثير بصري سريع وسلس)
    document.getElementById('btn-deposit').style.background = (tab === 'deposit') ? '#0088cc' : '#1c1c1c';
    document.getElementById('btn-history').style.background = (tab === 'history') ? '#0088cc' : '#1c1c1c';
    document.getElementById('btn-withdraw').style.background = (tab === 'withdraw') ? '#0088cc' : '#1c1c1c';

    // تحديث قيم الأرصدة في الواجهة
    const znBalanceEl = document.getElementById('wallet-zn-balance');
    const usdBalanceEl = document.getElementById('wallet-usd-balance');
    if (znBalanceEl) znBalanceEl.innerText = walletZnBalance.toLocaleString();
    if (usdBalanceEl) usdBalanceEl.innerText = (walletZnBalance * usdRate).toFixed(5) + " $";

    // توليد المحتوى الداخلي بناءً على التبويب المحدد
    if (tab === 'deposit') {
        content.innerHTML = `
            <div style="background:#1c1c1c; padding:15px; border-radius:10px; border:1px solid #333; text-align:center;">
                <p style="color:#aaa; font-size:13px; margin:0 0 15px 0;">قم بنسخ عنوان المحفظة أدناه لإيداع عملات TON أو ZN لتطوير مزرعتك:</p>
                <div style="background:#0f0f0f; padding:10px; border-radius:8px; font-family:monospace; color:#00cc66; font-size:12px; word-break:break-all; border:1px solid #222; margin-bottom:15px;">
                    EQB3nCn...قريباً_ربط_المحفظة
                </div>
                <button style="width:100%; padding:10px; background:#00cc66; border:none; color:white; border-radius:5px; font-weight:bold;">نسخ العنوان 📋</button>
            </div>`;
    } else if (tab === 'history') {
        content.innerHTML = `
            <div style="background:#1c1c1c; padding:15px; border-radius:10px; border:1px solid #222;">
                <div style="color:#aaa; font-size:13px; text-align:center; padding:10px 0;">لا توجد عمليات سابقة حالياً 📥</div>
            </div>`;
    } else if (tab === 'withdraw') {
        content.innerHTML = `
            <div style="background:#1c1c1c; padding:15px; border-radius:10px; border:1px solid #333;">
                <label style="display:block; font-size:12px; color:#aaa; margin-bottom:5px;">أدخل كمية السحب (الحد الأدنى 50,000 ZN):</label>
                <input type="number" placeholder="0.00" style="width:100%; padding:10px; background:#0f0f0f; border:1px solid #333; color:#fff; border-radius:5px; margin-bottom:15px; box-sizing:border-box;">
                <button style="width:100%; padding:10px; background:#cc0000; border:none; color:white; border-radius:5px; font-weight:bold;">طلب سحب الأرباح 📤</button>
            </div>`;
    }
}

// ⚡ التحسين الخارق للسرعة وحل مشكلة الشاشة الفاضية فوراً ⚡
// فحص فائق السرعة كل 100 ملي ثانية (يعمل 10 مرات في الثانية الواحدة) لضمان استجابة لحظية مذهلة للمستخدم
setInterval(() => {
    const walletSection = document.getElementById('main-wallet-section');
    const walletContent = document.getElementById('wallet-content');
    
    if (walletSection && walletContent) {
        // إذا كان المستخدم ضغط على زر المحفظة وأصبح القسم مرئياً والمحتوى فارغ
        if (walletSection.style.display !== 'none' && window.getComputedStyle(walletSection).display !== 'none' && walletContent.innerHTML === '') {
            renderWalletTab(walletActiveTab);
        }
    }
}, 100); // 100ms تضمن تعمير الشاشة بشكل خاطف دون أي شعور بالضعف في السيرفر أو البوت!
