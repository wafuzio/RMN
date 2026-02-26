from bs4 import BeautifulSoup
import sys

def inspect(html_path):
    print(f"Inspecting: {html_path}")
    with open(html_path, 'r', errors='ignore') as f:
        soup = BeautifulSoup(f, 'html.parser')
    
    # Find all elements containing "Sponsored Ad"
    # We use a lambda to find string matches, then get parent
    targets = soup.find_all(string=lambda t: t and "Sponsored Ad" in t)
    print(f"Found {len(targets)} 'Sponsored Ad' text nodes.")
    
    for i, t in enumerate(targets):
        parent = t.parent
        print(f"\n--- Match #{i+1} ---")
        print(f"Text: {t.strip()[:100]}...")
        print(f"Parent Tag: {parent.name}")
        print(f"Parent Classes: {parent.get('class')}")
        
        # Walk up to find ad container
        curr = parent
        path = []
        for _ in range(10):
            if curr is None: break
            
            # Check for identifying attributes
            ident = f"{curr.name}"
            if curr.get('id'): ident += f"#{curr.get('id')}"
            if curr.get('class'): ident += f".{'.'.join(curr.get('class'))}"
            if curr.get('data-cel-widget'): ident += f"[data-cel-widget='{curr.get('data-cel-widget')}']"
            
            path.append(ident)
            
            if 's-left-ads-item' in curr.get('class', []) or \
               (curr.get('id') and 'desktop-ad' in curr.get('id')) or \
               (curr.get('data-cel-widget') and 'advertising' in curr.get('data-cel-widget')):
                print(f"  -> FOUND CONTAINER: {ident}")
            
            curr = curr.parent
        
        print("  Path (upwards): " + " < ".join(path[:5]))

if __name__ == "__main__":
    inspect("/Users/dan.maguire/.windsurf/worktrees/Amazon_Scrape/Amazon_Scrape-9d0cf4f1/--output-dir/runs/search_results_amazon_--output-dir_20251125_171200.html")
