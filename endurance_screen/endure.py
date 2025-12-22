#!/usr/bin/env python3
"""
Endure CLI - Remote file editor with conflict detection
"""
import sys
import os
import tempfile
import subprocess
import requests
import argparse
import webbrowser

def get_editor():
    """Get the user's preferred editor"""
    return os.environ.get('EDITOR', 'vim')

def fetch_file(url):
    """Fetch file content and hash from server"""
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data['content'], data['hash']
    except requests.RequestException as e:
        print(f"Error fetching file: {e}", file=sys.stderr)
        sys.exit(1)
    except (KeyError, ValueError) as e:
        print(f"Invalid response from server. Did you use the right URL?\nError: {e}", file=sys.stderr)
        sys.exit(1)

def edit_content(content):
    """Open content in editor and return edited version"""
    editor = get_editor()
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        temp_path = f.name
    
    try:
        subprocess.run([editor, temp_path], check=True)
        with open(temp_path, 'r') as f:
            edited_content = f.read()
        return edited_content
    finally:
        os.unlink(temp_path)

def push_file(url, content, file_hash):
    """Push edited content back to server"""
    try:
        response = requests.post(
            url,
            json={'content': content, 'hash': file_hash},
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 409:
            data = response.json()
            print("⚠️  CONFLICT: File has been modified on server", file=sys.stderr)
            print(f"\nCurrent server content:\n{data['current_content']}", file=sys.stderr)
            print("\nYour changes were not saved.", file=sys.stderr)
            sys.exit(1)
        
        response.raise_for_status()
        print("✓ File saved successfully")
        return True
        
    except requests.RequestException as e:
        print(f"Error pushing file: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Endure CLI")
    parser.add_argument("url", help="The URL of the endurance server (e.g. http://endure:1024)")
    parser.add_argument("--web", action="store_true", help="Open the web editor in your browser instead of CLI")
    args = parser.parse_args()
    
    # 1. Clean the base URL
    url = args.url.rstrip('/')
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url

    # 2. Handle Web Mode
    if args.web:
        # Strip API endpoint if user accidentally included it, then add /edit
        base_url = url.split('/api/')[0]
        web_url = f"{base_url}/edit"
        print(f"Opening web editor at {web_url}...")
        webbrowser.open(web_url)
        sys.exit(0)

    # 3. Handle CLI Mode
    # Automatically append API endpoint if not present
    if not url.endswith('/api/reminders'):
        url = f"{url}/api/reminders"
    
    print(f"Fetching {url}...")
    content, file_hash = fetch_file(url)
    
    print(f"Opening in {get_editor()}...")
    edited_content = edit_content(content)
    
    if edited_content == content:
        print("No changes made.")
        sys.exit(0)
    
    print("Saving changes...")
    push_file(url, edited_content, file_hash)

if __name__ == '__main__':
    main()