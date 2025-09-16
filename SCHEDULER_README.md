# Grocery Retail Ad Monitor - Automated Scheduler System

## Overview

The Grocery Retail Ad Monitor now includes a comprehensive automated scheduling system that can monitor and execute scraping tasks for multiple clients at their specified times, running independently of the GUI application.

## Components

### 1. GUI Scheduler Settings (keyword_input.py)
- **Default Times**: 8am, 12pm, 4pm (configurable per client)
- **Client-Specific Configurations**: Each client can have their own schedule
- **Schedule Persistence**: Settings are saved per client in `output/{client}/schedule_config.json`
- **Auto-Population**: When selecting a client, their saved schedule automatically loads

### 2. Scheduler Daemon (scheduler_daemon.py)
- **Independent Operation**: Runs separately from the GUI
- **Multi-Client Support**: Monitors all clients with saved schedules
- **Automatic Discovery**: Finds all client schedule configurations
- **Concurrent Execution**: Can run multiple client schedules simultaneously
- **Comprehensive Logging**: All activities logged to `logs/scheduler_daemon.log`

### 3. Startup Script (start_scheduler.sh)
- **Easy Launch**: Simple script to start the scheduler daemon
- **Environment Setup**: Automatically activates virtual environment
- **Log Management**: Creates logs directory and provides log file location

## How It Works

### Schedule Configuration
1. **In GUI**: Select a client, configure schedule times and days
2. **Save Schedule**: Creates `output/{client_name}/schedule_config.json`
3. **Format**:
   ```json
   {
     "runs": 3,
     "times": [["8", "00", "AM"], ["12", "00", "PM"], ["4", "00", "PM"]],
     "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
     "client": "Client Name"
   }
   ```

### Daemon Operation
1. **Discovery**: Scans `output/*/schedule_config.json` files every 30 seconds
2. **Time Matching**: Checks if current time matches any scheduled time
3. **Day Validation**: Ensures today is a scheduled day
4. **Keyword Loading**: Retrieves keywords from `client_history.json`
5. **Execution**: Runs scraping for each keyword in separate threads
6. **Processing**: Automatically processes HTML files after scraping
7. **Logging**: Records all activities with timestamps

### Duplicate Prevention
- **Run Tracking**: Prevents multiple runs within the same minute
- **Thread Management**: Ensures only one scraping session per client per time slot
- **Cleanup**: Automatically removes old run tracking data

## Usage

### Setting Up Schedules
1. Launch the GUI: `source .venv/bin/activate && python keyword_input.py`
2. Select or create a client
3. Enter keywords for the client
4. Configure schedule times and days
5. Click "Save Schedule"

### Running the Scheduler
1. **Start Daemon**: `./start_scheduler.sh`
2. **Monitor Logs**: `tail -f logs/scheduler_daemon.log`
3. **Stop Daemon**: Press `Ctrl+C`

### Multiple Clients
- Each client can have different schedules
- Daemon monitors all clients simultaneously
- Schedules run independently and concurrently

## File Structure

```
output/
├── client_history.json          # Keywords for all clients
├── {client_name}/
│   ├── schedule_config.json     # Client's schedule configuration
│   ├── keywords_*.txt           # Saved keyword files
│   ├── search_results_*.html    # Scraped HTML files
│   ├── *.png                    # Screenshots
│   └── scheduler.log            # Client-specific logs
└── ...

logs/
└── scheduler_daemon.log         # Main daemon log file
```

## Features

### Scheduler Daemon Features
- ✅ **Multi-Client Support**: Handles unlimited clients
- ✅ **Concurrent Execution**: Multiple schedules run simultaneously
- ✅ **Automatic Discovery**: Finds new client schedules automatically
- ✅ **Robust Error Handling**: Continues running despite individual failures
- ✅ **Comprehensive Logging**: Detailed logs for monitoring and debugging
- ✅ **Duplicate Prevention**: Avoids running the same schedule multiple times
- ✅ **Resource Management**: Proper thread cleanup and timeout handling

### GUI Integration Features
- ✅ **Client-Specific Settings**: Each client has independent schedule configuration
- ✅ **Auto-Population**: Saved schedules load automatically when selecting clients
- ✅ **Default Times**: Sensible defaults (8am, 12pm, 4pm) for new schedules
- ✅ **Persistent Storage**: Schedules saved to client-specific JSON files
- ✅ **Day Selection**: Configurable days of the week for each client

## Monitoring and Troubleshooting

### Log Files
- **Main Daemon Log**: `logs/scheduler_daemon.log`
- **Client Logs**: `output/{client}/scheduler.log` (when using GUI scheduler)

### Common Log Messages
- `Scheduler daemon started - monitoring client schedules`
- `Starting scheduled scrape for client: {client_name}`
- `Successfully scraped keyword '{keyword}' for {client_name}`
- `Completed scheduled scrape for {client_name}: X/Y keywords successful`

### Troubleshooting
1. **No Schedules Running**: Check if schedule_config.json files exist in client directories
2. **Keywords Not Found**: Verify client_history.json contains keywords for the client
3. **Scraping Failures**: Check individual keyword error messages in logs
4. **Time Issues**: Ensure system time is correct and schedule times are valid

## Example Workflow

1. **Setup Client A**:
   - Keywords: ["protein bars", "energy drinks"]
   - Schedule: 8am, 2pm, 6pm on weekdays

2. **Setup Client B**:
   - Keywords: ["organic snacks", "gluten free"]
   - Schedule: 10am, 4pm on Monday, Wednesday, Friday

3. **Start Daemon**: `./start_scheduler.sh`

4. **Automatic Execution**:
   - 8am weekdays: Client A scrapes
   - 10am Mon/Wed/Fri: Client B scrapes
   - 2pm weekdays: Client A scrapes
   - 4pm Mon/Wed/Fri: Client B scrapes
   - 6pm weekdays: Client A scrapes

All schedules run automatically and independently, with full logging and error handling.
