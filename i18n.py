TEXTS = {
    "uz": {
        "intro": (
            "👋 Assalomu alaykum!\n\n"
            "🛵 Sizni <b>Yandex Eats</b> kuryerlik lavozimiga ishga taklif qilamiz!\n\n"
            "💰 Hamma to'lovlar biz tarafdan amalga oshiriladi.\n"
            "🪪 Sizdan faqat pasportingizning <b>asli</b> bo'lishi kerak.\n\n"
            "📝 Quyida qisqa anketa qoldiring — biz siz bilan albatta aloqaga chiqamiz!"
        ),
        "choose_language": "Tilni tanlang / Выберите язык:",
        "greeting": (
            "Assalomu alaykum! Yandex Eats kuryer lavozimiga xush kelibsiz.\n\n"
            "Iltimos, telefon raqamingizni pastdagi tugma orqali yuboring 👇"
        ),
        "share_phone_button": "📱 Raqamni ulashish",
        "phone_not_shared": "Iltimos, pastdagi '📱 Raqamni ulashish' tugmasini bosing.",
        "thanks_phone": "Rahmat! ✅",
        "ask_age_confirm": "Siz 18 yoshga to'lganmisiz?",
        "ask_age_number": "Necha yoshdasiz? Iltimos, raqam bilan yozing (masalan: 23):",
        "age_not_digit": "❗️ Iltimos, faqat raqam kiriting (masalan: 23):",
        "age_out_of_range": "❗️ Iltimos, haqiqiy yoshingizni raqam bilan kiriting:",
        "ask_passport": "Pasportingizning nusxasi (skan/rasm) bormi?",
        "ask_tashkent": "Siz hozirda Toshkentdamisiz?",
        "ask_experience": "Siz oldin kuryerlik bilan shug'ullanganmisiz?",
        "ask_transport": "Sizda shaxsiy transportingiz bormi?",
        "reject": "😔 Afsuski, siz hozircha kuryer lavozimiga to'g'ri kelmaysiz.",
        "congrats": (
            "🎉 Tabriklaymiz! Siz kuryerlik testidan muvaffaqiyatli o'tdingiz.\n\n"
            "🕐 Uchrashuv vaqti: {meeting_time}\n"
            "📞 Bog'lanish uchun raqam: {contact_phone}"
        ),
        "office_location": "📍 Ofisimiz manzili:",
        "scooters_intro": "🛵 Bizda quyidagi transport (skuter) takliflari mavjud:",
        "scooter_free_label": "Bepul muddat",
        "scooter_price_label": "Narxi",
        "want_scooter_button": "🛒 Shu skuterni olmoqchiman",
        "scooter_chosen_toast": "✅ So'rovingiz qabul qilindi!",
        "scooter_chosen_confirm": (
            "✅ Siz \"{scooter_name}\" skuterini tanladingiz.\n"
            "Tez orada operatorlarimiz siz bilan bog'lanishadi."
        ),
        "yes": "✅ Ha",
        "no": "❌ Yo'q",
    },
    "ru": {
        "choose_language": "Tilni tanlang / Выберите язык:",
        "greeting": (
            "Здравствуйте! Добро пожаловать на позицию курьера Yandex Eats.\n\n"
            "Пожалуйста, отправьте свой номер телефона с помощью кнопки ниже 👇"
        ),
        "share_phone_button": "📱 Поделиться номером",
        "phone_not_shared": "Пожалуйста, нажмите кнопку '📱 Поделиться номером' ниже.",
        "thanks_phone": "Спасибо! ✅",
        "ask_age_confirm": "Вам исполнилось 18 лет?",
        "ask_age_number": "Сколько вам лет? Пожалуйста, напишите цифрами (например: 23):",
        "age_not_digit": "❗️ Пожалуйста, введите только цифры (например: 23):",
        "age_out_of_range": "❗️ Пожалуйста, введите свой настоящий возраст цифрами:",
        "ask_passport": "Есть ли у вас копия паспорта (скан/фото)?",
        "ask_tashkent": "Вы сейчас находитесь в Ташкенте?",
        "ask_experience": "Вы раньше занимались курьерской доставкой?",
        "ask_transport": "У вас есть личный транспорт?",
        "reject": "😔 К сожалению, вы пока не подходите на должность курьера.",
        "congrats": (
            "🎉 Поздравляем! Вы успешно прошли тест на курьера.\n\n"
            "🕐 Время встречи: {meeting_time}\n"
            "📞 Номер для связи: {contact_phone}"
        ),
        "office_location": "📍 Адрес нашего офиса:",
        "scooters_intro": "🛵 У нас есть следующие варианты транспорта (скутеров):",
        "scooter_free_label": "Бесплатный период",
        "scooter_price_label": "Цена",
        "want_scooter_button": "🛒 Хочу этот скутер",
        "scooter_chosen_toast": "✅ Ваш запрос принят!",
        "scooter_chosen_confirm": (
            "✅ Вы выбрали скутер \"{scooter_name}\".\n"
            "В ближайшее время наш оператор свяжется с вами."
        ),
        "yes": "✅ Да",
        "no": "❌ Нет",
    },
}

DEFAULT_LANG = "uz"


def t(lang: str, key: str, **kwargs) -> str:
    """Berilgan til va kalit bo'yicha tarjima matnini qaytaradi."""
    lang_dict = TEXTS.get(lang, TEXTS[DEFAULT_LANG])
    text = lang_dict.get(key, TEXTS[DEFAULT_LANG].get(key, key))
    if kwargs:
        text = text.format(**kwargs)
    return text
