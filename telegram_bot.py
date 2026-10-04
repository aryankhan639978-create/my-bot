import requests
import time
import os
import re
import threading
import http.server
import socketserver
from bs4 import BeautifulSoup

BOT_TOKEN = "8688229218:AAHWXB03KtuMEsn1TRZowSWejAe8EEPS9PQ"
OMNIROUTE_URL = "https://photographers-union-single-steps.trycloudflare.com/v1/chat/completions"
OMNIROUTE_KEY = "sk-5f238e76072d7926-eb6545-bf561a7c"

MODELS = {
    "sonnet": "kr/claude-sonnet-4.5",
    "haiku": "kr/claude-haiku-4.5",
    "deepseek": "kr/deepseek-3.2",
    "glm": "kr/glm-5",
    "qwen": "kr/qwen3-coder-next",
    "minimax": "kr/minimax-m2.5",
    "gemini": "agy/gemini-3-flash",
    "opus": "agy/claude-opus-4.6-thinking",
    "auto": "auto",
    "fusion": "fusion",
    "chaos": "auto/chaos"
}

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "You are an expert full-stack developer and UI/UX designer. "
        "Always provide complete, working, error-free code. "
        "When the user asks for a website, ALWAYS generate the full code in these three blocks:\n"
        "```html\n(full HTML with no errors)\n```\n"
        "```css\n(full CSS with modern design)\n```\n"
        "```javascript\n(full JS with working features)\n```\n"
        "For Python: ```python\n(full code)\n```\n"
        "If the user shares a website URL or describes a design, analyze it and recreate a similar UI. "
        "If the user asks about modding, explain step-by-step with clear instructions. "
        "If the user asks any question, answer it directly and clearly. "
        "Always test your code mentally before sending. Never send incomplete or broken code. "
        "If the user writes in Hindi, reply in Hindi. "
        "NEVER just introduce yourself. ALWAYS answer the user's question with actual code or detailed explanation."
    )
}

current_model_key = "gemini"
chat_history = {}
stats = {"messages": 0, "start_time": time.time()}
last_message_time = {}
RATE_LIMIT_SECONDS = 3
PROJECT_DIR = os.path.expanduser("~/projects")
SERVER_PORT = 8090

bot_status = {"online": True, "last_reply_time": 0, "processing": False}
response_times = []

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 30, "offset": offset}
    return requests.get(url, params=params).json()

def send_message(chat_id, text, parse_mode=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    requests.post(url, json=payload)

def send_typing(chat_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendChatAction"
    requests.post(url, json={"chat_id": chat_id, "action": "typing"})

def get_avg_response_time():
    if not response_times:
        return 0
    return sum(response_times) / len(response_times)

def estimate_wait_time():
    avg = get_avg_response_time()
    if avg == 0:
        return "~5-10 सेकंड"
    if avg < 10:
        return f"~{int(avg)} सेकंड"
    elif avg < 60:
        return f"~{int(avg)} सेकंड"
    else:
        return f"~{int(avg/60)} मिनट"

def fetch_website(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 10)"}
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            return None
        soup = BeautifulSoup(response.text, "html.parser")
        css_content = ""
        for style in soup.find_all("style"):
            css_content += style.string + "\n" if style.string else ""
        js_content = ""
        for script in soup.find_all("script"):
            if script.string:
                js_content += script.string + "\n"
        css_links = [link.get("href") for link in soup.find_all("link", rel="stylesheet") if link.get("href")]
        js_links = [script.get("src") for script in soup.find_all("script") if script.get("src")]
        for tag in soup.find_all(["style", "script"]):
            tag.decompose()
        html_content = str(soup)
        return {
            "html": html_content,
            "css": css_content,
            "js": js_content,
            "css_links": css_links[:3],
            "js_links": js_links[:3]
        }
    except Exception as e:
        return {"error": str(e)}

def ask_omniroute(messages, model_name):
    headers = {"Authorization": f"Bearer {OMNIROUTE_KEY}", "Content-Type": "application/json"}
    data = {"model": model_name, "messages": [SYSTEM_PROMPT] + messages}
    try:
        response = requests.post(OMNIROUTE_URL, headers=headers, json=data, timeout=300)
        result = response.json()
        if "choices" in result:
            return result["choices"][0]["message"]["content"]
        return f"Error: {result}"
    except Exception as e:
        return f"Error: {str(e)}"

def save_project(reply):
    os.makedirs(PROJECT_DIR, exist_ok=True)
    saved = []
    preview_file = None
    blocks = re.findall(r"```(\w+)?\n(.*?)```", reply, re.DOTALL)
    for lang, code in blocks:
        lang = (lang or "").lower()
        code = code.strip()
        if lang == "html":
            with open(os.path.join(PROJECT_DIR, "index.html"), "w") as f:
                f.write(code)
            saved.append("index.html")
            preview_file = "index.html"
        elif lang == "css":
            with open(os.path.join(PROJECT_DIR, "style.css"), "w") as f:
                f.write(code)
            saved.append("style.css")
        elif lang in ["javascript", "js"]:
            with open(os.path.join(PROJECT_DIR, "script.js"), "w") as f:
                f.write(code)
            saved.append("script.js")
        elif lang == "python":
            with open(os.path.join(PROJECT_DIR, "main.py"), "w") as f:
                f.write(code)
            saved.append("main.py")
        elif lang == "java":
            with open(os.path.join(PROJECT_DIR, "Main.java"), "w") as f:
                f.write(code)
            saved.append("Main.java")
        elif lang in ["cpp", "c++"]:
            with open(os.path.join(PROJECT_DIR, "main.cpp"), "w") as f:
                f.write(code)
            saved.append("main.cpp")
    return saved, preview_file

def start_server():
    os.makedirs(PROJECT_DIR, exist_ok=True)
    os.chdir(PROJECT_DIR)
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", SERVER_PORT), handler) as httpd:
        httpd.serve_forever()

def is_rate_limited(chat_id):
    now = time.time()
    if chat_id in last_message_time:
        if now - last_message_time[chat_id] < RATE_LIMIT_SECONDS:
            return True
    last_message_time[chat_id] = now
    return False

def main():
    global current_model_key
    print("Bot started...")
    os.makedirs(PROJECT_DIR, exist_ok=True)
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    print(f"Server started at http://localhost:{SERVER_PORT}")
    offset = None
    while True:
        try:
            updates = get_updates(offset)
            for update in updates.get("result", []):
                offset = update["update_id"] + 1
                if "message" not in update:
                    continue
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                if "text" not in msg:
                    continue
                user_text = msg["text"].strip()
                stats["messages"] += 1
                bot_status["online"] = True

                # ===== कमांड्स =====

                if user_text == "/status":
                    avg = get_avg_response_time()
                    status_text = (
                        f"🟢 बॉट ऑनलाइन है\n\n"
                        f"📊 स्थिति:\n"
                        f"• ऑनलाइन: ✅ हाँ\n"
                        f"• औसत रिप्लाई टाइम: {int(avg)} सेकंड\n"
                        f"• अनुमानित प्रतीक्षा: {estimate_wait_time()}\n"
                        f"• कुल मैसेज: {stats['messages']}\n"
                        f"• वर्तमान मॉडल: {current_model_key}"
                    )
                    send_message(chat_id, status_text)
                    continue

                if user_text == "/ping":
                    send_message(chat_id, "🏓 Pong! बॉट ऑनलाइन है।")
                    continue

                if user_text == "/start":
                    welcome = (
                        "🤖 नमस्ते! मैं आपका AI कोडिंग असिस्टेंट हूँ।\n\n"
                        "मैं कर सकता हूँ:\n"
                        "• वेबसाइट/ऐप बनाना\n"
                        "• किसी भी वेबसाइट का UI कॉपी करना\n"
                        "• मॉडिंग में मदद करना\n"
                        "• किसी भी सवाल का जवाब देना\n\n"
                        "📌 कमांड्स:\n"
                        "/status - बॉट ऑनलाइन है? रिप्लाई टाइम?\n"
                        "/ping - बॉट चालू है?\n"
                        "/model - मॉडल बदलें\n"
                        "/fusion - सभी AI मिलकर काम करें\n"
                        "/chaos - कई AI एक साथ\n"
                        "/website - वेबसाइट लिंक\n"
                        "/files - बनी फाइलें\n"
                        "/clear - चैट साफ\n"
                        "/stats - आँकड़े"
                    )
                    send_message(chat_id, welcome)
                    continue

                if user_text == "/help":
                    help_text = (
                        "📖 मदद\n\n"
                        "• सीधे सवाल पूछें\n"
                        "• कोड माँगें: 'मुझे कैलकुलेटर बनाओ'\n"
                        "• फाइल में कोड: '... फाइल में भेजो'\n"
                        "• मॉडल बदलें: /model sonnet\n"
                        "• सभी AI: /fusion\n"
                        "• चैट साफ: /clear"
                    )
                    send_message(chat_id, help_text)
                    continue

                if user_text == "/fusion":
                    current_model_key = "fusion"
                    send_message(chat_id, "🔥 Fusion मोड चालू! अब सारे AI मिलकर काम करेंगे।\n\n⚠️ ध्यान दें: इस मोड में रिप्लाई में थोड़ा समय लगेगा, लेकिन क्वालिटी सबसे अच्छी मिलेगी।")
                    continue

                if user_text == "/chaos":
                    current_model_key = "chaos"
                    send_message(chat_id, "⚡ Chaos मोड चालू! कई AI एक साथ काम करेंगे।\n\n⚠️ ध्यान दें: इस मोड में रिप्लाई में थोड़ा समय लगेगा।")
                    continue

                if user_text == "/website":
                    send_message(chat_id, f"🌐 आपका प्रोजेक्ट:\n\nhttp://localhost:{SERVER_PORT}/index.html")
                    continue

                if user_text == "/files":
                    files = os.listdir(PROJECT_DIR) if os.path.exists(PROJECT_DIR) else []
                    if files:
                        send_message(chat_id, "📁 फाइलें:\n\n" + "\n".join([f"• {f}" for f in files]))
                    else:
                        send_message(chat_id, "अभी कोई फाइल नहीं बनी।")
                    continue

                if user_text == "/stats":
                    uptime = int(time.time() - stats["start_time"])
                    hours = uptime // 3600
                    minutes = (uptime % 3600) // 60
                    avg = get_avg_response_time()
                    stats_text = (
                        f"📊 आँकड़े\n\n"
                        f"• कुल मैसेज: {stats['messages']}\n"
                        f"• चालू समय: {hours}घं {minutes}मि\n"
                        f"• मॉडल: {current_model_key}\n"
                        f"• औसत रिप्लाई: {int(avg)} सेकंड"
                    )
                    send_message(chat_id, stats_text)
                    continue

                if user_text == "/clear":
                    chat_history[chat_id] = []
                    send_message(chat_id, "✅ चैट साफ हो गई।")
                    continue

                if user_text.startswith("/model"):
                    parts = user_text.split()
                    if len(parts) == 1:
                        model_list = "\n".join([f"• /model {k}" for k in MODELS.keys()])
                        send_message(chat_id, f"वर्तमान मॉडल: {current_model_key}\n\n{model_list}\n\n💡 सुझाव: /fusion या /chaos भी भेज सकते हैं।")
                    elif len(parts) == 2:
                        new_key = parts[1].lower()
                        if new_key in MODELS:
                            current_model_key = new_key
                            send_message(chat_id, f"✅ मॉडल बदला: {MODELS[current_model_key]}")
                        else:
                            send_message(chat_id, f"❌ '{new_key}' नहीं मिला।")
                    continue

                # अगर कोई अज्ञात कमांड है
                if user_text.startswith("/"):
                    send_message(chat_id, f"❓ '{user_text}' कमांड नहीं मिला। /help भेजें।")
                    continue

                # ===== सामान्य मैसेज =====

                start_time = time.time()
                wait_time = estimate_wait_time()
                send_message(chat_id, f"⏳ {wait_time} में रिप्लाई मिलेगा...")
                send_typing(chat_id)

                # वेबसाइट स्क्रैपिंग
                url_match = re.search(r"https?://[^\s]+", user_text)
                if url_match:
                    url = url_match.group(0)
                    send_message(chat_id, f"🔍 {url} को स्कैन कर रहा हूँ...")
                    site_data = fetch_website(url)
                    if site_data and "error" not in site_data:
                        scraped_info = (
                            f"Website URL: {url}\n\n"
                            f"HTML (cleaned):\n{site_data['html'][:3000]}\n\n"
                            f"Inline CSS:\n{site_data['css'][:2000]}\n\n"
                            f"External CSS links: {site_data['css_links']}\n"
                            f"External JS links: {site_data['js_links']}\n\n"
                            f"User request: {user_text}\n\n"
                            f"Please recreate a similar UI in HTML/CSS/JS based on this design."
                        )
                        user_text = scraped_info
                    else:
                        send_message(chat_id, f"⚠️ वेबसाइट नहीं खुल पाई। फिर भी कोशिश कर रहा हूँ...")

                if chat_id not in chat_history:
                    chat_history[chat_id] = []
                chat_history[chat_id].append({"role": "user", "content": user_text})
                recent_history = chat_history[chat_id][-10:]
                reply = ask_omniroute(recent_history, MODELS[current_model_key])
                chat_history[chat_id].append({"role": "assistant", "content": reply})

                elapsed = time.time() - start_time
                response_times.append(elapsed)
                if len(response_times) > 10:
                    response_times.pop(0)
                bot_status["last_reply_time"] = elapsed

                saved, preview = save_project(reply)
                if saved:
                    msg_text = f"✅ प्रोजेक्ट बन गया!\n\n📁 फाइलें: {', '.join(saved)}"
                    if preview:
                        msg_text += f"\n\n🌐 यहाँ देखें:\nhttp://localhost:{SERVER_PORT}/{preview}"
                    elif "main.py" in saved:
                        msg_text += f"\n\n💡 चलाने के लिए: python ~/projects/main.py"
                    send_message(chat_id, msg_text)
                else:
                    if len(reply) > 4000:
                        for i in range(0, len(reply), 4000):
                            send_message(chat_id, reply[i:i+4000])
                    else:
                        send_message(chat_id, reply)

                send_message(chat_id, f"⏱️ रिप्लाई टाइम: {int(elapsed)} सेकंड")

        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Bot stopped.")
    except Exception as e:
        print(f"Fatal error: {e}")
        time.sleep(10)
