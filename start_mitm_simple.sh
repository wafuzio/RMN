#!/bin/bash
cd /Users/dan.maguire/Documents/Amazon_Scrape
.venv/bin/mitmweb --listen-host 0.0.0.0 --listen-port 8080 --web-host 0.0.0.0 --web-port 8081 --mode transparent --showhost
