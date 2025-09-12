from flask import Flask, render_template, request, jsonify
from collections import Counter
import re
from main import AmazonSession
import nltk
from nltk.util import ngrams
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import json
import os
import sys
import glob
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

app = Flask(__name__)

# Download required NLTK data
nltk.download('punkt')
nltk.download('stopwords')
stop_words = set(stopwords.words('english'))

# ---------- Helpers for Scheduler/Clients ----------
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / 'output'
HISTORY_FILE = OUTPUT_DIR / 'client_history.json'

DEFAULT_SCHEDULE = {
    "runs": 3,
    "times": [("8", "00", "AM"), ("12", "00", "PM"), ("4", "00", "PM")],
    "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
}

def sanitize_folder(name: str) -> str:
    return ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in name)

def get_client_dir(client: str) -> Path:
    return OUTPUT_DIR / sanitize_folder(client)

def load_client_history() -> dict:
    if not HISTORY_FILE.exists():
        return {}
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_client_history(history: dict) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2)

def load_schedule_config(client):
    if not client:
        return DEFAULT_SCHEDULE.copy()
    client_dir = get_client_dir(client)
    schedule_path = client_dir / 'schedule_config.json'
    if schedule_path.exists():
        try:
            with open(schedule_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception:
            pass
    return DEFAULT_SCHEDULE.copy()

def save_schedule_config(client: str, config: dict) -> None:
    client_dir = get_client_dir(client)
    client_dir.mkdir(parents=True, exist_ok=True)
    # Always store client in config
    cfg = dict(config)
    cfg['client'] = client
    with open(client_dir / 'schedule_config.json', 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)

def iter_all_schedule_entries():
    pattern = str(OUTPUT_DIR / '*' / 'schedule_config.json')
    for path in glob.glob(pattern):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            client = cfg.get('client', Path(path).parent.name)
            times = cfg.get('times', [])
            days = cfg.get('days', [])
            for day in days:
                for hour_str, minute_str, ampm in times:
                    try:
                        h12 = int(hour_str); m = int(minute_str)
                        h24 = h12
                        if ampm == 'PM' and h12 < 12:
                            h24 += 12
                        elif ampm == 'AM' and h12 == 12:
                            h24 = 0
                        yield { 'client': client, 'day': day, 'hour': h24, 'minute': m }
                    except Exception:
                        continue
        except Exception:
            continue

def get_all_scheduled_times(exclude_client):
    scheduled = set()
    for entry in iter_all_schedule_entries():
        if exclude_client and entry['client'] == exclude_client:
            continue
        # include 5-minute window around scheduled time
        for offset in range(-2, 3):
            mm = entry['minute'] + offset
            hh = entry['hour']
            if mm >= 60:
                mm -= 60; hh += 1
            elif mm < 0:
                mm += 60; hh -= 1
            if hh >= 24: hh = 0
            if hh < 0: hh = 23
            scheduled.add((entry['day'], hh, mm))
    return scheduled

def is_time_conflicted(hour24, minute, days, exclude_client):
    scheduled = get_all_scheduled_times(exclude_client)
    for day in days:
        if (day, hour24, minute) in scheduled:
            return True
    return False

def find_next_available_time(hour12, minute, ampm, days, exclude_client):
    h24 = hour12
    if ampm == 'PM' and hour12 < 12:
        h24 += 12
    elif ampm == 'AM' and hour12 == 12:
        h24 = 0
    ch, cm = h24, minute
    for _ in range(24 * 12):
        if not is_time_conflicted(ch, cm, days, exclude_client):
            if ch == 0:
                return 12, cm, 'AM'
            if ch < 12:
                return ch, cm, 'AM'
            if ch == 12:
                return 12, cm, 'PM'
            return ch - 12, cm, 'PM'
        cm += 5
        if cm >= 60:
            cm = 0; ch += 1
            if ch >= 24: ch = 0
    return hour12, minute, ampm

# ---------- Existing search/analysis logic ----------

def extract_common_words_and_phrases(titles):
    # Process single words
    words = []
    for title in titles:
        tokens = word_tokenize(title.lower())
        words.extend([word for word in tokens if word.isalpha() and word not in stop_words])
    word_freq = Counter(words).most_common(10)

    # Process phrases (2-3 words)
    phrases = []
    for title in titles:
        tokens = word_tokenize(title.lower())
        two_grams = list(ngrams(tokens, 2))
        three_grams = list(ngrams(tokens, 3))
        phrases.extend([' '.join(gram) for gram in two_grams + three_grams])
    phrase_freq = Counter(phrases).most_common(10)

    return {
        'words': [{'word': word, 'count': count} for word, count in word_freq],
        'phrases': [{'phrase': phrase, 'count': count} for phrase, count in phrase_freq]
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scheduler')
def scheduler_page():
    return render_template('scheduler.html')

@app.route('/nfl')
def nfl_dashboard():
    import os, glob
    brand = request.args.get('brand', default='Land_O_Frost')
    keywords = []
    try:
        base_dir = os.path.join('output', brand)
        if os.path.isdir(base_dir):
            files = sorted(glob.glob(os.path.join(base_dir, 'keywords_*.txt')))
            if files:
                latest = files[-1]
                with open(latest, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            keywords.append(line)
    except Exception as e:
        print(f"Keyword load error for brand {brand}: {e}")
    return render_template('nfl_dashboard.html', brand=brand, keywords=keywords)

@app.route('/search', methods=['POST'])
def search():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        scraper = AmazonSession()
    except Exception as e:
        error_msg = 'Failed to initialize Amazon session' if 'session' in str(e) else 'Invalid request data'
        return jsonify({
            'error': f'{error_msg}: {str(e)}',
            'products': [],
            'analysis': {'words': [], 'phrases': []}
        }), 500

    primary_query = data.get('primaryQuery', '')
    secondary_query = data.get('secondaryQuery', '')
    boolean_operator = data.get('booleanOperator', 'AND')
    asins = data.get('asins', [])
    pages = data.get('pages', [1])
    max_items = int(data.get('maxItems', 50))
    must_include = data.get('mustInclude', '')
    must_exclude = data.get('mustExclude', '')
    match_type = data.get('matchType', 'any')
    organic_only = data.get('organicOnly', True)

    all_products = []
    titles = []

    if asins:
        for asin in asins:
            pass
    elif primary_query:
        primary_results = []
        for page in pages:
            if len(primary_results) >= max_items:
                break
            try:
                response = scraper.getRawSearchHTML(primary_query, page)
                if response:
                    remaining = max_items - len(primary_results)
                    products = scraper.extract_products(response, limit=remaining)
                    if organic_only:
                        products = [p for p in products if not p.get('sponsored', False)]
                        products = products[:remaining]
                    for idx, product in enumerate(products):
                        product['primary_rank'] = (page - 1) * len(products) + idx + 1
                    primary_results.extend(products)
                    if len(primary_results) >= max_items:
                        primary_results = primary_results[:max_items]
                        break
            except Exception as e:
                print(f"Error fetching page {page}: {str(e)}")
                break
        if secondary_query:
            secondary_results = []
            for page in pages:
                if len(secondary_results) >= max_items:
                    break
                try:
                    response = scraper.getRawSearchHTML(secondary_query, page)
                    if response:
                        remaining = max_items - len(secondary_results)
                        products = scraper.extract_products(response, limit=remaining)
                        if organic_only:
                            products = [p for p in products if not p.get('sponsored', False)]
                            products = products[:remaining]
                        for idx, product in enumerate(products):
                            product['secondary_rank'] = (page - 1) * len(products) + idx + 1
                        secondary_results.extend(products)
                        if len(secondary_results) >= max_items:
                            secondary_results = secondary_results[:max_items]
                            break
                except Exception as e:
                    print(f"Error fetching page {page}: {str(e)}")
                    break
            if boolean_operator == 'AND':
                primary_asins = {p['asin']: p for p in primary_results}
                secondary_asins = {p['asin']: p for p in secondary_results}
                common_asins = set(primary_asins.keys()) & set(secondary_asins.keys())
                for asin in common_asins:
                    product = primary_asins[asin].copy()
                    product['secondary_rank'] = secondary_asins[asin]['secondary_rank']
                    all_products.append(product)
            else:
                seen_asins = set()
                for product in primary_results + secondary_results:
                    if product['asin'] not in seen_asins:
                        seen_asins.add(product['asin'])
                        all_products.append(product)
        else:
            all_products = primary_results

        filtered_products = []
        for idx, product in enumerate(all_products, 1):
            title = product['title'].lower()
            if must_include:
                include_terms = [term.strip().lower() for term in must_include.split(',')]
                if match_type == 'all':
                    if not all(term in title for term in include_terms):
                        continue
                else:
                    if not any(term in title for term in include_terms):
                        continue
            if must_exclude:
                exclude_terms = [term.strip().lower() for term in must_exclude.split(',')]
                if any(term in title for term in exclude_terms):
                    continue
            filtered_products.append(product)
            titles.append(title)
        all_products = filtered_products[:max_items]

    try:
        word_phrase_analysis = extract_common_words_and_phrases(titles)
        return jsonify({
            'products': all_products,
            'analysis': word_phrase_analysis,
            'status': 'success'
        })
    except Exception as e:
        return jsonify({
            'error': f'Error processing results: {str(e)}',
            'products': all_products if all_products else [],
            'analysis': {'words': [], 'phrases': []}
        }), 500

# ---------- Scheduler/Clients API ----------

@app.route('/api/clients')
def api_clients():
    history = load_client_history()
    return jsonify({ 'clients': sorted(list(history.keys())) })

@app.route('/api/client/<client>')
def api_client_data(client):
    history = load_client_history()
    keywords = history.get(client, [])
    schedule = load_schedule_config(client)
    return jsonify({ 'client': client, 'keywords': keywords, 'schedule': schedule })

@app.route('/api/client/<client>/keywords', methods=['POST'])
def api_save_keywords(client):
    data = request.get_json() or {}
    keywords = data.get('keywords', [])
    if not isinstance(keywords, list):
        return jsonify({ 'error': 'Invalid keywords' }), 400
    history = load_client_history()
    history[client] = keywords
    save_client_history(history)
    client_dir = get_client_dir(client)
    client_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    with open(client_dir / f'keywords_{ts}.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(keywords))
    return jsonify({ 'status': 'ok' })

@app.route('/api/client/<client>/schedule', methods=['POST'])
def api_save_schedule(client):
    data = request.get_json() or {}
    runs = int(data.get('runs', 1))
    times = data.get('times', [])
    days = data.get('days', [])
    cfg = { 'runs': runs, 'times': times, 'days': days, 'client': client }
    save_schedule_config(client, cfg)
    return jsonify({ 'status': 'ok' })

@app.route('/api/schedules/overview')
def api_schedules_overview():
    items = list(iter_all_schedule_entries())
    return jsonify({ 'items': items })

@app.route('/api/conflicts', methods=['POST'])
def api_conflicts():
    data = request.get_json() or {}
    client = data.get('client')
    times = data.get('times', [])
    days = data.get('days', [])
    results = []
    for t in times:
        try:
            h = int(str(t[0]))
            m = int(str(t[1]))
            a = str(t[2])
        except Exception:
            results.append({ 'conflict': False })
            continue
        h24 = h
        if a == 'PM' and h < 12:
            h24 += 12
        elif a == 'AM' and h == 12:
            h24 = 0
        conflict = is_time_conflicted(h24, m, days, client)
        suggestion = None
        if conflict:
            sh, sm, sa = find_next_available_time(h, m, a, days, client)
            if (sh, sm, sa) != (h, m, a):
                suggestion = { 'hour': sh, 'minute': sm, 'ampm': sa }
        results.append({ 'conflict': bool(conflict), 'suggestion': suggestion })
    return jsonify({ 'results': results })

# ---------- Run Now (one-off) ----------

def write_status(client, message, done=False, success=None):
    client_dir = get_client_dir(client)
    client_dir.mkdir(parents=True, exist_ok=True)
    status = { 'message': message, 'done': done }
    if success is not None:
        status['success'] = success
    with open(client_dir / 'scrape_status.json', 'w', encoding='utf-8') as f:
        json.dump(status, f)


def run_scrape_for_client(client: str):
    try:
        history = load_client_history()
        keywords = history.get(client, [])
        if not keywords:
            write_status(client, 'No keywords found for selected client', True)
            return
        client_dir = get_client_dir(client)
        success_count = 0
        write_status(client, f'Starting run for {client}...')
        for i, keyword in enumerate(keywords, 1):
            write_status(client, f'Scraping {i}/{len(keywords)}: {keyword}')
            cmd = [
                sys.executable if 'sys' in globals() else 'python3',
                str(PROJECT_ROOT / 'kroger_search_and_capture.py'),
                '--search', keyword,
                '--output-dir', str(client_dir)
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if res.returncode == 0:
                    success_count += 1
                else:
                    pass
            except Exception:
                pass
        write_status(client, 'Processing saved HTML files...')
        try:
            res = subprocess.run([
                sys.executable if 'sys' in globals() else 'python3',
                str(PROJECT_ROOT / 'process_saved_html.py'),
                '--input-dir', str(client_dir), '--output-dir', str(client_dir), '--all-files'
            ], capture_output=True, text=True, timeout=300)
        except Exception:
            pass
        write_status(client, f'Completed. {success_count}/{len(keywords)} successful', True, success_count)
    except Exception as e:
        write_status(client, f'Error: {e}', True)

@app.route('/api/scrape/<client>', methods=['POST'])
def api_scrape_now(client):
    thread = threading.Thread(target=run_scrape_for_client, args=(client,), daemon=True)
    thread.start()
    return jsonify({ 'status': 'started' }), 202

@app.route('/api/status/<client>')
def api_status(client):
    p = get_client_dir(client) / 'scrape_status.json'
    if not p.exists():
        return jsonify({ 'message': 'No status yet', 'done': False })
    try:
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception:
        return jsonify({ 'message': 'Unavailable', 'done': False })

if __name__ == '__main__':
    app.run(debug=True, port=5006)
