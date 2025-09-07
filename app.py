from flask import Flask, render_template, request, jsonify
from collections import Counter
import re
from main import AmazonSession
import nltk
from nltk.util import ngrams
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import json

app = Flask(__name__)

# NLTK resources may not be available at runtime; use safe fallbacks
try:
    stop_words = set(stopwords.words('english'))
except Exception:
    stop_words = {
        'the','and','a','an','of','in','on','for','to','with','by','from','at','as','is','are','was','were','be','been','this','that','these','those'
    }

def safe_tokenize(text: str):
    try:
        return word_tokenize(text)
    except Exception:
        return re.findall(r"[A-Za-z]+", text)

def extract_common_words_and_phrases(titles):
    # Process single words
    words = []
    for title in titles:
        tokens = [t.lower() for t in safe_tokenize(title)]
        words.extend([w for w in tokens if w.isalpha() and w not in stop_words])

    word_freq = Counter(words).most_common(10)

    # Process phrases (2-3 words)
    phrases = []
    for title in titles:
        tokens = [t.lower() for t in safe_tokenize(title)]
        # Generate 2-gram and 3-gram phrases without relying on external datasets
        two_grams = ['{} {}'.format(tokens[i], tokens[i+1]) for i in range(len(tokens)-1)] if len(tokens) >= 2 else []
        three_grams = ['{} {} {}'.format(tokens[i], tokens[i+1], tokens[i+2]) for i in range(len(tokens)-2)] if len(tokens) >= 3 else []
        phrases.extend(two_grams + three_grams)

    phrase_freq = Counter(phrases).most_common(10)

    return {
        'words': [{'word': word, 'count': count} for word, count in word_freq],
        'phrases': [{'phrase': phrase, 'count': count} for phrase, count in phrase_freq]
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        # Initialize scraper
        scraper = AmazonSession()
    except Exception as e:
        error_msg = 'Failed to initialize Amazon session' if 'session' in str(e) else 'Invalid request data'
        return jsonify({
            'error': f'{error_msg}: {str(e)}',
            'products': [],
            'analysis': {'words': [], 'phrases': []}
        }), 500
    
    # Extract search parameters
    primary_query = data.get('primaryQuery', '')
    secondary_query = data.get('secondaryQuery', '')
    boolean_operator = data.get('booleanOperator', 'AND')
    asins = data.get('asins', [])
    pages = data.get('pages', [1])
    max_items = int(data.get('maxItems', 50))
    must_include = data.get('mustInclude', '')
    must_exclude = data.get('mustExclude', '')
    match_type = data.get('matchType', 'any')  # 'any' or 'all'
    organic_only = data.get('organicOnly', True)
    
    all_products = []
    titles = []
    
    # Handle ASIN-based search
    if asins:
        for asin in asins:
            # Implement direct ASIN lookup
            pass
    
    # Handle keyword-based search
    elif primary_query:
        # Get primary search results
        primary_results = []
        
        for page in pages:
            if len(primary_results) >= max_items:
                break
                
            try:
                response = scraper.getRawSearchHTML(primary_query, page)
                if response:
                    remaining = max_items - len(primary_results)
                    # Pass the limit to extract_products to minimize processing
                    print(f"\nDEBUG: Fetching page {page} for primary query '{primary_query}'")
                    products = scraper.extract_products(response, limit=remaining)
                    print(f"DEBUG: Got {len(products)} products from extract_products")
                    
                    if organic_only:
                        print(f"DEBUG: Filtering sponsored products from {len(products)} items")
                        products = [p for p in products if not p.get('sponsored', False)]
                        print(f"DEBUG: {len(products)} products remain after filtering sponsored")
                        # Re-check limit after filtering
                        products = products[:remaining]
                        print(f"DEBUG: {len(products)} products after applying remaining limit {remaining}")
                    
                    for idx, product in enumerate(products):
                        product['primary_rank'] = (page - 1) * len(products) + idx + 1
                    
                    primary_results.extend(products)
                    print(f"DEBUG: Total primary results now: {len(primary_results)}")
                    
                    if len(primary_results) >= max_items:
                        primary_results = primary_results[:max_items]
                        print(f"DEBUG: Trimmed to max items: {len(primary_results)}")
                        break
            except Exception as e:
                print(f"Error fetching page {page}: {str(e)}")
                break
        
        # Get secondary search results if needed
        if secondary_query:
            secondary_results = []
            
            for page in pages:
                if len(secondary_results) >= max_items:
                    break
                    
                try:
                    response = scraper.getRawSearchHTML(secondary_query, page)
                    if response:
                        remaining = max_items - len(secondary_results)
                        # Pass the limit to extract_products to minimize processing
                        products = scraper.extract_products(response, limit=remaining)
                        
                        if organic_only:
                            products = [p for p in products if not p.get('sponsored', False)]
                            # Re-check limit after filtering
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
            
            # Combine results based on boolean operator
            if boolean_operator == 'AND':
                # Find products that appear in both searches by ASIN
                primary_asins = {p['asin']: p for p in primary_results}
                secondary_asins = {p['asin']: p for p in secondary_results}
                common_asins = set(primary_asins.keys()) & set(secondary_asins.keys())
                
                for asin in common_asins:
                    product = primary_asins[asin].copy()
                    product['secondary_rank'] = secondary_asins[asin]['secondary_rank']
                    all_products.append(product)
            else:  # OR
                # Combine all unique products
                seen_asins = set()
                for product in primary_results + secondary_results:
                    if product['asin'] not in seen_asins:
                        seen_asins.add(product['asin'])
                        all_products.append(product)
        else:
            all_products = primary_results
        
        print(f"\nDEBUG: Starting filtering process on {len(all_products)} products")
        # Apply filters
        filtered_products = []
        for idx, product in enumerate(all_products, 1):
            title = product['title'].lower()
            print(f"\nDEBUG: Processing product {idx}: {title[:50]}...")
            
            # Handle inclusion criteria
            if must_include:
                include_terms = [term.strip().lower() for term in must_include.split(',')]
                print(f"DEBUG: Checking inclusion terms: {include_terms}")
                if match_type == 'all':
                    if not all(term in title for term in include_terms):
                        print(f"DEBUG: Product {idx} failed ALL inclusion check")
                        continue
                else:  # 'any'
                    if not any(term in title for term in include_terms):
                        print(f"DEBUG: Product {idx} failed ANY inclusion check")
                        continue
                print(f"DEBUG: Product {idx} passed inclusion filters")
            
            # Handle exclusion criteria
            if must_exclude:
                exclude_terms = [term.strip().lower() for term in must_exclude.split(',')]
                print(f"DEBUG: Checking exclusion terms: {exclude_terms}")
                if any(term in title for term in exclude_terms):
                    print(f"DEBUG: Product {idx} matched exclusion term")
                    continue
                print(f"DEBUG: Product {idx} passed exclusion filters")
            
            filtered_products.append(product)
            titles.append(title)
            print(f"DEBUG: Added product {idx} to filtered results")
        
        print(f"\nDEBUG: Filtering complete. {len(filtered_products)} products remain")
        
        all_products = filtered_products[:max_items]
    
    try:
        # Extract common words and phrases
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5006)
