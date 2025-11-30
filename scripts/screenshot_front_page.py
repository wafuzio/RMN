#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Front Page Screenshot Capture Tool

Captures full-page screenshots of retailer homepages for competitive intelligence
and UI/UX monitoring.

Usage:
    python scripts/screenshot_front_page.py --retailer kroger
    python scripts/screenshot_front_page.py --all
    python scripts/screenshot_front_page.py --retailer walmart --profile-dir ~/ChromeProfiles/walmart

Storage:
    output/screen_capture/<retailer>/front_pages/<retailer>__front_page__DYYYY-MM-DD_THH-MM.SS.png
"""

import argparse
import base64
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


# Retailer homepage URLs
RETAILER_URLS = {
    "kroger": "https://www.kroger.com/",
    "walmart": "https://www.walmart.com/",
    "amazon": "https://www.amazon.com/",
    "instacart": "https://www.instacart.com/",
    "target": "https://www.target.com/",
}


def _check_px_block(page) -> tuple:
    """Check if page is blocked by PerimeterX.
    
    Returns (is_blocked: bool, reason: str)
    """
    try:
        content = page.content()
        
        # PerimeterX CAPTCHA - "Press & Hold" button
        if page.locator("#px-captcha").count() > 0:
            return True, "perimeterx_captcha (Press & Hold)"
        
        # "Robot or human?" text
        if "Robot or human?" in content:
            return True, "perimeterx_captcha (Robot or human)"
        
        # Blocked page redirect
        if "/blocked" in page.url.lower():
            return True, "blocked_redirect"
        
        # Access denied
        if "access denied" in content.lower():
            return True, "access_denied"
        
        # Check for PX modal overlay
        if page.locator('[class*="px-captcha"]').count() > 0:
            return True, "px_modal"
        
        return False, ""
    except Exception as e:
        return False, f"check_error: {e}"


def get_output_root():
    """Resolve output root directory for front page screenshots."""
    # Priority 1: FRONT_PAGE_OUTPUT_ROOT env var
    if os.getenv("FRONT_PAGE_OUTPUT_ROOT"):
        return Path(os.getenv("FRONT_PAGE_OUTPUT_ROOT"))
    
    # Priority 2: SCRAPER_HOME/output/screen_capture
    if os.getenv("SCRAPER_HOME"):
        return Path(os.getenv("SCRAPER_HOME")) / "output" / "screen_capture"
    
    # Priority 3: Project root fallback
    return PROJECT_ROOT / "output" / "screen_capture"


def get_profile_dir(retailer: str, cli_profile: str = None):
    """Resolve profile directory for retailer.
    
    For bot-protected sites (Kroger, Walmart, Target), we use the MAIN scraper profile
    which has established session cookies. Fresh profiles get blocked.
    For other sites (Amazon, Instacart), we use dedicated frontpage profiles.
    """
    # Priority 1: CLI argument
    if cli_profile and Path(cli_profile).is_dir():
        return cli_profile
    
    # Priority 2: Front-page-specific env var (KROGER_FRONTPAGE_PROFILE_DIR)
    env_var = f"{retailer.upper()}_FRONTPAGE_PROFILE_DIR"
    if os.getenv(env_var) and Path(os.getenv(env_var)).is_dir():
        return os.getenv(env_var)
    
    chrome_profiles = Path.home() / "ChromeProfiles"
    
    # Priority 3: For bot-protected sites, use dedicated frontpage profile
    # These need to be seeded from the main scraper profile once to have session cookies
    # Run: cp -r ~/ChromeProfiles/kroger_clean_profile ~/ChromeProfiles/kroger_frontpage_profile
    if retailer in ('kroger', 'walmart', 'target'):
        frontpage_profile = chrome_profiles / f"{retailer}_frontpage_profile"
        if frontpage_profile.exists():
            return str(frontpage_profile)
        # Fallback to main profile only if frontpage profile doesn't exist
        main_profile_names = {
            'kroger': 'kroger_clean_profile',
            'walmart': 'walmart_clean2', 
            'target': 'target_profile',
        }
        main_profile = chrome_profiles / main_profile_names.get(retailer, f"{retailer}_profile")
        if main_profile.exists():
            # Auto-clone the main profile for frontpage use
            import shutil
            print(f"[{retailer}] Cloning main profile to frontpage profile...")
            shutil.copytree(str(main_profile), str(frontpage_profile), dirs_exist_ok=True)
            # Remove lock files from the clone
            for lock in ['SingletonLock', 'SingletonCookie', 'SingletonSocket']:
                lock_path = frontpage_profile / lock
                if lock_path.exists() or lock_path.is_symlink():
                    lock_path.unlink()
            print(f"[{retailer}] Created frontpage profile from main profile")
            return str(frontpage_profile)
    
    # Priority 4: ~/ChromeProfiles/<retailer>_frontpage_profile (dedicated for screenshots)
    if chrome_profiles.is_dir():
        frontpage_profile = chrome_profiles / f"{retailer}_frontpage_profile"
        # Create if it doesn't exist - front page captures don't need login state
        if not frontpage_profile.exists():
            frontpage_profile.mkdir(parents=True, exist_ok=True)
            print(f"[{retailer}] Created new frontpage profile: {frontpage_profile}")
        return str(frontpage_profile)
    
    # Priority 4: SCRAPER_HOME/profiles/<retailer>_frontpage
    if os.getenv("SCRAPER_HOME"):
        profile_path = Path(os.getenv("SCRAPER_HOME")) / "profiles" / f"{retailer}_frontpage"
        if not profile_path.exists():
            profile_path.mkdir(parents=True, exist_ok=True)
        return str(profile_path)
    
    # Priority 5: Project root profiles (frontpage-specific)
    profile_path = PROJECT_ROOT / "profiles" / f"{retailer}_frontpage"
    if not profile_path.exists():
        profile_path.mkdir(parents=True, exist_ok=True)
    return str(profile_path)


def extract_readable_text(page, retailer: str = None) -> str:
    """
    Extract all visible text from the page, organized semantically:
    - Navigation links (header department links)
    - Page headlines (main promotional banners)
    - Section headers (deal section titles)
    - Deals (item + price/discount together)
    - Content items (products, text)
    
    Retailer-specific extraction rules are applied based on the retailer parameter.
    """
    # JavaScript to extract text with semantic grouping
    retailer_js = retailer or ""
    extract_script = """
    (retailer) => {
        const results = {
            page_headlines: [],   // Main page banners/headlines  
            banner_text: [],      // Banner/promo headlines and messages
            section_headers: [],  // Section titles (4+ star deals, etc.)
            deals: [],            // Items with their prices/discounts
            promo_text: [],       // Promotional copy
            other_text: []        // Other meaningful text
        };
        
        const seen = new Set();
        const seenDeals = new Set();
        
        // Helper to clean text
        const clean = (text) => {
            if (!text) return '';
            return text.replace(/\\s+/g, ' ').trim();
        };
        
        // Check if element is in header/nav area
        const isInHeader = (el) => {
            let parent = el;
            while (parent) {
                const tag = parent.tagName?.toLowerCase();
                if (tag === 'header' || tag === 'nav') return true;
                if (parent.id?.toLowerCase().includes('nav')) return true;
                if (parent.className?.includes?.('nav') || parent.className?.includes?.('header')) return true;
                parent = parent.parentElement;
            }
            return false;
        };
        
        // Check if text looks like a price/discount
        const isPriceOrDiscount = (text) => /^\\$[\\d,.]+|^\\d+%\\s*off|^Save\\s*\\$|^Up to \\d+%/i.test(text);
        
        // Check if element is visible
        const isVisible = (el) => {
            if (!el) return false;
            try {
                const style = window.getComputedStyle(el);
                return style.display !== 'none' && 
                       style.visibility !== 'hidden' && 
                       style.opacity !== '0';
            } catch {
                return true;
            }
        };
        
        // Get direct text only (not from children)
        const getDirectText = (el) => {
            let text = '';
            for (const node of el.childNodes) {
                if (node.nodeType === Node.TEXT_NODE) {
                    text += node.textContent;
                }
            }
            return clean(text);
        };
        
        // Find the product/item card container for a price element
        const findItemContext = (el) => {
            let parent = el.parentElement;
            let depth = 0;
            
            while (parent && depth < 8) {
                // Look for common card/item container patterns
                const className = parent.className || '';
                const testId = parent.getAttribute('data-testid') || '';
                
                // Check if this looks like a product/deal card
                if (className.includes('card') || className.includes('Card') ||
                    className.includes('product') || className.includes('Product') ||
                    className.includes('deal') || className.includes('Deal') ||
                    className.includes('item') || className.includes('Item') ||
                    testId.includes('product') || testId.includes('deal')) {
                    
                    // Try to find the item name within this container
                    const nameEl = parent.querySelector('h3, h4, [class*="title"], [class*="Title"], [class*="name"], [class*="Name"], a[href]');
                    if (nameEl) {
                        const name = clean(nameEl.innerText || nameEl.textContent);
                        if (name && name.length > 3 && name.length < 150) {
                            return name;
                        }
                    }
                    
                    // Try aria-label on the container or links
                    const ariaLabel = parent.getAttribute('aria-label') || 
                                     parent.querySelector('a')?.getAttribute('aria-label');
                    if (ariaLabel && ariaLabel.length > 5) {
                        return clean(ariaLabel);
                    }
                }
                
                // Also check for links with meaningful text
                if (parent.tagName?.toLowerCase() === 'a') {
                    const linkText = clean(parent.innerText);
                    if (linkText && linkText.length > 10 && linkText.length < 150 && !isPriceOrDiscount(linkText)) {
                        return linkText;
                    }
                }
                
                parent = parent.parentElement;
                depth++;
            }
            
            return null;
        };
        
        // === RETAILER-SPECIFIC BANNER EXTRACTION ===
        
        // Walmart-specific: skinnyBannerText, styled spans, promo banners
        if (retailer === 'walmart') {
            // Skinny banner text (e.g., "Last-minute Thanksgiving needs")
            document.querySelectorAll('[class*="skinnyBannerText"], [class*="BannerText"]').forEach(el => {
                const text = clean(el.innerText);
                if (text && text.length > 5 && text.length < 150 && !seen.has(text)) {
                    seen.add(text);
                    results.banner_text.push(text);
                }
            });
            
            // Styled announcement spans (e.g., "Stores closed on Thanksgiving Day")
            document.querySelectorAll('span[style*="color"]').forEach(el => {
                const text = clean(el.innerText);
                // Look for announcement-style text (not prices, not too short)
                if (text && text.length > 15 && text.length < 200 && !seen.has(text) && !isPriceOrDiscount(text)) {
                    // Skip if it's just navigation or button text
                    if (!/^(Shop|View|See|Sign|Log|Cart|Account)/i.test(text)) {
                        seen.add(text);
                        results.banner_text.push(text);
                    }
                }
            });
            
            // Walmart promo cards with tc (text-center) class
            document.querySelectorAll('.tc, [class*="promo"], [class*="Promo"]').forEach(el => {
                const text = clean(el.innerText);
                if (text && text.length > 10 && text.length < 200 && !seen.has(text) && !isPriceOrDiscount(text)) {
                    seen.add(text);
                    results.banner_text.push(text);
                }
            });
        }
        
        // Kroger-specific: hero banners, weekly ad headlines
        if (retailer === 'kroger') {
            document.querySelectorAll('[class*="hero"], [class*="Hero"], [class*="banner"], [class*="Banner"], [class*="promo"], [class*="Promo"]').forEach(el => {
                const text = clean(el.innerText);
                if (text && text.length > 10 && text.length < 200 && !seen.has(text) && !isPriceOrDiscount(text)) {
                    seen.add(text);
                    results.banner_text.push(text);
                }
            });
        }
        
        // Amazon-specific: hero headlines, deal banners
        if (retailer === 'amazon') {
            document.querySelectorAll('[class*="hero"], [class*="Hero"], [class*="gateway"], [class*="Gateway"], [data-component-type*="hero"]').forEach(el => {
                const h1 = el.querySelector('h1, h2, [role="heading"]');
                if (h1) {
                    const text = clean(h1.innerText);
                    if (text && text.length > 5 && !seen.has(text)) {
                        seen.add(text);
                        results.banner_text.push(text);
                    }
                }
            });
        }
        
        // Target-specific: comprehensive extraction in page order
        if (retailer === 'target') {
            // Hero banner alt text (e.g., "Target Black Friday It's here!")
            document.querySelectorAll('img[alt]').forEach(img => {
                const alt = img.getAttribute('alt');
                if (!alt || alt.length < 5 || seen.has(alt)) return;
                
                // Check if it's a hero/banner image
                const isHero = img.closest('[data-test*="hero"], [data-test*="Superhero"], [class*="hero"], [class*="Hero"]');
                const isBanner = /black friday|deal|promo|sale|holiday|christmas|thanksgiving/i.test(alt);
                
                if (isHero || isBanner) {
                    seen.add(alt);
                    results.banner_text.push(alt);
                }
            });
            
            // Process main content sections in DOM order
            // Find all major content containers
            const mainContent = document.querySelector('main, [role="main"], #mainContent') || document.body;
            
            // Process carousels with their category badges in order
            mainContent.querySelectorAll('[data-test*="carousel"], [data-test*="Carousel"], [class*="carousel"], [class*="Carousel"]').forEach(carousel => {
                // Get the section title/badge (e.g., "Doorbusters", "Deal of the Day")
                const sectionContainer = carousel.closest('section, [data-test*="section"], [class*="Section"]') || carousel.parentElement?.parentElement;
                
                // Look for category badges/titles near this carousel
                let sectionTitle = '';
                if (sectionContainer) {
                    const titleEl = sectionContainer.querySelector('h2, h3, [data-test*="title"], [class*="title"], [class*="Title"]');
                    if (titleEl) {
                        sectionTitle = clean(titleEl.innerText);
                    }
                    
                    // Also check for navigation items that act as category labels
                    const navItems = sectionContainer.querySelectorAll('li a, [role="tab"], button[class*="tab"]');
                    if (navItems.length > 0 && !sectionTitle) {
                        const badges = [];
                        navItems.forEach(item => {
                            const text = clean(item.innerText);
                            if (text && text.length > 2 && text.length < 50 && !seen.has(text)) {
                                badges.push(text);
                            }
                        });
                        if (badges.length > 0) {
                            sectionTitle = badges.join(' | ');
                        }
                    }
                }
                
                if (sectionTitle && !seen.has(sectionTitle)) {
                    seen.add(sectionTitle);
                    results.section_headers.push(sectionTitle);
                }
                
                // Get products in this carousel
                carousel.querySelectorAll('[data-test*="item-card"], [class*="Card"]').forEach(card => {
                    const titleEl = card.querySelector('[data-test="product-title-sm"], [data-test="product-title-md-lg"], [class*="title"], [class*="Title"]');
                    const imgEl = card.querySelector('img[alt]');
                    const priceEl = card.querySelector('[data-test*="Price"]');
                    
                    const title = titleEl ? clean(titleEl.innerText) : (imgEl ? imgEl.getAttribute('alt') : '');
                    const price = priceEl ? clean(priceEl.innerText) : '';
                    
                    if (title && title.length > 5 && !seenDeals.has(title)) {
                        seenDeals.add(title);
                        seen.add(title);
                        if (price) {
                            results.deals.push(`${price} - ${title}`);
                        } else {
                            results.promo_text.push(title);
                        }
                    }
                });
            });
            
            // Process deal cards (pbo = promotional block object) with their promo + category
            mainContent.querySelectorAll('[data-test*="pbo"], [class*="pbo"], [data-component-id*="STORY"]').forEach(card => {
                const promoEl = card.querySelector('[data-test="pbo-short-desc"], [class*="short-desc"], h3, [class*="heading"]');
                const titleEl = card.querySelector('[data-test="pbo-title"], [class*="title"], p');
                
                const promo = promoEl ? clean(promoEl.innerText) : '';
                const title = titleEl ? clean(titleEl.innerText) : '';
                
                // Combine promo with category (e.g., "40% off - select kid's clothing")
                if (promo && title && !seen.has(promo + title)) {
                    seen.add(promo + title);
                    results.deals.push(`${promo} - ${title}`);
                } else if (promo && !seen.has(promo)) {
                    seen.add(promo);
                    results.section_headers.push(promo);
                } else if (title && !seen.has(title)) {
                    seen.add(title);
                    results.promo_text.push(title);
                }
            });
            
            // Promotional banners and hero content
            mainContent.querySelectorAll('[data-test*="promo"], [data-test*="hero"], [data-test*="Superhero"]').forEach(el => {
                const text = clean(el.innerText);
                if (text && text.length > 10 && text.length < 300 && !seen.has(text) && !isPriceOrDiscount(text)) {
                    seen.add(text);
                    results.banner_text.push(text);
                }
            });
            
            // Story cards and multi-story links
            mainContent.querySelectorAll('[data-test*="MultiStory/Link"], [data-test*="StandardComponent/Link"]').forEach(el => {
                const headingEl = el.querySelector('h2, h3, h4, [role="heading"]');
                const descEl = el.querySelector('p, [class*="desc"]');
                
                const heading = headingEl ? clean(headingEl.innerText) : '';
                const desc = descEl ? clean(descEl.innerText) : '';
                
                if (heading && !seen.has(heading)) {
                    seen.add(heading);
                    if (desc && !seen.has(desc)) {
                        seen.add(desc);
                        results.section_headers.push(`${heading} - ${desc}`);
                    } else {
                        results.section_headers.push(heading);
                    }
                }
            });
        }
        
        // === IMAGE ALT TEXT EXTRACTION (all retailers) ===
        document.querySelectorAll('img[alt]').forEach(img => {
            const alt = img.getAttribute('alt');
            if (!alt || alt.length < 5 || alt.length > 300 || seen.has(alt)) return;
            
            // Skip generic/useless alts
            if (/^(image|photo|picture|icon|logo|arrow|close|menu|search|cart)$/i.test(alt)) return;
            if (/^(previous|next|left|right|up|down)$/i.test(alt)) return;
            
            seen.add(alt);
            
            // Check if this looks like a banner/hero image
            const width = img.naturalWidth || img.width || 0;
            const isInHero = img.closest('[class*="hero"], [class*="Hero"], [class*="banner"], [class*="Banner"], [class*="gateway"], [class*="Gateway"]');
            const isPromoAlt = /black friday|deal|promo|sale|holiday|christmas|thanksgiving|shop now|save|off/i.test(alt);
            
            if (isInHero || isPromoAlt || width > 800 || alt.includes('\\n') || alt.length > 50) {
                // Promotional banner image
                results.banner_text.push(alt.replace(/\\n/g, ' - '));
            } else {
                // Product image
                results.promo_text.push(alt);
            }
        });
        
        // First pass: Find all deals (price + context)
        const priceElements = document.body.querySelectorAll('span, div, p');
        for (const el of priceElements) {
            if (!isVisible(el)) continue;
            
            const text = getDirectText(el);
            if (!text || !isPriceOrDiscount(text)) continue;
            
            const context = findItemContext(el);
            if (context && !seenDeals.has(context)) {
                seenDeals.add(context);
                results.deals.push(`${text} - ${context}`);
            }
        }
        
        // Second pass: Process headings, links, etc.
        const elements = document.body.querySelectorAll('h1, h2, h3, h4, h5, h6, a, button, span, p, li, [role="heading"]');
        
        for (const el of elements) {
            if (!isVisible(el)) continue;
            
            const tag = el.tagName?.toLowerCase();
            const inHeader = isInHeader(el);
            
            // Get text
            let text = getDirectText(el);
            if (!text || text.length < 2) {
                text = clean(el.innerText);
            }
            
            // Skip empty, too short, already seen, or price-only text
            if (!text || text.length < 2 || seen.has(text)) continue;
            if (text.length > 200) continue;
            if (isPriceOrDiscount(text)) continue; // Skip standalone prices
            
            seen.add(text);
            
            // === CATEGORIZE ===
            
            // Skip header/nav content entirely
            if (inHeader) continue;
            
            // H1 = Page headlines (main banners)
            if (tag === 'h1' || (el.getAttribute('role') === 'heading' && el.getAttribute('aria-level') === '1')) {
                results.page_headlines.push(text);
                continue;
            }
            
            // H2 = Section headers
            if (tag === 'h2' || (el.getAttribute('role') === 'heading' && el.getAttribute('aria-level') === '2')) {
                results.section_headers.push(text);
                continue;
            }
            
            // H3-H6 = Subsection headers (also section headers)
            if (['h3', 'h4', 'h5', 'h6'].includes(tag)) {
                results.section_headers.push(text);
                continue;
            }
            
            // Skip buttons - not useful for content extraction
            if (tag === 'button' || el.getAttribute('role') === 'button') {
                continue;
            }
            
            // Links - potential product names or promo text
            if (tag === 'a') {
                if (text.length > 10 && text.length < 100 && !seenDeals.has(text)) {
                    results.promo_text.push(text);
                }
                continue;
            }
            
            // Spans and paragraphs - promotional text
            if (['span', 'p'].includes(tag)) {
                if (text.length > 15 && text.length < 150) {
                    results.promo_text.push(text);
                }
                continue;
            }
            
            // List items
            if (tag === 'li' && text.length > 3 && text.length < 100) {
                results.other_text.push(text);
            }
        }
        
        return results;
    }
    """
    
    try:
        data = page.evaluate(extract_script, retailer_js)
        
        output = []
        
        # Format each category with clear headers
        # Skip nav_links and buttons for cleaner output - focus on content
        sections = [
            ('page_headlines', 'PAGE HEADLINES', 'Main promotional banners and hero text'),
            ('banner_text', 'BANNER & ANNOUNCEMENT TEXT', 'Promotional banners, announcements, and featured messages'),
            ('section_headers', 'SECTION HEADERS', 'Deal sections and content area titles'),
            ('deals', 'DEALS & OFFERS', 'Items with their prices/discounts'),
            ('promo_text', 'PROMOTIONAL TEXT', 'Marketing copy and product links'),
            ('other_text', 'OTHER TEXT', 'Additional content'),
        ]
        
        for key, title, description in sections:
            items = data.get(key, [])
            if items:
                output.append('')
                output.append('=' * 70)
                output.append(f'  {title}')
                output.append(f'  {description}')
                output.append('=' * 70)
                output.append(f'  ({len(items)} items)')
                output.append('')
                for i, item in enumerate(items, 1):
                    output.append(f'  {i:3}. {item}')
        
        return '\n'.join(output)
    except Exception as e:
        return f"[Error extracting text: {e}]"


def check_page_errors(page, retailer: str) -> tuple[bool, str]:
    """Check if page has error states that would make screenshot invalid.
    
    Returns (has_error, error_message)
    """
    error_indicators = [
        # Kroger-specific errors
        "Let's try again",
        "We're having trouble connecting",
        "problem displaying",
        "please try again",
        # Generic errors
        "Something went wrong",
        "Error loading",
        "Unable to load",
        "Page not found",
        "404",
        "500 Internal Server Error",
        "Service Unavailable",
        "Access Denied",
    ]
    
    try:
        # Get visible text from page
        body_text = page.evaluate("() => document.body.innerText")
        
        for indicator in error_indicators:
            if indicator.lower() in body_text.lower():
                return True, f"Found error indicator: '{indicator}'"
        
        # Check for error containers (Kroger-specific)
        error_containers = page.locator('.error-container, [class*="error"], [class*="Error"]').count()
        if error_containers > 2:  # Some sites have minor error styling, only fail on multiple
            return True, f"Found {error_containers} error containers"
        
        return False, ""
    except Exception as e:
        return False, ""  # Can't check, proceed anyway


def capture_fullpage_cdp(context, page, output_path: Path, retailer: str = None):
    """Capture full-page screenshot - same approach as main scraper.
    
    Simple approach: scroll to trigger lazy loading, then full_page=True screenshot.
    """
    
    # Check for page errors before capturing
    has_error, error_msg = check_page_errors(page, retailer)
    if has_error:
        raise Exception(f"Page has errors, cannot capture: {error_msg}")
    
    # Scroll to trigger lazy-loaded content (same as main scraper)
    try:
        vh = page.evaluate("() => window.innerHeight")
        doc_h = page.evaluate("() => document.body.scrollHeight")
        step = int(vh * 0.4)  # Smaller steps = more positions for images to hydrate
        
        # Scroll down to trigger lazy loading
        y = 0
        while y < doc_h - vh:
            page.evaluate(f"window.scrollTo(0, {y})")
            page.wait_for_timeout(200)
            y += step
            doc_h = page.evaluate("() => document.body.scrollHeight")
        
        # Scroll to bottom
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(300)
        
        # Return to top
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(300)
    except Exception as e:
        print(f"  [warn] Scroll warmup failed: {e}")
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Simple full_page screenshot - same as main scraper
    page.screenshot(path=str(output_path), full_page=True)
    
    return output_path


def save_html(page, output_path: Path):
    """Save the full HTML content of the page."""
    html_path = output_path.with_suffix('.html')
    try:
        html_content = page.content()
        html_path.write_text(html_content, encoding='utf-8')
        return html_path
    except Exception as e:
        print(f"  [warn] Failed to save HTML: {e}")
        return None


def save_readable_text(page, output_path: Path, retailer: str = None):
    """Save extracted readable text from the page."""
    text_path = output_path.with_suffix('.txt')
    try:
        # Get page title and URL for header
        title = page.title() or "Unknown"
        url = page.url
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        header = f"""{'='*70}
FRONT PAGE TEXT CAPTURE
{'='*70}
Title: {title}
URL: {url}
Retailer: {retailer or 'Unknown'}
Captured: {timestamp}
{'='*70}

"""
        text_content = extract_readable_text(page, retailer)
        text_path.write_text(header + text_content, encoding='utf-8')
        return text_path
    except Exception as e:
        print(f"  [warn] Failed to save text: {e}")
        return None


def capture_front_page(retailer: str, profile_dir: str = None, timeout: int = 30, output_root: Path = None):
    """
    Capture front page screenshot for a single retailer.
    
    Args:
        retailer: Retailer slug (kroger, walmart, etc.)
        profile_dir: Optional profile directory path
        timeout: Navigation timeout in seconds
        output_root: Optional output root directory
    
    Returns:
        dict with keys: success (bool), path (str|None), error (str|None), duration (float)
    """
    start_time = time.time()
    
    if retailer not in RETAILER_URLS:
        return {
            "success": False,
            "path": None,
            "error": f"Unknown retailer: {retailer}",
            "duration": 0
        }
    
    url = RETAILER_URLS[retailer]
    output_root = output_root or get_output_root()
    
    # Generate output path
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M.%S")
    filename = f"{retailer}__front_page__D{timestamp}.png"
    output_path = output_root / retailer / "front_pages" / filename
    
    print(f"[{retailer}] Starting capture...")
    print(f"[{retailer}] URL: {url}")
    print(f"[{retailer}] Output will be: {output_path}")
    
    # Resolve profile
    resolved_profile = get_profile_dir(retailer, profile_dir)
    if resolved_profile:
        print(f"[{retailer}] Using profile: {resolved_profile}")
    else:
        print(f"[{retailer}] No profile (incognito mode)")
    
    try:
        import sys
        print(f"[{retailer}] Initializing Playwright...", flush=True)
        
        with sync_playwright() as p:
            # Minimal args - let Chrome be visible and work normally
            # The --no-startup-window and --silent-launch were causing hangs
            browser_args = [
                '--use-angle=metal',  # Force ANGLE→Metal backend on macOS
                '--enable-gpu-rasterization',
                '--ignore-gpu-blocklist',
                '--no-first-run',
                '--disable-notifications',
            ]
            
            if not resolved_profile:
                raise RuntimeError(f"Profile required for {retailer} - cannot run without persistent profile")
            
            # Remove any stale lock files before launching
            profile_path = Path(resolved_profile)
            for lock_file in ['SingletonLock', 'SingletonCookie', 'SingletonSocket']:
                lock_path = profile_path / lock_file
                if lock_path.exists() or lock_path.is_symlink():
                    try:
                        lock_path.unlink()
                        print(f"[{retailer}] Removed stale {lock_file}")
                    except:
                        pass
            
            launch_options = {
                'user_data_dir': resolved_profile,
                'headless': False,  # ALWAYS headed
                'viewport': {"width": 1280, "height": 720},
                'locale': 'en-US',
                'args': browser_args,
                'ignore_default_args': ['--enable-automation'],  # Prevents navigator.webdriver=true
                'chromium_sandbox': True,  # CRITICAL: Force sandbox ON
            }
            
            # Use real Chrome for bot-protected sites (Walmart, Target, Kroger)
            use_real_chrome = retailer in ('walmart', 'target', 'kroger')
            if use_real_chrome:
                launch_options['channel'] = 'chrome'
                print(f"[{retailer}] Launching real Chrome...")
            else:
                print(f"[{retailer}] Launching Chromium...")
            
            context = p.chromium.launch_persistent_context(**launch_options)
            
            if use_real_chrome:
                print(f"[{retailer}] ✅ Real Chrome launched (correct JA3 fingerprint)")
            
            # Force navigator.webdriver to be undefined
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            # Set Accept-Language header
            context.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
            
            page = context.pages[0] if context.pages else context.new_page()
            
            # Navigate with retry
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    print(f"[{retailer}] Navigating (attempt {attempt + 1}/{max_retries})...")
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                    print(f"[{retailer}] DEBUG: DOM loaded, waiting for network to settle...")
                    # Try networkidle but don't fail if it times out - page is usually usable
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                        print(f"[{retailer}] DEBUG: Network idle")
                    except PlaywrightTimeout:
                        print(f"[{retailer}] DEBUG: Network didn't fully idle, continuing anyway...")
                    break
                except PlaywrightTimeout:
                    if attempt == max_retries - 1:
                        raise
                    print(f"[{retailer}] Timeout on navigation, retrying...")
                    time.sleep(2)
            
            # Additional grace period for JS hydration
            page.wait_for_timeout(2000)
            
            # Check for bot detection / PX block (especially Walmart/Target)
            if retailer in ('walmart', 'target'):
                is_blocked, block_reason = _check_px_block(page)
                if is_blocked:
                    print(f"[{retailer}] ❌ BOT DETECTED: {block_reason}")
                    context.close()
                    return {
                        "success": False,
                        "path": None,
                        "error": f"Bot detected: {block_reason}",
                        "duration": time.time() - start_time
                    }
                print(f"[{retailer}] ✅ No bot detection triggered")
            
            # Retailer-specific handling
            if retailer == "kroger":
                # Close Kroger popups (store selector, newsletter, terms, etc.)
                print(f"[{retailer}] Checking for popups...")
                popup_selectors = [
                    'button.kds-Modal-closeButton',  # Kroger's modal close button class
                    'button[aria-label="Close pop-up"]',  # Terms modal
                    'button[aria-label="Close"]',
                    'button[aria-label="close"]',
                    '[data-testid="ModalCloseButton"]',
                    '[data-testid="modal-close-button"]',
                    '.kds-DismissalButton',  # Kroger dismissal button
                    '.ReactModal__Content button[aria-label*="lose"]',
                    '[role="dialog"] button[aria-label*="lose"]',
                    '[role="dialog"] button[aria-label*="pop-up"]',
                ]
                for selector in popup_selectors:
                    try:
                        popup_btn = page.locator(selector).first
                        if popup_btn.is_visible(timeout=500):
                            popup_btn.click()
                            print(f"[{retailer}] Closed popup: {selector}")
                            page.wait_for_timeout(500)
                    except:
                        pass
                
                # Remove any remaining modals from DOM entirely
                page.evaluate("""
                    () => {
                        document.querySelectorAll('.ReactModalPortal, .kds-Modal-overlay, [role="dialog"], [class*="Modal"], [class*="Overlay"]')
                            .forEach(el => el.remove());
                    }
                """)
                page.wait_for_timeout(300)
                
                # Scroll through page to trigger lazy-loaded images
                print(f"[{retailer}] Scrolling to trigger lazy-load images...")
                page.evaluate("""
                    async () => {
                        const delay = ms => new Promise(r => setTimeout(r, ms));
                        const viewportHeight = window.innerHeight;
                        const totalHeight = document.body.scrollHeight;
                        
                        // Scroll down in small chunks (40% viewport) to ensure all images enter viewport
                        for (let y = 0; y < totalHeight; y += viewportHeight * 0.4) {
                            window.scrollTo(0, y);
                            await delay(300);  // Wait for images in viewport to start loading
                        }
                        
                        // Scroll to bottom
                        window.scrollTo(0, totalHeight);
                        await delay(400);
                        
                        // Scroll back to top
                        window.scrollTo(0, 0);
                        await delay(300);
                    }
                """)
                
                # Now wait for all images to finish loading
                print(f"[{retailer}] Waiting for images to finish loading...")
                page.evaluate("""
                    () => {
                        return new Promise((resolve) => {
                            const images = document.querySelectorAll('img');
                            let loaded = 0;
                            const total = images.length;
                            if (total === 0) { resolve(); return; }
                            
                            const checkDone = () => {
                                loaded++;
                                if (loaded >= total) resolve();
                            };
                            
                            images.forEach(img => {
                                if (img.complete) {
                                    checkDone();
                                } else {
                                    img.addEventListener('load', checkDone);
                                    img.addEventListener('error', checkDone);
                                }
                            });
                            
                            // Timeout after 5 seconds
                            setTimeout(resolve, 5000);
                        });
                    }
                """)
                print(f"[{retailer}] Images hydrated")
                page.wait_for_timeout(1000)  # Final settle
            
            elif retailer == "target":
                # Target needs extra time for hydration - wait for key elements
                print(f"[{retailer}] Waiting for page hydration...")
                hydration_selectors = [
                    '[data-test="@web/Homepage"]',
                    '[data-test="carousel"]',
                    '[data-test="product-card"]',
                    'main [class*="StyledComponent"]',
                    '[class*="ProductCard"]',
                    '[data-test="categoryCard"]',
                ]
                
                # Wait for at least one hydration indicator
                for selector in hydration_selectors:
                    try:
                        page.wait_for_selector(selector, timeout=5000)
                        print(f"[{retailer}] Found hydration marker: {selector}")
                        break
                    except:
                        pass
                
                # Dismiss sign-in dropdown and other popups
                print(f"[{retailer}] Checking for popups/dropdowns...")
                
                # Click elsewhere to dismiss any open dropdowns (sign-in, etc.)
                try:
                    page.mouse.click(640, 400)  # Click center of page
                    page.wait_for_timeout(300)
                except:
                    pass
                
                # Close any modal/popup overlays
                popup_selectors = [
                    'button[aria-label="close"]',
                    'button[aria-label="Close"]',
                    '[data-test="modal-close-button"]',
                    '[data-test="@web/CloseButton"]',
                    'button[data-test="close-button"]',
                    '[class*="ModalClose"]',
                    '[class*="CloseButton"]',
                ]
                for selector in popup_selectors:
                    try:
                        popup_btn = page.locator(selector).first
                        if popup_btn.is_visible(timeout=300):
                            popup_btn.click()
                            print(f"[{retailer}] Closed popup: {selector}")
                            page.wait_for_timeout(300)
                    except:
                        pass
                
                # Remove dropdown overlays from DOM
                page.evaluate("""
                    () => {
                        // Remove sign-in dropdown and other floating elements
                        document.querySelectorAll('[class*="Dropdown"], [class*="dropdown"], [class*="Popover"], [class*="popover"], [role="menu"], [role="dialog"]')
                            .forEach(el => {
                                // Only remove if it's floating/overlay (not main content)
                                const style = window.getComputedStyle(el);
                                if (style.position === 'absolute' || style.position === 'fixed') {
                                    el.remove();
                                }
                            });
                    }
                """)
                page.wait_for_timeout(200)
                
                # Extra scroll to trigger lazy loading
                page.evaluate("window.scrollTo(0, 500)")
                page.wait_for_timeout(1000)
                page.evaluate("window.scrollTo(0, 1500)")
                page.wait_for_timeout(1000)
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(1500)
                
                # Wait for images to load
                page.evaluate("""
                    () => new Promise(resolve => {
                        const images = document.querySelectorAll('img');
                        let loaded = 0;
                        const total = images.length;
                        if (total === 0) return resolve();
                        
                        const checkDone = () => {
                            loaded++;
                            if (loaded >= total) resolve();
                        };
                        
                        images.forEach(img => {
                            if (img.complete) checkDone();
                            else {
                                img.onload = checkDone;
                                img.onerror = checkDone;
                            }
                        });
                        
                        // Timeout fallback
                        setTimeout(resolve, 5000);
                    })
                """)
                print(f"[{retailer}] Hydration complete")
            
            # Capture screenshot
            print(f"[{retailer}] Capturing full-page screenshot...")
            capture_fullpage_cdp(context, page, output_path, retailer)
            
            # Save HTML
            print(f"[{retailer}] Saving HTML...")
            html_path = save_html(page, output_path)
            
            # Save readable text
            print(f"[{retailer}] Extracting readable text...")
            text_path = save_readable_text(page, output_path, retailer)
            
            # Get file size
            file_size_mb = output_path.stat().st_size / (1024 * 1024)
            
            # Get dimensions
            try:
                from PIL import Image
                img = Image.open(output_path)
                width, height = img.size
                dimensions = f"{width}x{height}"
            except:
                dimensions = "unknown"
            
            duration = time.time() - start_time
            
            print(f"[{retailer}] ✓ Success!")
            print(f"[{retailer}] Screenshot: {output_path}")
            if html_path:
                print(f"[{retailer}] HTML: {html_path}")
            if text_path:
                print(f"[{retailer}] Text: {text_path}")
            print(f"[{retailer}] Size: {dimensions} ({file_size_mb:.1f} MB)")
            print(f"[{retailer}] Duration: {duration:.1f}s")
            
            # Cleanup
            context.close()
            if not resolved_profile:
                browser.close()
            
            return {
                "success": True,
                "path": str(output_path),
                "html_path": str(html_path) if html_path else None,
                "text_path": str(text_path) if text_path else None,
                "error": None,
                "duration": duration
            }
    
    except Exception as e:
        duration = time.time() - start_time
        error_msg = str(e)
        print(f"[{retailer}] ✗ Failed: {error_msg}")
        
        return {
            "success": False,
            "path": None,
            "error": error_msg,
            "duration": duration
        }


def main():
    parser = argparse.ArgumentParser(
        description="Capture front page screenshots of retailer homepages"
    )
    parser.add_argument(
        "--retailer",
        choices=list(RETAILER_URLS.keys()),
        help="Retailer to capture (kroger, walmart, amazon, instacart, target)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Capture all retailers"
    )
    parser.add_argument(
        "--profile-dir",
        help="Browser profile directory (optional)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Navigation timeout in seconds (default: 30)"
    )
    parser.add_argument(
        "--output-root",
        help="Output root directory (default: output/screen_capture)"
    )
    
    args = parser.parse_args()
    
    if not args.retailer and not args.all:
        parser.error("Must specify --retailer or --all")
    
    output_root = Path(args.output_root) if args.output_root else get_output_root()
    
    if args.all:
        retailers = list(RETAILER_URLS.keys())
        print(f"\n{'='*60}")
        print(f"Capturing front pages for {len(retailers)} retailers...")
        print(f"Output: {output_root}")
        print(f"{'='*60}\n")
        
        results = []
        for i, retailer in enumerate(retailers, 1):
            print(f"\n[{i}/{len(retailers)}] {retailer.upper()}")
            print("-" * 60)
            result = capture_front_page(
                retailer,
                profile_dir=args.profile_dir,
                timeout=args.timeout,
                output_root=output_root
            )
            results.append((retailer, result))
            print()
        
        # Summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        successful = sum(1 for _, r in results if r["success"])
        print(f"Successful: {successful}/{len(retailers)}")
        print()
        
        for retailer, result in results:
            status = "✓" if result["success"] else "✗"
            if result["success"]:
                print(f"{status} {retailer}:")
                print(f"    Screenshot: {result['path']}")
                if result.get('html_path'):
                    print(f"    HTML: {result['html_path']}")
                if result.get('text_path'):
                    print(f"    Text: {result['text_path']}")
            else:
                print(f"{status} {retailer}: {result['error']}")
        
        print(f"{'='*60}\n")
        
        return 0 if successful == len(retailers) else 1
    
    else:
        result = capture_front_page(
            args.retailer,
            profile_dir=args.profile_dir,
            timeout=args.timeout,
            output_root=output_root
        )
        return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
