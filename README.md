# 🚀 Telegram File & Video Downloader Bot (Up to 2GB)

एक आधुनिक, हाई-स्पीड Telegram Downloader Bot जो **Terabox**, **Diskwala**, और किसी भी **Direct Video/File Link** को 2GB तक डाउनलोड और अपलोड कर सकता है।

> [!NOTE]
> **No Assistant ID Needed:** यह बॉट पूरी तरह से आपके सामान्य **Bot Token** पर काम करता है। किसी भी यूजर अकाउंट, फोन नंबर या स्ट्रिंग सेशन की ज़रूरत नहीं है!

---

## ✨ Features (मुख्य विशेषताएं)

- ⚡ **Pure Bot Mode:** केवल एक Bot Token से 2 GB तक की फाइलें डाउनलोड/अपलोड।
- 📢 **Force Subscribe:** यूज़र को फाइल भेजने से पहले आपके चैनल को जॉइन करवाता है (with Try Again verification).
- 🖼️ **Custom Thumbnail:** यूज़र अपना खुद का थंबनेल लगा सकते हैं (`/set_thumb`, `/view_thumb`, `/del_thumb`)।
- ✍️ **Custom Caption:** यूज़र अपना कस्टम कैप्शन सेट कर सकते हैं (`/set_caption`, `{filename}`, `{filesize}` tags)।
- 📊 **Real-time Progress Bar:** डाउनलोड और अपलोड की स्पीड, प्रतिशत, साइज़ और बचा हुआ समय (ETA) दिखाता है।
- 🗄️ **Persistent Database:** MongoDB Atlas (Free Cloud Database) + Local SQLite Fallback।
- 🛠️ **Admin Panel:**
  - `/stats`: बॉट का Uptime, Total Users, CPU और RAM उपयोग।
  - `/broadcast`: सभी रजिस्टर्ड यूज़र्स को एक क्लिक में मैसेज/फॉरवर्ड भेजना (लाइव प्रोग्रेस के साथ)।
- 🌐 **24/7 Free Hosting Ready:** Render और Koyeb के लिए इन-बिल्ट हेल्थ चेक वेब सर्वर।

---

## 📋 Commands (कमांड सूची)

### आम यूज़र्स के लिए:
| Command | विवरण |
| :--- | :--- |
| `/start` | बॉट शुरू करें और आकर्षक वेलकम मेनू देखें |
| `/help` | बॉट का उपयोग करने का तरीका |
| `/about` | बॉट की जानकारी |
| `/set_thumb` | फोटो के साथ रिप्लाई करके कस्टम थंबनेल सेट करें |
| `/view_thumb` | अपना वर्तमान थंबनेल देखें |
| `/del_thumb` | अपना कस्टम थंबनेल हटाएं |
| `/set_caption` | कस्टम कैप्शन सेट करें (e.g. `/set_caption File: {filename}`) |
| `/view_caption` | वर्तमान कैप्शन देखें |
| `/del_caption` | कस्टम कैप्शन हटाएं |

### केवल Admin के लिए:
| Command | विवरण |
| :--- | :--- |
| `/stats` | बॉट की स्थिति, कुल यूज़र्स और सर्वर लोड देखें |
| `/broadcast` | किसी भी मैसेज को रिप्लाई करें या टेक्स्ट लिखें सभी को भेजने के लिए |

---

## 🔑 आवश्यक Credentials कैसे प्राप्त करें?

1. **BOT_TOKEN:**
   - Telegram पर **[@BotFather](https://t.me/BotFather)** के पास जाएँ।
   - `/newbot` भेजें, नाम और यूज़रनेम चुनें।
   - आपको एक `BOT_TOKEN` मिलेगा।

2. **API_ID & API_HASH:**
   - [my.telegram.org](https://my.telegram.org) पर अपने Telegram नंबर से लॉगिन करें।
   - **API development tools** पर जाएँ और एक नया App बनाएँ।
   - आपको `API_ID` (नंबर) और `API_HASH` (स्ट्रिंग) मिल जाएगा।

3. **ADMIN_ID:**
   - Telegram पर **[@userinfobot](https://t.me/userinfobot)** को `/start` भेजें।
   - आपका न्यूमेरिकल ID दिखेगा (उदा: `123456789`)।

4. **FORCE_SUB_CHANNEL (Optional):**
   - अपने चैनल का यूज़रनेम (उदा: `MyChannelName`) या Channel ID (उदा: `-1001234567890`)।
   - बॉट को उस चैनल में **Admin** बना कर `Add Members` की परमिशन दें।

5. **MONGO_URI (Free Database):**
   - [mongodb.com](https://www.mongodb.com/) पर मुफ़्त अकाउंट बनाएँ।
   - Free **M0 Shared Cluster** बनाएँ और Connection String कॉपी करें (उदा: `mongodb+srv://user:pass@cluster0...`)।
   - _नोट: अगर आप इसे खाली छोड़ते हैं, तो बॉट अपने आप SQLite पर चलेगा।_

---

## 🌐 24/7 Free Hosting Setup (Render पर फ्री में कैसे चलाएँ)

Render.com पर बॉट 24/7 बिना किसी पैसे के आसानी से होस्ट हो जाता है:

### Step 1: GitHub पर कोड अपलोड करें
1. GitHub पर एक नया **Private / Public Repository** बनाएँ।
2. इस फोल्डर की सभी फाइलें उस रिपॉजिटरी में पुश कर दें।

### Step 2: Render.com पर Deploy करें
1. [Render.com](https://render.com) पर मुफ़्त अकाउंट बनाएँ।
2. **Dashboard** पर जाकर **"New +"** -> **"Web Service"** चुनें।
3. अपने GitHub Repository को कनेक्ट करें।
4. सेटिंग्स भरें:
   - **Name:** `my-telegram-downloader-bot`
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
   - **Plan:** `Free`
5. **Environment Variables** सेक्शन में नीचे दी गई वैल्यूज़ जोड़ें:
   - `BOT_TOKEN` = आपका बॉट टोकन
   - `API_ID` = आपका API ID
   - `API_HASH` = आपका API Hash
   - `ADMIN_ID` = आपका Telegram ID
   - `FORCE_SUB_CHANNEL` = आपके चैनल का नाम
   - `MONGO_URI` = आपका MongoDB URL
   - `PORT` = `8080`
6. **"Create Web Service"** पर क्लिक करें। 2-3 मिनट में आपका बॉट चालू हो जाएगा!

### Step 3: बॉट को हमेशा 24/7 चालू रखने के लिए (Keep Alive)
Render का फ्री टियर 15 मिनट इनएक्टिव रहने पर स्लीप में चला जाता है। इसे हमेशा जगाए रखने के लिए:
1. Render पर आपको जो URL मिला (उदा: `https://my-telegram-downloader-bot.onrender.com`), उसे कॉपी करें।
2. [cron-job.org](https://cron-job.org) या [UptimeRobot](https://uptimerobot.com) पर फ्री अकाउंट बनाएँ।
3. हर **10 मिनट** पर अपने उस URL पर एक HTTP GET रिक्वेस्ट पिंग सेट कर दें।
4. अब आपका बॉट **365 दिन 24/7** बिना रुके चलेगा!

---

## 💻 अपने कंप्यूटर पर लोकल टेस्ट कैसे करें

```bash
# 1. dependencies इनस्टॉल करें
pip install -r requirements.txt

# 2. .env.sample को कॉपी करके .env बनाएँ और अपनी वैल्यूज़ भरें
cp .env.sample .env

# 3. बॉट रन करें
python main.py
```
