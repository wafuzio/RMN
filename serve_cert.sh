#!/bin/bash
cd ~/.mitmproxy
python3 -m http.server 8082 --bind 0.0.0.0
