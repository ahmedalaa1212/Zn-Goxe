const express = require('express');
const cors = require('cors');
const admin = require('firebase-admin');
const path = require('path');

const app = express();
app.use(cors());
app.use(express.json());

// 👉 السطر ده بيخلي السيرفر يعرض صفحات اللعبة والمجلدات بتاعتك جوه تليجرام
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

// مسار تحديث الرصيد (الـ Claim)
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

// فتح صفحة اللعبة الرئيسية (index.html) فوراً عند فتح الرابط
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// 🔴 التعديل السحري والنهائي لحل مشكلة البورت:
// ريلواي مضبوط يبعت الزوار لـ 8080، والسطر ده هيخليه يشتغل على 8080 ويقبل الاتصالات الخارجية!
const PORT = process.env.PORT || 8080;
app.listen(PORT, "0.0.0.0", () => {
  console.log(`Server is running on port ${PORT}`);
});
