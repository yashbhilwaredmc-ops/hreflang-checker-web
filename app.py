# app.py
from flask import Flask, render_template, request, jsonify, send_file
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import requests
import pandas as pd
import time
from threading import Thread
import queue
import os
import tempfile

app = Flask(__name__)

class WebHreflangChecker:
    def __init__(self):
        self.results = []
    
    def analyze_url(self, url, method="Auto"):
        try:
            if method == "Auto" or method == "HTTP":
                response = self.fetch_http(url)
            else:
                return {"error": "Browser automation not supported on server"}
            
            if not response:
                return {
                    "url": url,
                    "status": "Failed",
                    "title": "",
                    "language": "",
                    "indexable": "❌",
                    "method": "Failed",
                    "user_agent": "N/A",
                    "issues": "Failed to fetch URL",
                    "hreflangs": []
                }
            
            return self.process_response(url, response)
            
        except Exception as e:
            return {
                "url": url,
                "status": "Error",
                "title": "",
                "language": "",
                "indexable": "❌",
                "method": "Failed",
                "user_agent": "N/A",
                "issues": f"Error: {str(e)}",
                "hreflangs": []
            }
    
    def fetch_http(self, url):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
            
            response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            response.raise_for_status()
            
            return {
                "method": "HTTP",
                "url": response.url,
                "status": response.status_code,
                "html": response.text,
                "headers": dict(response.headers),
                "user_agent": headers["User-Agent"]
            }
            
        except Exception as e:
            print(f"HTTP request failed: {str(e)}")
            return None
    
    def process_response(self, url, response):
        html = response["html"]
        method = response["method"]
        
        soup = BeautifulSoup(html, 'html.parser')
        title = soup.title.string if soup.title else "No Title"
        lang = soup.html.get('lang', '-') if soup.html else '-'
        indexable = "✔️" if self.check_indexable(soup) else "❌"
        
        # Extract hreflang tags
        hreflang_tags = []
        issues = []
        
        for link in soup.find_all('link', rel='alternate'):
            hreflang = link.get('hreflang', '').lower()
            href = urljoin(url, link.get('href', ''))
            if hreflang and href:
                hreflang_tags.append({"hreflang": hreflang, "url": href})
                
                if not self.validate_hreflang(hreflang):
                    issues.append(f"Invalid hreflang: {hreflang}")
        
        return {
            "url": url,
            "status": f"{response.get('status', '200')} OK",
            "title": title[:100] + "..." if len(title) > 100 else title,
            "language": lang,
            "indexable": indexable,
            "method": method,
            "user_agent": response.get("user_agent", "N/A"),
            "issues": ", ".join(issues) if issues else "Valid",
            "hreflangs": hreflang_tags
        }
    
    def validate_hreflang(self, hreflang):
        if hreflang == 'x-default':
            return True
        # Simple validation - you can enhance this
        return len(hreflang) <= 10
    
    def check_indexable(self, soup):
        robots = soup.find('meta', attrs={'name': 'robots'})
        return not (robots and 'noindex' in robots.get('content', '').lower())

checker = WebHreflangChecker()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.json
    url = data.get('url', '').strip()
    method = data.get('method', 'Auto')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    result = checker.analyze_url(url, method)
    return jsonify(result)

@app.route('/analyze-bulk', methods=['POST'])
def analyze_bulk():
    urls = request.json.get('urls', [])
    method = request.json.get('method', 'Auto')
    
    if not urls:
        return jsonify({"error": "No URLs provided"}), 400
    
    results = []
    for url in urls:
        if url.strip():
            result = checker.analyze_url(url.strip(), method)
            results.append(result)
            time.sleep(1)  # Be nice to servers
    
    return jsonify({"results": results})

@app.route('/export-csv', methods=['POST'])
def export_csv():
    data = request.json.get('results', [])
    
    if not data:
        return jsonify({"error": "No data to export"}), 400
    
    # Create DataFrame
    df_data = []
    for result in data:
        row = {
            "URL": result["url"],
            "Status": result["status"],
            "Title": result["title"],
            "Language": result["language"],
            "Indexable": result["indexable"],
            "Method": result["method"],
            "User-Agent": result["user_agent"],
            "Issues": result["issues"]
        }
        
        # Add hreflangs
        for i, hreflang in enumerate(result["hreflangs"][:3], 1):
            row[f"hreflang {i}"] = hreflang["hreflang"]
            row[f"URL {i}"] = hreflang["url"]
        
        df_data.append(row)
    
    df = pd.DataFrame(df_data)
    
    # Save to temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
    df.to_csv(temp_file.name, index=False)
    temp_file.close()
    
    return send_file(temp_file.name, as_attachment=True, download_name='hreflang_report.csv')

if __name__ == '__main__':
    app.run(debug=True)
