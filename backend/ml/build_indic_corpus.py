"""Build the multilingual (en + hi + te + or + romanised) email corpus.

Synthetic-by-construction: no large public Indic phishing corpus exists, so
phishing and benign rows are slot-filled from templates using the keyword
resource (ml/indic_keywords.json) and translated phrase banks. Variations
come from synonym swaps, name/amount/date randomisation and script mixing
(Indic script + Latin digits/brand names). Deterministic under seed 42.

Output: ml/data/train_emails_multilang.csv with columns clean_text,label,lang
  - hi / te / or  : 1000 phishing + 1000 benign rows each
  - roman         : 1000 phishing + 1000 benign rows (romanised Hinglish/Tenglish)
  - en            : every existing English row from ml/data/train_emails.csv

Usage (from the backend directory):
    python ml/build_indic_corpus.py [--llm-augment] [--per-lang 1000]

--llm-augment paraphrases a small subset of the phishing templates through the
shared LLM gateway OFFLINE (batch, cached via explanation_cache) before the
CSV is written; the run stays deterministic because paraphrases are cached and
appended after the seeded slot-fill rows.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/ on sys.path for every launch style

import argparse
import random
from pathlib import Path

import pandas as pd

ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR / "data"
KEYWORDS_PATH = ML_DIR / "indic_keywords.json"
SEED = 42

LANGS = ("hi", "te", "or", "roman")

# ---------------------------------------------------------------------------
# Slot banks (script-mixed: Latin digits/brand names inside Indic text)
# ---------------------------------------------------------------------------
NAMES_HI = ["राहुल शर्मा", "प्रिया पटेल", "अमित कुमार", "स्नेहा गुप्ता", "विक्रम सिंह", "अनु मेहता"]
NAMES_TE = ["రాహుల్ శర్మ", "ప్రియ రెడ్డి", "అమిత్ కుమార్", "స్నేహ గుప్తా", "విక్రమ్ రావు", "అను మెహతా"]
NAMES_OR = ["ରାହୁଲ ଶର୍ମା", "ପ୍ରିୟା ପଟ୍ଟନାୟକ", "ଅମିତ କୁମାର", "ସ୍ନେହା ଗୁପ୍ତା", "ବିକ୍ରମ ସିଂ", "ଅନୁ ମେହେରା"]
NAMES_RO = ["Rahul", "Priya", "Amit", "Sneha", "Vikram", "Anu"]
BANKS = ["SBI", "HDFC Bank", "ICICI Bank", "Axis Bank", "Paytm Bank", "Kotak 811"]
AMOUNTS = ["Rs. 5,000", "Rs. 10,499", "Rs. 1,999", "Rs. 25,000", "INR 8,750", "Rs. 999"]
DATES = ["12/06/2026", "01/07/2026", "28/06/2026", "15/07/2026", "03/08/2026"]
HOURS = ["24", "12", "48", "6"]
OTP_DIGITS = ["4312", "9087", "5561", "7789", "2043", "6610"]
PHISH_URLS = [
    "http://185.220.101.7/kyc/update",
    "https://sbi-kyc-verify.xyz/login",
    "http://hdfc-secure.top/otp",
    "https://paytm-cashback.link/claim",
    "http://icici-alerts.work/verify",
]
BENIGN_URLS = [
    "https://www.wikipedia.org/",
    "https://www.sbi.co.in/",
    "https://calendar.example.com/invite",
    "https://shop.example.com/orders",
]

GREETINGS_HI = ["नमस्ते", "प्रिय ग्राहक", "सेवा में", "प्रिय {name}"]
GREETINGS_TE = ["నమస్కారం", "గౌరవనీయ కస్టమర్", "ప్రియమైన {name}"]
GREETINGS_OR = ["ନମସ୍କାର", "ଜଣେ ଗ୍ରାହକଙ୍କ ପାଇଁ", "ପ୍ରିୟ {name}"]
GREETINGS_RO = ["Namaste", "Dear customer", "Hi {name}", "Hello {name}"]

SIGNOFFS_HI = ["धन्यवाद", "सादर", "ग्राहक सेवा टीम"]
SIGNOFFS_TE = ["ధన్యవాదాలు", "శుభాకాంక్షలు", "కస్టమర్ కేర్ టీమ్"]
SIGNOFFS_OR = ["ଧନ୍ୟବାଦ", "ଶୁଭେଚ୍ଛା", "ଗ୍ରାହକ ସେବା ଦଳ"]
SIGNOFFS_RO = ["Thanks", "Regards", "Customer Care Team"]

# ---------------------------------------------------------------------------
# Phishing templates: {kw_X} slots are filled from indic_keywords.json
# categories (urgency / credential / payment / otp / kyc), guaranteeing the
# corpus exercises the exact phrases the detector matches on.
# ---------------------------------------------------------------------------
PHISHING_TEMPLATES = {
    "hi": [
        "{greeting}, आपका {bank} खाता {kw_urgency}। {kw_kyc} के लिए {url} पर जाएं।",
        "{greeting}, {kw_urgency}: आपका खाता {date} तक सत्यापित नहीं हुआ तो {kw_urgency2}। {kw_credential}।",
        "{greeting}, आपके मोबाइल पर {kw_otp} की आवश्यकता है। रुकें नहीं, {kw_otp2} और अपना खाता चालू रखें।",
        "{greeting}, {bank} से: {kw_kyc} बाकी है। {amount} की {kw_payment} करें, वरना {kw_urgency}।",
        "{greeting}, आपने {amount} का लॉटरी पुरस्कार जीता है! प्राप्त करने के लिए {kw_payment} करें और {url} पर {kw_credential}।",
        "{greeting}, आपका KYC {date} को समाप्त हो रहा है। {kw_kyc} करें: {url} — {kw_otp}।",
        "{greeting}, संदिग्ध लॉगिन पाया गया। {kw_credential} और OTP {otp} दर्ज करें, वरना {kw_urgency}।",
        "{greeting}, {bank} अलर्ट: {amount} की अस्वीकृत लेनदेन। रिफंड के लिए {kw_payment} और {url} पर {kw_otp}।",
        "{greeting}, नौकरी का ऑफर: {amount} मासिक। रजिस्ट्रेशन शुल्क के लिए {kw_payment}, फिर {kw_credential}।",
        "{greeting}, आपका खाता {kw_urgency}। बचाने के लिए {kw_credential} और {kw_kyc} — {url}।",
    ],
    "te": [
        "{greeting}, మీ {bank} ఖాతా {kw_urgency}। {kw_kyc} కోసం {url} సందర్శించండి।",
        "{greeting}, {kw_urgency}: మీ ఖాతా {date} నాటికి ధృవీకరించకపోతే {kw_urgency2}। {kw_credential}।",
        "{greeting}, మీ ఫోన్‌లో {kw_otp} అవసరం। ఆలస్యం చేయవద్దు, {kw_otp2}, ఖాతా చేతనంగా ఉంచండి।",
        "{greeting}, {bank} నుండి: {kw_kyc} మిగిలిపోయింది। {amount} {kw_payment}, లేదా {kw_urgency}।",
        "{greeting}, {amount} లాటరీ బహుమతి గెలిచారు! అందుకోవడానికి {kw_payment} చేసి {url} లో {kw_credential}।",
        "{greeting}, మీ KYC {date} న గడువు ముగుస్తుంది। {kw_kyc}: {url} — {kw_otp}।",
        "{greeting}, అనుమానాస్పద లాగిన్ కనుగొనబడింది। {kw_credential} మరియు OTP {otp} నమోదు చేయండి, లేదా {kw_urgency}।",
        "{greeting}, {bank} అలర్ట్: {amount} తిరస్కరించబడిన లావాదేవీ। రీఫండ్ కోసం {kw_payment} మరియు {url} లో {kw_otp}।",
        "{greeting}, ఉద్యోగ ఆఫర్: నెలకు {amount}। నమోదు రుసుముకు {kw_payment}, తర్వాత {kw_credential}।",
        "{greeting}, మీ ఖాతా {kw_urgency}। కాపాడటానికి {kw_credential} మరియు {kw_kyc} — {url}।",
    ],
    "or": [
        "{greeting}, ଆପଣଙ୍କ {bank} ଖାତା {kw_urgency}। {kw_kyc} ପାଇଁ {url} ପରିଦର୍ଶନ କରନ୍ତୁ।",
        "{greeting}, {kw_urgency}: {date} ଭିତରେ ଖାତା ଯାଞ୍ଚ ନ ହେଲେ {kw_urgency2}। {kw_credential}।",
        "{greeting}, ଆପଣଙ୍କ ମୋବାଇଲରେ {kw_otp} ଆବଶ୍ୟକ। ବିଳମ୍ବ କରନ୍ତୁ ନାହିଁ, {kw_otp2}, ଖାତା ସକ୍ରିୟ ରଖନ୍ତୁ।",
        "{greeting}, {bank} ଠାରୁ: {kw_kyc} ବାକି ଅଛି। {amount} {kw_payment}, ନହେଲେ {kw_urgency}।",
        "{greeting}, {amount} ଲଟେରୀ ପୁରସ୍କାର ଜିତିଛନ୍ତି! ଗ୍ରହଣ କରିବାକୁ {kw_payment} କରନ୍ତୁ ଏବଂ {url} ରେ {kw_credential}।",
        "{greeting}, ଆପଣଙ୍କ KYC {date} ରେ ସମାପ୍ତ ହେବ। {kw_kyc}: {url} — {kw_otp}।",
        "{greeting}, ସନ୍ଦେହଜନକ ଲଗଇନ୍ ମିଳିଲା। {kw_credential} ଏବଂ OTP {otp} ଦିଅନ୍ତୁ, ନହେଲା {kw_urgency}।",
        "{greeting}, {bank} ଆଲର୍ଟ: {amount} ଲେଣଦେନ ପ୍ରତ୍ୟାଖ୍ୟାତ। ରିଫଣ୍ଡ ପାଇଁ {kw_payment} ଏବଂ {url} ରେ {kw_otp}।",
        "{greeting}, ଚାକିରି ଅଫର୍: ମାସିକ {amount}। ନୋଟେଷନ ଫି ପାଇଁ {kw_payment}, ପରେ {kw_credential}।",
        "{greeting}, ଆପଣଙ୍କ ଖାତା {kw_urgency}। ରକ୍ଷା କରିବାକୁ {kw_credential} ଏବଂ {kw_kyc} — {url}।",
    ],
    "roman": [
        "{greeting}, aapka {bank} khata {kw_urgency}. {kw_kyc} ke liye {url} par jayein.",
        "{greeting}, {kw_urgency}: {date} tak khata verify nahi hua to {kw_urgency2}. {kw_credential}.",
        "{greeting}, aapke phone par {kw_otp} zaroori hai. Deri na karein, {kw_otp2} aur khata active rakhein.",
        "{greeting}, {bank} se: {kw_kyc} baaki hai. {amount} ki {kw_payment} karein, warna {kw_urgency}.",
        "{greeting}, aapne {amount} ki lottery jeeti hai! claim karne ke liye {kw_payment} aur {url} par {kw_credential}.",
        "{greeting}, aapka KYC {date} ko expire hoga. {kw_kyc}: {url} — {kw_otp}.",
        "{greeting}, suspicious login mila. {kw_credential} aur OTP {otp} daaliye, warna {kw_urgency}.",
        "{greeting}, {bank} alert: {amount} ki transaction reject hui. refund ke liye {kw_payment} aur {url} par {kw_otp}.",
        "{greeting}, job offer: monthly {amount}. registration fees ke liye {kw_payment}, phir {kw_credential}.",
        "{greeting}, aapka khata {kw_urgency}. bachane ke liye {kw_credential} aur {kw_kyc} — {url}.",
    ],
}

# ---------------------------------------------------------------------------
# Benign templates: service/transactional mail with no attack indicators.
# ---------------------------------------------------------------------------
BENIGN_TEMPLATES = {
    "hi": [
        "{greeting}, आपके {bank} खाते में {amount} जमा हुआ है। विवरण ऐप में देखें।",
        "{greeting}, आपका ऑर्डर डिस्पैच हो गया है और {date} तक पहुंच जाएगा।",
        "{greeting}, यह आपकी साप्ताहिक न्यूज़लेटर है। इस सप्ताह की चुनी हुई कहानियां पढ़ें।",
        "{greeting}, बैठक {date} को सुबह 10 बजे निर्धारित है। कैलेंडर आमंत्रण संलग्न है।",
        "{greeting}, आपकी छमाही बिजली की बिल {amount} जारी हुई है, बिना अतिरिक्त शुल्क के भुगतान करें।",
        "{greeting}, पासवर्ड सफलतापूर्वक बदल दिया गया। यदि आपने यह नहीं किया, सहायता टीम से संपर्क करें।",
        "{greeting}, आपकी फ्लाईट {date} की पुष्टि हो गई है। वेब चेक-इन 24 घंटे पहले खुलेगा।",
        "{greeting}, वेतन {amount} क्रेडिट हो गया है। वेतन स्लिप पोर्टल पर उपलब्ध है।",
        "{greeting}, लाइब्रेरी की किताब {date} तक लौटाएं। ऑनलाइन नवीनीकरण उपलब्ध है।",
        "{greeting}, आपकी अपॉइंटमेंट {date} को दोपहर 3 बजे की पुष्टि हो गई है। {url} पर विवरण देखें।",
    ],
    "te": [
        "{greeting}, మీ {bank} ఖాతాలో {amount} జమ అయింది. వివరాలు యాప్‌లో చూడండి.",
        "{greeting}, మీ ఆర్డర్ పంపబడింది మరియు {date} నాటికి వస్తుంది.",
        "{greeting}, ఇది మీ వారపు న్యూస్‌లెటర్. ఈ వారం ఎంపిక చేసిన కథనాలు చదవండి.",
        "{greeting}, సమావేశం {date} ఉదయం 10 గంటలకు నిర్ణయించబడింది. క్యాలెండర్ ఆహ్వానం జోడించబడింది.",
        "{greeting}, మీ ఆరు నెలల విద్యుత్ బిల్లు {amount} జారీ అయింది, అదనపు రుసుము లేకుండా చెల్లించండి.",
        "{greeting}, పాస్‌వర్డ్ విజయవంతంగా మార్చబడింది. మీరు చేయకుంటే, సపోర్ట్ టీమ్‌ను సంప్రదించండి.",
        "{greeting}, మీ ఫ్లైట్ {date} కి ధృవీకరించబడింది. వెబ్ చెక్-ఇన్ 24 గంటల ముందు ప్రారంభమవుతుంది.",
        "{greeting}, జీతం {amount} జమ అయింది. జీతం స్లిప్ పోర్టల్‌లో అందుబాటులో ఉంది.",
        "{greeting}, లైబ్రరీ పుస్తకం {date} లోపు తిరిగి ఇవ్వండి. ఆన్‌లైన్ రెన్యూవల్ అందుబాటులో ఉంది.",
        "{greeting}, మీ అపాయింట్‌మెంట్ {date} మధ్యాహ్నం 3 గంటలకు ధృవీకరించబడింది. {url} లో వివరాలు చూడండి.",
    ],
    "or": [
        "{greeting}, ଆପଣଙ୍କ {bank} ଖାତାରେ {amount} ଜମା ହୋଇଛି। ବିବରଣୀ ଆପ୍ ରେ ଦେଖନ୍ତୁ।",
        "{greeting}, ଆପଣଙ୍କ ଅର୍ଡର ପଠାଯାଇଛି ଏବଂ {date} ଭିତରେ ପହଞ୍ଚିବ।",
        "{greeting}, ଏହା ଆପଣଙ୍କ ସାପ୍ତାହିକ ନ୍ୟୁଜ୍‌ଲେଟର। ଏହି ସପ୍ତାହର ମନୋନୀତ କାହାଣୀ ପଢ଼ନ୍ତୁ।",
        "{greeting}, ବୈଠକ {date} ସକାଳ ୧୦ ଟାରେ ନିର୍ଧାରିତ। କ୍ୟାଲେଣ୍ଡର ନିମନ୍ତ୍ରଣ ସଂଲଗ୍ନ।",
        "{greeting}, ଆପଣଙ୍କ ଷାଣ୍ମାସିକ ବିଦ୍ୟୁତ୍ ବିଲ୍ {amount} ପ୍ରଦାନ ହୋଇଛି, ଅତିରିକ୍ତ ଫି ବିନା ଦେୟ କରନ୍ତୁ।",
        "{greeting}, ପାସୱାର୍ଡ ସଫଳତାର ସହ ବଦଳାଯାଇଛି। ଆପଣ ନ କଲେ, ସହାୟତା ଦଳକୁ ଯୋଗାଯୋଗ କରନ୍ତୁ।",
        "{greeting}, ଆପଣଙ୍କ ଫ୍ଲାଇଟ୍ {date} ପାଇଁ ନିଶ୍ଚିତ ହୋଇଛି। ୱେବ୍ ଚେକ୍-ଇନ୍ 24 ଘଣ୍ଟା ପୂର୍ବରୁ ଖୋଲିବ।",
        "{greeting}, ଦରମହା {amount} ଜମା ହୋଇଗଲା। ଦରମହା ସ୍ଲିପ୍ ପୋର୍ଟାଲରେ ଉପଲବ୍ଧ।",
        "{greeting}, ଲାଇବ୍ରେରୀ ବହି {date} ଭିତରେ ଫେରାନ୍ତୁ। ଅନଲାଇନ୍ ନବୀକରଣ ଉପଲବ୍ଧ।",
        "{greeting}, ଆପଣଙ୍କ ଅପଏଣ୍ଟମେଣ୍ଟ {date} ଅପରାହ୍ନ 3 ଟାରେ ନିଶ୍ଚିତ। {url} ରେ ବିବରଣୀ ଦେଖନ୍ତୁ।",
    ],
    "roman": [
        "{greeting}, aapke {bank} khate mein {amount} jama hua hai. details app mein dekhein.",
        "{greeting}, aapka order dispatch ho gaya hai aur {date} tak pahunch jayega.",
        "{greeting}, yeh aapki weekly newsletter hai. is hafte ki chuni hui kahaniyan padhein.",
        "{greeting}, meeting {date} ko subah 10 baje scheduled hai. calendar invite attached hai.",
        "{greeting}, aapki six-month bijli bill {amount} jaari hui hai, bina extra fees ke pay karein.",
        "{greeting}, password successfully change ho gaya. agar aapne nahi kiya, support team se contact karein.",
        "{greeting}, aapki flight {date} ke liye confirm ho gayi hai. web check-in 24 ghante pehle khulega.",
        "{greeting}, salary {amount} credit ho gayi hai. salary slip portal par available hai.",
        "{greeting}, library ki kitab {date} tak wapas karein. online renewal available hai.",
        "{greeting}, aapki appointment {date} ko dopahar 3 baje confirm ho gayi hai. {url} par details dekhein.",
    ],
}

GREETINGS = {"hi": GREETINGS_HI, "te": GREETINGS_TE, "or": GREETINGS_OR, "roman": GREETINGS_RO}
SIGNOFFS = {"hi": SIGNOFFS_HI, "te": SIGNOFFS_TE, "or": SIGNOFFS_OR, "roman": SIGNOFFS_RO}
NAMES = {"hi": NAMES_HI, "te": NAMES_TE, "or": NAMES_OR, "roman": NAMES_RO}


def load_keywords() -> dict:
    import json

    with KEYWORDS_PATH.open(encoding="utf-8") as fh:
        resource = json.load(fh)
    bank = resource["languages"]
    # The JSON key is "romanised"; the corpus/detector lang code is "roman".
    bank["roman"] = bank.pop("romanised")
    return bank


def _fill_slot(rng: random.Random, category: str, lang: str, keyword_bank: dict) -> str:
    return rng.choice(keyword_bank[lang][category])


def _render(
    rng: random.Random,
    template: str,
    lang: str,
    keyword_bank: dict,
    url_bank: list[str],
) -> str:
    """Fill {kw_*} slots from the keyword resource and the context slots."""
    categories = [c for c in ("urgency", "credential", "payment", "otp", "kyc") if f"{{kw_{c}}}" in template]
    text = template
    # Each kw category used twice (kw_X and kw_X2) draws two different phrases.
    for category in categories:
        phrases = rng.sample(keyword_bank[lang][category], k=min(2, len(keyword_bank[lang][category])))
        text = text.replace(f"{{kw_{category}}}", phrases[0])
        if f"{{kw_{category}2}}" in text:
            text = text.replace(f"{{kw_{category}2}}", phrases[1])
    replacements = {
        "{greeting}": rng.choice(GREETINGS[lang]).replace("{name}", rng.choice(NAMES[lang])),
        "{name}": rng.choice(NAMES[lang]),
        "{bank}": rng.choice(BANKS),
        "{amount}": rng.choice(AMOUNTS),
        "{date}": rng.choice(DATES),
        "{hours}": rng.choice(HOURS),
        "{otp}": rng.choice(OTP_DIGITS),
        "{url}": rng.choice(url_bank),
    }
    for slot, value in replacements.items():
        text = text.replace(slot, value)
    # Sign-off: append a random closing to add surface variation.
    if rng.random() < 0.7:
        text = f"{text}\n{rng.choice(SIGNOFFS[lang])}"
    return " ".join(text.split())


def build_rows(per_lang: int, keyword_bank: dict) -> list[dict]:
    """Slot-fill per_lang phishing + per_lang benign rows for every Indic lang."""
    rng = random.Random(SEED)
    rows: list[dict] = []
    for lang in LANGS:
        phishing_templates = PHISHING_TEMPLATES[lang]
        benign_templates = BENIGN_TEMPLATES[lang]
        for label, templates, url_bank in (
            (1, phishing_templates, PHISH_URLS),
            (0, benign_templates, BENIGN_URLS),
        ):
            for i in range(per_lang):
                template = templates[i % len(templates)]
                text = _render(rng, template, lang, keyword_bank, url_bank)
                rows.append({"clean_text": text, "label": label, "lang": lang})
    return rows


def llm_augment(rows: list[dict], subset: int = 20) -> list[dict]:
    """OFFLINE paraphrase of a small phishing subset through the LLM gateway.

    Batched and cached: explanation_cache dedupes identical inputs, and the
    gateway's provider chain (Groq -> OpenRouter -> rule-based) never raises —
    on total failure the original row is kept unchanged. Requires backend env
    (GROQ_API_KEY / OPENROUTER_API_KEY); run from the backend directory.
    """
    import asyncio

    from app.ai.llm_gateway import explain, make_cache_key

    rng = random.Random(SEED)
    phishing_rows = [row for row in rows if row["label"] == 1]
    chosen = rng.sample(phishing_rows, k=min(subset, len(phishing_rows)))

    async def _paraphrase_all() -> list[str]:
        outputs = []
        for row in chosen:
            explained = await explain(
                "corpus_paraphrase",
                (
                    "You are a text-rewriting assistant. Paraphrase the given "
                    "message, keeping its language and script and its meaning. "
                    "Return only the paraphrased text."
                ),
                row["clean_text"],
                make_cache_key("corpus_paraphrase", row["clean_text"]),
                json_mode=False,
            )
            outputs.append(explained["explanation"])
        return outputs

    try:
        paraphrases = asyncio.run(_paraphrase_all())
    except Exception as exc:  # pragma: no cover - env without LLM keys
        print(f"  llm-augment unavailable ({exc}); keeping the seeded rows only")
        return []

    augmented: list[dict] = []
    for row, paraphrase in zip(chosen, paraphrases):
        text = " ".join(str(paraphrase).split())
        if text and text.lower() != row["clean_text"].lower():
            augmented.append({"clean_text": text, "label": 1, "lang": row["lang"]})
    print(f"  llm-augment: {len(augmented)} paraphrased rows appended (cached)")
    return augmented


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-lang", type=int, default=1000, help="phishing + benign rows per Indic language")
    parser.add_argument("--llm-augment", action="store_true", help="paraphrase a subset offline through the LLM gateway (batch, cached)")
    args = parser.parse_args()

    keyword_bank = load_keywords()
    rows = build_rows(args.per_lang, keyword_bank)
    print(f"  slot-filled {len(rows)} Indic/romanised rows across {len(LANGS)} languages (seed {SEED})")

    if args.llm_augment:
        rows.extend(llm_augment(rows))

    english = pd.read_csv(DATA_DIR / "train_emails.csv").dropna()
    english["lang"] = "en"
    english = english[["clean_text", "label", "lang"]]
    print(f"  existing English rows: {len(english)} (lang=en, from train_emails.csv)")

    frame = pd.DataFrame(rows, columns=["clean_text", "label", "lang"])
    combined = pd.concat([english, frame], ignore_index=True)
    combined["label"] = combined["label"].astype(int)
    combined.to_csv(DATA_DIR / "train_emails_multilang.csv", index=False)

    summary = combined.groupby(["lang", "label"]).size().unstack(fill_value=0)
    print("  corpus summary (rows per lang x label):")
    print(summary.to_string())
    print(f"  wrote {len(combined)} rows -> {DATA_DIR / 'train_emails_multilang.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
