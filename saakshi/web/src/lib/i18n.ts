/* The nine languages Saakshi speaks (each checked end to end with Gnani Timbre and Prisma),
   and the words on the main speaking screen in each. Everything a person hears is in their
   language; deeper screens fall back to English where a string isn't listed here. */

export type Lang = "hi-IN" | "en-IN" | "ta-IN" | "te-IN" | "kn-IN" | "ml-IN" | "mr-IN" | "bn-IN" | "gu-IN";

export const LANGS: { code: Lang; native: string; english: string; hello: string }[] = [
  { code: "hi-IN", native: "हिन्दी", english: "Hindi", hello: "नमस्ते" },
  { code: "en-IN", native: "English", english: "English", hello: "Hello" },
  { code: "ta-IN", native: "தமிழ்", english: "Tamil", hello: "வணக்கம்" },
  { code: "te-IN", native: "తెలుగు", english: "Telugu", hello: "నమస్కారం" },
  { code: "kn-IN", native: "ಕನ್ನಡ", english: "Kannada", hello: "ನಮಸ್ಕಾರ" },
  { code: "ml-IN", native: "മലയാളം", english: "Malayalam", hello: "നമസ്കാരം" },
  { code: "mr-IN", native: "मराठी", english: "Marathi", hello: "नमस्कार" },
  { code: "bn-IN", native: "বাংলা", english: "Bengali", hello: "নমস্কার" },
  { code: "gu-IN", native: "ગુજરાતી", english: "Gujarati", hello: "નમસ્તે" },
];

const S = {
  choose: {
    "en-IN": "Choose your language", "hi-IN": "अपनी भाषा चुनिए", "ta-IN": "உங்கள் மொழியைத் தேர்ந்தெடுங்கள்",
    "te-IN": "మీ భాషను ఎంచుకోండి", "kn-IN": "ನಿಮ್ಮ ಭಾಷೆಯನ್ನು ಆರಿಸಿ", "ml-IN": "നിങ്ങളുടെ ഭാഷ തിരഞ്ഞെടുക്കുക",
    "mr-IN": "तुमची भाषा निवडा", "bn-IN": "আপনার ভাষা বেছে নিন", "gu-IN": "તમારી ભાષા પસંદ કરો",
  },
  listening: {
    "en-IN": "Listening… just speak", "hi-IN": "सुन रही हूँ… बस बोलिए", "ta-IN": "கேட்டுக்கொண்டிருக்கிறேன்… பேசுங்கள்",
    "te-IN": "వింటున్నాను… మాట్లాడండి", "kn-IN": "ಕೇಳುತ್ತಿದ್ದೇನೆ… ಮಾತನಾಡಿ", "ml-IN": "കേൾക്കുന്നു… സംസാരിക്കൂ",
    "mr-IN": "ऐकत आहे… बोला", "bn-IN": "শুনছি… বলুন", "gu-IN": "સાંભળું છું… બોલો",
  },
  hearing: {
    "en-IN": "Hearing you…", "hi-IN": "आपकी बात सुन रही हूँ…", "ta-IN": "நீங்கள் பேசுவதைக் கேட்கிறேன்…",
    "te-IN": "మీ మాట వింటున్నాను…", "kn-IN": "ನಿಮ್ಮ ಮಾತು ಕೇಳುತ್ತಿದ್ದೇನೆ…", "ml-IN": "നിങ്ങൾ പറയുന്നത് കേൾക്കുന്നു…",
    "mr-IN": "तुमचं बोलणं ऐकत आहे…", "bn-IN": "আপনার কথা শুনছি…", "gu-IN": "તમારી વાત સાંભળું છું…",
  },
  thinking: {
    "en-IN": "Saakshi is thinking…", "hi-IN": "साक्षी सोच रही है…", "ta-IN": "சாக்ஷி யோசிக்கிறார்…",
    "te-IN": "సాక్షి ఆలోచిస్తోంది…", "kn-IN": "ಸಾಕ್ಷಿ ಯೋಚಿಸುತ್ತಿದ್ದಾರೆ…", "ml-IN": "സാക്ഷി ആലോചിക്കുന്നു…",
    "mr-IN": "साक्षी विचार करत आहे…", "bn-IN": "সাক্ষী ভাবছে…", "gu-IN": "સાક્ષી વિચારે છે…",
  },
  speaking: {
    "en-IN": "Saakshi is speaking · talk to interrupt", "hi-IN": "साक्षी बोल रही है · बीच में बोल सकते हैं",
    "ta-IN": "சாக்ஷி பேசுகிறார் · இடையில் பேசலாம்", "te-IN": "సాక్షి మాట్లాడుతోంది · మధ్యలో మాట్లాడవచ్చు",
    "kn-IN": "ಸಾಕ್ಷಿ ಮಾತನಾಡುತ್ತಿದ್ದಾರೆ · ನಡುವೆ ಮಾತನಾಡಬಹುದು", "ml-IN": "സാക്ഷി സംസാരിക്കുന്നു · ഇടയ്ക്ക് സംസാരിക്കാം",
    "mr-IN": "साक्षी बोलत आहे · मध्ये बोलू शकता", "bn-IN": "সাক্ষী বলছে · মাঝে কথা বলতে পারেন",
    "gu-IN": "સાક્ષી બોલે છે · વચ્ચે બોલી શકો છો",
  },
  paused: {
    "en-IN": "Mic paused · tap to listen again", "hi-IN": "माइक रुका है · फिर सुनने के लिए दबाएँ",
    "ta-IN": "மைக் நிறுத்தப்பட்டது · மீண்டும் தட்டவும்", "te-IN": "మైక్ ఆపబడింది · మళ్ళీ నొక్కండి",
    "kn-IN": "ಮೈಕ್ ನಿಲ್ಲಿಸಲಾಗಿದೆ · ಮತ್ತೆ ಒತ್ತಿ", "ml-IN": "മൈക്ക് നിർത്തി · വീണ്ടും തൊടുക",
    "mr-IN": "माइक थांबला आहे · पुन्हा दाबा", "bn-IN": "মাইক বন্ধ · আবার চাপুন", "gu-IN": "માઇક બંધ છે · ફરી દબાવો",
  },
  start: {
    "en-IN": "Start talking", "hi-IN": "बात शुरू करें", "ta-IN": "பேசத் தொடங்குங்கள்", "te-IN": "మాట్లాడటం మొదలుపెట్టండి",
    "kn-IN": "ಮಾತನಾಡಲು ಶುರು ಮಾಡಿ", "ml-IN": "സംസാരിച്ചു തുടങ്ങൂ", "mr-IN": "बोलायला सुरुवात करा",
    "bn-IN": "কথা বলা শুরু করুন", "gu-IN": "વાત શરૂ કરો",
  },
  introTitle: {
    "en-IN": "Say your work out loud", "hi-IN": "अपना काम बोलकर लिखवाइए", "ta-IN": "உங்கள் வேலையைச் சொல்லுங்கள்",
    "te-IN": "మీ పని గురించి చెప్పండి", "kn-IN": "ನಿಮ್ಮ ಕೆಲಸದ ಬಗ್ಗೆ ಹೇಳಿ", "ml-IN": "നിങ്ങളുടെ ജോലിയെക്കുറിച്ച് പറയൂ",
    "mr-IN": "तुमचं काम सांगा", "bn-IN": "আপনার কাজের কথা বলুন", "gu-IN": "તમારા કામ વિશે કહો",
  },
  introHint: {
    "en-IN": "Tell Saakshi whose place you worked at and how much you got. No buttons: just talk, like on a phone call.",
    "hi-IN": "बताइए किसके यहाँ काम किया और कितने पैसे मिले। बटन दबाने की ज़रूरत नहीं, फ़ोन की तरह बस बात कीजिए।",
    "ta-IN": "யார் வீட்டில் வேலை செய்தீர்கள், எவ்வளவு கிடைத்தது என்று சொல்லுங்கள். பொத்தான் தேவையில்லை, போனில் பேசுவது போல பேசுங்கள்.",
    "te-IN": "ఎవరి దగ్గర పని చేశారు, ఎంత వచ్చింది చెప్పండి. బటన్ అవసరం లేదు, ఫోన్‌లో లాగే మాట్లాడండి.",
    "kn-IN": "ಯಾರ ಮನೆಯಲ್ಲಿ ಕೆಲಸ ಮಾಡಿದಿರಿ, ಎಷ್ಟು ಸಿಕ್ಕಿತು ಎಂದು ಹೇಳಿ. ಬಟನ್ ಬೇಡ, ಫೋನ್‌ನಲ್ಲಿ ಮಾತನಾಡುವಂತೆ ಮಾತನಾಡಿ.",
    "ml-IN": "ആരുടെ വീട്ടിൽ ജോലി ചെയ്തു, എത്ര കിട്ടി എന്ന് പറയൂ. ബട്ടൺ വേണ്ട, ഫോണിൽ സംസാരിക്കുന്നതുപോലെ സംസാരിക്കൂ.",
    "mr-IN": "कोणाकडे काम केलं आणि किती पैसे मिळाले ते सांगा. बटण दाबायची गरज नाही, फोनवर बोलल्यासारखं बोला.",
    "bn-IN": "কার বাড়িতে কাজ করেছেন আর কত টাকা পেয়েছেন, বলুন। বোতাম লাগবে না, ফোনে কথা বলার মতো বলুন।",
    "gu-IN": "કોના ઘરે કામ કર્યું અને કેટલા પૈસા મળ્યા, તે કહો. બટન દબાવવાની જરૂર નથી, ફોનની જેમ વાત કરો.",
  },
  tabSpeak: {
    "en-IN": "Speak", "hi-IN": "बोलो", "ta-IN": "பேசு", "te-IN": "మాట్లాడు", "kn-IN": "ಮಾತನಾಡಿ", "ml-IN": "സംസാരിക്കൂ",
    "mr-IN": "बोला", "bn-IN": "বলুন", "gu-IN": "બોલો",
  },
  tabRecord: {
    "en-IN": "My record", "hi-IN": "मेरा रिकॉर्ड", "ta-IN": "என் பதிவு", "te-IN": "నా రికార్డు", "kn-IN": "ನನ್ನ ದಾಖಲೆ",
    "ml-IN": "എന്റെ രേഖ", "mr-IN": "माझा रेकॉर्ड", "bn-IN": "আমার রেকর্ড", "gu-IN": "મારો રેકોર્ડ",
  },
  tabShare: {
    "en-IN": "Share", "hi-IN": "शेयर", "ta-IN": "பகிர்", "te-IN": "పంచుకో", "kn-IN": "ಹಂಚಿಕೊಳ್ಳಿ", "ml-IN": "പങ്കിടുക",
    "mr-IN": "शेअर", "bn-IN": "শেয়ার", "gu-IN": "શેર",
  },
  orType: {
    "en-IN": "or type…", "hi-IN": "या लिखिए…", "ta-IN": "அல்லது தட்டச்சு செய்யுங்கள்…", "te-IN": "లేదా టైప్ చేయండి…",
    "kn-IN": "ಅಥವಾ ಟೈಪ್ ಮಾಡಿ…", "ml-IN": "അല്ലെങ്കിൽ ടൈപ്പ് ചെയ്യൂ…", "mr-IN": "किंवा टाइप करा…", "bn-IN": "অথবা লিখুন…",
    "gu-IN": "અથવા લખો…",
  },
  micBlocked: {
    "en-IN": "Microphone blocked. Allow it in the browser, or type instead.",
    "hi-IN": "माइक की अनुमति नहीं मिली। ब्राउज़र में अनुमति दीजिए, या लिखिए।",
    "ta-IN": "மைக் அனுமதி இல்லை. உலாவியில் அனுமதியுங்கள், அல்லது தட்டச்சு செய்யுங்கள்.",
    "te-IN": "మైక్ అనుమతి లేదు. బ్రౌజర్‌లో అనుమతించండి, లేదా టైప్ చేయండి.",
    "kn-IN": "ಮೈಕ್ ಅನುಮತಿ ಇಲ್ಲ. ಬ್ರೌಸರ್‌ನಲ್ಲಿ ಅನುಮತಿಸಿ, ಅಥವಾ ಟೈಪ್ ಮಾಡಿ.",
    "ml-IN": "മൈക്ക് അനുമതിയില്ല. ബ്രൗസറിൽ അനുവദിക്കൂ, അല്ലെങ്കിൽ ടൈപ്പ് ചെയ്യൂ.",
    "mr-IN": "माइकची परवानगी नाही. ब्राउझरमध्ये परवानगी द्या, किंवा टाइप करा.",
    "bn-IN": "মাইকের অনুমতি নেই। ব্রাউজারে অনুমতি দিন, অথবা লিখুন।",
    "gu-IN": "માઇકની પરવાનગી નથી. બ્રાઉઝરમાં પરવાનગી આપો, અથવા લખો.",
  },
  tabHome: {
    "en-IN": "Home", "hi-IN": "होम", "ta-IN": "முகப்பு", "te-IN": "హోమ్", "kn-IN": "ಮುಖಪುಟ", "ml-IN": "ഹോം",
    "mr-IN": "होम", "bn-IN": "হোম", "gu-IN": "હોમ",
  },
  speakNew: {
    "en-IN": "Speak new work", "hi-IN": "नया काम बोलकर जोड़ें", "ta-IN": "புதிய வேலையைச் சொல்லுங்கள்",
    "te-IN": "కొత్త పని చెప్పండి", "kn-IN": "ಹೊಸ ಕೆಲಸ ಹೇಳಿ", "ml-IN": "പുതിയ ജോലി പറയൂ", "mr-IN": "नवीन काम सांगा",
    "bn-IN": "নতুন কাজের কথা বলুন", "gu-IN": "નવું કામ કહો",
  },
  continue: {
    "en-IN": "Continue", "hi-IN": "आगे बढ़ें", "ta-IN": "தொடரவும்", "te-IN": "కొనసాగించండి", "kn-IN": "ಮುಂದುವರಿಸಿ",
    "ml-IN": "തുടരുക", "mr-IN": "पुढे चला", "bn-IN": "এগিয়ে যান", "gu-IN": "આગળ વધો",
  },
} satisfies Record<string, Record<Lang, string>>;

export type Key = keyof typeof S;

export function t(key: Key, lang: string | null | undefined): string {
  const row = S[key] as Record<string, string>;
  return row[lang ?? "en-IN"] ?? row["en-IN"];
}

import UI from "./ui-strings.json";

/** Screen text: hand-written Hindi when given, English, or the pre-translated string for the other seven
 *  languages (scripts/build_i18n.py fills ui-strings.json). {name} placeholders are filled from `vars`. */
export function tx(lang: string | null | undefined, en: string, hi?: string, vars?: Record<string, string | number>): string {
  const l = lang ?? "en-IN";
  let s = l === "hi-IN" && hi ? hi : l === "en-IN" ? en : ((UI as Record<string, Record<string, string>>)[l]?.[en] ?? en);
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
  return s;
}

export const langName = (code: string | null | undefined) => LANGS.find((l) => l.code === code)?.native ?? "English";

/** Kinds of work, in the reader's language. */
export function roleName(role: string, lang: string | null | undefined): string {
  const r: Record<string, string> = {
    domestic: tx(lang, "Domestic worker", "घरेलू कामगार"), cook: tx(lang, "Cook", "रसोइया"), nanny: tx(lang, "Nanny", "आया"),
    driver: tx(lang, "Driver", "ड्राइवर"), construction: tx(lang, "Construction worker", "निर्माण मज़दूर"),
    painter: tx(lang, "Painter", "पेंटर"), plumber: tx(lang, "Plumber", "प्लंबर"), electrician: tx(lang, "Electrician", "बिजली मिस्त्री"),
    tailor: tx(lang, "Tailor", "दर्ज़ी"), security: tx(lang, "Security guard", "सुरक्षा गार्ड"),
    delivery: tx(lang, "Delivery partner", "डिलीवरी पार्टनर"), other: tx(lang, "Worker", "कामगार"),
  };
  return r[role] ?? r.other;
}

/** "just now", "5 minutes ago", "yesterday", in the reader's language (the browser knows them all). */
export function agoIn(iso: string, lang: string | null | undefined): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  try {
    const rtf = new Intl.RelativeTimeFormat(lang ?? "en-IN", { numeric: "auto" });
    if (s < 45) return rtf.format(0, "second");
    if (s < 3600) return rtf.format(-Math.floor(s / 60), "minute");
    if (s < 86400) return rtf.format(-Math.floor(s / 3600), "hour");
    if (s < 86400 * 7) return rtf.format(-Math.floor(s / 86400), "day");
    return new Date(iso).toLocaleDateString(lang ?? "en-IN", { day: "numeric", month: "short" });
  } catch { return new Date(iso).toLocaleDateString(); }
}

/** A month ("2026-10") as its short name in the reader's language. */
export function monthShort(ym: string, lang: string | null | undefined): string {
  try { return new Date(`${ym.slice(0, 7)}-15T00:00:00`).toLocaleString(lang ?? "en-IN", { month: "short" }); }
  catch { return ym.slice(5, 7); }
}

/** What happened, in the worker's language (the server log itself is an English operator log). */
export function eventText(kind: string, raw: string, lang: string | null | undefined): string {
  const m: Record<string, string> = {
    "entry.saved": tx(lang, "You saved a work record", "आपने काम का रिकॉर्ड सेव किया"),
    "entry.withdrawn": tx(lang, "You withdrew a record", "आपने एक रिकॉर्ड वापस लिया"),
    "call.queued": tx(lang, "Saakshi will call your employer to confirm", "साक्षी पुष्टि के लिए नियोक्ता को फ़ोन करेगी"),
    "call.done": tx(lang, "A confirmation call finished", "पुष्टि की कॉल पूरी हुई"),
    "link.created": tx(lang, "A confirmation link is ready to send", "पुष्टि का लिंक भेजने के लिए तैयार है"),
    "link.done": tx(lang, "An employer answered your link", "नियोक्ता ने आपके लिंक का जवाब दिया"),
    "share.created": tx(lang, "You shared your record", "आपने अपना रिकॉर्ड शेयर किया"),
    "share.revoked": tx(lang, "You stopped sharing a record", "आपने शेयर बंद किया"),
    "worker.joined": tx(lang, "You joined Saakshi", "आप साक्षी से जुड़ीं"),
    "worker.created": tx(lang, "You joined Saakshi", "आप साक्षी से जुड़ीं"),
  };
  return m[kind] ?? (lang === "en-IN" || lang === "hi-IN" ? raw : tx(lang, "Your record was updated", "आपका रिकॉर्ड अपडेट हुआ"));
}

/** A record's state, in the reader's language. */
export function statusName(status: string, lang: string | null | undefined): string {
  const m: Record<string, string> = {
    verified: tx(lang, "Verified", "पक्का"), corrected: tx(lang, "Employer corrected", "नियोक्ता ने सुधारा"),
    pending: tx(lang, "Awaiting confirmation", "पुष्टि का इंतज़ार"), calling: tx(lang, "Calling employer", "नियोक्ता को फ़ोन"),
    disputed: tx(lang, "Not confirmed", "पुष्टि नहीं हुई"), unconfirmed: tx(lang, "Unreachable", "संपर्क नहीं हुआ"),
    self_declared: tx(lang, "Self-declared", "ख़ुद का बयान"), withdrawn: tx(lang, "Withdrawn", "वापस लिया"),
    queued: tx(lang, "Queued", "कतार में"), callback: tx(lang, "Call back later", "बाद में फ़ोन"),
  };
  return m[status] ?? status;
}

/** Evidence level names, in the reader's language. */
export function levelName(level: number, lang: string | null | undefined): string {
  return [tx(lang, "Unverified", "अपुष्ट"), tx(lang, "Employer confirmed", "नियोक्ता ने पुष्टि की"),
    tx(lang, "Payment proven", "भुगतान साबित"), tx(lang, "Established", "पक्का रिकॉर्ड")][level] ?? "";
}
