# Grocery Retail Ad Monitoring Project – Full Outline & Intent

(TOA = Targeted Onsite Ad)

⸻

## 🎯 Primary Objective

Build a fully automated, repeatable pipeline that captures, logs, and stores Targeted Onsite Ad (TOA) placements from grocery retailer search results — across multiple search terms, three times daily — to track sponsored brand presence and creative variation over time.

This system acts as a passive intelligence-gathering tool, enabling structured observation of grocery retailers' onsite retail media placements from a buyer's POV.

⸻

## 🧱 Core Use Case

“Which brands are paying to appear at the top of search results on grocery retailer websites for key terms — and how often do those placements rotate throughout the day?”

This system allows you to:

• Identify which brands are appearing in TOA slots
• Capture the headline, image, call-to-action, and destination URL
• Track TOA frequency, timing, and creative variation per term
• Use these patterns to infer paid media strategy, rotation windows, and budget intensity

⸻

## 🧠 Strategic Rationale

Grocery retailers monetize onsite search via programmatic TOA banner units, which are opaque to external observers and not archived in any ad transparency library.

This project:

• Automates TOA discovery across time and search terms
• Captures ad placements that would otherwise be missed
• Enables benchmarking of brand presence and messaging frequency
• Acts as a proxy for paid share of voice and campaign activity

⸻

## 🧪 Scraping Environment

**✅ Logged-in Session**  

- TOA units are only visible while logged into a Kroger account  
- Playwright is used with a persistent `user_data_dir` (profile)  
- Login is manual once, then session data is reused across runs  

**✅ Timing Strategy**

- ~15 search terms are scraped at 3 intervals daily:
- Morning (e.g. 9am)
- Afternoon (e.g. 2pm)
- Evening (e.g. 8pm)
- Result: ~45 scrapes/day, providing rotation insights across time

⸻

## 📁 File Structure

### Core Files

#### Kroger_login.py

Handles authenticated session setup:
• get_authenticated_context(user_data_dir)
  • Launches Chromium with Playwright profile
  • Navigates to Kroger homepage
  • Opens login menu and prompts manual sign-in
  • Waits for user to complete login
  • Returns (context, page) for reuse
• Includes load_cookies() and save_cookies() for session persistence

### Execution Scripts

#### kroger_search_and_capture.py

Performs searches and captures data:
• Verifies login status using existing cookies
• Runs search queries to test authenticated access
• Captures screenshots and HTML of search results
• Saves data for later processing

#### process_saved_html.py

Processes saved HTML files to extract TOA data:
• Finds HTML files saved by kroger_search_and_capture.py
• Parses HTML to extract TOA data without browser automation
• Saves structured JSON data of extracted ads
• Avoids Playwright timeout and asyncio issues

#### keyword_input.py

User interface:
• Simple GUI for entering keywords to scrape
• Runs kroger_search_and_capture.py for each keyword
• Processes saved HTML files automatically

### Utilities

#### kroger_auth_snapshot.py

Provides utilities to save and restore authentication state:
• create_auth_snapshot() - Creates a complete snapshot from a working browser session
• restore_auth_snapshot() - Restores authentication from a previously saved snapshot
• verify_login_status() - Checks if the current browser profile is logged into Kroger

### Archived

#### archived/Kroger_TOA.py

Previous TOA extraction functionality (archived):
• extract_toa_ad() - Parses TOA elements (now imported by process_saved_html.py)
• extract_common_words_and_phrases() - Analyzes ad content (now imported by process_saved_html.py)
• get_rendered_html() - Browser automation (replaced by kroger_search_and_capture.py)
• extract_toa_ads_from_url() - Complete extraction pipeline (split into separate components)

#### archived/Kroger_TOA2.py

Previous test runner (archived):
• Defined list of search terms
• Ran extract_toa_ads_from_url() for each
• Logged output to timestamped JSON

### Scheduler (TBD)

A future job runner will:
• Automate execution 3x/day
• Optionally support headless scraping once stability is confirmed

## 🛪 Bot Security + Session Challenges

Kroger uses Akamai’s Web Application Firewall (WAF) to enforce anti-bot protections. This can result in hard blocks, silent failures, or full-page lockouts if scraping behavior is detected.

🔒 Confirmed Protection Stack
• Vendor: Akamai Bot Protection
• Trigger point: Often occurs on login flow or when session cookies are inconsistent
• Typical Error:

    Access Denied  
You don't have permission to access "<http://login.kroger.com/>..." on this server.  
Reference #18.4d3a2f17.1756952675.b674a62  

## 🔧 Next Steps

1. 🔄 Add scheduling functionality for automated runs (3 times daily).
2. 🔄 Implement error recovery for failed searches.
3. 🔄 Add detailed logging for better monitoring and diagnostics.

⸻
