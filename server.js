const express = require('express');
const cors = require('cors');
const admin = require('firebase-admin');

const app = express();
app.use(cors());
app.use(express.json());

// 👉 السطر السحري: ده اللي بيخلي السيرفر يعرض ملفات اللعبة (الواجهة والمجلدات بتاعتك) جوه تليجرام
app.use(express.static(__dirname));

// ربط السيرفر بقاعدة بيانات فايربيس بشكل آمن من خلال المتغير المخفي
const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount)
});

const db = admin.firestore();

// مسار تحديث الرصيد - ده اللي بيستقبل طلبات زيادة الرصيد من اللاعبين
app.post('/api/claim', async (req, res) => {
    const { telegramId, addedAmount } = req.body;
    
    try {
        const userRef = db.collection('users').doc(telegramId.toString());
        const doc = await userRef.get();
        
        if (!doc.exists) {
            // لو اللاعب أول مرة يلعب، ننشئ له حساب بالرصيد الجديد
            await userRef.set({ balance: addedAmount });
        } else {
            // لو اللاعب موجود، نزود الأرباح على رصيده القديم
            const currentBalance = doc.data().balance || 0;
            await userRef.update({ balance: currentBalance + addedAmount });
        }
        
        res.status(200).json({ success: true, message: 'تم تحديث الرصيد بنجاح!' });
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

// تشغيل السيرفر
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});
