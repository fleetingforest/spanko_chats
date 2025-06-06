from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
import uuid
from passlib.hash import pbkdf2_sha256
import firebase_admin
from firebase_admin import credentials, firestore
from openai import OpenAI

app = Flask(__name__)
app.secret_key = os.getenv("DISCIPLINE_SECRET", "discipline-secret-key")

# Initialize Fireworks AI client
fireworks_api_key = os.getenv("FIREWORKS_API_KEY")
if fireworks_api_key:
    fireworks_client = OpenAI(
        api_key=fireworks_api_key,
        base_url="https://api.fireworks.ai/inference/v1"
    )
else:
    fireworks_client = None

# Initialize Firebase
firebase_credentials = os.getenv("FIREBASE_CREDENTIALS", "spanking-chat-firebase-adminsdk-fbsvc-e7307d7abb.json")
if os.path.exists(firebase_credentials):
    cred = credentials.Certificate(firebase_credentials)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
else:
    db = None  # Fall back to in-memory store when credentials are missing
    in_memory_db = {
        'discipline_users': {},
        'discipline_profiles': {}
    }

# ----- Helper functions -----
def register_user(email, password):
    """Register a new user either in Firestore or the in-memory store."""
    if db:
        user_ref = db.collection('discipline_users').document(email)
        if user_ref.get().exists:
            return False, "Email already registered"
        hashed = pbkdf2_sha256.hash(password)
        user_ref.set({
            'email': email,
            'password': hashed,
            'created_at': firestore.SERVER_TIMESTAMP
        })
    else:
        if email in in_memory_db['discipline_users']:
            return False, "Email already registered"
        hashed = pbkdf2_sha256.hash(password)
        in_memory_db['discipline_users'][email] = {
            'email': email,
            'password': hashed
        }
    return True, "Registration successful"

def login_user(email, password):
    """Validate user credentials."""
    if db:
        user_ref = db.collection('discipline_users').document(email)
        doc = user_ref.get()
        if not doc.exists:
            return False, "User not found"
        data = doc.to_dict()
    else:
        data = in_memory_db['discipline_users'].get(email)
        if not data:
            return False, "User not found"
    if pbkdf2_sha256.verify(password, data['password']):
        session['user_email'] = email
        return True, "Login successful"
    return False, "Invalid credentials"

# ----- Routes -----
@app.route('/', methods=['GET', 'POST'])
def landing():
    if request.method == 'POST':
        # Save user configuration to session
        session['user_name'] = request.form.get('name')
        session['user_gender'] = request.form.get('gender')
        disciplinarian = {
            'name': request.form.get('d_name'),
            'gender': request.form.get('d_gender'),
            'age': request.form.get('d_age'),
            'personality': request.form.get('d_personality'),
            'strictness': request.form.get('strictness'),
            'punishments': request.form.getlist('punishments')
        }
        session['disciplinarian'] = disciplinarian
        return redirect(url_for('signup'))
    return render_template('landing.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        success, message = register_user(email, password)
        if success:
            session['user_email'] = email
            profile = {
                'user_name': session.get('user_name'),
                'user_gender': session.get('user_gender'),
                'disciplinarian': session.get('disciplinarian'),
                'rules': [],
                'punishments': [],
                'history': [],
                'todos': []
            }
            if db:
                db.collection('discipline_profiles').document(email).set(profile)
            else:
                in_memory_db['discipline_profiles'][email] = profile
            return redirect(url_for('dashboard'))
        flash(message)
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        success, message = login_user(email, password)
        if success:
            return redirect(url_for('dashboard'))
        flash(message)
    return render_template('login_user.html')

@app.route('/dashboard')
def dashboard():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

# ----- Data Endpoints -----
def _get_profile(email):
    if db:
        doc = db.collection('discipline_profiles').document(email).get()
        return doc.to_dict() if doc.exists else {}
    return in_memory_db['discipline_profiles'].get(email, {})

def _update_profile(email, fields):
    if db:
        db.collection('discipline_profiles').document(email).update(fields)
    else:
        in_memory_db['discipline_profiles'][email].update(fields)

@app.route('/data/history')
def get_history():
    if 'user_email' not in session:
        return jsonify([]), 401
    profile = _get_profile(session['user_email'])
    return jsonify(profile.get('history', []))

@app.route('/data/rules')
def get_rules():
    if 'user_email' not in session:
        return jsonify([]), 401
    profile = _get_profile(session['user_email'])
    return jsonify(profile.get('rules', []))

@app.route('/data/rules', methods=['POST'])
def add_rule():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    rule = request.json.get('rule')
    if not rule:
        return jsonify({'error': 'No rule provided'}), 400
    profile = _get_profile(session['user_email'])
    rules = profile.get('rules', [])
    rules.append(rule)
    _update_profile(session['user_email'], {'rules': rules})
    return jsonify({'status': 'ok'})

@app.route('/data/punishments')
def get_punishments():
    if 'user_email' not in session:
        return jsonify([]), 401
    profile = _get_profile(session['user_email'])
    return jsonify(profile.get('punishments', []))

@app.route('/data/punishments', methods=['POST'])
def add_punishment():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    punishment = request.json.get('punishment')
    if not punishment:
        return jsonify({'error': 'No punishment provided'}), 400
    profile = _get_profile(session['user_email'])
    punishments = profile.get('punishments', [])
    punishments.append({'text': punishment, 'completed': False})
    _update_profile(session['user_email'], {'punishments': punishments})
    return jsonify({'status': 'ok'})

@app.route('/data/todos')
def get_todos():
    if 'user_email' not in session:
        return jsonify([]), 401
    profile = _get_profile(session['user_email'])
    return jsonify(profile.get('todos', []))

@app.route('/data/todos', methods=['POST'])
def add_todo():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    item = request.json.get('item')
    if not item:
        return jsonify({'error': 'No item provided'}), 400
    profile = _get_profile(session['user_email'])
    todos = profile.get('todos', [])
    todos.append({'text': item, 'completed': False})
    _update_profile(session['user_email'], {'todos': todos})
    return jsonify({'status': 'ok'})

# Chat endpoint using Fireworks DeepSeek model
@app.route('/chat', methods=['POST'])
def chat():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    message = request.json.get('message')
    email = session['user_email']
    
    profile_ref = None
    if db:
        profile_ref = db.collection('discipline_profiles').document(email)
        profile_doc = profile_ref.get()
        profile = profile_doc.to_dict() if profile_doc.exists else {}
    else:
        profile = in_memory_db['discipline_profiles'].get(email, {})
    
    conversation = profile.get('history', [])

    disciplinarian_config = profile.get('disciplinarian')
    if not isinstance(disciplinarian_config, dict):
        # Fallback to a very generic disciplinarian if config is missing or invalid
        disciplinarian_config = {
            'name': "Disciplinarian", 
            'age': "an unspecified age", 
            'gender': "an unspecified gender",
            'personality': "standard", 
            'strictness': "moderate", 
            'punishments': []
        }

    system_prompt = generate_system_prompt(disciplinarian_config)
    if not conversation or (conversation[0]['role'] == 'system' and conversation[0]['content'] != system_prompt):
        # Update system prompt if it's new or changed
        if conversation and conversation[0]['role'] == 'system':
            conversation[0]['content'] = system_prompt
        else:
            conversation.insert(0, {'role': 'system', 'content': system_prompt})
    elif not conversation: # Should be caught by above, but as a safeguard
        conversation.append({'role': 'system', 'content': system_prompt})
        
    conversation.append({'role': 'user', 'content': message})

    if fireworks_client:
        try:
            response = fireworks_client.chat.completions.create(
                model="accounts/fireworks/models/deepseek-coder-6.7b-instruct", # Example model, adjust as needed
                messages=conversation
            )
            reply = response.choices[0].message.content
        except Exception as e:
            # Log the error e
            reply = "Sorry, I encountered an error trying to respond."
    else:
        reply = f"(AI response placeholder) You said: {message}"  # Fallback when no API key
    
    conversation.append({'role': 'assistant', 'content': reply})

    if db and profile_ref:
        profile_ref.update({'history': conversation})
    else:
        in_memory_db['discipline_profiles'][email]['history'] = conversation
    return jsonify({'reply': reply})

# Utility to build system prompt from disciplinarian config
def generate_system_prompt(config):
    if not isinstance(config, dict):
        config = {} # Ensure config is a dictionary

    name = config.get('name') or "Your Disciplinarian"
    age = str(config.get('age') or "an unspecified age") # Ensure age is string for f-string
    gender = config.get('gender') or "an unspecified gender"
    personality = config.get('personality') or "a standard"
    strictness = config.get('strictness') or "moderate"
    
    punishments_list = config.get('punishments', [])
    if isinstance(punishments_list, list) and punishments_list:
        punishments_str = ', '.join(punishments_list)
    else:
        punishments_str = "not specified"

    prompt = (
        f"You are {name}, a {age}-year-old {gender} disciplinarian. "
        f"Your personality is {personality} and your strictness level is {strictness}. "
        f"You believe in punishments such as: {punishments_str}. "
        "Your goal is to discipline and support the user with firm but caring guidance. "
        "If the user breaks established rules you must assign an appropriate punishment from the list of available punishments."
    )
    return prompt

if __name__ == '__main__':
    app.run(debug=True)
