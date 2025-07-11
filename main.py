from flask import Flask, request, Response
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

app = Flask(__name__)

# ✅ Csak ezekből a domainekből engedünk tartalmat
MEGBIZHATO_DOMAINNEK = [
    "index.hu", "telex.hu", "444.hu", "bbc.com", "euronews.com",
    "hu.wikipedia.org", "en.wikipedia.org",
    "fandom.com", "gamepedia.com", "minecraft.wiki"
]

# 🔍 Keresés DuckDuckGo segítségével
def duckduckgo_search(q):
    res = requests.post("https://html.duckduckgo.com/html/", data={"q": q})
    soup = BeautifulSoup(res.text, "html.parser")
    return [a['href'] for a in soup.select('.result__a')]

# 🧽 Letisztított szöveg kiszedése egy oldalról
def extract_text(url):
    try:
        domain = urlparse(url).netloc.lower()
        if not any(d in domain for d in MEGBIZHATO_DOMAINNEK):
            return None  # ⛔ Szűrés: nem megbízható

        print("✅ Elfogadott domain:", domain)
        r = requests.get(url, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]
        clean_text = "\n".join(paragraphs)
        return f"Forrás: {url}\n\n{clean_text}\n"
    except Exception as e:
        print("❌ Hiba cikk letöltésekor:", e)
        return None

@app.route("/search")
def search():
    query = request.args.get("q", "")
    links = duckduckgo_search(query)
    texts = []

    for url in links:
        text = extract_text(url)
        if text:
            texts.append(text)
        if len(texts) >= 2:
            break  # max 2 megbízható forrás

    if not texts:
        return Response("Nem találtam megbízható információt.", mimetype="text/plain")

    full_text = "\n\n---\n\n".join(texts)
    return Response(full_text, mimetype="text/plain")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
