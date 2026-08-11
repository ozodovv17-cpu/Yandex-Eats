# Yandex Eats Kuryer Saralash Boti

## Yangi qo'shilganlar (bu versiyada)

### -2. Skuterlarni tahrirlash + "Shu skuterni olmoqchiman" tugmasi + kunlik hisobot

**Skuterlarni tahrirlash**: admin panelda har bir skuter yonida endi "✏️ Tahrirlash" tugmasi bor — nomi, rasmi, bepul muddati yoki narxini alohida-alohida o'zgartirish mumkin (avval o'chirib qayta qo'shish shart emas edi).

**"🛒 Shu skuterni olmoqchiman" tugmasi**: testdan o'tgan nomzodga ko'rsatilgan har bir skuter ostida endi tugma bor. Nomzod bossa:
- Nomzodga tasdiqlash xabari chiqadi ("operatorlarimiz bog'lanadi")
- Adminlarga darhol xabar boradi: kim, qaysi skuterni tanladi, telefon raqami bilan

**Kunlik avtomatik hisobot**: har kuni belgilangan vaqtda (standart: 20:00, Toshkent vaqti) barcha adminlarga o'sha kunning statistikasi (kirganlar/o'tganlar/rad etilganlar + rad sabablari) avtomatik yuboriladi.
- Yangi `scheduler.py` fayli shu ishni bajaradi, `main.py` bot ishga tushganda uni fon vazifasi (background task) sifatida ishga tushiradi.
- Sozlash: `.env` faylida `DAILY_REPORT_ENABLED`, `DAILY_REPORT_HOUR`, `DAILY_REPORT_MINUTE`.
- Kutmasdan darhol sinab ko'rish uchun: Admin panel → 📊 Statistika → "📨 Kunlik hisobotni hozir yuborish".

### -1. Transport (skuter) bo'limi
- Nomzod to'liq savol-javobdan o'tib, lokatsiya (ofis manzili) yuborilgandan KEYIN, agar admin panelda skuterlar qo'shilgan bo'lsa — ularning ro'yxati avtomatik ko'rsatiladi: rasm + nom + necha muddatga bepulligi + narxi.
- **Admin panelda**: 🛠 Admin panel → "🛵 Skuterlar (transport)" bo'limi.
  - **Qo'shish**: "➕ Skuter qo'shish" → rasmni yuboring (yoki rasmsiz o'tish uchun "-" yozing) → nomini yozing → bepul muddatini yozing → narxini yozing. Tayyor — avtomatik ro'yxatga qo'shiladi.
  - **Ko'rish**: ro'yxatdagi skuter nomiga bossangiz, to'liq kartochkasi (rasm + ma'lumot) chiqadi.
  - **O'chirish**: har bir skuter yonidagi ❌ tugmasi orqali.
  - Skuter qo'shilmagan bo'lsa, bu bo'lim nomzodlarga umuman ko'rsatilmaydi — hech narsa buzilmaydi.

### 0. /start xabariga taklifnoma matni va stiker
- `/start` bosilganda endi til tanlashdan OLDIN qisqa taklifnoma xabari chiqadi: ish haqida, to'lovlar biz tarafdan ekani, pasport asli kerakligi haqida (`i18n.py` → `TEXTS["uz"]["intro"]`).
- Xabar bilan birga stiker ham yuborilishi mumkin. Stiker ixtiyoriy — `WELCOME_STICKER_ID` muhit o'zgaruvchisi orqali sozlanadi (`.env.example`ga qarang).
- **O'zingiz yoqtirgan stikerni qo'shish uchun**: shu botga (admin sifatida) istalgan stikerni yuboring — bot sizga o'sha stikerning `file_id`sini javob qilib yuboradi. Shu ID'ni nusxalab, `WELCOME_STICKER_ID` ga qo'ying (Railway'da: Variables bo'limiga). Agar bu o'zgaruvchi bo'sh qolsa, stiker yuborilmaydi, faqat matn ketadi — hech narsa buzilmaydi.
- Taklifnoma matnini o'zgartirish uchun `i18n.py` faylidagi `"intro"` qatorini tahrirlang.

### 1. Nomzodlar ro'yxatini bot ichida ko'rish
- Admin panelda **"📋 Nomzodlar ro'yxati"** tugmasi qo'shildi.
- Eng so'nggi murojaat qilganlardan boshlab, har sahifada 5 tadan ko'rsatiladi, "⬅️ Oldingi / Keyingi ➡️" tugmalari orqali varaqlanadi.
- Har bir nomzodni bosganda — to'liq ma'lumot: ism, til, telefon, yosh, pasport, Toshkent, tajriba, transport, sana, holat (✅ o'tdi / ❌ rad etildi — sababi bilan / ⏳ jarayonda tark etgan).
- Bu CSV eksportni almashtirmaydi — CSV hamon mavjud, faqat endi tezkor ko'rish uchun botning o'zida ham ro'yxat bor.

### 2. Ko'p tillilik (o'zbek + rus)
- Bot `/start` bosilganda endi birinchi navbatda til so'raydi: **🇺🇿 O'zbekcha** yoki **🇷🇺 Русский**.
- Tanlangan tilga qarab barcha savol-javoblar (telefon so'rash, yosh, pasport, Toshkent, tajriba, transport, rad javobi, tabrik xabari) shu tilda ko'rsatiladi.
- Har bir nomzodning tili bazada saqlanadi (`lang` ustuni) va:
  - Adminga yuboriladigan xabarda ko'rsatiladi (`🌐 Til: 🇷🇺 RU`)
  - CSV eksportga ham qo'shilgan
  - Bot ichidagi nomzod tafsilotlarida ko'rinadi
- **Admin panelning o'zi** hamon faqat o'zbek tilida ishlaydi (buni alohida so'ramagansiz) — faqat kuryer nomzodi bilan suhbat ikki tilli.
- Yangi til qo'shish oson: `i18n.py` faylidagi `TEXTS` lug'atiga yangi til kodi (masalan `"en"`) va tarjimalarini qo'shsangiz bo'ldi.

---

## Railway'ga joylashtirish (deploy)

### 1-usul: GitHub orqali (tavsiya etiladi)

1. Loyihani GitHub'ga yuklang.
2. [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
3. Railway `requirements.txt` orqali Python muhitini avtomatik aniqlaydi (Nixpacks).
4. **Variables** bo'limiga qo'shing:
   - `BOT_TOKEN` — @BotFather dan olingan token
   - `ADMIN_IDS` — super-admin(lar)ning Telegram ID(lari), vergul bilan: `123456789,987654321`
   - (ixtiyoriy) `DB_PATH` — pastga qarang
5. Start buyrug'i avtomatik `python main.py` (`railway.json`/`Procfile` orqali).
6. **Deploy** — loglarda `Bot ishga tushdi, polling boshlandi...` chiqsa, tayyor.

### 2-usul: Railway CLI orqali

```bash
npm i -g @railway/cli
railway login
cd yandex_courier_bot
railway init
railway variables set BOT_TOKEN=SIZNING_TOKEN
railway variables set ADMIN_IDS=123456789
railway up
```

### Ma'lumotlarni doimiy saqlash (MUHIM!)

Railway'da konteyner qayta yaratilganda (redeploy, restart) `bot.db` fayli **o'chib ketishi mumkin**.

1. Railway loyihada **+ New → Volume** → Mount path: `/data`.
2. **Variables**ga `DB_PATH=/data/bot.db` qo'shing.
3. Qayta deploy qiling — endi baza doimiy saqlanadi.

### Lokalda ishga tushirish

```bash
pip install -r requirements.txt
cp .env.example .env   # to'ldiring
BOT_TOKEN=... ADMIN_IDS=... python main.py
```

---

## Bot oqimi (to'liq, ikki tilli)

1. `/start` — **til tanlash** (🇺🇿 / 🇷🇺).
2. Telefon raqami so'raladi (faqat "Raqamni ulashish/Поделиться номером" tugmasi orqali).
3. "18 yoshga to'lganmisiz?" — Ha/Yo'q.
   - Yo'q → rad javobi, to'xtaydi.
   - Ha → "Necha yoshdasiz?" (raqam kiritiladi). 18 dan kichik chiqsa — rad javobi.
4. "Pasportingizning nusxasi bormi?" — Yo'q → darhol rad javobi.
5. "Siz hozirda Toshkentdamisiz?" — Yo'q → rad javobi.
6. "Oldin kuryerlik bilan shug'ullanganmisiz?" — ikkalasi ham davom etadi.
7. "Sizda shaxsiy transportingiz bormi?" — ikkalasi ham davom etadi.
8. Muvaffaqiyatli yakunlansa:
   - Tabrik xabari (tanlangan tilda) + uchrashuv vaqti + aloqa raqami
   - Lokatsiya (geo yoki matn, admin belgilagan)
   - Adminlarga to'liq ma'lumot bilan xabar boradi (o'zbek tilida): ism, til, telefon, yosh, pasport, Toshkent, tajriba, transport.

## Admin panel (`/admin`)

- 📞 Aloqa raqamini o'zgartirish
- 📍 Lokatsiyani belgilash (geo yoki matn) / 🗑 o'chirish
- 🕐 Uchrashuv vaqtini belgilash
- 📊 Statistika: Bugun/Kecha, Shu hafta/oy, Rad sabablari, CSV eksport
- 📋 **Nomzodlar ro'yxati** — bot ichida sahifalab ko'rish, har bir nomzodning to'liq kartochkasi
- 👤 Adminlarni boshqarish: ro'yxat, qo'shish (ID yoki forward orqali), o'chirish (super-adminlardan tashqari)

## Fayllar tuzilishi

```
yandex_courier_bot/
├── main.py
├── config.py
├── database.py
├── i18n.py                 # o'zbek/rus tarjimalari
├── requirements.txt
├── Procfile
├── railway.json
├── runtime.txt
├── .env.example
├── .gitignore
├── handlers/
│   ├── user.py           # kuryer nomzodi bilan suhbat oqimi (ikki tilli)
│   └── admin.py           # admin panel (nomzodlar ro'yxati bilan)
└── README.md
```

## Qolgan ishlar (agar kerak bo'lsa)

- Boshqa tillar qo'shish (masalan tojik, qirg'iz) — `i18n.py`ga qo'shimcha qilish yetarli.
- Telegram webhook rejimiga o'tish (hozir polling — Railway'da to'liq ishlaydi).
- To'liq real foydalanuvchilar bilan end-to-end sinov (hozirgacha kod darajasida avtomatik testlar orqali tekshirildi).
