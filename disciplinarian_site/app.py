from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, stream_with_context, Response
import firebase_admin
from firebase_admin import credentials, firestore, auth, storage
from openai import OpenAI as FireworksOpenAI # Renamed to avoid conflict if another OpenAI client is used
import os
from datetime import datetime, timezone
import uuid # For generating unique chat IDs
from passlib.hash import pbkdf2_sha256
import re # Added import for regular expressions
import requests # For DeepInfra API call
import json # For parsing AI response
import sys # For sys.stdout.flush()
import time # Added for token rate limiting

app = Flask(__name__)
app.secret_key = os.getenv("DISCIPLINE_SECRET", "discipline-secret-key")


# Initialize Fireworks AI Client
fireworks_api_key = os.getenv("FIREWORKS_API_KEY")
if fireworks_api_key:
    fireworks_client = FireworksOpenAI(
        api_key=fireworks_api_key,
        base_url="https://api.fireworks.ai/inference/v1"
    )
else:
    fireworks_client = None
    print("Warning: FIREWORKS_API_KEY not found. AI chat functionality will be disabled.")

# Configuration for DeepInfra
DEEPINFRA_API_KEY = os.environ.get("DEEPINFRA_API_KEY")
# User should verify/set this to the specific "Deepseek R1 05-28" model identifier on DeepInfra.
# Using a common Deepseek model as a placeholder.
DEEPINFRA_MODEL_NAME = os.environ.get("DEEPINFRA_MODEL_NAME", "deepseek-ai/DeepSeek-R1-Turbo")


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
def format_ai_response_text(text):
    """Formats AI response text to convert markdown-like bold/italics to HTML,
    and capitalizes the first letter only after sentence-ending punctuation or newlines."""
    import re
    
    # Replace **text** with <b>Text</b> (non-greedy), only capitalizing after sentence-ending punctuation or newlines
    def format_bold(match):
        content = match.group(1)
        if not content:
            return "<b></b>"
        
        # Check what comes before the match
        start_pos = match.start()
        before_match = text[:start_pos]
        should_capitalize = start_pos == 0 or re.search(r'[.!?\n]\s*$', before_match)
        
        if should_capitalize:
            return f"<b>{content[0].upper() + content[1:] if len(content) > 0 else ''}</b>"
        else:
            return f"<b>{content}</b>"
    
    # Replace *text* with <i>Text</i> - only match if both asterisks are present
    def format_italic(match):
        content = match.group(1)
        if not content:
            return "<i></i>"
        
        # Check what comes before the match
        start_pos = match.start()
        before_match = text[:start_pos]
        should_capitalize = start_pos == 0 or re.search(r'[.!?\n]\s*$', before_match)
        
        if should_capitalize:
            return f"<i>{content[0].upper() + content[1:] if len(content) > 0 else ''}</i>"
        else:
            return f"<i>{content}</i>"
    
    # First handle bold (double asterisks)
    text = re.sub(r'\*\*([^*]+?)\*\*', format_bold, text)
    # Then handle italics - only match complete pairs of single asterisks
    # Use word boundaries to be more conservative
    text = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', format_italic, text)
    
    return text

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

# Helper function to get user profile, with history migration/initialization
def _get_profile(email):
    if not db: return {}
    profile_ref = db.collection('discipline_profiles').document(email)
    profile_doc = profile_ref.get()
    if not profile_doc.exists:
        # Create a default profile if it doesn't exist
        default_profile = {
            'email': email,
            'user_name': 'User', # Default name
            'history': [],
            'rules': [],
            'punishments': [],
            'todos': [],
            'disciplinarian': {
                'name': "Disciplinarian", 'age': "an unspecified age", 
                'gender': "an unspecified gender", 'personality': "standard", 
                'strictness': "moderate", 'punishments': []
            },
            'created_at': datetime.now(timezone.utc)
        }
        profile_ref.set(default_profile)
        return default_profile
    
    profile_data = profile_doc.to_dict()

    # History migration and initialization
    history = profile_data.get('history')
    if history is None:
        profile_data['history'] = []
    elif isinstance(history, list) and (not history or (isinstance(history[0], dict) and 'role' in history[0] and 'id' not in history[0])):
        # Old format: flat list of messages, needs migration
        if history: # Only migrate if there are messages
            legacy_chat_id = str(uuid.uuid4())
            profile_data['history'] = [{
                'id': legacy_chat_id,
                'name': 'Legacy Chat',
                'messages': history,
                'created_at': datetime.now(timezone.utc).isoformat()
            }]
        else:
            profile_data['history'] = []
    # Ensure all history items are dicts and have 'created_at' (add if missing for older migrated items)
    migrated_history = []
    for item in profile_data.get('history', []):
        if isinstance(item, dict):
            if 'created_at' not in item:
                item['created_at'] = datetime.now(timezone.utc).isoformat()
            if 'id' not in item: # Should not happen if migration above worked, but as a safeguard
                item['id'] = str(uuid.uuid4())
            if 'name' not in item:
                item['name'] = f"Chat {item['id'][:8]}"
            if 'messages' not in item:
                item['messages'] = []
            migrated_history.append(item)
    profile_data['history'] = sorted(migrated_history, key=lambda x: x['created_at'], reverse=True)

    return profile_data

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
    
    email = session['user_email']
    profile = _get_profile(email) # Fetch the profile
    
    user_display_name = profile.get('user_name', 'User') # Get user's name from profile
    disciplinarian_config = profile.get('disciplinarian', {})
    ai_display_name = disciplinarian_config.get('name', "Disciplinarian") # Get AI's name

    # The initialization of active_chat_id will be handled by the frontend
    # calling /data/active_chat_session on load.
    return render_template('dashboard.html', 
                           user_name=user_display_name, 
                           ai_name=ai_display_name) # Pass both names

# ----- Data Endpoints -----
def _get_profile(email):
    if not db: return {}
    profile_ref = db.collection('discipline_profiles').document(email)
    profile_doc = profile_ref.get()
    if not profile_doc.exists:
        # Create a default profile if it doesn't exist
        default_profile = {
            'email': email,
            'user_name': 'User', # Default name
            'history': [],
            'rules': [],
            'punishments': [],
            'todos': [],
            'disciplinarian': {
                'name': "Disciplinarian", 'age': "an unspecified age", 
                'gender': "an unspecified gender", 'personality': "standard", 
                'strictness': "moderate", 'punishments': []
            },
            'created_at': datetime.now(timezone.utc)
        }
        profile_ref.set(default_profile)
        return default_profile
    
    profile_data = profile_doc.to_dict()

    # History migration and initialization
    history = profile_data.get('history')
    if history is None:
        profile_data['history'] = []
    elif isinstance(history, list) and (not history or (isinstance(history[0], dict) and 'role' in history[0] and 'id' not in history[0])):
        # Old format: flat list of messages, needs migration
        if history: # Only migrate if there are messages
            legacy_chat_id = str(uuid.uuid4())
            profile_data['history'] = [{
                'id': legacy_chat_id,
                'name': 'Legacy Chat',
                'messages': history,
                'created_at': datetime.now(timezone.utc).isoformat()
            }]
        else:
            profile_data['history'] = []
    # Ensure all history items are dicts and have 'created_at' (add if missing for older migrated items)
    migrated_history = []
    for item in profile_data.get('history', []):
        if isinstance(item, dict):
            if 'created_at' not in item:
                item['created_at'] = datetime.now(timezone.utc).isoformat()
            if 'id' not in item: # Should not happen if migration above worked, but as a safeguard
                item['id'] = str(uuid.uuid4())
            if 'name' not in item:
                item['name'] = f"Chat {item['id'][:8]}"
            if 'messages' not in item:
                item['messages'] = []
            migrated_history.append(item)
    profile_data['history'] = sorted(migrated_history, key=lambda x: x['created_at'], reverse=True)

    return profile_data

def _update_profile(email, fields):
    if not db: return
    # Ensure 'history' is sorted before saving if it's part of fields
    if 'history' in fields and isinstance(fields['history'], list):
        # Ensure all history items are dicts and have 'created_at'
        processed_history = []
        for item in fields['history']:
            if isinstance(item, dict):
                if 'created_at' not in item:
                    # Add a default created_at if missing, though this should be rare
                    item['created_at'] = datetime.now(timezone.utc).isoformat()
                processed_history.append(item)
        fields['history'] = sorted(processed_history, key=lambda x: x.get('created_at', ''), reverse=True)
    db.collection('discipline_profiles').document(email).update(fields)

@app.route('/data/active_chat_session', methods=['GET'])
def get_active_chat_session():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    email = session['user_email']
    profile = _get_profile(email)
    user_history = profile.get('history', [])

    active_chat_id = session.get('active_chat_id')
    active_chat = None

    if active_chat_id:
        active_chat = next((chat for chat in user_history if chat['id'] == active_chat_id), None)

    if not active_chat:
        if user_history: # Default to the most recent chat
            active_chat = user_history[0] # Assumes history is sorted newest first
        else: # No chats exist, create a new one
            new_chat_id = str(uuid.uuid4())
            active_chat = {
                'id': new_chat_id,
                'name': 'New Chat', # Will be updated after first message
                'messages': [],
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            user_history.insert(0, active_chat) # Add to beginning
            profile['history'] = user_history
            _update_profile(email, {'history': user_history})
        session['active_chat_id'] = active_chat['id']
    
    return jsonify(active_chat)

@app.route('/data/history_list', methods=['GET'])
def get_history_list():
    if 'user_email' not in session:
        return jsonify([]), 401
    profile = _get_profile(session['user_email'])
    history_summary = [
        {'id': chat['id'], 'name': chat.get('name', f"Chat {chat['id'][:8]}"), 'created_at': chat['created_at']}
        for chat in profile.get('history', [])
    ]
    return jsonify(sorted(history_summary, key=lambda x: x['created_at'], reverse=True))

@app.route('/select_chat_session/<chat_id>', methods=['POST'])
def select_chat_session(chat_id):
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    email = session['user_email']
    profile = _get_profile(email)
    user_history = profile.get('history', [])
    
    selected_chat = next((chat for chat in user_history if chat['id'] == chat_id), None)
    
    if selected_chat:
        session['active_chat_id'] = chat_id
        return jsonify(selected_chat)
    return jsonify({'error': 'Chat not found'}), 404

@app.route('/new_chat_session', methods=['POST'])
def new_chat_session():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    email = session['user_email']
    profile = _get_profile(email)
    user_history = profile.get('history', [])

    new_chat_id = str(uuid.uuid4())
    initial_messages = []

    # Generate AI's first message
    user_name = profile.get('user_name', 'the user')
    user_gender = profile.get('user_gender', 'unknown gender')
    disciplinarian_config = profile.get('disciplinarian', {})
    system_prompt = generate_system_prompt(disciplinarian_config, user_name, user_gender, profile)
    
    ai_first_message_content = f"(AI response placeholder) Hello {user_name}, I am {disciplinarian_config.get('name', 'Disciplinarian')}. How can I assist you today?"

    if fireworks_client:
        try:
            # Instruct AI to introduce itself and start the conversation
            messages_for_ai_initiation = [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': "Please introduce yourself and start our interaction based on your persona."}
            ]
            response = fireworks_client.chat.completions.create(
                model="accounts/fireworks/models/deepseek-v3-0324", # Main chat model
                messages=messages_for_ai_initiation,
                max_tokens=300, # Limit initial message length
                temperature=0.7
            )
            raw_ai_first_message = response.choices[0].message.content
            ai_first_message_content = format_ai_response_text(raw_ai_first_message) # Format the response
        except Exception as e:
            app.logger.error(f"Fireworks API error during new chat initiation: {e}")
            ai_first_message_content = "I'm ready to chat, but there was a slight hiccup starting up. Let's begin!"

    initial_messages.append({'role': 'assistant', 'content': ai_first_message_content})

    new_chat = {
        'id': new_chat_id,
        'name': 'New Chat', # Will be updated by AI after first user message if logic remains in /chat
        'messages': initial_messages,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    user_history.insert(0, new_chat) # Add to the beginning (most recent)
    _update_profile(email, {'history': user_history})
    session['active_chat_id'] = new_chat_id
    
    return jsonify(new_chat)

@app.route('/delete_chat_session/<chat_id>', methods=['POST'])
def delete_chat_session(chat_id):
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    email = session['user_email']
    profile = _get_profile(email)
    user_history = profile.get('history', [])

    chat_to_delete_index = -1
    for i, chat in enumerate(user_history):
        if chat['id'] == chat_id:
            chat_to_delete_index = i
            break

    if chat_to_delete_index == -1:
        return jsonify({'error': 'Chat not found'}), 404

    # Remove the chat
    user_history.pop(chat_to_delete_index)
    # No need to set profile['history'] = user_history here, _update_profile will use the modified list
    
    if session.get('active_chat_id') == chat_id:
        session.pop('active_chat_id', None)

    _update_profile(email, {'history': user_history}) # Pass the modified list directly
    
    return jsonify({'message': 'Chat session deleted successfully'}), 200


@app.route('/chat', methods=['POST'])
def chat():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized stream init'}), 401

    email = session['user_email']
    data = request.json
    message_content = data.get('message')

    if not message_content:
        return jsonify({'error': 'No message provided for stream init'}), 400

    profile = _get_profile(email)
    user_history = profile.get('history', [])
    active_chat_id = session.get('active_chat_id')
    active_conversation_obj = None

    if active_chat_id:
        active_conversation_obj = next((conv for conv in user_history if conv['id'] == active_chat_id), None)

    if not active_conversation_obj:
        # This case should ideally be handled by the frontend ensuring active_chat_id is set
        # or by redirecting to start a new chat if no active_chat_id.
        # For robustness, if we reach here, it implies an issue with session or chat creation.
        # Creating a new chat here might lead to unexpected behavior if client isn't aware.
        app.logger.error(f"Chat called without a valid active_conversation_obj for user {email}, active_chat_id: {active_chat_id}")
        # Attempt to create/select one, similar to get_active_chat_session logic
        if user_history:
            active_conversation_obj = user_history[0]
            session['active_chat_id'] = active_conversation_obj['id']
        else:
            # If no history, a new chat should have been made via /new_chat_session or /data/active_chat_session
            # This is a fallback, ideally should not be hit if client flow is correct.
            new_id = str(uuid.uuid4())
            active_conversation_obj = {
                'id': new_id, 'name': 'New Chat', 'messages': [],
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            # Generate AI's first message for this implicitly created new chat
            user_name_for_init = profile.get('user_name', 'the user')
            user_gender_for_init = profile.get('user_gender', 'unknown gender')
            disciplinarian_config_for_init = profile.get('disciplinarian', {})
            system_prompt_for_init = generate_system_prompt(disciplinarian_config_for_init, user_name_for_init, user_gender_for_init, profile)
            ai_first_message_content_init = f"(AI response placeholder) Hello {user_name_for_init}. Let's chat."
            if fireworks_client:
                try:
                    messages_for_ai_initiation = [
                        {'role': 'system', 'content': system_prompt_for_init},
                        {'role': 'user', 'content': "Please introduce yourself and start our interaction based on your persona."}
                    ]
                    response_init = fireworks_client.chat.completions.create(
                        model="accounts/fireworks/models/deepseek-v3-0324",
                        messages=messages_for_ai_initiation, max_tokens=150, temperature=0.7
                    )
                    raw_ai_first_message_init = response_init.choices[0].message.content
                    ai_first_message_content_init = format_ai_response_text(raw_ai_first_message_init)
                except Exception as e_init:
                    app.logger.error(f"Fireworks API error during implicit new chat initiation: {e_init}")
            active_conversation_obj['messages'].append({'role': 'assistant', 'content': ai_first_message_content_init})
            user_history.insert(0, active_conversation_obj)
            session['active_chat_id'] = new_id
            # _update_profile(email, {'history': user_history}) # Will be updated after current message exchange

    current_messages = list(active_conversation_obj.get('messages', [])) # Make a mutable copy
    current_messages.append({'role': 'user', 'content': message_content})
    
    conversation_name_updated = False
    # AI Naming Logic
    # Check if it's the first user message after AI's intro (i.e., messages list has AI intro, then this user message)
    # A "New Chat" from /new_chat_session has one 'assistant' message.
    # So, after user adds their first message, length is 2.
    if len(current_messages) == 2 and active_conversation_obj.get('name') == 'New Chat' and current_messages[0]['role'] == 'assistant' and current_messages[1]['role'] == 'user':
        first_user_msg_for_naming = message_content
        if fireworks_client:
            try:
                naming_prompt_messages = [
                    {'role': 'system', 'content': 'You are a helpful assistant. Based on the user\'s first message, create a concise title for this conversation. The title should be a maximum of 5 words and directly state the topic.'},
                    {'role': 'user', 'content': f"User's first message: \"{first_user_msg_for_naming}\"\n\nTitle:"}
                ]
                name_response = fireworks_client.chat.completions.create(
                    model="accounts/fireworks/models/deepseek-v3-0324",
                    messages=naming_prompt_messages, max_tokens=20, temperature=0.3
                )
                new_name = name_response.choices[0].message.content.strip().replace('"', '')
                active_conversation_obj['name'] = new_name if new_name else f"Chat {active_conversation_obj['created_at'][:10]}"
                conversation_name_updated = True
            except Exception as e_name:
                app.logger.error(f"Error generating conversation name: {e_name}")
                active_conversation_obj['name'] = f"Chat {active_conversation_obj['created_at'][:10]}" # Fallback
                conversation_name_updated = True # Name was set to fallback
        else: # No fireworks client
            active_conversation_obj['name'] = f"Chat {active_conversation_obj['created_at'][:10]}"
            conversation_name_updated = True


    user_name = profile.get('user_name', 'the user')
    user_gender = profile.get('user_gender', 'unknown gender')
    disciplinarian_config = profile.get('disciplinarian', {})
    system_prompt = generate_system_prompt(disciplinarian_config, user_name, user_gender, profile)
    
    messages_for_ai = [{'role': 'system', 'content': system_prompt}] + current_messages

    def generate_stream():
        nonlocal current_messages
        nonlocal active_conversation_obj
        
        # Start the stream immediately with a signal and record start time
        stream_start_time = time.time()
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        
        if conversation_name_updated:
            yield f"data: {json.dumps({'type': 'metadata', 'chat_name': active_conversation_obj.get('name')})}\n\n"

        if not fireworks_client:
            placeholder_reply = f"(AI response placeholder) You said: {message_content}"
            formatted_placeholder_reply = format_ai_response_text(placeholder_reply)
            yield f"data: {json.dumps({'type': 'content', 'content': formatted_placeholder_reply})}\n\n"
            current_messages.append({'role': 'assistant', 'content': formatted_placeholder_reply})
            active_conversation_obj['messages'] = current_messages
            
            # Update history in profile
            updated_history = [conv if conv['id'] != active_chat_id else active_conversation_obj for conv in user_history]
            _update_profile(email, {'history': updated_history})
            
            yield f"data: {json.dumps({'type': 'complete', 'suggestion': None})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            stream = fireworks_client.chat.completions.create(
                model="accounts/fireworks/models/deepseek-v3-0324",
                messages=messages_for_ai,
                stream=True,
                max_tokens=1000,
                temperature=0.7
            )
            
            full_ai_response_raw = ""
            token_delay = 1.0 / 20.0  # 20 tokens per second = 1/20 second per token
            
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_ai_response_raw += content
                    yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                    time.sleep(token_delay)  # Rate limit to 20 tokens per second
            
            formatted_full_ai_response = format_ai_response_text(full_ai_response_raw)
            current_messages.append({'role': 'assistant', 'content': formatted_full_ai_response})
            active_conversation_obj['messages'] = current_messages
            
            # Update history
            history_to_update = []
            for conv in user_history:
                if conv['id'] == active_chat_id:
                    history_to_update.append(active_conversation_obj)
                else:
                    history_to_update.append(conv)
            if not any(conv['id'] == active_chat_id for conv in user_history):
                history_to_update.insert(0, active_conversation_obj)

            _update_profile(email, {'history': history_to_update})

            # Analyze for suggestions immediately
            suggestion_result = _analyze_message_for_actions_internal(formatted_full_ai_response)
            
            # Calculate remaining delay time (30 seconds from stream start)
            elapsed_time = time.time() - stream_start_time
            delay_remaining = max(0, 30.0 - elapsed_time)
            
            # Wait for the remaining delay time before sending suggestion
            if delay_remaining > 0:
                time.sleep(delay_remaining)
            
            yield f"data: {json.dumps({'type': 'complete', 'suggestion': suggestion_result})}\n\n"

        except Exception as e:
            app.logger.error(f"Error during AI stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    # Enhanced headers for proper streaming
    headers = {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
        'X-Accel-Buffering': 'no',  # Disable nginx buffering
        'Connection': 'keep-alive'
    }
    
    return Response(
        stream_with_context(generate_stream()), 
        mimetype='text/event-stream', 
        headers=headers
    )

@app.route('/chat_stream')
def chat_stream():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    message_content = request.args.get('message')
    if not message_content:
        return jsonify({'error': 'No message provided'}), 400

    email = session['user_email']
    profile = _get_profile(email)
    user_history = profile.get('history', [])
    active_chat_id = session.get('active_chat_id')
    active_conversation_obj = None

    if active_chat_id:
        active_conversation_obj = next((conv for conv in user_history if conv['id'] == active_chat_id), None)

    if not active_conversation_obj:
        # Handle missing conversation similar to /chat route
        if user_history:
            active_conversation_obj = user_history[0]
            session['active_chat_id'] = active_conversation_obj['id']
        else:
            new_id = str(uuid.uuid4())
            active_conversation_obj = {
                'id': new_id, 'name': 'New Chat', 'messages': [],
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            user_history.insert(0, active_conversation_obj)
            session['active_chat_id'] = new_id

    current_messages = list(active_conversation_obj.get('messages', []))
    current_messages.append({'role': 'user', 'content': message_content})
    
    # Handle conversation naming
    conversation_name_updated = False
    if len(current_messages) == 2 and active_conversation_obj.get('name') == 'New Chat':
        if fireworks_client:
            try:
                naming_prompt_messages = [
                    {'role': 'system', 'content': 'Create a concise title (5 words max) for this conversation.'},
                    {'role': 'user', 'content': f"User's message: \"{message_content}\"\n\nTitle:"}
                ]
                name_response = fireworks_client.chat.completions.create(
                    model="accounts/fireworks/models/deepseek-v3-0324",
                    messages=naming_prompt_messages, max_tokens=20, temperature=0.3
                )
                new_name = name_response.choices[0].message.content.strip().replace('"', '')
                active_conversation_obj['name'] = new_name if new_name else f"Chat {active_conversation_obj['created_at'][:10]}"
                conversation_name_updated = True
            except Exception as e_name:
                app.logger.error(f"Error generating conversation name: {e_name}")
                active_conversation_obj['name'] = f"Chat {active_conversation_obj['created_at'][:10]}"
                conversation_name_updated = True

    user_name = profile.get('user_name', 'the user')
    user_gender = profile.get('user_gender', 'unknown gender')
    disciplinarian_config = profile.get('disciplinarian', {})
    system_prompt = generate_system_prompt(disciplinarian_config, user_name, user_gender, profile)
    
    messages_for_ai = [{'role': 'system', 'content': system_prompt}] + current_messages

    def generate():
        # Send start signal immediately and record start time
        stream_start_time = time.time()
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        
        if conversation_name_updated:
            yield f"data: {json.dumps({'type': 'metadata', 'chat_name': active_conversation_obj.get('name')})}\n\n"

        if not fireworks_client:
            placeholder_reply = f"(AI response placeholder) You said: {message_content}"
            formatted_placeholder_reply = format_ai_response_text(placeholder_reply)
            yield f"data: {json.dumps({'type': 'content', 'content': formatted_placeholder_reply})}\n\n"
            current_messages.append({'role': 'assistant', 'content': formatted_placeholder_reply})
            active_conversation_obj['messages'] = current_messages
            
            updated_history = [conv if conv['id'] != active_chat_id else active_conversation_obj for conv in user_history]
            _update_profile(email, {'history': updated_history})
            
            yield f"data: {json.dumps({'type': 'complete', 'suggestion': None})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            stream = fireworks_client.chat.completions.create(
                model="accounts/fireworks/models/deepseek-v3-0324",
                messages=messages_for_ai,
                stream=True,
                max_tokens=1000,
                temperature=0.7
            )
            
            full_ai_response_raw = ""
            token_delay = 1.0 / 30.0  # 30 tokens per second = 1/30 second per token
            
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_ai_response_raw += content
                    yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                    time.sleep(token_delay)  # Rate limit to 30 tokens per second
            
            formatted_full_ai_response = format_ai_response_text(full_ai_response_raw)
            current_messages.append({'role': 'assistant', 'content': formatted_full_ai_response})
            active_conversation_obj['messages'] = current_messages
            
            # Update history
            history_to_update = []
            for conv in user_history:
                if conv['id'] == active_chat_id:
                    history_to_update.append(active_conversation_obj)
                else:
                    history_to_update.append(conv)
            if not any(conv['id'] == active_chat_id for conv in user_history):
                history_to_update.insert(0, active_conversation_obj)

            _update_profile(email, {'history': history_to_update})

            # Analyze for suggestions immediately
            suggestion_result = _analyze_message_for_actions_internal(formatted_full_ai_response)
            
            # Calculate remaining delay time (30 seconds from stream start)
            elapsed_time = time.time() - stream_start_time
            delay_remaining = max(0, 30.0 - elapsed_time)
            
            # Wait for the remaining delay time before sending suggestion
            if delay_remaining > 0:
                time.sleep(delay_remaining)
            
            yield f"data: {json.dumps({'type': 'complete', 'suggestion': suggestion_result})}\n\n"

        except Exception as e:
            app.logger.error(f"Error during AI stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return Response(generate(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no'
    })

# Utility to build system prompt from disciplinarian config
def generate_system_prompt(config, user_name, user_gender, user_profile=None):
    name = config.get('name', "Disciplinarian")
    age = config.get('age', "an unspecified age")
    gender = config.get('gender', "an unspecified gender")
    personality = config.get('personality', "standard")
    strictness = config.get('strictness', "moderate")
    # punishments_config = disciplinarian_config.get('punishments', []) # Not used in prompt typically

    prompt = (
        f"You are {name}, a {gender} disciplinarian of {age}. "
        f"Your personality is {personality} and your strictness level is {strictness}. "
        f"You are speaking to {user_name}, who is {user_gender}. "
        "Maintain your role as the disciplinarian throughout the conversation. "
        "Address the user directly based on the scenario and their messages."
    )
    
    # Add user's rules, punishments, and todos to the system prompt
    if user_profile:
        rules = user_profile.get('rules', [])
        if rules:
            prompt += f"\n\n{user_name}'s established rules:\n"
            for i, rule in enumerate(rules, 1):
                prompt += f"{i}. {rule}\n"
        
        punishments = user_profile.get('punishments', [])
        active_punishments = []
        for p in punishments:
            if isinstance(p, dict) and not p.get('completed', False):
                active_punishments.append(p.get('text', ''))
            elif isinstance(p, str):
                active_punishments.append(p)
        
        if active_punishments:
            prompt += f"\n{user_name}'s current punishments:\n"
            for i, punishment in enumerate(active_punishments, 1):
                prompt += f"{i}. {punishment}\n"
        
        todos = user_profile.get('todos', [])
        active_todos = []
        for t in todos:
            if isinstance(t, dict) and not t.get('completed', False):
                active_todos.append(t.get('text', ''))
            elif isinstance(t, str):
                active_todos.append(t)
        
        if active_todos:
            prompt += f"\n{user_name}'s current to-do items:\n"
            for i, todo in enumerate(active_todos, 1):
                prompt += f"{i}. {todo}\n"
        
        if rules or active_punishments or active_todos:
            prompt += "\nRefer to these rules, punishments, and tasks as appropriate during your interactions."
    
    return prompt

@app.route('/data/rules', methods=['GET', 'POST'])
def handle_rules():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    email = session['user_email']
    profile = _get_profile(email)
    
    if request.method == 'GET':
        return jsonify(profile.get('rules', []))
    
    elif request.method == 'POST':
        data = request.json
        rule = data.get('rule', '').strip()
        if not rule:
            return jsonify({'error': 'Rule cannot be empty'}), 400
        
        rules = profile.get('rules', [])
        if rule not in rules:
            rules.append(rule)
            _update_profile(email, {'rules': rules})
        
        return jsonify({'message': 'Rule added successfully'}), 200

@app.route('/data/rules/delete', methods=['POST'])
def delete_rule():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    email = session['user_email']
    profile = _get_profile(email)
    data = request.json
    rule_to_delete = data.get('rule', '').strip()
    
    if not rule_to_delete:
        return jsonify({'error': 'Rule cannot be empty'}), 400
    
    rules = profile.get('rules', [])
    if rule_to_delete in rules:
        rules.remove(rule_to_delete)
        _update_profile(email, {'rules': rules})
        return jsonify({'message': 'Rule deleted successfully'}), 200
    
    return jsonify({'error': 'Rule not found'}), 404

@app.route('/data/punishments', methods=['GET', 'POST'])
def handle_punishments():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    email = session['user_email']
    profile = _get_profile(email)
    
    if request.method == 'GET':
        punishments = profile.get('punishments', [])
        # Convert to format expected by frontend (with text and completed fields)
        formatted_punishments = []
        for p in punishments:
            if isinstance(p, str):
                formatted_punishments.append({'text': p, 'completed': False})
            elif isinstance(p, dict):
                formatted_punishments.append(p)
        return jsonify(formatted_punishments)
    
    elif request.method == 'POST':
        data = request.json
        punishment = data.get('punishment', '').strip()
        if not punishment:
            return jsonify({'error': 'Punishment cannot be empty'}), 400
        
        punishments = profile.get('punishments', [])
        punishment_obj = {'text': punishment, 'completed': False}
        
        # Check if punishment already exists
        existing = any(p.get('text') == punishment if isinstance(p, dict) else p == punishment for p in punishments)
        if not existing:
            punishments.append(punishment_obj)
            _update_profile(email, {'punishments': punishments})
        
        return jsonify({'message': 'Punishment added successfully'}), 200

@app.route('/data/punishments/delete', methods=['POST'])
def delete_punishment():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    email = session['user_email']
    profile = _get_profile(email)
    data = request.json
    punishment_to_delete = data.get('punishment_text', '').strip()
    
    if not punishment_to_delete:
        return jsonify({'error': 'Punishment cannot be empty'}), 400
    
    punishments = profile.get('punishments', [])
    updated_punishments = []
    found = False
    
    for p in punishments:
        if isinstance(p, str) and p != punishment_to_delete:
            updated_punishments.append(p)
        elif isinstance(p, dict) and p.get('text') != punishment_to_delete:
            updated_punishments.append(p)
        else:
            found = True
    
    if found:
        _update_profile(email, {'punishments': updated_punishments})
        return jsonify({'message': 'Punishment deleted successfully'}), 200
    
    return jsonify({'error': 'Punishment not found'}), 404

@app.route('/data/todos', methods=['GET', 'POST'])
def handle_todos():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    email = session['user_email']
    profile = _get_profile(email)
    
    if request.method == 'GET':
        todos = profile.get('todos', [])
        # Convert to format expected by frontend (with text and completed fields)
        formatted_todos = []
        for t in todos:
            if isinstance(t, str):
                formatted_todos.append({'text': t, 'completed': False})
            elif isinstance(t, dict):
                formatted_todos.append(t)
        return jsonify(formatted_todos)
    
    elif request.method == 'POST':
        data = request.json
        todo_item = data.get('item', '').strip()
        if not todo_item:
            return jsonify({'error': 'Todo item cannot be empty'}), 400
        
        todos = profile.get('todos', [])
        todo_obj = {'text': todo_item, 'completed': False}
        
        # Check if todo already exists
        existing = any(t.get('text') == todo_item if isinstance(t, dict) else t == todo_item for t in todos)
        if not existing:
            todos.append(todo_obj)
            _update_profile(email, {'todos': todos})
        
        return jsonify({'message': 'Todo added successfully'}), 200

@app.route('/data/todos/delete', methods=['POST'])
def delete_todo():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    email = session['user_email']
    profile = _get_profile(email)
    data = request.json
    todo_to_delete = data.get('todo_text', '').strip()
    
    if not todo_to_delete:
        return jsonify({'error': 'Todo item cannot be empty'}), 400
    
    todos = profile.get('todos', [])
    updated_todos = []
    found = False
    
    for t in todos:
        if isinstance(t, str) and t != todo_to_delete:
            updated_todos.append(t)
        elif isinstance(t, dict) and t.get('text') != todo_to_delete:
            updated_todos.append(t)
        else:
            found = True
    
    if found:
        _update_profile(email, {'todos': updated_todos})
        return jsonify({'message': 'Todo deleted successfully'}), 200
    
    return jsonify({'error': 'Todo not found'}), 404


def _analyze_message_for_actions_internal(message_text):
    """
    Internal helper to analyze message text for actions using DeepInfra.
    Returns a suggestion dict or None.
    """
    if not DEEPINFRA_API_KEY:
        app.logger.error("DeepInfra API key (DEEPINFRA_API_KEY) not configured for internal analysis.")
        return None # Or raise an exception / return an error structure

    if not message_text:
        return None

    prompt_text = f"""You are an intelligent assistant integrated into a disciplinarian chat application. Your task is to analyze the following message, which was sent by the AI disciplinarian to the user. Determine if this message clearly and directly suggests that a new rule should be created, a new punishment should be assigned, or a new to-do item should be added for the user.

Message from AI Disciplinarian:
"{message_text}"

Based *only* on this message, does it explicitly state or strongly imply one of the following actions for the user?
1.  A new rule to be followed (e.g., "From now on, you must...", "A new rule is...")
2.  A new punishment to be administered (e.g., "Your punishment will be...", "You are assigned...")
3.  A new to-do item to be completed (e.g., "You need to...", "Your task is...")

If yes, and only if the suggestion is clear and actionable, respond ONLY with a JSON object in the exact following format:
{{"type": "rule", "text": "The specific text of the rule."}}
OR
{{"type": "punishment", "text": "The specific text of the punishment."}}
OR
{{"type": "todo", "text": "The specific text of the to-do item."}}

The "text" field should contain the concise and direct wording of the rule, punishment, or to-do item as suggested in the message.
If the message does NOT clearly suggest any of these specific actions, or if it's ambiguous, respond ONLY with the literal word:
null

Do not include any other explanatory text, greetings, or markdown formatting around your response. Your entire response must be either the JSON object or the word 'null'.
"""
    try:
        api_url = "https://api.deepinfra.com/v1/openai/chat/completions"
        headers = {
            "Authorization": f"Bearer {DEEPINFRA_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": DEEPINFRA_MODEL_NAME,
            "messages": [{"role": "user", "content": prompt_text}],
            "max_tokens": 1500,
            "temperature": 0.1,
            "reasoning_effort": "low"
        }
        
        response = requests.post(api_url, headers=headers, json=payload, timeout=60)
        response.raise_for_status() 
        
        ai_response_data = response.json()
        content = ai_response_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        
        # Strip think tags from R1 response
        content = strip_think_tags(content)

        if not content or content.lower() == "null":
            app.logger.info("DeepInfra internal analysis: No suggestion or null.")
            return None

        try:
            suggestion = json.loads(content)
            if isinstance(suggestion, dict) and "type" in suggestion and "text" in suggestion:
                if suggestion["type"] in ["rule", "punishment", "todo"] and isinstance(suggestion["text"], str) and suggestion["text"].strip():
                    app.logger.info(f"DeepInfra internal analysis: Suggestion found - Type: {suggestion['type']}, Text: {suggestion['text'][:50]}...")
                    return suggestion
                else:
                    app.logger.warning(f"DeepInfra internal analysis returned invalid type/text: Type='{suggestion.get('type')}', Text='{suggestion.get('text')}'")
                    return None
            else:
                app.logger.warning(f"DeepInfra internal analysis returned non-standard JSON structure: {content}")
                return None
        except json.JSONDecodeError:
            app.logger.warning(f"DeepInfra internal analysis returned non-JSON content that was not 'null': {content}")
            return None

    except requests.exceptions.HTTPError as http_err:
        error_message = f"DeepInfra API HTTP error during internal analysis: {http_err}"
        error_details = ""
        if http_err.response is not None:
            try:
                error_details = http_err.response.json()
            except ValueError:
                error_details = http_err.response.text
            app.logger.error(f"{error_message} - Status: {http_err.response.status_code} - Details: {error_details}")
        else:
            app.logger.error(error_message)
        return None # Or a specific error object if frontend needs to know
    except requests.exceptions.RequestException as req_err:
        app.logger.error(f"Error calling DeepInfra API (RequestException) during internal analysis: {req_err}")
        return None
    except Exception as e:
        app.logger.error(f"Unexpected error in _analyze_message_for_actions_internal: {e}", exc_info=True)
        return None


@app.route('/analyze_message_for_actions', methods=['POST'])
def analyze_message_for_actions_route():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    message_text = data.get('message')

    if not message_text:
        return jsonify({"error": "No message provided for analysis"}), 400
    
    if not DEEPINFRA_API_KEY: # Check again as this is a public endpoint
        app.logger.error("DeepInfra API key (DEEPINFRA_API_KEY) not configured for route.")
        return jsonify({"error": "AI analysis service not configured (API key missing)"}), 503

    suggestion = _analyze_message_for_actions_internal(message_text)

    if suggestion is None and DEEPINFRA_API_KEY: # If key exists but analysis failed or returned None
        # Check if it was an actual error or just no suggestion
        # _analyze_message_for_actions_internal logs errors, so here we just return based on result
        # If it's None, we assume no suggestion or an internal error already logged.
        pass # Fall through to return jsonify(suggestion) which will be jsonify(None)

    # If _analyze_message_for_actions_internal returned an error object (not implemented yet, but future)
    # if isinstance(suggestion, dict) and 'error' in suggestion:
    #    return jsonify(suggestion), suggestion.get('status_code', 500)

    return jsonify(suggestion)


def strip_think_tags(text):
    """
    Strip <think>...</think> tags from R1 model responses.
    Returns the text content after the closing </think> tag, or original text if no tags found.
    """
    if not text:
        return text
    
    # Find the last </think> tag and return everything after it
    think_end_pattern = r'</think>\s*'
    match = re.search(think_end_pattern, text, re.IGNORECASE | re.DOTALL)
    
    if match:
        # Return everything after the last </think> tag, stripped of leading/trailing whitespace
        return text[match.end():].strip()
    
    # If no </think> tag found, return original text
    return text

if __name__ == '__main__':
    app.run(debug=True)
