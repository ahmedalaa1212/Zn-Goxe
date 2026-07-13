function showTab(tab) {
    const content = document.getElementById('wallet-content');
    
    if (tab === 'deposit') {
        content.innerHTML = `
            <div style="text-align:center; padding:20px; background:#1c1c1c; border-radius:10px;">
                <p>عنوان المحفظة للإيداع:</p>
                <div style="background:#000; padding:10px; margin:10px 0; border-radius:5px; color:#00ff00;">UQAm...89xZ</div>
                <button style="background:#0088cc; border:none; padding:10px 20px; border-radius:5px; color:#fff;">نسخ العنوان</button>
            </div>`;
    } 
    else if (tab === 'history') {
        content.innerHTML = `<div style="color:#aaa; text-align:center;">لا توجد عمليات حالياً.</div>`;
    } 
    else if (tab === 'withdraw') {
        // التحقق من ربط المحفظة (بفرض وجود متغير)
        const isLinked = false; 
        content.innerHTML = `
            <div style="padding:20px; background:#1c1c1c; border-radius:10px;">
                ${!isLinked ? `
                    <div style="text-align:center; color:#ff4444;">يجب ربط المحفظة أولاً لبدء السحب</div>
                    <button style="width:100%; margin-top:10px; padding:10px; background:#ff4444; border:none; color:white; border-radius:5px;">ربط المحفظة الآن</button>
                ` : `
                    <input type="number" placeholder="المبلغ (ZN)" style="width:100%; padding:10px; margin-bottom:10px; border-radius:5px; border:none;">
                    <button style="width:100%; padding:10px; background:#00cc66; border:none; color:white; border-radius:5px;">طلب سحب</button>
                `}
            </div>`;
    }
}

// عرض الإيداع كافتراضي
showTab('deposit');
