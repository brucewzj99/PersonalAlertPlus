from __future__ import annotations

CHECK_IN_MESSAGES = {
    "en": {
        "audio_file": "check_in_en.mp3",
        "text": "This is your safety check. Please press the button below to confirm you are okay. If you need help, please let us know.",
    },
    "zh": {
        "audio_file": "check_in_zh.mp3",
        "text": "这是您的安全检查。请点击下方的按钮确认您一切安好。如果您需要帮助，请告诉我们。",
    },
    "ms": {
        "audio_file": "check_in_ms.mp3",
        "text": "Ini adalah semakan keselamatan anda. Sila tekan butang di bawah untuk mengesahkan anda baik-baik saja. Jika anda memerlukan bantuan, sila beritahu kami.",
    },
    "ta": {
        "audio_file": "check_in_ta.mp3",
        "text": "இது உங்கள் பாதுகாப்பு செக் ஆகும். நீங்கள் சரியாக இருப்பதை உறுதிப்படுத்த கீழே உள்ள பொத்தானை அழுத்தவும். உதவி தேவைப்பட்டால், தெரிவிக்கவும்.",
    },
    "nan": {
        "audio_file": "check_in_nan.mp3",
        "text": "这是您的安全检查。请点击下方的按钮确认您一切安好。如果您需要帮助，请告诉我们。",
    },
    "yue": {
        "audio_file": "check_in_yue.mp3",
        "text": "呢個係您嘅安全檢查。請撳以下嘅按鈕確認您冇事。如果需要幫手，請話比我哋知。",
    },
}

NEED_INFO_MESSAGES = {
    "en": {
        "audio_file": "need_info_en.mp3",
        "text": "We have received your alert. To help you better, please tell us more about your situation. What happened?",
    },
    "zh": {
        "audio_file": "need_info_zh.mp3",
        "text": "我们已收到您的警报。为了更好地帮助您，请告诉我们更多关于您的情况。发生了什么？",
    },
    "ms": {
        "audio_file": "need_info_ms.mp3",
        "text": "Kami telah menerima amaran anda. Untuk membantu anda dengan lebih baik, sila beritahu kami lebih lanjut tentang keadaan anda. Apa yang berlaku?",
    },
    "ta": {
        "audio_file": "need_info_ta.mp3",
        "text": "உங்கள் எச்சரிக்கை பெறப்பட்டது. உங்களுக்கு சிறப்பாக உதவ, உங்கள் நிலைமை பற்றி மேலும் தெரிவிக்கவும். என்ன நடந்தது?",
    },
    "nan": {
        "audio_file": "need_info_nan.mp3",
        "text": "阮已经收到你的警报。为了更好帮助你，请告诉我们更多关于你的情况。发生什么事？",
    },
    "yue": {
        "audio_file": "need_info_yue.mp3",
        "text": "我哋已经收到你嘅警报。为了帮你更好，请话多啲关于你嘅情况。发生咩事？",
    },
}


def get_check_in_message(language: str) -> dict:
    return CHECK_IN_MESSAGES.get(language, CHECK_IN_MESSAGES["en"])


def get_audio_path(language: str) -> str:
    msg = get_check_in_message(language)
    return f"assets/audio/{language}/{msg['audio_file']}"


def get_need_info_message(language: str) -> dict:
    return NEED_INFO_MESSAGES.get(language, NEED_INFO_MESSAGES["en"])


def get_need_info_audio_path(language: str) -> str:
    msg = get_need_info_message(language)
    return f"assets/audio/{language}/{msg['audio_file']}"
