from flask import Flask, request, jsonify
import os
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

# DuckDuckGo keresés (első 3 link)
def duckduckgo_search(q):
    res = requests.post("https://html.duckduckgo.com/html/", data={"q": q})
    soup = BeautifulSoup(res.text, "html.parser")
    return [a['href'] for a in soup.select('.result__a')][:3]

# Weboldal szövegének kinyerése
def get_text(url):
    try:
        r = requests.get(url, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        return " ".join(p.text for p in soup.find_all("p")).strip()
    except:
        return ""

# AI összegzés OpenRouteren keresztül
def ai_summary(text):
    data = {
        "model": "mistralai/mixtral-8x7b-instruct",
        "messages": [{
            "role": "user",
            "content": f"Foglalj össze magyarul:\n\n{text[:4000]}"
        }]
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
    return res.json()["choices"][0]["message"]["content"]

# /search végpont
@app.route("/search")
def search():
    q = request.args.get("q", "")
    links = duckduckgo_search(q)
    results = []

    for link in links[:1]:  # csak az első linket dolgozzuk fel, hogy ne timeoutoljon
        text = get_text(link)
        if len(text) > 200:
            summary = ai_summary(text)
            results.append({"link": link, "összegzés": summary})

    return jsonify({"lekérdezés": q, "találatok": results})

# Alkalmazás indítása Render által megadott porton
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
