#!/usr/bin/env python3
"""
Parse Sparky API captures from curl command or HTTP Catcher export.

Usage:
    python3 parse_har_curl.py <input_file>
    
Input can be:
- Text file containing curl command
- HTTP Catcher export (with request and response)
- Just the JSON response

This will:
1. Extract the query and response JSON
2. Parse with parse_sparky_capture.py
3. Generate CAPTURE_LOG.md entry with add_to_log.py
4. Save parsed JSON to data/captures/
"""

import json
import sys
import re
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote
import subprocess


def extract_from_curl(text: str) -> tuple:
    """Extract query and response JSON from curl command format."""
    
    # Find the request body (--data-raw)
    data_match = re.search(r"--data-raw\s+'([^']+)'", text)
    if not data_match:
        data_match = re.search(r'--data-raw\s+"([^"]+)"', text)
    
    request_json = None
    query_text = None
    
    if data_match:
        request_body = data_match.group(1)
        try:
            request_json = json.loads(request_body)
            # Extract query from message.query
            if 'message' in request_json and 'query' in request_json['message']:
                query_text = unquote(request_json['message']['query'])
        except json.JSONDecodeError:
            pass
    
    # Find the response JSON (last JSON object in the text)
    # Look for the response after "HTTP/1.1 200" or at the end
    response_start = text.rfind('{"intentName"')
    if response_start == -1:
        response_start = text.rfind('{"appContextStack"')
    
    response_json = None
    if response_start != -1:
        response_text = text[response_start:].strip()
        # Take first complete JSON object
        try:
            response_json = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to find just the response object
            lines = response_text.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('{'):
                    try:
                        response_json = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
    
    return query_text, request_json, response_json


def extract_from_json(text: str) -> tuple:
    """Extract from plain JSON response."""
    
    try:
        response_json = json.loads(text)
        
        # Try to extract query from response
        query_text = None
        if 'responseMessage' in response_json:
            raw_response = response_json.get('responseMessage', {}).get('rawResponse', [])
            if raw_response and len(raw_response) > 0:
                query_text = raw_response[0].get('query', '')
        
        return query_text, None, response_json
    except json.JSONDecodeError:
        return None, None, None


def archive_capture(input_file: Path, query_text: str):
    """Archive the raw capture before clearing input file."""
    archive_dir = Path(__file__).parent / "data" / "raw_captures"
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename with timestamp and query
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_query = re.sub(r'[^\w\s-]', '', query_text[:50]).strip().replace(' ', '_')
    archive_filename = f"{timestamp}_{safe_query}.txt"
    archive_path = archive_dir / archive_filename
    
    # Copy the input file to archive
    with open(input_file, 'r') as f:
        content = f.read()
    
    with open(archive_path, 'w') as f:
        f.write(content)
    
    print(f"📦 Archived raw capture to: {archive_path}")
    return archive_path


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 parse_har_curl.py <input_file>")
        sys.exit(1)
    
    input_file = Path(sys.argv[1])
    
    if not input_file.exists():
        print(f"❌ Error: File not found: {input_file}")
        sys.exit(1)
    
    # Read input
    with open(input_file, 'r') as f:
        content = f.read()
    
    # Try to extract query and response
    query_text, request_json, response_json = extract_from_curl(content)
    
    if not response_json:
        # Try plain JSON
        query_text, request_json, response_json = extract_from_json(content)
    
    if not response_json:
        print("❌ Error: Could not extract response JSON from input")
        print("\nExpected format:")
        print("  - curl command with --data-raw and response")
        print("  - HTTP Catcher export with request and response")
        print("  - Plain JSON response")
        sys.exit(1)
    
    if not query_text:
        print("⚠️  Warning: Could not extract query text from input")
        query_text = input("Enter query text manually: ").strip()
    
    print(f"✅ Extracted query: {query_text}")
    print(f"✅ Extracted response JSON")
    
    # Archive the raw capture before processing
    archive_capture(input_file, query_text)
    
    # Save response JSON to temp file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    query_slug = re.sub(r'[^a-z0-9]+', '_', query_text.lower())[:50]
    
    temp_response_file = Path(f"/tmp/sparky_response_{timestamp}.json")
    with open(temp_response_file, 'w') as f:
        json.dump(response_json, f, indent=2)
    
    print(f"\n📄 Saved response to: {temp_response_file}")
    
    # Parse with parse_sparky_capture.py
    print("\n🔍 Parsing response...")
    parser_script = Path(__file__).parent / "parse_sparky_capture.py"
    
    result = subprocess.run(
        [sys.executable, str(parser_script), str(temp_response_file)],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"❌ Error parsing response:")
        print(result.stderr)
        sys.exit(1)
    
    print(result.stdout)
    
    # Find the parsed output file
    parsed_file = Path(f"data/captures/{timestamp}_{temp_response_file.stem}_parsed.json")
    
    if not parsed_file.exists():
        print("⚠️  Warning: Could not find parsed output file")
        print("Run add_to_log.py manually on the parsed file")
        # Clear input file before exiting
        if input_file.name == "new_capture_input.txt":
            with open(input_file, 'w') as f:
                f.write("")
            print(f"🧹 Cleared {input_file.name} for next capture")
        sys.exit(0)
    
    # Generate log entry
    print("\n📝 Generating CAPTURE_LOG.md entry...")
    log_script = Path(__file__).parent / "add_to_log.py"
    
    result = subprocess.run(
        [sys.executable, str(log_script), str(parsed_file)],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"❌ Error generating log entry:")
        print(result.stderr)
        sys.exit(1)
    
    print(result.stdout)
    
    # Auto-append to CAPTURE_LOG.md
    log_file = Path(__file__).parent.parent / "docs" / "CAPTURE_LOG.md"
    
    # Extract just the log entry (skip the header/footer)
    log_lines = result.stdout.split('\n')
    start_idx = None
    end_idx = None
    
    for i, line in enumerate(log_lines):
        if line.startswith('## Capture'):
            start_idx = i
        elif start_idx is not None and line.startswith('=' * 80):
            end_idx = i
            break
    
    if start_idx is not None and end_idx is not None:
        log_entry = '\n'.join(log_lines[start_idx:end_idx])
        
        # Append to log file
        with open(log_file, 'a') as f:
            f.write('\n' + log_entry + '\n')
        
        print(f"\n✅ Auto-appended to {log_file}")
    else:
        print(f"\n⚠️  Could not extract log entry for auto-append")
    
    # Clear the input file if it's new_capture_input.txt
    if input_file.name == "new_capture_input.txt":
        with open(input_file, 'w') as f:
            f.write("")
        print(f"\n🧹 Cleared {input_file.name} for next capture")


if __name__ == "__main__":
    main()
    
    # Trigger analysis prompt
    analysis_script = Path(__file__).parent / "analyze_latest_capture.py"
    if analysis_script.exists():
        subprocess.run([sys.executable, str(analysis_script)])

