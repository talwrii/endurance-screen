#!/usr/bin/env python3
"""
Endure CLI - Remote file editor with conflict detection
"""
import sys
import os
import tempfile
import subprocess
import requests
from urllib.parse import urljoin


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
        print(f"Invalid response from server: {e}", file=sys.stderr)
        sys.exit(1)


def edit_content(content):
    """Open content in editor and return edited version"""
    editor = get_editor()
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        temp_path = f.name
    
    try:
        # Open editor
        subprocess.run([editor, temp_path], check=True)
        
        # Read edited content
        with open(temp_path, 'r') as f:
            edited_content = f.read()
        
        return edited_content
    finally:
        # Clean up temp file
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
            # Conflict - file was modified
            data = response.json()
            print("⚠️  CONFLICT: File has been modified on server", file=sys.stderr)
            print(f"\nCurrent server content:\n{data['current_content']}", file=sys.stderr)
            print("\nYour changes were not saved.", file=sys.stderr)
            print("Fetch the file again to see current version.", file=sys.stderr)
            sys.exit(1)
        
        response.raise_for_status()
        print("✓ File saved successfully")
        return True
        
    except requests.RequestException as e:
        print(f"Error pushing file: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main CLI entry point"""
    if len(sys.argv) != 2:
        print("Usage: endure <url>", file=sys.stderr)
        print("\nExample:", file=sys.stderr)
        print("  endure https://yourserver.com/api/reminders", file=sys.stderr)
        sys.exit(1)
    
    url = sys.argv[1]
    
    # Ensure URL has scheme
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    
    print(f"Fetching {url}...")
    content, file_hash = fetch_file(url)
    
    print(f"Opening in {get_editor()}...")
    edited_content = edit_content(content)
    
    # Check if content changed
    if edited_content == content:
        print("No changes made.")
        sys.exit(0)
    
    print("Saving changes...")
    push_file(url, edited_content, file_hash)


if __name__ == '__main__':
    main()