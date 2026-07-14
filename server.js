const express = require('express');
const cors = require('cors');
const admin = require('firebase-admin');
const path = require('path');

const app = express();
app.use(cors());
app.use(express.json());

// 👉 إعداد المجلدات عشان السيرفر يشوفها كلها
app.use(express.static(__dirname));
app.use('/farm', express.static(path.join(__dirname, 'farm')));
app.use('/shop', express.static(path.join(__dirname, 'shop')));
app.use('/friends', express.static(path.join(__dirname, 'friends')));
app.use('/wallet', express.static(path.join(__dirname, 'wallet')));
app.use('/settings', express.static(path.join(__dirname, 'settings')));

// ربط السيرفر بقاعدة بيانات فايربيس
const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount)
});

const db = admin.firestore();

// مسار تحديث الرصيد
app.post('/api/claim', async (req, res) => {
    const { telegramId, addedAmount } = req.body;
    
    try {
        const userRef = db.collection('users').doc(telegramId.toString());
        const doc = await userRef.get();
        
        if (!doc.exists) {
            await userRef.set({ balance: addedAmount });
        } else {
            const currentBalance = doc.data().balance || 0;
            await userRef.update({ balance: currentBalance + addedAmount });
        }
        
        res.status(200).json({ success: true, message: 'تم تحديث الرصيد بنجاح!' });
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

// المسار الافتراضي لفتح الصفحة الرئيسية (تأكد من اسم الملف، مثلاً farm.html أو index.html)
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'farm', 'farm.html')); 
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});
