from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta
import os
import json

app = Flask(__name__)
app.secret_key = os.urandom(24)

REMINDERS_FILE = 'reminders.txt'
CONFIG_FILE = 'config.json'

def load_config():
    if not os.path.exists(CONFIG_FILE):
        config = {'password': 'admin123'}
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def load_reminders():
    if not os.path.exists(REMINDERS_FILE):
        return []
    
    with open(REMINDERS_FILE, 'r') as f:
        lines = f.readlines()
    
    reminders = []
    now = datetime.now()
    
    for line in lines:
        line = line.strip()
        if not line or '|' not in line:
            continue
        
        time_str, description = line.split('|', 1)
        time_str = time_str.strip()
        description = description.strip()
        
        try:
            reminder_time = datetime.strptime(time_str, '%H:%M').replace(
                year=now.year, month=now.month, day=now.day
            )
            
            # If time has passed today, skip it
            if reminder_time > now:
                reminders.append({
                    'time': reminder_time,
                    'time_str': time_str,
                    'description': description,
                    'original': line
                })
        except ValueError:
            continue
    
    return sorted(reminders, key=lambda x: x['time'])

def save_reminders(reminders):
    with open(REMINDERS_FILE, 'w') as f:
        for reminder in reminders:
            f.write(reminder['original'] + '\n')

@app.route('/')
def index():
    reminders = load_reminders()
    
    # Auto-save cleaned reminders (removes past items)
    save_reminders(reminders)
    
    # Get up to 3 reminders to display
    display_reminders = reminders[:3] if reminders else []
    remaining_count = max(0, len(reminders) - 3)
    
    return render_template('index.html', 
                         display_reminders=display_reminders,
                         remaining_count=remaining_count)

@app.route('/edit', methods=['GET', 'POST'])
def edit():
    config = load_config()
    
    if request.method == 'POST':
        if 'login' in request.form:
            if request.form.get('password') == config['password']:
                session['authenticated'] = True
                return redirect(url_for('edit'))
        elif 'save' in request.form and session.get('authenticated'):
            content = request.form.get('content', '')
            with open(REMINDERS_FILE, 'w') as f:
                f.write(content)
            return redirect(url_for('edit'))
    
    if not session.get('authenticated'):
        return render_template('login.html')
    
    if os.path.exists(REMINDERS_FILE):
        with open(REMINDERS_FILE, 'r') as f:
            content = f.read()
    else:
        content = ''
    
    return render_template('edit.html', content=content)

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)