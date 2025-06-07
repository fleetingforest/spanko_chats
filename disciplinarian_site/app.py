from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
import uuid
from passlib.hash import pbkdf2_sha256
import firebase_admin
from firebase_admin import credentials, firestore, storage
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
# Use the same credentials file as the main app, assuming execution from project root
cred_path = "spanking-chat-firebase-adminsdk-fbsvc-e7307d7abb.json" # Changed path
db = None # Initialize db to None in case initialization fails
bucket = None # Initialize bucket to None

try:
    cred = credentials.Certificate(cred_path)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {
            'storageBucket': 'spanking-chat.firebasestorage.app'
        })
    db = firestore.client()
    bucket = storage.bucket() # bucket is used by other parts of the app, so initialize it
except Exception as e:
    app.logger.error(f"Failed to initialize Firebase: {e}. Running without Firebase.")
    # The app will proceed without db, and functions using db will need to handle db being None
    # or raise errors. For this specific request, we aim to use the main DB.
    # If Firebase is critical, the app should ideally not run or have a more robust error handling.

# ----- Helper functions -----
def register_user(email, password):
    """Register a new user in Firestore using the 'users' collection."""
    if not db:
        return False, "Database not available"
    user_ref = db.collection('users').document(email) # Changed collection to 'users'
    if user_ref.get().exists:
        return False, "Email already registered"
    hashed_password = pbkdf2_sha256.hash(password)
    user_ref.set({
        'email': email,
        'password': hashed_password,
        'active': True,  # Added field
        'fs_uniquifier': str(uuid.uuid4()),  # Added field
        'roles': ['user'],  # Added field
        'created_at': firestore.SERVER_TIMESTAMP
    })
    return True, "Registration successful"

def login_user(email, password):
    """Validate user credentials against the 'users' collection."""
    if not db:
        return False, "Database not available"
    user_ref = db.collection('users').document(email) # Changed collection to 'users'
    doc = user_ref.get()
    if not doc.exists:
        return False, "User not found"
    user_data = doc.to_dict()
    # Check password and if user is active
    if user_data and pbkdf2_sha256.verify(password, user_data.get('password')) and user_data.get('active', False): # Added check for user_data
        session['user_email'] = email
        session['fs_uniquifier'] = user_data.get('fs_uniquifier') # Added to session
        return True, "Login successful"
    return False, "Invalid credentials or user inactive"

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

@app.route('/logout') # Add this new route
def logout():
    session.pop('user_email', None)
    session.pop('fs_uniquifier', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

# ----- Data Endpoints -----
def _get_profile(email):
    if not db: return {}
    profile_doc = db.collection('discipline_profiles').document(email).get() # Corrected variable name
    return profile_doc.to_dict() if profile_doc.exists else {} # Corrected variable name

def _update_profile(email, fields): # Corrected function definition
    if not db: return
    db.collection('discipline_profiles').document(email).update(fields) # Corrected indentation

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
    try:
        if 'user_email' not in session:
            return jsonify({'error': 'Unauthorized - No user session'}), 401
        
        if not request.is_json:
            return jsonify({'error': 'Invalid request: Content-Type must be application/json'}), 400
            
        data = request.get_json()
        if not data: # Handles cases where request.is_json is true but data is null (e.g. empty body)
            return jsonify({'error': 'Invalid request: No JSON data received'}), 400

        message = data.get('message')
        if not message:
            return jsonify({'error': 'Invalid request: No message provided in JSON payload'}), 400

        email = session['user_email']
        
        profile_ref = None
        profile = {} # Initialize profile
        if db:
            profile_ref = db.collection('discipline_profiles').document(email)
            profile_doc = profile_ref.get()
            profile = profile_doc.to_dict() if profile_doc.exists else {}
        # else: # Removed in-memory fallback
            # profile = in_memory_db['discipline_profiles'].get(email, {}) # Removed in-memory_db reference

        if not profile: # Should not happen if user is logged in and profile created at signup
            return jsonify({'error': 'User profile not found'}), 500

        conversation = profile.get('history', [])
        user_name = profile.get('user_name', 'the user') # Get user_name from profile
        user_gender = profile.get('user_gender', 'unknown gender') # Get user_gender from profile

        disciplinarian_config = profile.get('disciplinarian')
        if not isinstance(disciplinarian_config, dict):
            disciplinarian_config = {
                'name': "Disciplinarian", 
                'age': "an unspecified age", 
                'gender': "an unspecified gender",
                'personality': "standard", 
                'strictness': "moderate", 
                'punishments': []
            }

        system_prompt = generate_system_prompt(disciplinarian_config, user_name, user_gender)
        
        if not conversation:
            conversation.append({'role': 'system', 'content': system_prompt})
        elif conversation[0]['role'] == 'system':
            if conversation[0]['content'] != system_prompt:
                conversation[0]['content'] = system_prompt
        else: 
            conversation.insert(0, {'role': 'system', 'content': system_prompt})
            
        conversation.append({'role': 'user', 'content': message})

        reply_content = ""
        if fireworks_client:
            try:
                response = fireworks_client.chat.completions.create(
                    model="accounts/fireworks/models/deepseek-v3-0324",
                    messages=conversation
                )
                reply_content = response.choices[0].message.content
            except Exception as e:
                app.logger.error(f"Fireworks API error: {e}")
                reply_content = "Sorry, I encountered an error trying to communicate with the AI model."
                # Optionally, you could return a 500 error here if the AI call is critical
                # return jsonify({'error': 'AI service unavailable'}), 503
        else:
            reply_content = f"(AI response placeholder) You said: {message}"
        
        conversation.append({'role': 'assistant', 'content': reply_content})

        if db and profile_ref:
            profile_ref.update({'history': conversation})
        # elif email in in_memory_db['discipline_profiles']: # Removed in-memory_db reference
            # in_memory_db['discipline_profiles'][email]['history'] = conversation # Removed in-memory_db reference
        # else: # Removed in-memory_db reference
            # app.logger.error(f"Profile for {email} disappeared before history update (in-memory).") # Removed in-memory_db reference

        return jsonify({'reply': reply_content})

    except Exception as e:
        app.logger.error(f"Unhandled exception in /chat: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected server error occurred.'}), 500

# Utility to build system prompt from disciplinarian config
def generate_system_prompt(config, user_name, user_gender):
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
        f"You are interacting with {user_name}, who is {user_gender}. "
        "Your goal is to discipline and support the user with firm but caring guidance. "
        "If the user breaks established rules you must assign an appropriate punishment from the list of available punishments."
    )
    return prompt

if __name__ == '__main__':
    app.run(debug=True)
