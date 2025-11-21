#!/usr/bin/env python3
"""
Syntax Error Checker - Catches common transcription errors in Python code
Specifically designed to catch missing parentheses on method calls like .first, .count, .all, etc.
"""

import re
import sys
import os
from pathlib import Path

def check_method_call_errors(file_path):
    """Check for missing parentheses on common Playwright method calls"""
    errors = []
    
    # Patterns that should ALWAYS have parentheses - these are the exact issues we've been hitting
    patterns = [
        # The big offenders - methods that MUST have parentheses
        (r'\.first[^(]', '.first MUST be .first() - missing parentheses!'),
        (r'\.count[^(]', '.count MUST be .count() - missing parentheses!'),
        (r'\.all[^(]', '.all MUST be .all() - missing parentheses!'),
        (r'\.last[^(]', '.last MUST be .last() - missing parentheses!'),
        
        # Method chains that are incomplete
        (r'\.locator\([^)]*\)\.first[^(]', 'locator().first should be locator().first()'),
        (r'\.locator\([^)]*\)\.count[^(]', 'locator().count should be locator().count()'),
        (r'\.locator\([^)]*\)\.all[^(]', 'locator().all should be locator().all()'),
        
        # Common Playwright method call patterns
        (r'\.nth\(\d+\)\.first[^(]', 'nth().first should be nth().first()'),
        (r'\.nth\(\d+\)\.count[^(]', 'nth().count should be nth().count()'),
        
        # Return statements with missing parentheses
        (r'return\s+\w+\.first[^(]', 'return statement missing parentheses on .first()'),
        (r'return\s+\w+\.count[^(]', 'return statement missing parentheses on .count()'),
        
        # Assignment with missing parentheses  
        (r'=\s*\w+\.locator\([^)]*\)\.first[^(]', 'assignment missing parentheses on .first()'),
        (r'=\s*\w+\.locator\([^)]*\)\.count[^(]', 'assignment missing parentheses on .count()'),
    ]
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        return [f"ERROR: Could not read file {file_path}: {e}"]
    
    for line_num, line in enumerate(lines, 1):
        for pattern, description in patterns:
            matches = re.finditer(pattern, line)
            for match in matches:
                # Skip if it's in a comment
                if line.strip().startswith('#'):
                    continue
                    
                # Get context around the match
                start = max(0, match.start() - 10)
                end = min(len(line), match.end() + 10)
                context = line[start:end].strip()
                
                errors.append({
                    'line': line_num,
                    'description': description,
                    'context': context,
                    'full_line': line.strip()
                })
    
    return errors

def check_python_syntax(file_path):
    """Check if the Python file compiles without syntax errors"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        
        compile(source, file_path, 'exec')
        return True, None
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, f"Error: {e}"

def print_banner(text, char='='):
    """Print a prominent banner"""
    width = max(60, len(text) + 10)
    print(char * width)
    print(f"{char} {text.center(width-4)} {char}")
    print(char * width)

def main():
    # Check the main scraper file
    script_dir = Path(__file__).parent.parent
    target_file = script_dir / "amazon_search_and_capture.py"
    
    if not target_file.exists():
        print_banner("❌ ERROR: amazon_search_and_capture.py NOT FOUND", '!')
        sys.exit(1)
    
    print_banner("🔍 SYNTAX ERROR CHECKER", '=')
    print(f"Checking: {target_file}")
    print()
    
    # Check Python syntax first
    syntax_ok, syntax_error = check_python_syntax(target_file)
    
    if not syntax_ok:
        print_banner("🚨 CRITICAL SYNTAX ERROR DETECTED", '!')
        print(f"❌ {syntax_error}")
        print()
        print("Fix this error before running the scraper!")
        print_banner("", '!')
        sys.exit(1)
    else:
        print("✅ Python syntax check: PASSED")
    
    # Check for method call errors
    method_errors = check_method_call_errors(target_file)
    
    if method_errors:
        print_banner("🚨 CRITICAL METHOD CALL ERRORS DETECTED", '!')
        print("❌ THESE WILL CAUSE 'str object is not callable' RUNTIME ERRORS!")
        print(f"❌ Found {len(method_errors)} method call issues that MUST be fixed:")
        print()
        
        for i, error in enumerate(method_errors, 1):
            print(f"🔥 CRITICAL ERROR #{i}:")
            print(f"   📍 Line {error['line']}: {error['description']}")
            print(f"   🔍 Context: ...{error['context']}...")
            print(f"   📝 Full line: {error['full_line']}")
            print(f"   💡 This will cause: 'str' object is not callable")
            print()
        
        print("🚨 THESE ERRORS WILL BREAK THE ENTIRE SCRAPER!")
        print("🚨 FIX ALL MISSING PARENTHESES BEFORE RUNNING!")
        print_banner("🛑 DO NOT RUN UNTIL FIXED", '!')
        sys.exit(1)
    else:
        print("✅ Method call check: PASSED")
    
    print()
    print_banner("🎉 ALL CHECKS PASSED - CODE LOOKS GOOD!", '=')

if __name__ == "__main__":
    main()
