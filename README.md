# Kroger TOA Scraper

A comprehensive automation platform for tracking and analyzing Targeted Onsite Ads (TOAs) on Kroger.com, featuring a native macOS app, web interface, scheduling system, and Builder.io integration.

## Overview

The Kroger TOA Scraper is a complete monitoring solution that provides:

- **Native macOS App**: PyInstaller-built GUI app with dock integration and custom icon
- **Web Interface**: Modern Bootstrap-based scheduler and dashboard
- **Automated Scheduling**: Multi-client conflict-aware scheduling system
- **Real-time Monitoring**: Background daemon for automated scraping
- **Builder.io Integration**: Vendored Flask API with CORS support
- **Advanced Ad Extraction**: Modular system for different ad types
- **Client Management**: Multi-tenant architecture with isolated data

## Architecture

### Desktop Application
- **Native macOS App Bundle**: `Kroger TOA Scraper.app` with custom icon and dock integration
- **PyInstaller Build**: Standalone executable with vendored dependencies
- **Tkinter GUI**: Modern interface with CSS-synchronized styling
- **Signal Handling**: Proper dock icon click restoration

### Web Interface
- **Flask Server**: `builder_server.py` with vendored dependencies in `libs/`
- **Bootstrap 5**: Modern responsive UI with custom CSS
- **Scheduler Dashboard**: Real-time conflict detection and management
- **API Endpoints**: RESTful interface for Builder.io integration

### Automation System
- **Background Daemon**: `scheduler_daemon.py` for automated execution
- **Multi-client Scheduling**: Conflict-aware time slot management
- **Real-time Monitoring**: 5-minute conflict windows with visual indicators
- **Cross-platform Compatibility**: macOS and Linux support

## Directory Structure

```
├── dist/
│   └── Kroger TOA Scraper.app/     # macOS app bundle
├── libs/                           # Vendored Flask dependencies
│   ├── flask/
│   ├── jinja2/
│   └── ...
├── static/
│   ├── css/
│   │   ├── style.css              # Main styling with CSS variables
│   │   └── scheduler.css          # Scheduler-specific styles
│   └── js/
├── templates/
│   ├── index.html                 # Main scheduler interface
│   └── nfl_dashboard.html         # NFL-style dashboard
├── output/
│   └── <client_name>/             # Client-specific directories
│       ├── main/                  # Full page screenshots
│       ├── TOA/                   # TOA-only images and results
│       ├── schedule_config.json   # Client scheduling configuration
│       ├── scheduler.log          # Client-specific logs
│       └── *.html                 # Saved HTML files
└── ad_extractors/                 # Modular ad extraction system
    ├── base_extractor.py
    ├── toa_extractor.py
    └── ...
```

## Key Components

### Desktop Application
- **keyword_input.py**: Main Tkinter GUI with CSS-synchronized styling
- **launcher**: macOS app bundle launcher with proper path resolution
- **kroger_toa_scraper.spec**: PyInstaller configuration with custom icon

### Web Interface & API
- **builder_server.py**: Flask server with vendored dependencies
- **templates/**: Bootstrap-based web interface
- **static/**: CSS/JS assets with CSS variables for theming

### Core Functionality
- **kroger_search_and_capture.py**: Playwright-based search automation
- **kroger_ad_core.py**: Core ad extraction with modular extractors
- **scheduler_daemon.py**: Background automation daemon
- **ad_extractors/**: Pluggable extraction system
  - **base_extractor.py**: Common extraction methods
  - **toa_extractor.py**: TOA-specific extraction
  - **carousel_extractor.py**: Carousel ad extraction
  - **skyscraper_extractor.py**: Skyscraper ad extraction

### Utilities
- **process_saved_html.py**: Batch HTML processing
- **capture_toa_images.py**: Precise TOA image cropping
- **test_*.py**: Comprehensive test suite

## API Endpoints

### Web Interface
- `GET /` - Main scheduler interface
- `GET /nfl` - NFL-style dashboard view

### Data API
- `GET /api/ads` - List all clients
- `GET /api/ads/<client>` - Get ads for specific client
- `GET /api/nfl-grid/<client>` - NFL-style grid data

### Asset Serving
- `GET /api/images/<client>/<filename>` - Full page screenshots
- `GET /api/toa/<client>/<filename>` - TOA-only images

### CORS Support
- Full CORS headers for Builder.io integration
- Vendored Flask dependencies for deployment compatibility

## Features

### Desktop Application
- **Native macOS Integration**: Proper dock icon, app bundle, Launch Services registration
- **Custom Icon Support**: Dynamic icon loading with PyInstaller compatibility
- **CSS Synchronization**: Desktop styling matches web interface variables
- **Signal Handling**: Proper window restoration on dock icon clicks

### Scheduling & Automation
- **Multi-client Scheduling**: Independent schedules per client with conflict detection
- **Real-time Conflict Visualization**: Color-coded time slots with suggestions
- **Background Daemon**: Automated execution with comprehensive logging
- **Cross-client Coordination**: 5-minute conflict windows prevent browser conflicts

### Web Interface
- **Modern Bootstrap UI**: Responsive design with custom theming
- **Real-time Updates**: Dynamic conflict checking and schedule management
- **Client Management**: Dropdown selection with history persistence
- **Visual Feedback**: Status indicators and progress tracking

### Technical Features
- **Session Persistence**: Akamai Bot Protection handling with cookie management
- **Modular Architecture**: Pluggable ad extractors for different ad types
- **Adaptive Detection**: Edge detection for precise TOA banner cropping
- **Vendor Independence**: Self-contained Flask dependencies for deployment
- **Cross-platform Support**: macOS and Linux compatibility

## Requirements

### System Requirements
- **macOS**: 10.14+ (for native app bundle)
- **Python**: 3.8+ with tkinter support
- **Memory**: 4GB+ RAM recommended
- **Storage**: 2GB+ for dependencies and output data

### Python Dependencies
- **Playwright**: Browser automation
- **BeautifulSoup4**: HTML parsing
- **Pillow (PIL)**: Image processing
- **Flask**: Web server (vendored in `libs/`)
- **NumPy**: Numerical operations
- **Tkinter**: GUI framework (usually included with Python)

## Installation

### Quick Start (macOS)
1. **Download the App**: Use the pre-built `Kroger TOA Scraper.app` from `dist/`
2. **Install Playwright**: `pip install playwright && playwright install`
3. **Launch**: Double-click the app or use `open "Kroger TOA Scraper.app"`

### Development Setup
1. **Clone Repository**:
   ```bash
   git clone <repository-url>
   cd Amazon_Scrape
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   playwright install
   ```

3. **Build App Bundle** (optional):
   ```bash
   pyinstaller kroger_toa_scraper.spec --noconfirm
   ```

## Usage

### Desktop Application

#### Launch the Native App
```bash
# Method 1: Direct launch
open "dist/Kroger TOA Scraper.app"

# Method 2: From source
python keyword_input.py
```

#### Using the GUI
1. **Select Client**: Choose existing client or create new one
2. **Enter Keywords**: Add search terms (one per line)
3. **Configure Schedule**: Set times and days for automated runs
4. **Run Now**: Execute immediate scraping
5. **Save Schedule**: Enable automated execution

### Web Interface

#### Start the Web Server
```bash
# With vendored dependencies
python builder_server.py

# Access at http://localhost:5006
```

#### Web Features
- **Scheduler Dashboard**: Visual schedule management
- **Client Overview**: Multi-client monitoring
- **Conflict Detection**: Real-time scheduling conflicts
- **API Access**: RESTful endpoints for integration

### Automation & Scheduling

#### Background Daemon
```bash
# Start scheduler daemon
./start_scheduler.sh

# Check daemon status
ps aux | grep scheduler_daemon
```

#### Manual Operations
```bash
# Process saved HTML files
python process_saved_html.py --input-dir output/<client> --output-dir output/<client>

# Create TOA-only images
python capture_toa_images.py <client_name>

# Run diagnostics
python test_kroger_diagnostics.py
```

## Configuration

### Client Management
- **Client History**: Stored in `output/client_history.json`
- **Schedule Config**: Per-client in `output/<client>/schedule_config.json`
- **Logs**: Client-specific logs in `output/<client>/scheduler.log`

### Styling Synchronization
The desktop app automatically syncs with web CSS variables:
```css
/* static/css/style.css */
:root {
    --primary-color: #2962ff;
    --secondary-color: #455a64;
    --background-color: #f5f7fa;
    --card-background: #ffffff;
}
```

### Builder.io Integration
1. **Start Server**: `python builder_server.py`
2. **Configure Builder**: Point to `http://localhost:5006`
3. **Access APIs**: Use `/api/` endpoints for data and images

## Development

### Adding New Ad Extractors
1. **Create Extractor**:
   ```bash
   cp ad_extractors/template_extractor.py ad_extractors/new_extractor.py
   ```

2. **Implement Logic**:
   ```python
   class NewExtractor(BaseExtractor):
       def extract_ads(self, soup, url):
           # Custom extraction logic
           return ads
   ```

3. **Register Extractor**:
   ```python
   # In kroger_ad_core.py
   from ad_extractors.new_extractor import NewExtractor
   ```

### Building App Bundle
```bash
# Update icon (optional)
cp new_icon.png icon2.png

# Build with PyInstaller
pyinstaller kroger_toa_scraper.spec --noconfirm

# Register with macOS
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "dist/Kroger TOA Scraper.app"
```

### Testing
```bash
# Run test suite
python test_diagnostics.py
python test_kroger_diagnostics.py
python test_session_persistence.py

# Test GUI components
python test_tkinter.py
```

## Troubleshooting

### Common Issues

**App Won't Launch from Dock**
- Rebuild app bundle: `pyinstaller kroger_toa_scraper.spec --noconfirm`
- Re-register with Launch Services: `lsregister -f "dist/Kroger TOA Scraper.app"`

**Scheduler Conflicts**
- Check daemon status: `ps aux | grep scheduler_daemon`
- Review logs: `tail -f output/<client>/scheduler.log`
- Use web interface for visual conflict resolution

**Builder.io Connection Issues**
- Verify Flask server: `curl http://localhost:5006`
- Check CORS headers in browser dev tools
- Ensure vendored dependencies: `ls libs/`

**Styling Issues**
- Desktop app reads CSS variables from `static/css/style.css`
- Rebuild app after CSS changes
- Check font availability: Inter font family

### Logs & Diagnostics
- **App Logs**: Console output when running from terminal
- **Scheduler Logs**: `output/<client>/scheduler.log`
- **Daemon Logs**: Check system logs for `scheduler_daemon.py`
- **Web Logs**: Flask server console output

## Known Issues
- **TOA and Skyscraper pulling too many times**: In some runs, the TOA and skyscraper extractors may over-collect, resulting in duplicate/extra captures beyond the intended single pass per page/keyword. This is under investigation.
  - Symptom: Repeated detections or multiple images/log entries for the same ad position.
  - Temporary mitigation: Limit concurrent runs, review `output/<client>/scheduler.log` for repetition, and deduplicate outputs by timestamp or filename when aggregating.
  - Planned fix: Add per-keyword/per-page debouncing and stricter deduplication by creative selector/ID and viewport region.

## License
Proprietary - Internal use only
