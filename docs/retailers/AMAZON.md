Amazon adapter

1. Quick Start
# 1) One-time login to create persistent profile
mkdir -p ~/Documents/Amazon_Scrape/profiles/amazon
python3 auth/retailer_auth.py --retailer amazon \
  --profile-dir ~/Documents/Amazon_Scrape/profiles/amazon

# 2) Point the adapter at your profile (put this in ~/.zshrc too)
export AMZ_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/amazon

# 3) Launch the GUI, choose Retailer=Amazon, then run keywords
python3 keyword_input.py

2. What it does (same flow as Kroger)

search_and_capture: navigates to Amazon search for each keyword using Playwright with a persistent Chrome user profile, saves:
HTML: output/amazon//runs/search_results_amazon__.html
JSON: output/amazon//runs/run_results_amazon__.json
extract_images: revisits the search URL and screenshots ad placements, saving PNGs to:
TOA: Sponsored Brands headline/Video (SB/SBV)
Skyscraper: right‑rail Sponsored Display (if present)
Carousel: Sponsored Products top strip/first row
Success rule (unchanged): success when TOA or Skyscraper ≥ 1; Carousel-only triggers retry then warn.

3. Paths, env, logs

Output
output/amazon//{TOA,Skyscraper,Carousel}
output/amazon//runs/{search_results_.html, run_results_.json}
Logs
logs/amazon/keyword_input.log
logs/amazon/image_extract_YYYYMMDD_HHMMSS.log
Env
AMZ_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/amazon
SCRAPER_HOME (optional; base root)

4. Using the GUI

Retailer dropdown: select Amazon
Client: pick/create
Enter keywords (one per line) and Run Scraper
Save Schedule if needed; the scheduler will run Amazon the same as other adapters and apply conflict rules.

5. Verifying a run

bash
# Recent run artifacts
ls -la ~/Documents/Amazon_Scrape/output/amazon/<client>/runs

# Images
ls -la ~/Documents/Amazon_Scrape/output/amazon/<client>/TOA
ls -la ~/Documents/Amazon_Scrape/output/amazon/<client>/Skyscraper
ls -la ~/Documents/Amazon_Scrape/output/amazon/<client>/Carousel

# Logs
EX=$(ls -t ~/Documents/Amazon_Scrape/logs/amazon/image_extract_*.log | head -1) ; tail -n 80 "$EX"

6. Troubleshooting
No images
Re‑login: python3 auth/retailer_auth.py --retailer amazon --profile-dir "$AMZ_PROFILE_DIR"
Confirm env: echo $AMZ_PROFILE_DIR
Check extractor log (see command above)
Selectors drift
Amazon markup mutates; adjust selectors in retailers/amazon/adapter.py and re‑run.
“Robot/Captcha” pages
Happens when session is stale or headless profile has no cookies. Refresh login.
Scheduler conflicts
The GUI filters unavailable minute choices; Save is disabled until conflicts are resolved.

7. Notes on placement mapping
TOA = SB/SBV “headline” near the top. If no SB/SBV found, we fall back to the top viewport slice so runs don’t fail hard while we tune selectors.
Skyscraper = right rail Sponsored Display; not always present.
Carousel = Sponsored Products top-of-search strip or first sponsored row.

8. Maintenance checklist
Validate selectors on 2–3 categories weekly (grocery/beauty/home)
Keep auth profile alive by logging in when prompted (cookie lifetime typically weeks)
Prefer running from source while tuning selectors; rebuild the .app only when UI code changes must ship


Appendix: CLI smoke test

bash
# One-off smoke test outside GUI
python3 - <<'PY'
from core.run_context import RunContext
from core.paths import output_dir_for, logs_dir_for
from retailers.amazon.adapter import AmazonAdapter
import os, time
base = os.path.expanduser('~/Documents/Amazon_Scrape')
client = 'test_client'
retailer = 'amazon'
out = output_dir_for(base, retailer, client)
logs = logs_dir_for(base, retailer)
ctx = RunContext(retailer=retailer, client=client, base_dir=base,
                 output_dir=out, runs_dir=os.path.join(out,'runs'),
                 logs_dir=logs, profile_dir=os.environ.get('AMZ_PROFILE_DIR'),
                 script_dir=os.path.dirname(__file__))
ad = AmazonAdapter()
ok = ad.search_and_capture('oregano oil', ctx)
pairs = ad.collect_pairs_for_run(ctx, time.time() - 120)
for j,h in pairs:
    print('PAIR:', j, h)
    print(ad.extract_images(j,h,ctx))
PY