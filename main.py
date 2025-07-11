from flask import Flask, request, jsonify
import os
import requests
from bs4 import BeautifulSoup
import urllib.parse
import re
import concurrent.futures
from datetime import datetime

app = Flask(__name__)
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# Prioritized domains for Hungarian news and authoritative sources
PRIORITY_DOMAINS = [
    'telex.hu', '444.hu', '24.hu', 'origo.hu', 'hvg.hu', 'index.hu',
    'bbc.com', 'theguardian.com', 'wikipedia.org', 'napi.hu', 'portfolio.hu'
]

def fix_duckduckgo_url(url):
    if url.startswith('//duckduckgo.com/l/?uddg='):
        decoded = urllib.parse.unquote(url.split('uddg=')[1])
        return decoded.split('&')[0]
    return url

def is_priority_source(url):
    domain = urllib.parse.urlparse(url).netloc
    return any(priority in domain for priority in PRIORITY_DOMAINS)

def duckduckgo_search(q):
    headers = {
        'User-Agent': USER_AGENT,
        'Accept-Language': 'hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    
    try:
        res = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": q},
            headers=headers,
            timeout=5
        )
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, "html.parser")
        results = []
        priority_results = []
        
        for result in soup.select('.result'):
            link = result.select_one('.result__a')
            if link and link.has_attr('href'):
                url = fix_duckduckgo_url(link['href'])
                title = link.get_text(strip=True)
                
                # Skip unwanted domains
                if any(domain in url for domain in ['facebook.com', 'twitter.com', 'youtube.com']):
                    continue
                
                result_data = {
                    'url': url,
                    'title': title,
                    'priority': is_priority_source(url)
                }
                
                if result_data['priority']:
                    priority_results.append(result_data)
                else:
                    results.append(result_data)
                
                if len(priority_results) + len(results) >= 10:  # Get more results initially
                    break
        
        # Combine with priority results first
        return priority_results + results[:10 - len(priority_results)]
    
    except Exception as e:
        print(f"Search error: {str(e)}")
        return []

def extract_main_content(url):
    try:
        headers = {
            'User-Agent': USER_AGENT,
            'Accept-Language': 'hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7'
        }
        
        response = requests.get(url, headers=headers, timeout=8)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(['script', 'style', 'nav', 'footer', 'iframe', 'noscript', 'form']):
            element.decompose()
        
        # Try to find the main content area with Hungarian-specific patterns
        main_content = (soup.find('main') or 
                       soup.find('article') or 
                       soup.find('div', class_=re.compile('content|main|post|cikk|szoveg', re.I)))
        
        if main_content:
            text = ' '.join(p.get_text(strip=True) for p in main_content.find_all(['p', 'h1', 'h2', 'h3']))
        else:
            text = ' '.join(p.get_text(strip=True) for p in soup.find_all('p'))
        
        # Clean up the text
        text = re.sub(r'\s+', ' ', text).strip()
        return text if len(text) > 150 else ""
    
    except Exception as e:
        print(f"Content error for {url}: {str(e)}")
        return ""

def ai_summary(text, query):
    try:
        prompt = f"""Készíts egy RÖVID, PONTOS összefoglalót magyar nyelven maximum 3 mondatban!
A téma: {query}
Fontos: Csak a legfontosabb információkat add meg, tényekre koncentrálj!

Szöveg:
{text[:5000]}"""
        
        data = {
            "model": "deepseek/deepseek-chat-v3-0324:free",
            "messages": [{
                "role": "user",
                "content": prompt
            }],
            "temperature": 0.2,
            "max_tokens": 150
        }
        
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=15
        )
        res.raise_for_status()
        
        return res.json()["choices"][0]["message"]["content"]
    
    except Exception as e:
        print(f"AI error: {str(e)}")
        return None

@app.route("/search")
def search():
    start_time = datetime.now()
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Üres keresési kifejezés"}), 400
    
    try:
        # Get search results (fast)
        search_results = duckduckgo_search(q)
        if not search_results:
            return jsonify({"lekérdezés": q, "találatok": []})
        
        # Process top results in parallel for speed
        processed_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_url = {
                executor.submit(
                    process_result,
                    result,
                    q
                ): result for result in search_results[:3]  # Only process top 3 for speed
            }
            
            for future in concurrent.futures.as_completed(future_to_url):
                result = future_to_url[future]
                try:
                    processed_result = future.result()
                    if processed_result:
                        processed_results.append(processed_result)
                except Exception as e:
                    print(f"Error processing {result['url']}: {str(e)}")
        
        # Sort by priority sources first
        processed_results.sort(key=lambda x: not x.get('priority', False))
        
        response = {
            "lekérdezés": q,
            "találatok": processed_results[:2],  # Return max 2 best results
            "response_time_ms": (datetime.now() - start_time).total_seconds() * 1000
        }
        
        return jsonify(response)
    
    except Exception as e:
        print(f"Endpoint error: {str(e)}")
        return jsonify({
            "error": "Hiba történt a keresés során",
            "details": str(e)
        }), 500

def process_result(result, query):
    url = result['url']
    content = extract_main_content(url)
    if not content:
        return None
    
    summary = ai_summary(content, query)
    if not summary:
        return None
    
    return {
        "link": url,
        "összegzés": summary,
        "forrás": result['title'],
        "priority": result['priority']
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)
