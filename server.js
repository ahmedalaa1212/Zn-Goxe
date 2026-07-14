const express = require('express');
const cors = require('cors');
const admin = require('firebase-admin');

const app = express();
app.use(cors());
app.use(express.json());

// ملحوظة: هنربط مفتاح فايربيس السري من خلال بيئة Railway وليس كملف للحماية
const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount)
});

const db = admin.firestore();

// مسار اختبار للتأكد إن السيرفر شغال
app.get('/', (req, res) => {
  res.send('Zn Goxe Server is Running!');
});

// مسار تحديث الرصيد (الـ Claim)
app.post('/api/claim', async (req, res) => {
    const { telegramId, addedAmount } = req.body;
    
    try {
        const userRef = db.collection('users').doc(telegramId.toString());
        const doc = await userRef.get();
        
        if (!doc.exists) {
            // لو اللاعب مش موجود، ننشئ له حساب برصيده الجديد
            await userRef.set({ balance: addedAmount });
        } else {
            // لو موجود، نزود على رصيده القديم
            const currentBalance = doc.data().balance || 0;
            await userRef.update({ balance: currentBalance + addedAmount });
        }
        
        res.status(200).json({ success: true, message: 'تم تحديث الرصيد بنجاح!' });
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});
