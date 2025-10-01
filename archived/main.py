import requests
import bs4
from bs4 import BeautifulSoup
import time
import csv
import urllib.parse
import re
from random import uniform
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
 
# Configuration
MAX_RETRIES = 5  # Increased retries
BASE_DELAY = 3.0  # Increased base delay
MAX_DELAY = 10.0  # Increased max delay
OUTPUT_DIR = Path('output')

# List of user agents to rotate through
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
]

__QUERY__ = 'oregano oil'

# For debugging, limit to first 3 products
DEBUG_LIMIT = 3
 
 
class SessionData:
    def __init__(self, headers=None, max_retries=3):
        if headers is None:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"}
        
        self.cookies = {}
        for attempt in range(max_retries):
            try:
                # Add delay between retries
                if attempt > 0:
                    time.sleep(uniform(BASE_DELAY * (2 ** attempt), MAX_DELAY))
                
                # Try different URLs if the first one fails
                urls = [
                    "https://www.amazon.com",
                    "https://amazon.com/home",
                    "https://www.amazon.com/home"
                ]
                
                for url in urls:
                    try:
                        initial = requests.get(url=url, headers=headers, timeout=10)
                        initial.raise_for_status()
                        
                        cookies_dict = initial.cookies.get_dict()
                        if all(k in cookies_dict for k in ['session-id', 'session-id-time', 'i18n-prefs']):
                            self.cookies = {
                                'session-id': cookies_dict['session-id'],
                                'session-id-time': cookies_dict['session-id-time'],
                                'i18n-prefs': cookies_dict['i18n-prefs']
                            }
                            print(f"Successfully initialized session using {url}")
                            return
                    except requests.RequestException as e:
                        print(f"Failed to initialize with {url}: {e}")
                        continue
                
                print(f"Attempt {attempt + 1}/{max_retries} failed to get required cookies")
            except Exception as e:
                if attempt == max_retries - 1:
                    raise ValueError(f"Failed to initialize session after {max_retries} attempts: {e}")
                print(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
        
        raise ValueError("Could not obtain required cookies from any URL")
    
    def get_cookies(self):
        return self.cookies
 
 
class AmazonSession:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"}
        self.session = requests.Session()
        session_data = SessionData()
        # Update session cookies
        self.session.cookies.update(session_data.get_cookies())
        OUTPUT_DIR.mkdir(exist_ok=True)

    def _extract_price(self, product: bs4.element.Tag) -> Optional[str]:
        price_whole = product.find('span', class_='a-price-whole')
        price_fraction = product.find('span', class_='a-price-fraction')
        if price_whole and price_fraction:
            return f"{price_whole.text.strip()}{price_fraction.text.strip()}"
        return None

    def extract_products(self, response, limit=None) -> List[Dict[str, Any]]:
        """Extract all products from a search response."""
        if not response:
            print("DEBUG: No response provided to extract_products")
            return []
            
        soup = bs4.BeautifulSoup(response.text, 'html.parser')
        product_containers = soup.find_all('div', attrs={'data-component-type': 's-search-result'})
        
        print(f"DEBUG: Found {len(product_containers)} product containers")
        
        if not product_containers:
            print("DEBUG: No product containers found in the HTML")
            return []
        
        products = []
        for idx, product in enumerate(product_containers, 1):
            print(f"\nDEBUG: Processing product {idx}/{len(product_containers)}")
            
            # Check if product is sponsored
            sponsored_element = product.find('span', {'class': ['puis-sponsored-label-text', 'a-color-secondary']})
            if sponsored_element and 'sponsor' in sponsored_element.text.lower():
                print(f"DEBUG: Skipping sponsored product {idx}")
                continue
                
            product_data = self._extract_product_data(product)
            
            if product_data['title'] and product_data['product_url']:
                products.append(product_data)
                print(f"DEBUG: Added product {len(products)}: {product_data['title'][:50]}...")
                
                # Only break if we have enough non-sponsored products
                if limit and len(products) >= limit:
                    print(f"DEBUG: Reached limit of {limit} non-sponsored products, stopping")
                    break
            else:
                print(f"DEBUG: Skipped product {idx} - missing title or URL")
                
        print(f"\nDEBUG: Extracted {len(products)} valid non-sponsored products out of {len(product_containers)} containers")
        return products

    def _extract_product_data(self, product: bs4.element.Tag) -> Dict[str, Any]:
        data = {
            'title': '',
            'price': '',
            'rating': '',
            'reviews_count': '',
            'image_url': '',
            'product_url': '',
            'sponsored': False,
            'asin': '',
            'brand': '',
            'search_page': '',  # Will be set by the caller
            'search_result': 0,  # Will be set based on index
            'unit_size': '',
            'form': '',
            'rank_1': '',
            'category_1': '',
            'rank_2': '',
            'category_2': ''
        }

        # Extract ASIN from the data-asin attribute
        asin = product.get('data-asin')
        if asin:
            data['asin'] = asin
            print(f"DEBUG: Found ASIN: {asin}")
        else:
            print("DEBUG: No ASIN found")
        
        # First find the product title container
        title_container = product.find('div', {'class': 's-title-instructions-style'})
        if not title_container:
            print("DEBUG: No title container found")
            return data
            
        # Then find the h2 that contains the title
        h2_elem = title_container.find('h2')
        if not h2_elem:
            print("DEBUG: No h2 element found in title container")
            return data
            
        # Finally get the actual title text from the span inside the h2
        title_elem = h2_elem.find('span')
        
        if title_elem:
            data['title'] = title_elem.text.strip()
            print(f"DEBUG: Found title: {data['title']}")
        else:
            print("DEBUG: No title span found in h2")
        
        # Price
        price_whole = product.find('span', class_='a-price-whole')
        price_fraction = product.find('span', class_='a-price-fraction')
        if price_whole and price_fraction:
            data['price'] = f"{price_whole.text.strip()}{price_fraction.text.strip()}"
            print(f"DEBUG: Found price: {data['price']}")
        else:
            print("DEBUG: No price found")
        
        # Rating and reviews count
        try:
            # First try to find reviews count from the aria-label
            reviews_link = product.find('a', {'class': 'a-link-normal', 'aria-label': lambda x: x and 'ratings' in x})
            if reviews_link:
                reviews_text = reviews_link.find('span', {'aria-hidden': 'true'})
                if reviews_text:
                    data['reviews_count'] = reviews_text.text.strip().replace(',', '')
                    print(f"DEBUG: Found reviews count: {data['reviews_count']}")
            
            # Then try to find rating
            rating_elem = product.find('span', {'class': 'a-icon-alt'})
            if rating_elem:
                rating_text = rating_elem.text
                if 'out of 5' in rating_text:
                    data['rating'] = rating_text.split(' ')[0]
                    print(f"DEBUG: Found rating: {data['rating']}")
        except Exception as e:
            print(f"DEBUG: Error extracting rating/reviews: {str(e)}")
        
        # Image URL
        img_elem = product.find('img', attrs={'class': 's-image'})
        if img_elem:
            data['image_url'] = img_elem.get('src', '')
            print("DEBUG: Found image URL")
        
        # Product URL - try multiple possible link selectors
        link_elem = None
        link_selectors = [
            {'class': 'a-link-normal s-no-outline'},
            {'class': 'a-link-normal s-underline-text s-underline-link-text s-link-style'},
            {'class': 'a-link-normal'}
        ]
        
        for selector in link_selectors:
            link_elem = product.find('a', attrs={'class': selector['class']})
            if link_elem and link_elem.get('href'):
                data['product_url'] = f"https://amazon.com{link_elem.get('href')}"
                print(f"DEBUG: Found URL using selector: {selector}")
                break
        
        # Extract manufacturer/brand from data-cel-widget
        cel_widget = product.get('data-cel-widget', '')
        if cel_widget:
            data['search_result'] = cel_widget
            # Extract search page number from the widget ID
            if 'search_result_' in cel_widget:
                try:
                    data['search_page'] = str(int(cel_widget.split('_')[2]) // 16 + 1)
                    print(f"DEBUG: Found search page: {data['search_page']}")
                except (IndexError, ValueError):
                    print("DEBUG: Could not extract search page number")

        # Get the product URL to fetch additional details
        if data['product_url']:
            try:
                # Add delay between product page requests
                time.sleep(uniform(1, 2))
                product_page = self.session.get(data['product_url'], headers=self.headers)
                if product_page.status_code == 200:
                    product_soup = BeautifulSoup(product_page.text, 'html.parser')
                    
                    # Extract brand
                    try:
                        brand_elem = product_soup.find('span', {'class': 'a-size-base po-break-word'})
                        if brand_elem:
                            data['brand'] = brand_elem.text.strip()
                            print(f"DEBUG: Found brand from product page: {data['brand']}")
                    except Exception as e:
                        print(f"DEBUG: Error extracting brand: {str(e)}")
                    
                    # Extract unit size and form
                    try:
                        title = data['title'].lower()
                        # Common unit patterns
                        unit_patterns = [
                            r'(\d+(?:\.\d+)?\s*(?:fl\.?\s*)?(?:oz|ounce|count|ct|capsule|ml|tablet|softgel)s?)',
                            r'\((\d+(?:\.\d+)?\s*(?:fl\.?\s*)?(?:oz|ounce|count|ct|capsule|ml|tablet|softgel)s?)\)'
                        ]
                        for pattern in unit_patterns:
                            match = re.search(pattern, title, re.IGNORECASE)
                            if match:
                                data['unit_size'] = match.group(1)
                                print(f"DEBUG: Found unit size: {data['unit_size']}")
                                break
                        
                        # Extract form
                        form_keywords = ['liquid', 'capsule', 'softgel', 'tablet', 'oil', 'extract', 'tincture']
                        for form in form_keywords:
                            if form in title:
                                data['form'] = form
                                print(f"DEBUG: Found form: {data['form']}")
                                break
                    except Exception as e:
                        print(f"DEBUG: Error extracting unit size and form: {str(e)}")
                    
                    # Extract best sellers ranks using multiple strategies
                    try:
                        ranks_found = []
                        
                        # Strategy 1: Look for standard rank format in list items
                        rank_items = product_soup.find_all(['span', 'li', 'td'], {'class': ['a-list-item', 'zg-bdg-text', 'a-text-normal']})
                        for item in rank_items:
                            text = item.get_text(strip=True)
                            if '#' in text and ' in ' in text:
                                try:
                                    # Use regex to reliably extract rank number and category
                                    rank_match = re.search(r'#([\d,]+)\s+in\s+([^#\n]+?)(?=\s*(?:#|$|\())', text)
                                    if rank_match:
                                        rank_num = rank_match.group(1).replace(',', '')
                                        category = rank_match.group(2).strip()
                                        # Validate rank number is numeric
                                        if rank_num.isdigit():
                                            ranks_found.append((rank_num, category))
                                            print(f"DEBUG: Found rank from list item: #{rank_num} in {category}")
                                except Exception as e:
                                    print(f"DEBUG: Could not parse rank from text '{text}': {e}")
                                    continue
                        
                        # Strategy 2: Look for ranks in the sales rank section
                        sales_rank = product_soup.find('div', {'id': 'SalesRank'})
                        if sales_rank:
                            text = sales_rank.get_text(strip=True)
                            rank_matches = re.finditer(r'#([\d,]+)\s+in\s+([^#\n]+?)(?=\s*(?:#|$|\())', text)
                            for match in rank_matches:
                                try:
                                    rank_num = match.group(1).replace(',', '')
                                    category = match.group(2).strip()
                                    if rank_num.isdigit():
                                        ranks_found.append((rank_num, category))
                                        print(f"DEBUG: Found rank from sales rank section: #{rank_num} in {category}")
                                except Exception as e:
                                    print(f"DEBUG: Could not parse rank from sales rank text: {e}")
                                    continue
                        
                        # Strategy 3: Look for ranks in product details table
                        details_table = product_soup.find('table', {'id': 'productDetails_detailBullets_sections1'})
                        if details_table:
                            rows = details_table.find_all('tr')
                            for row in rows:
                                if 'Best Sellers Rank' in row.get_text():
                                    text = row.get_text(strip=True)
                                    rank_matches = re.finditer(r'#([\d,]+)\s+in\s+([^#\n]+?)(?=\s*(?:#|$|\())', text)
                                    for match in rank_matches:
                                        try:
                                            rank_num = match.group(1).replace(',', '')
                                            category = match.group(2).strip()
                                            if rank_num.isdigit():
                                                ranks_found.append((rank_num, category))
                                                print(f"DEBUG: Found rank from details table: #{rank_num} in {category}")
                                        except Exception as e:
                                            print(f"DEBUG: Could not parse rank from details row: {e}")
                                            continue
                        
                        # Remove duplicates while preserving order
                        seen = set()
                        ranks_found = [(r, c) for r, c in ranks_found if not (r in seen or seen.add(r))]
                        
                        # Sort ranks by number and assign to rank fields
                        if ranks_found:
                            ranks_found.sort(key=lambda x: int(x[0]))
                            for i, (rank, category) in enumerate(ranks_found[:2], 1):
                                data[f'rank_{i}'] = rank
                                data[f'category_{i}'] = category
                                print(f"DEBUG: Assigned rank {i}: #{rank} in {category}")
                        else:
                            print("DEBUG: No valid ranks found")
                    except Exception as e:
                        print(f"DEBUG: Error in rank extraction: {str(e)}")

                    
                    # Extract Ships from and Sold by information
                    try:
                        # Try multiple selectors for merchant info
                        merchant_info = None
                        selectors = [
                            {'id': 'merchant-info'},
                            {'id': 'tabular-buybox'},
                            {'id': 'buybox'},
                            {'id': 'apex_desktop'},
                            {'id': 'fresh-merchant-info'}
                        ]
                        
                        for selector in selectors:
                            element = product_soup.find('div', selector)
                            if element:
                                info_text = element.get_text(separator=' ', strip=True)
                                if 'Ships from' in info_text or 'Sold by' in info_text:
                                    merchant_info = element
                                    break
                        
                        if merchant_info:
                            info_text = merchant_info.get_text(separator=' ', strip=True)
                            
                            # Extract Ships from
                            ships_from_patterns = [
                                r'Ships from:\s*([^.]+?)(?=\s*Sold by:|$)',
                                r'Ships from\s*([^.]+?)(?=\s*Sold by:|$)',
                                r'Shipped from:\s*([^.]+?)(?=\s*Sold by:|$)',
                                r'Ships from\s*Amazon\.com\s*Sold by\s*([^.]+?)(?=\s*Ships from:|$)',
                                r'Ships from\s*([^.]+?)(?=\s*$)',
                                r'Fresh\s*([^.]+?)(?=\s*Sold by:|$)',  # Fresh-specific pattern
                                r'Amazon Fresh\s*([^.]+?)(?=\s*Sold by:|$)'  # Amazon Fresh pattern
                            ]
                            
                            for pattern in ships_from_patterns:
                                ships_from_match = re.search(pattern, info_text)
                                if ships_from_match:
                                    ships_from = ships_from_match.group(1).strip()
                                    # Remove any remaining prefix
                                    ships_from = re.sub(r'^(Ships from:|Ships from|Shipped from:)\s*', '', ships_from)
                                    data['ships_from'] = ships_from.strip()
                                    print(f"DEBUG: Found ships from: {data['ships_from']}")
                                    break
                            
                            # Extract Sold by
                            sold_by_patterns = [
                                r'Sold by:\s*([^.]+?)(?=\s*Ships from:|$)',
                                r'Sold by\s*([^.]+?)(?=\s*Ships from:|$)',
                                r'Seller:\s*([^.]+?)(?=\s*Ships from:|$)',
                                r'Sold by\s*([^.]+?)(?=\s*$)',
                                r'Fresh from\s*([^.]+?)(?=\s*$)',  # Fresh-specific pattern
                                r'Fresh by\s*([^.]+?)(?=\s*$)',  # Fresh-specific pattern
                                r'Amazon Fresh by\s*([^.]+?)(?=\s*$)'  # Amazon Fresh pattern
                            ]
                            
                            for pattern in sold_by_patterns:
                                sold_by_match = re.search(pattern, info_text)
                                if sold_by_match:
                                    sold_by = sold_by_match.group(1).strip()
                                    # Remove any remaining prefix
                                    sold_by = re.sub(r'^(Sold by:|Sold by|Seller:)\s*', '', sold_by)
                                    data['sold_by'] = sold_by.strip()
                                    print(f"DEBUG: Found sold by: {data['sold_by']}")
                                    break
                            
                            # Try to find merchant info in links if not found in text
                            if not data.get('sold_by'):
                                merchant_links = merchant_info.find_all('a', href=True)
                                for link in merchant_links:
                                    if 'seller=' in link['href']:
                                        data['sold_by'] = link.get_text(strip=True)
                                        print(f"DEBUG: Found sold by from link: {data['sold_by']}")
                                        break
                    except Exception as e:
                        print(f"DEBUG: Error extracting shipping info: {str(e)}")
                    
                    # Extract rating more reliably
                    try:
                        rating_elem = product_soup.find('span', {'class': 'a-icon-alt'})
                        if rating_elem and 'out of' in rating_elem.text:
                            try:
                                data['rating'] = float(rating_elem.text.split('out of')[0].strip())
                                print(f"DEBUG: Found rating: {data['rating']}")
                            except ValueError:
                                print("DEBUG: Could not parse rating")
                        
                        # Try alternate rating location
                        if not data['rating']:
                            rating_section = product_soup.find('div', {'id': 'averageCustomerReviews'})
                            if rating_section:
                                rating_text = rating_section.text
                                rating_match = re.search(r'(\d+(?:\.\d+)?).+?out of 5', rating_text)
                                if rating_match:
                                    data['rating'] = float(rating_match.group(1))
                                    print(f"DEBUG: Found rating from alternate section: {data['rating']}")
                    except Exception as e:
                        print(f"DEBUG: Error extracting rating: {str(e)}")
                            
            except Exception as e:
                print(f"DEBUG: Error fetching product details: {str(e)}")
        
        if not data['brand']:
            print("DEBUG: No brand found")

        # Sponsored tag
        sponsored_elem = product.find('span', string='Sponsored')
        data['sponsored'] = bool(sponsored_elem)
        
        # Print raw HTML for debugging if no title found
        if not data['title']:
            print("\nDEBUG: Raw product HTML:")
            print(product.prettify()[:500])  # Print first 500 chars to avoid spam
            print("...")
        
        return data

    def getRawSearchHTML(self, query: str, page: int = 1, retries: int = MAX_RETRIES) -> Optional[requests.Response]:
        encoded_query = urllib.parse.quote(query)
        
        for attempt in range(retries):
            try:
                # Rotate user agents
                self.headers['User-Agent'] = USER_AGENTS[attempt % len(USER_AGENTS)]
                
                # Exponential backoff delay with jitter
                delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
                jitter = uniform(-0.5, 0.5)  # Add random jitter
                time.sleep(delay + jitter)
                
                # Try different Amazon domains
                domains = [
                    'https://www.amazon.com',
                    'https://amazon.com',
                    'https://smile.amazon.com'
                ]
                
                for domain in domains:
                    try:
                        url = f'{domain}/s?k={encoded_query}&page={page}'
                        print(f'Trying URL: {url}')
                        
                        response = requests.get(
                            url=url,
                            headers=self.headers,
                            cookies=self.session.cookies.get_dict(),
                            timeout=15  # Increased timeout
                        )
                        
                        if response.status_code == 200:
                            return response
                        elif response.status_code == 503:
                            print(f'Service unavailable from {domain}, trying next domain...')
                            continue
                        else:
                            response.raise_for_status()
                    except requests.RequestException as e:
                        print(f'Error making request to {domain} (attempt {attempt + 1}/{retries}): {e}')
                        continue
                
                print(f'All domains failed on attempt {attempt + 1}')
            except Exception as e:
                print(f'Unexpected error on attempt {attempt + 1}: {e}')
                
            if attempt < retries - 1:
                print(f'Retrying in {delay:.1f} seconds...')
            else:
                print('All attempts failed')
        
        return None

    def getPaginationAmount(self, query: str) -> int:
        return 3  # Limited to first 3 pages as requested

    def save_results_to_csv(self, products: List[Dict[str, Any]], query: str):
        if not products:
            print('No products to save')
            return
        
        # Define column order for better readability
        columns = [
            'title', 'brand', 'price', 'rating', 'reviews_count',
            'category_1', 'rank_1', 'category_2', 'rank_2',
            'unit_size', 'form', 'asin', 'search_page', 'search_result',
            'country_of_origin', 'ships_from', 'sold_by',
            'feature_bullets', 'aplus_content', 'image_url', 'product_url',
            'sponsored'
        ]

        # Clean and format the data
        cleaned_products = []
        for product in products:
            cleaned_product = {}
            for col in columns:
                value = product.get(col, '')
                
                # Convert numeric strings to proper format
                if col == 'price' and value:
                    try:
                        value = f"{float(str(value).replace('$', '').replace(',', '')):.2f}"
                    except (ValueError, TypeError):
                        value = ''
                elif col in ['rating', 'rank_1', 'rank_2'] and value:
                    try:
                        value = str(float(str(value).replace(',', '')))
                    except (ValueError, TypeError):
                        value = ''
                elif col == 'reviews_count' and value:
                    try:
                        value = str(int(str(value).replace(',', '')))
                    except (ValueError, TypeError):
                        value = ''
                elif col in ['search_page', 'search_result']:
                    value = str(value) if value else ''
                elif col == 'sponsored':
                    value = 'Yes' if value else 'No'
                else:
                    # Clean text fields
                    value = str(value).strip()
                    value = ' '.join(value.split())  # Normalize whitespace
                    value = value.replace('\n', ' ').replace('\r', '')
                    
                cleaned_product[col] = value
            
            cleaned_products.append(cleaned_product)
        
        # Create output directory and generate filename
        OUTPUT_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = OUTPUT_DIR / f'amazon_results_{urllib.parse.quote(query)}_{timestamp}.csv'
        
        # Write to CSV with UTF-8-SIG encoding for Excel compatibility
        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(cleaned_products)
        
        print(f'\nSuccessfully saved {len(products)} products to CSV in the output directory')
 
 
def main():
    try:
        s = AmazonSession()
        all_products = []
        
        # Only process page 1 for debugging
        page = 1
        print(f'Scraping page {page}...')
        response = s.getRawSearchHTML(__QUERY__, page)
        
        if not response:
            print('Failed to get response')
            return
        
        soup = bs4.BeautifulSoup(response.text, 'html.parser')
        product_containers = soup.find_all('div', attrs={'data-component-type': 's-search-result'})
        
        if not product_containers:
            print('No products found')
            return
        
        # Limit to DEBUG_LIMIT products
        product_containers = product_containers[:DEBUG_LIMIT]
        print(f'Found {len(product_containers)} products on page {page} (collecting up to {DEBUG_LIMIT} total for debugging)')
        
        # Extract data from each product
        print(f"\nDEBUG: Processing {len(product_containers)} containers")
        for idx, product in enumerate(product_containers, 1):
            print(f"\nDEBUG: Processing product {idx}")
            product_data = s._extract_product_data(product)
            product_data['search_page'] = page  # Set current page number
            product_data['search_result'] = idx  # Set search result position
            
            # Clean up rank numbers to be just integers
            if product_data['rank_1']:
                product_data['rank_1'] = product_data['rank_1'].split('#')[1].split(' ')[0] if '#' in product_data['rank_1'] else ''
            if product_data['rank_2']:
                product_data['rank_2'] = product_data['rank_2'].split('#')[1].split(' ')[0] if '#' in product_data['rank_2'] else ''
            
            if product_data['title'] and product_data['product_url']:
                # Get additional details from product page with retries
                max_retries = 3
                response = None
                
                for attempt in range(max_retries):
                    try:
                        print(f"DEBUG: Fetching details from product page (attempt {attempt + 1}/{max_retries})...")
                        
                        # Add random delay between requests
                        delay = uniform(BASE_DELAY * (2 ** attempt), MAX_DELAY * (2 ** attempt))
                        time.sleep(delay)
                        
                        response = s.session.get(
                            url=product_data['product_url'],
                            headers=s.headers,
                            timeout=15
                        )
                        
                        if response.status_code == 200:
                            break
                        elif response.status_code in [503, 429, 403]:
                            print(f"Rate limited (status {response.status_code}), retrying in {delay:.1f} seconds...")
                            if attempt < max_retries - 1:
                                continue
                        else:
                            response.raise_for_status()
                    except Exception as e:
                        print(f"Error on attempt {attempt + 1}: {e}")
                        if attempt < max_retries - 1:
                            continue
                        else:
                            print("Failed to fetch product page after all retries")
                            break
                
                if response and response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Extract brand from product page
                    try:
                        brand_elem = soup.find('span', {'class': 'a-size-base po-break-word'})
                        if brand_elem:
                            product_data['brand'] = brand_elem.text.strip()
                            print(f"DEBUG: Found brand from product page: {product_data['brand']}")
                    except Exception as e:
                        print(f"DEBUG: Could not extract brand from product page: {e}")
                    
                    # Extract best sellers ranks from product page
                    try:
                        rank_items = soup.find_all('span', {'class': 'a-list-item'})
                        ranks_found = []
                        for item in rank_items:
                            if '#' in item.text and 'in' in item.text:
                                try:
                                    rank_text = item.text.strip()
                                    rank_num = rank_text.split('#')[1].split(' in ')[0].strip().replace(',', '')
                                    category = rank_text.split(' in ')[1].strip()
                                    ranks_found.append((rank_num, category))
                                except Exception as e:
                                    print(f"DEBUG: Could not parse rank item {item.text}: {e}")
                        
                        # Sort ranks by number and assign to rank fields
                        ranks_found.sort(key=lambda x: int(x[0]))
                        for i, (rank, category) in enumerate(ranks_found[:2], 1):
                            product_data[f'rank_{i}'] = rank
                            product_data[f'category_{i}'] = category
                            print(f"DEBUG: Found rank {i}: #{rank} in {category}")
                    except Exception as e:
                        print(f"DEBUG: Could not extract ranks from product page: {e}")
                    
                    print("DEBUG: Successfully extracted product page details")
                    all_products.append(product_data)
                    print(f"SUCCESS: {product_data['title']} - ${product_data['price']}")
        
        # Save results to CSV
        if all_products:
            s.save_results_to_csv(all_products, __QUERY__)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == '__main__':
    main()