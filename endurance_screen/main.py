from flask import Flask, render_template_string, request, redirect, url_for, jsonify
from datetime import datetime
import os
import hashlib
import argparse
import time
import threading
import re

app = Flask(__name__)
app.secret_key = os.urandom(24)

REMINDERS_FILE = 'reminders.txt'

# Global synchronization primitive
update_condition = threading.Condition()

# --- IN-EDITOR DOCUMENTATION ---
DEFAULT_CONTENT = """# ENDURANCE HUD INSTRUCTIONS
# ==========================================
#
# 1. HEADER FIELDS
#    Goal:           <Objective>
#    Reason:         <Why?>
#    Calorie Target: <Daily Limit, e.g. 2000>
#
# 2. THE PLAN & CALORIES
#    Format: HH:MM | Description (include calories like '500kcal')
#    
#    * Past items count towards "Consumed" total.
#    * Future items wait in the list.
#
# ==========================================
# EXAMPLE:
#
# Goal: 24 Hour Fast
# Reason: Control.
# Calorie Target: 500
#
# 08:00 | Black Coffee (5 kcal)
# 12:00 | Bone Broth (50 kcal)
"""

# --- HARDCODED TEMPLATES ---

HTML_INDEX = """
<!DOCTYPE html>
<html>
<head>
    <title>Endurance Screen</title>
    <meta http-equiv="refresh" content="300">
    <script>
        var currentHash = "{{ page_hash }}";
        var nextTargetStr = "{{ next_target }}"; // ISO string from server
        
        function setStatus(status) {
            var el = document.getElementById('status-dot');
            if (status === 'connected') {
                el.className = 'status connected';
            } else {
                el.className = 'status disconnected';
            }
        }

        function makeRequest(method, url, callback, errorCallback) {
            var xhr = new XMLHttpRequest();
            xhr.open(method, url, true);
            xhr.onreadystatechange = function() {
                if (xhr.readyState === 4) {
                    if (xhr.status === 200) {
                        try {
                            var data = JSON.parse(xhr.responseText);
                            callback(data);
                        } catch (e) {
                            errorCallback(e);
                        }
                    } else if (xhr.status === 502) {
                        // Server timeout, retry after delay
                        setTimeout(function() {
                            waitForUpdate();
                        }, 1000);
                    } else {
                        errorCallback(new Error('Request failed'));
                    }
                }
            };
            xhr.send();
        }

        function waitForUpdate() {
            setStatus('connected');
            makeRequest('GET', '/api/poll?hash=' + currentHash, 
                function(data) {
                    if (data.changed) {
                        window.location.reload();
                    } else {
                        waitForUpdate();
                    }
                },
                function(error) {
                    setStatus('disconnected');
                    setTimeout(waitForUpdate, 5000);
                }
            );
        }

        // T-MINUS COUNTDOWN LOGIC (Updates every 60s)
        function updateCountdown() {
            if (!nextTargetStr || nextTargetStr === 'None') return;

            var target = new Date(nextTargetStr);
            var now = new Date();
            var diff = target - now;

            var el = document.getElementById('countdown-display');
            if (!el) return;

            if (diff <= 0) {
                el.innerHTML = "NOW";
                el.className = "countdown blinking";
                return;
            }

            var totalMinutes = Math.floor(diff / (1000 * 60));
            var hours = Math.floor(totalMinutes / 60);
            var minutes = totalMinutes % 60;

            // Format: "T- 1h 45m" or just "T- 45m" if less than an hour
            var timeText;
            if (hours > 0) {
                timeText = "T- " + hours + "h " + minutes + "m";
            } else {
                timeText = "T- " + minutes + "m";
            }
            el.innerHTML = timeText;
            
            // Blink if less than 5 minutes
            if (hours === 0 && minutes < 5) {
                el.className = "countdown blinking";
            } else {
                el.className = "countdown";
            }
        }

        function onWindowLoad() {
            waitForUpdate();
            
            // Align the update to the start of the next minute for precision
            var now = new Date();
            var secondsUntilNextMinute = 60 - now.getSeconds();
            
            updateCountdown(); // Run immediately on load
            
            setTimeout(function() {
                updateCountdown();
                setInterval(updateCountdown, 60000); // Run every 60s thereafter
            }, secondsUntilNextMinute * 1000);
        }

        // Cross-browser event listener
        if (window.addEventListener) {
            window.addEventListener('load', onWindowLoad, false);
        } else if (window.attachEvent) {
            window.attachEvent('onload', onWindowLoad);
        } else {
            window.onload = onWindowLoad;
        }
    </script>
    <style>
        body { 
            background: #000; 
            color: #fff; 
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; 
            text-align: center; 
            margin: 0; 
            padding: 20px; 
        }
        
        .container {
            display: table;
            width: 100%;
            height: 95vh;
            table-layout: fixed;
        }
        
        .header { 
            display: table-row;
            margin-bottom: 20px; 
            border-bottom: 2px solid #333; 
            padding-bottom: 20px; 
        }
        
        .header-content {
            display: table-cell;
            vertical-align: top;
            padding-bottom: 20px;
            border-bottom: 2px solid #333;
        }
        
        .goal { font-size: 2.5em; font-weight: bold; color: #fff; margin: 0; text-transform: uppercase; letter-spacing: 2px; }
        .reason { font-size: 1.4em; color: #888; margin-top: 10px; font-style: italic; }

        .cal-container { margin-top: 20px; text-align: center; }
        .cal-text { font-size: 1.5em; font-family: monospace; color: #0ff; display: inline-block; margin-right: 15px; }
        .cal-bar-bg { 
            width: 300px; 
            height: 10px; 
            background: #333; 
            border-radius: 5px; 
            overflow: hidden; 
            display: inline-block;
            vertical-align: middle;
            position: relative;
        }
        .cal-bar-fill { 
            height: 100%; 
            background: #0ff; 
            transition: width 0.5s;
            position: absolute;
            left: 0;
            top: 0;
        }
        .cal-bar-fill.warning { background: #f00; }

        .content { 
            display: table-row;
            height: 100%;
        }
        
        .content-cell {
            display: table-cell;
            vertical-align: top;
            padding-top: 20px;
        }
        
        .reminder { 
            font-size: 4em; 
            margin-bottom: 25px; 
            border-bottom: 1px solid #222; 
            padding-bottom: 20px; 
            position: relative;
        }
        .time { color: #f00; font-weight: bold; display: block; margin-bottom: 10px; }
        .desc { color: #ddd; }
        
        /* The Countdown Badge */
        .countdown {
            font-size: 0.4em; /* Relative to the huge 4em parent */
            color: #ff9900;
            display: block;
            margin-top: 10px;
            font-family: monospace;
            font-weight: bold;
        }
        .blinking { 
            -webkit-animation: blinker 1s linear infinite;
            -moz-animation: blinker 1s linear infinite;
            animation: blinker 1s linear infinite; 
            color: #f00; 
        }
        @-webkit-keyframes blinker { 50% { opacity: 0; } }
        @-moz-keyframes blinker { 50% { opacity: 0; } }
        @keyframes blinker { 50% { opacity: 0; } }

        .more { color: #555; font-size: 1.5em; margin-top: 50px; }
        .empty { color: #444; margin-top: 100px; font-size: 2em; }
        
        .status { position: fixed; bottom: 10px; right: 10px; width: 12px; height: 12px; border-radius: 50%; }
        .status.connected { 
            background: #004400; 
            -webkit-box-shadow: 0 0 5px #0f0; 
            -moz-box-shadow: 0 0 5px #0f0; 
            box-shadow: 0 0 5px #0f0; 
            opacity: 0.6; 
        }
        .status.disconnected { 
            background: #f00; 
            -webkit-box-shadow: 0 0 10px #f00; 
            -moz-box-shadow: 0 0 10px #f00; 
            box-shadow: 0 0 10px #f00; 
            opacity: 1; 
        }
        
        /* Better mobile support */
        @media (max-width: 768px) {
            body { padding: 10px; }
            .goal { font-size: 2em; }
            .reminder { font-size: 3em; }
            .cal-bar-bg { width: 200px; }
        }
    </style>
</head>
<body>
    <div class="container">
        {% if goal or reason or calorie_target %}
        <div class="header">
            <div class="header-content">
                {% if goal %}<div class="goal">{{ goal }}</div>{% endif %}
                {% if reason %}<div class="reason">{{ reason }}</div>{% endif %}
                
                {% if calorie_target %}
                <div class="cal-container">
                    <div class="cal-text">{{ calories_eaten }} / {{ calorie_target }} kcal</div>
                    <div class="cal-bar-bg">
                        <div class="cal-bar-fill {% if calories_eaten > calorie_target %}warning{% endif %}" 
                             style="width: {{ (calories_eaten / calorie_target * 100)|round|int }}%;"></div>
                    </div>
                </div>
                {% endif %}
            </div>
        </div>
        {% endif %}

        <div class="content">
            <div class="content-cell">
                {% if display_reminders %}
                    {% for r in display_reminders %}
                        <div class="reminder">
                            <span class="time">{{ r.time_str }}</span>
                            <span class="desc">{{ r.description }}</span>
                            
                            {% if loop.index0 == 0 %}
                                <span id="countdown-display" class="countdown">
                                {% if time_diff_minutes is not none %}
                                    {% if time_diff_minutes <= 0 %}
                                        NOW
                                    {% else %}
                                        T- 
                                        {% if time_diff_minutes >= 60 %}
                                            {{ (time_diff_minutes // 60)|int }}h {{ (time_diff_minutes % 60)|int }}m
                                        {% else %}
                                            {{ time_diff_minutes|int }}m
                                        {% endif %}
                                    {% endif %}
                                {% endif %}
                                </span>
                            {% endif %}
                        </div>
                    {% endfor %}
                {% else %}
                    <div class="empty">Nothing to endure right now.</div>
                {% endif %}

                {% if remaining_count > 0 %}
                    <div class="more">+ {{ remaining_count }} more items later</div>
                {% endif %}
            </div>
        </div>
    </div>

    <div id="status-dot" class="status connected" title="Connection Status"></div>
</body>
</html>
"""

HTML_EDIT = """
<!DOCTYPE html>
<html>
<head>
    <title>Edit Plan</title>
    <style>
        body { background: #111; color: #fff; font-family: monospace; margin: 0; }
        .container { height: 100vh; display: table; width: 100%; }
        form { display: table-cell; vertical-align: top; padding: 20px; }
        textarea { 
            width: 100%; 
            height: 80vh; 
            background: #222; 
            color: #0f0; 
            border: 1px solid #444; 
            padding: 15px; 
            font-size: 16px; 
            font-family: monospace; 
            resize: none;
            box-sizing: border-box;
        }
        .bar { padding: 10px 0; text-align: right; }
        button { 
            padding: 10px 30px; 
            background: #0066cc; 
            color: white; 
            border: none; 
            font-size: 16px; 
            cursor: pointer; 
        }
        button:hover { background: #0088ee; }
    </style>
</head>
<body>
    <div class="container">
        <form method="POST">
            <div class="bar">
                <button type="submit" name="save">Save Changes</button>
            </div>
            <textarea name="content" spellcheck="false">{{ content }}</textarea>
        </form>
    </div>
</body>
</html>
"""

# --- HELPER FUNCTIONS ---

def calculate_hash(content):
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def get_file_content_safe():
    if not os.path.exists(REMINDERS_FILE):
        return DEFAULT_CONTENT
    with open(REMINDERS_FILE, 'r') as f:
        content = f.read()
        return content if content.strip() else DEFAULT_CONTENT

def extract_calories(text):
    match = re.search(r'\b(\d+)\s*(?:k?cal)\b', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 0

def parse_file():
    if not os.path.exists(REMINDERS_FILE):
        return None, None, None, 0, []
    
    with open(REMINDERS_FILE, 'r') as f:
        lines = f.readlines()
    
    reminders = []
    goal = None
    reason = None
    calorie_target = None
    calories_eaten = 0
    now = datetime.now()
    
    for line in lines:
        line = line.strip()
        if not line: continue

        lower_line = line.lower()
        if lower_line.startswith('goal:'):
            goal = line.split(':', 1)[1].strip()
            continue
        if lower_line.startswith('reason:'):
            reason = line.split(':', 1)[1].strip()
            continue
        if lower_line.startswith('calorie target:') or lower_line.startswith('calories:'):
            try:
                target_str = line.split(':', 1)[1].strip()
                target_digits = re.sub(r'[^\d]', '', target_str)
                if target_digits:
                    calorie_target = int(target_digits)
            except ValueError:
                pass
            continue

        if line.startswith('#') or '|' not in line:
            continue
        
        time_str, description = line.split('|', 1)
        time_str = time_str.strip()
        description = description.strip()
        
        item_cals = extract_calories(description)
        
        try:
            reminder_time = datetime.strptime(time_str, '%H:%M').replace(
                year=now.year, month=now.month, day=now.day
            )
            
            if reminder_time <= now:
                calories_eaten += item_cals
            else:
                reminders.append({
                    'time': reminder_time,
                    'time_str': time_str,
                    'description': description,
                })
        except ValueError:
            continue
    
    return goal, reason, calorie_target, calories_eaten, sorted(reminders, key=lambda x: x['time'])

# --- API ROUTES ---

@app.route('/api/poll')
def api_poll():
    client_hash = request.args.get('hash')
    timeout = 30
    
    current_content = get_file_content_safe()
    current_hash = calculate_hash(current_content)
    
    if current_hash != client_hash:
        return jsonify({'changed': True, 'hash': current_hash})

    with update_condition:
        update_condition.wait(timeout=timeout)
    
    current_content = get_file_content_safe()
    current_hash = calculate_hash(current_content)
    
    if current_hash != client_hash:
        return jsonify({'changed': True, 'hash': current_hash})
        
    return jsonify({'changed': False})

@app.route('/api/reminders', methods=['GET', 'POST'])
def api_reminders():
    content = get_file_content_safe()

    if request.method == 'GET':
        return jsonify({'content': content, 'hash': calculate_hash(content)})

    if request.method == 'POST':
        data = request.json
        if not data: return jsonify({'error': 'No JSON data'}), 400

        new_content = data.get('content', '')
        client_hash = data.get('hash')
        current_hash = calculate_hash(content)

        if client_hash and client_hash != current_hash:
            return jsonify({'current_content': content}), 409
            
        with open(REMINDERS_FILE, 'w') as f:
            f.write(new_content)
        
        with update_condition:
            update_condition.notify_all()
            
        return jsonify({'status': 'success'})

# --- BROWSER ROUTES ---

@app.route('/')
def index():
    goal, reason, calorie_target, calories_eaten, reminders = parse_file()
    display_reminders = reminders[:3] if reminders else []
    remaining_count = max(0, len(reminders) - 3)
    
    current_content = get_file_content_safe()
    page_hash = calculate_hash(current_content)
    
    next_target = None
    time_diff_minutes = None

    if reminders:
        next_event = reminders[0]['time']
        next_target = next_event.isoformat()
        
        # Calculate time diff for server-side render
        now = datetime.now()
        diff = next_event - now
        total_seconds = diff.total_seconds()
        
        if total_seconds > 0:
            time_diff_minutes = int(total_seconds // 60)
        else:
            time_diff_minutes = 0

    return render_template_string(HTML_INDEX, 
                                goal=goal,
                                reason=reason,
                                calorie_target=calorie_target,
                                calories_eaten=calories_eaten,
                                display_reminders=display_reminders,
                                remaining_count=remaining_count,
                                page_hash=page_hash,
                                next_target=next_target,
                                time_diff_minutes=time_diff_minutes)

@app.route('/edit', methods=['GET', 'POST'])
def edit():
    if request.method == 'POST' and 'save' in request.form:
        content = request.form.get('content', '')
        with open(REMINDERS_FILE, 'w') as f:
            f.write(content)
        
        with update_condition:
            update_condition.notify_all()
            
        return redirect(url_for('edit'))
    
    content = get_file_content_safe()
    return render_template_string(HTML_EDIT, content=content)

# --- MAIN ---

def main():
    parser = argparse.ArgumentParser(description="Endure Server")
    parser.add_argument('--host', default='0.0.0.0', help='Host IP')
    parser.add_argument('--port', type=int, default=5000, help='Port')
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    args = parser.parse_args()

    print("Starting Endurance Server on http://{}:{}".format(args.host, args.port))
    app.run(debug=args.debug, host=args.host, port=args.port, threaded=True)

if __name__ == '__main__':
    main()