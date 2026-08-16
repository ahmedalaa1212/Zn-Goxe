window.initWalletView = function() {
    console.log("تم فتح قائمة المحفظة الرئيسية");
    
    // ربط الأزرار لتغيير القوائم الفرعية
    const tabs = document.querySelectorAll('.wallet-tab-btn');
    tabs.forEach(tab => {
        tab.addEventListener('click', (e) => {
            tabs.forEach(t => t.classList.remove('active'));
            e.target.classList.add('active');
            const targetFolder = e.target.getAttribute('data-target');
            loadWalletSubView(targetFolder);
        });
    });

    // استدعاء ملف الإيداع كواجهة افتراضية عند فتح المحفظة
    loadWalletSubView('deposit');
};

async function loadWalletSubView(folderName) {
    const container = document.getElementById('wallet-sub-content');
    if (!container) return;

    container.innerHTML = '<div style="text-align: center; color: #8b949e; padding: 20px;">جاري تحميل البيانات...</div>';

    try {
        const cacheBuster = `?v=${Date.now()}`;
        // مسار جلب الملف بناءً على تقسيمة المجلدات الخاصة بك
        const response = await fetch(`wallet/${folderName}/${folderName}.html${cacheBuster}`);
        
        if (response.ok) {
            const htmlContent = await response.text();
            
            // التأكد من أن الملف ليس فارغاً ولم يرجع index.html بالخطأ
            if (htmlContent.includes('id="global-toast-container"') || htmlContent.includes('<title>Zn Goxe')) {
                container.innerHTML = `<div style="text-align: center; color: #f39c12; padding: 20px;">ملف ${folderName}.html لا يزال قيد التطوير.</div>`;
            } else {
                container.innerHTML = htmlContent;
                // جلب سكريبت القائمة الفرعية
                await loadWalletSubScript(`wallet/${folderName}/${folderName}.js${cacheBuster}`);
                
                // تشغيل دالة التهيئة الخاصة بالقائمة الفرعية إذا كانت موجودة
                const initFunc = `init${folderName.charAt(0).toUpperCase() + folderName.slice(1)}View`;
                if (typeof window[initFunc] === 'function') {
                    window[initFunc]();
                }
            }
        } else {
            container.innerHTML = `<div style="text-align: center; color: #ff4757; padding: 20px;">تعذر تحميل القائمة (${response.status})</div>`;
        }
    } catch (err) {
        console.error(`خطأ أثناء تحميل مجلد ${folderName}:`, err);
        container.innerHTML = `<div style="text-align: center; color: #ff4757; padding: 20px;">حدث خطأ في الاتصال.</div>`;
    }
}

function loadWalletSubScript(scriptUrl) {
    return new Promise((resolve) => {
        const cleanUrl = scriptUrl.split('?')[0];
        const existingScript = document.querySelector(`script[src*="${cleanUrl}"]`);
        
        if (existingScript) {
            existingScript.remove();
        }
        
        const script = document.createElement('script');
        script.src = scriptUrl;
        script.onload = () => resolve(); 
        script.onerror = () => resolve(); 
        document.body.appendChild(script);
    });
}

// دالة تحديث واجهة المحفظة عند إعادة فتحها (يتم استدعاؤها من game.js تلقائياً)
window.onWalletTabOpen = function() {
    if (typeof window.updateUI === 'function') {
        window.updateUI();
    }
};
