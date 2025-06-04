from flask import Flask, render_template, request, jsonify, session, send_file, url_for, Response, redirect, flash, send_from_directory
import openai_tts_test  # Import the TTS script
from openai import OpenAI
import os
import time
import json
from datetime import datetime, timedelta, date, timezone
from cryptography.fernet import Fernet, InvalidToken
import hashlib
import base64
import firebase_admin
from firebase_admin import credentials, storage, firestore
from passlib.hash import pbkdf2_sha256  # For password hashing
import uuid
import requests
import secrets
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from flask_mail import Mail, Message
import usage_reports  # Import our new usage reporting module
from personas import get_personas, get_character_names, get_standard_system_prompt  # Import personas from separate file
import traceback



app = Flask(__name__)

@app.before_request
def redirect_to_primary_domain():
    if request.host == "spanking-chat.onrender.com":
        return redirect("https://discipline.chat" + request.full_path, code=301)

app.secret_key = "your-secret-key"  # Required for session
app.config['SECURITY_PASSWORD_SALT'] = os.getenv("SECURITY_PASSWORD_SALT", "your-password-salt")


# Mail configuration from environment variables
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_DEBUG'] = True  # Enable debug output

# Initialize Mail
mail = Mail(app)

# Initialize the serializer for generating secure tokens
serializer = URLSafeTimedSerializer(app.secret_key)

# Initialize OpenAI client (replace with your actual API key)
client = OpenAI(
    api_key=os.getenv("DEEPINFRA_API_KEY"),
    base_url="https://api.deepinfra.com/v1/openai"
)

# Initialize Fireworks client for speech-to-text
fireworks_client = OpenAI(
    api_key=os.getenv("FIREWORKS_API_KEY"),
    base_url="https://api.fireworks.ai/inference/v1"
)

# Initialize Firebase
cred = credentials.Certificate("spanking-chat-firebase-adminsdk-fbsvc-e7307d7abb.json")  # Replace with your service account key path
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'spanking-chat.firebasestorage.app'  # Replace with your Firebase bucket
    })
bucket = storage.bucket()

# Initialize Firestore
db = firestore.client()

PATREON_CLIENT_ID = os.getenv("PATREON_CLIENT_ID")
PATREON_CLIENT_SECRET = os.getenv("PATREON_CLIENT_SECRET")
PATREON_REDIRECT_URI = ("https://spanking-chat.onrender.com/patreon/callback")

standard_system_prompt = get_standard_system_prompt()

# Define multiple personas with their system prompts
PERSONAS = get_personas()  # Load personas from external file

# Store conversation, current persona, and voice chat status
conversation = [{"role": "system", "content": PERSONAS["Daddy"].format("")}]  # Default to Daddy
current_persona = "Daddy"
scenario = ""
voice_chat_enabled = False

# Database setup
FREE_TOKEN_LIMIT = 2_500_000
PATREON_TOKEN_LIMIT = 12_500_000
FREE_VOICE_TOKEN_LIMIT = 50_000
PATREON_VOICE_TOKEN_LIMIT = 250_000

SECRET_SALT = os.getenv("SECRET_SALT", b"your-secret-salt-here")  # Use env var


def get_tokens(ip_address):
    doc_ref = db.collection('token_usage').document(ip_address)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict().get('tokens', 0)
    return 0

def check_token_thresholds(ip_address):
    """Check if user has hit specific token thresholds and return appropriate Patreon promotion message"""
    # First check if the user is logged in and is already a Patreon subscriber
    user_email = session.get('user_email')
    if user_email and is_authenticated():
        patreon_status = get_user_patreon_status(user_email)
        if patreon_status == "active":
            # Don't show promotions to active Patreon subscribers
            return None
    # If not logged in or not a Patreon subscriber, proceed to check thresholds
            
    tokens = get_tokens(ip_address)
    
    # Get shown notification thresholds for this user
    doc_ref = db.collection('token_notifications').document(ip_address)
    doc = doc_ref.get()
    shown_thresholds = doc.to_dict().get('shown_thresholds', []) if doc.exists else []
    
    # Check each threshold and only show notifications for new thresholds
    notification = None
    
    # First threshold: 50,000 tokens
    if tokens >= 50000 and 50000 not in shown_thresholds:
        notification = """
        <div class="patreon-promo">
            <div class="patreon-icon"></div>
            <div class="patreon-message">
                <h3>Enjoying Discipline Chat?</h3>
                <a href="https://www.patreon.com/c/SpankingChat" target="_blank" class="patreon-button">Join Patreon!</a>
            </div>
        </div>
        """
        shown_thresholds.append(50000)
    
    # Second threshold: 250,000 tokens
    elif tokens >= 250000 and 250000 not in shown_thresholds:
        notification = """
        <div class="patreon-promo">
            <div class="patreon-icon"></div>
            <div class="patreon-message">
                <h3>Enjoying Discipline Chat?</h3>
                <a href="https://www.patreon.com/c/SpankingChat" target="_blank" class="patreon-button">Support Us on Patreon!</a>
            </div>
        </div>
        """
        shown_thresholds.append(250000)
    
    # Recurring thresholds: every 250k after 500k
    elif tokens >= 500000:
        # Calculate the nearest 250k milestone
        milestone = 500000 + (((tokens - 500000) // 250000) * 250000)
        if milestone not in shown_thresholds and tokens >= milestone:
            notification = f"""
            <div class="patreon-promo">
                <div class="patreon-icon"></div>
                <div class="patreon-message">
                    <h3>You're amazing!</h3>
                    <p>Your ongoing usage helps us improve. Patreon members get priority support!</p>
                    <a href="https://www.patreon.com/c/SpankingChat" target="_blank" class="patreon-button">Become a Patron!</a>
                </div>
            </div>
            """
            shown_thresholds.append(milestone)
    
    # Update the database with the new shown thresholds if we're showing a notification
    if notification:
        doc_ref.set({'shown_thresholds': shown_thresholds}, merge=True)
    
    return notification

def update_tokens(ip_address, tokens):
    doc_ref = db.collection('token_usage').document(ip_address)
    doc_ref.set({
        'tokens': firestore.Increment(tokens)
    }, merge=True)

    update_daily_metrics('tokens', tokens)

def get_voice_tokens(ip_address):
    doc_ref = db.collection('token_usage').document(ip_address)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict().get('voice_tokens', 0)
    return 0

def update_voice_tokens(ip_address, tokens):
    doc_ref = db.collection('token_usage').document(ip_address)
    doc_ref.set({
        'voice_tokens': firestore.Increment(tokens)
    }, merge=True)
    
    # Track daily metrics
    update_daily_metrics('voice_tokens', tokens)
    
def update_daily_metrics(metric_type, value=1, persona=None, hour=None, origin=None):
    """
    Update daily usage metrics in Firestore
    
    Args:
        metric_type: Type of metric to update (tokens, voice_tokens, queries)
        value: Value to increment by
        persona: Current persona being used (if applicable)
        hour: Hour of the day (if applicable)
        origin: User origin or referrer (if applicable)
    """
    today = datetime.now().date().isoformat()
    daily_log_ref = db.collection('daily_logs').document(today)
    
    # Get current hour if not provided
    if hour is None:
        hour = str(datetime.now().hour).zfill(2)
        
    # Update basic metrics
    if metric_type == 'tokens':
        daily_log_ref.set({
            'total_tokens': firestore.Increment(value),
            'last_updated': firestore.SERVER_TIMESTAMP
        }, merge=True)
    elif metric_type == 'voice_tokens':
        daily_log_ref.set({
            'total_voice_tokens': firestore.Increment(value),
            'last_updated': firestore.SERVER_TIMESTAMP
        }, merge=True)
    elif metric_type == 'queries':
        daily_log_ref.set({
            'total_queries': firestore.Increment(value),
            'last_updated': firestore.SERVER_TIMESTAMP
        }, merge=True)
    
    # Update active users (count unique IPs)
    user_ip = get_client_ip()
    daily_log_ref.set({
        'active_user_ips': firestore.ArrayUnion([user_ip]),
        'last_updated': firestore.SERVER_TIMESTAMP
    }, merge=True)
    
    # Update hourly usage
    hourly_field = f'hourly_usage.{hour}'
    daily_log_ref.set({
        hourly_field: firestore.Increment(1),
        'last_updated': firestore.SERVER_TIMESTAMP
    }, merge=True)
    
    # Update persona usage if provided
    if persona:
        persona_field = f'persona_usage.{persona}'
        daily_log_ref.set({
            persona_field: firestore.Increment(1),
            'last_updated': firestore.SERVER_TIMESTAMP
        }, merge=True)
    
    # Update user origin if provided
    if origin:
        origin_field = f'user_origins.{origin}'
        daily_log_ref.set({
            origin_field: firestore.Increment(1),
            'last_updated': firestore.SERVER_TIMESTAMP
        }, merge=True)
        
    # Also update the active_users count
    # We need to get the actual document to count unique IPs
    doc = daily_log_ref.get()
    if doc.exists:
        doc_data = doc.to_dict()
        unique_ips = len(set(doc_data.get('active_user_ips', [])))
        daily_log_ref.set({
            'active_users': unique_ips,
            'last_updated': firestore.SERVER_TIMESTAMP
        }, merge=True)

def derive_key(ip_address):
    """Derive a Fernet key from the user's IP address and a secret salt."""
    key_material = ip_address.encode() + SECRET_SALT
    key = hashlib.sha256(key_material).digest()[:32]  # 32 bytes for Fernet
    return base64.urlsafe_b64encode(key)  # Fernet expects base64-encoded key

def encrypt_file(file_path, key):
    """Encrypt a file using Fernet and upload to Firebase."""
    fernet = Fernet(key)
    with open(file_path, 'rb') as f:
        data = f.read()
    encrypted_data = fernet.encrypt(data)
    encrypted_filename = os.path.basename(file_path) + '.enc'
    blob = bucket.blob(f"audio/{encrypted_filename}")
    blob.upload_from_string(encrypted_data, content_type='application/octet-stream')
    os.remove(file_path)  # Remove the unencrypted file
    return encrypted_filename

def decrypt_file_data(encrypted_data, key):
    """Decrypt data using Fernet, returning the decrypted data."""
    fernet = Fernet(key)
    try:
        decrypted_data = fernet.decrypt(encrypted_data)
        return decrypted_data
    except InvalidToken:
        return None

def get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()  # Get the first IP
    else:
        ip = request.remote_addr
    return ip

# Firestore user management
def register_user(email, password):
    user_ref = db.collection('users').document(email)
    if user_ref.get().exists:
        return False, "Email already registered"
    hashed_password = pbkdf2_sha256.hash(password)
    user_ref.set({
        'email': email,
        'password': hashed_password,
        'active': True,
        'fs_uniquifier': str(uuid.uuid4()),
        'roles': ['user'],
        'created_at': firestore.SERVER_TIMESTAMP
    })
    return True, "Registration successful"

def login_user(email, password):
    user_ref = db.collection('users').document(email)
    doc = user_ref.get()
    if not doc.exists:
        return False, "User not found"
    user_data = doc.to_dict()
    if pbkdf2_sha256.verify(password, user_data['password']) and user_data['active']:
        session['user_email'] = email
        session['fs_uniquifier'] = user_data['fs_uniquifier']
        return True, "Login successful"
    return False, "Invalid credentials"

def logout_user():
    session.pop('user_email', None)
    session.pop('fs_uniquifier', None)

def is_authenticated():
    return 'user_email' in session

def get_user_patreon_status(email):
    user_ref = db.collection('users').document(email)
    doc = user_ref.get()
    return doc.to_dict().get('patreon_status', 'inactive') if doc.exists else 'inactive'

def get_user_patreon_linked(email):
    user_ref = db.collection('users').document(email)
    doc = user_ref.get()
    return doc.to_dict().get('patreon_linked', False) if doc.exists else False

# Patreon OAuth routes
@app.route("/patreon/login")
def patreon_login():
    if not is_authenticated():
        return redirect(url_for("login"))
    
    state = secrets.token_hex(16)
    session["oauth_state"] = state

    auth_url = (
        f"https://www.patreon.com/oauth2/authorize?"
        f"response_type=code&client_id={PATREON_CLIENT_ID}&"
        f"redirect_uri={PATREON_REDIRECT_URI}&"
        f"scope=identity%20identity.memberships&"
        f"state={state}"
    )
    return redirect(auth_url)

@app.route("/patreon/callback")
def patreon_callback():
    if not is_authenticated():
        return redirect(url_for("login"))
    
    state = request.args.get("state")
    if state != session.pop("oauth_state", None):  # Ensure it matches the stored value
        return render_template("login.html", error="Invalid state parameter")

    
    code = request.args.get("code")
    if not code:
        return render_template("login.html", error="Patreon authentication failed")

    # Exchange code for access token
    token_url = "https://www.patreon.com/api/oauth2/token"
    data = {
        "code": code,
        "grant_type": "authorization_code",
        "client_id": PATREON_CLIENT_ID,
        "client_secret": PATREON_CLIENT_SECRET,
        "redirect_uri": PATREON_REDIRECT_URI
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(token_url, data=data, headers=headers)
    token_data = response.json()

    if "access_token" not in token_data:
        return render_template("login.html", error="Failed to get Patreon access token")

    # Get Patreon user info
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    user_response = requests.get("https://www.patreon.com/api/oauth2/v2/identity?include=memberships", headers=headers)
    user_data = user_response.json()

    patreon_id = user_data["data"]["id"]
    email = session['user_email']
    user_ref = db.collection('users').document(email)

    # Check membership status
    membership = user_data.get("included", [])
    patreon_status = "inactive"
    for item in membership:
        if item.get("type") == "member":
            attributes = item.get("attributes", {})
            if attributes.get("currently_entitled_amount_cents", 0) > 0:
                patreon_status = "active"
                break  # Stop checking after finding an active membership

    # Update Firestore with Patreon info
    user_ref.update({
        'patreon_id': patreon_id,
        'patreon_access_token': token_data['access_token'],
        'patreon_status': patreon_status,
        'patreon_linked': True  # Set patreon_linked to True
    })

    return redirect(url_for("index"))

# Patreon Webhook
@app.route("/patreon/webhook", methods=["POST"])
def patreon_webhook():
    # Verify webhook signature (optional, requires Patreon secret)
    event_type = request.headers.get("X-Patreon-Event")
    data = request.json

    if event_type in ["members:pledge:create", "members:pledge:update"]:
        patreon_id = data["data"]["relationships"]["user"]["data"]["id"]
        pledge_amount = data["data"]["attributes"]["currently_entitled_amount_cents"]
        status = "active" if pledge_amount > 0 else "inactive"
        
        # Find user by patreon_id and update status
        users_ref = db.collection('users').where('patreon_id', '==', patreon_id).stream()
        for user in users_ref:
            user_ref = db.collection('users').document(user.id)
            user_ref.update({'patreon_status': status})
            app.logger.info(f"Updated Patreon status for {user.id} to {status}")

    elif event_type == "members:pledge:delete":
        patreon_id = data["data"]["relationships"]["user"]["data"]["id"]
        users_ref = db.collection('users').where('patreon_id', '==', patreon_id).stream()
        for user in users_ref:
            user_ref = db.collection('users').document(user.id)
            user_ref.update({'patreon_status': 'inactive'})
            app.logger.info(f"Set Patreon status for {user.id} to inactive")

    return jsonify({"status": "Webhook received"}), 200


@app.route("/")
def index():
    global conversation, current_persona, scenario, voice_chat_enabled
    # Reset conversation and scenario on page load, keep current persona
    conversation = [{"role": "system", "content": PERSONAS[current_persona].format("")}]
    scenario = ""
    voice_chat_enabled = False
    print("Conversation reset on page load with persona:", current_persona)
    
    patreon_linked = False
    if 'user_email' in session:
        user_email = session['user_email']
        patreon_linked = get_user_patreon_linked(user_email)
    
    return render_template("chat.html", messages=conversation[1:], personas=list(PERSONAS.keys()), current_persona=current_persona, patreon_linked=patreon_linked)

@app.route("/voice_chat")
def voice_chat():
    global conversation, current_persona, scenario, voice_chat_enabled
    # Reset conversation and scenario on page load, keep current persona
    conversation = [{"role": "system", "content": PERSONAS[current_persona].format("")}]
    scenario = ""
    voice_chat_enabled = True  # Enable voice chat by default for this route
    print("Voice chat page loaded with persona:", current_persona)
    
    patreon_linked = False
    if 'user_email' in session:
        user_email = session['user_email']
        patreon_linked = get_user_patreon_linked(user_email)
    
    return render_template("voice_chat.html", messages=conversation[1:], personas=list(PERSONAS.keys()), current_persona=current_persona, patreon_linked=patreon_linked)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        action = request.form.get("action")
        email = request.form.get("email")
        password = request.form.get("password")
        
        if action == "login":
            success, message = login_user(email, password)
            if success:
                return redirect(url_for("index"))
            return render_template("login.html", error=message)
        
        elif action == "register":
            success, message = register_user(email, password)
            if success:
                return render_template("login.html", success=message)
            return render_template("login.html", error=message)
    
    return render_template("login.html")

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/set_persona", methods=["POST"])
def set_persona():
    global conversation, current_persona, scenario
    new_persona = request.json.get("persona")
    if new_persona in PERSONAS:
        current_persona = new_persona
        # Reset conversation with the new persona's prompt and empty scenario
        conversation = [{"role": "system", "content": PERSONAS[current_persona].format("")}]
        scenario = ""
        print("Persona switched to:", current_persona)
        return jsonify({
            "status": f"Switched to {current_persona}!", 
            "conversation": conversation[1:],
            "current_persona": current_persona
        })
    return jsonify({"status": "Invalid persona"}), 400

@app.route("/set_scenario", methods=["POST"])
def set_scenario():
    global scenario, current_persona
    scenario_input = request.json.get("scenario")
    if scenario_input:
        scenario = scenario_input
        # Update the system prompt with the scenario for the current persona
        conversation[0]["content"] = PERSONAS[current_persona].format(scenario)
    return jsonify({
        "status": "Scenario set!",
        "current_persona": current_persona
    })

@app.route("/toggle_voice_chat", methods=["POST"])
def toggle_voice_chat():
    global voice_chat_enabled
    # Accept a parameter from the client to set the voice chat mode explicitly
    if request.json and 'voice_chat_enabled' in request.json:
        voice_chat_enabled = request.json['voice_chat_enabled']
    else:
        # Fall back to toggling if no explicit value is provided
        voice_chat_enabled = not voice_chat_enabled
    
    print(f"Voice chat mode set to: {voice_chat_enabled}")
    return jsonify({"voice_chat_enabled": voice_chat_enabled})

@app.route("/send", methods=["POST"])
def send_message():
    global conversation, current_persona, voice_chat_enabled
    user_message = request.json.get("message")
    user_name = request.json.get("user_name", "You")
    user_ip = get_client_ip()
    user_email = session.get('user_email', None)
    if user_email and is_authenticated():
        token_limit = PATREON_TOKEN_LIMIT if get_user_patreon_status(user_email) == "active" else FREE_TOKEN_LIMIT
        voice_token_limit = PATREON_VOICE_TOKEN_LIMIT if get_user_patreon_status(user_email) == "active" else FREE_VOICE_TOKEN_LIMIT
    else:
        token_limit = FREE_TOKEN_LIMIT
        voice_token_limit = FREE_VOICE_TOKEN_LIMIT

    if not user_message:
        return jsonify({"status": "No message provided"}), 400

    # Check token limit for the IP address
    if get_tokens(user_ip) >= token_limit:
        return jsonify({
            "status": "Token limit exceeded",
            "limit_data": {
                "title": "*SMACK* Token limit exceeded",
                "message": "Support us on Patreon to keep the spankings coming!",
                "button_text": "Join Patreon!"
            }
        }), 403

    
    # Add user message to conversation
    conversation.append({"role": "user", "content": f"{user_name}: {user_message}"})

    # Call Llama API for AI response
    completion = client.chat.completions.create(
        model="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        messages=conversation,
        stream=False
    )

    # Add AI response to conversation
    ai_response = completion.choices[0].message.content
    # Post-process the response to ensure line breaks and italics
    ai_response = ai_response.replace(". ", ".\n").replace("! ", "!\n")

    # Define possible prefixes to strip
    persona_prefix = f"{current_persona}: "
    character_names = get_character_names()  # Get character names from external file
    character_prefix = f"{character_names.get(current_persona, '')}: " if current_persona in character_names else None

    # Remove either persona or character prefix if present
    if ai_response.startswith(persona_prefix):
        ai_response = ai_response[len(persona_prefix):].lstrip()
    elif character_prefix and ai_response.startswith(character_prefix):
        ai_response = ai_response[len(character_prefix):].lstrip()
    
    # Add the persona prefix once
    final_response = f"{character_prefix}{ai_response}"
    conversation.append({"role": "assistant", "content": final_response})

    # Update token count for the IP address
    update_tokens(user_ip, completion.usage.total_tokens)

    # Print the number of tokens processed so far for the user's IP address
    total_tokens = get_tokens(user_ip)
    print(f"IP {user_ip} has processed {total_tokens} tokens so far.")

    # Convert AI response to audio if voice chat is enabled and token limit is not exceeded
    audio_url = None
    voice_tokens = get_voice_tokens(user_ip)
    if voice_chat_enabled and voice_tokens <= voice_token_limit:
        try:
            # Get streaming response directly from TTS function
            stream_response = openai_tts_test.convert_text_to_audio(ai_response, current_persona)
            if stream_response:
                # Generate a unique streaming endpoint URL for this response
                stream_id = str(uuid.uuid4())
                session[f'stream_{stream_id}'] = {
                    'text': ai_response,
                    'persona': current_persona,
                    'created_at': datetime.now().timestamp()
                }
                audio_url = url_for('stream_audio', stream_id=stream_id)
                
                # Update voice token usage
                num_chars = len(ai_response)
                update_voice_tokens(user_ip, num_chars)
                voice_tokens = get_voice_tokens(user_ip)
                print(f"IP {user_ip} has used {voice_tokens} voice tokens so far.")
        except Exception as e:
            app.logger.error(f"Error converting text to audio for streaming: {e}")

    # Check if user has hit any token thresholds and should see a Patreon promotion
    patreon_promo = check_token_thresholds(user_ip)
    
    # Return the updated conversation (excluding system prompt), current persona, audio URL, and any patreon promo
    return jsonify({
        "status": "Message received!", 
        "conversation": conversation[1:],
        "current_persona": current_persona,
        "audio_url": audio_url,
        "patreon_promo": patreon_promo  # This will be None if no threshold is reached
    })

# Add streaming send message endpoint
@app.route("/send_stream", methods=["GET"])
def send_message_stream():
    global conversation, current_persona, voice_chat_enabled
    user_message = request.args.get("message")
    user_name = request.args.get("user_name", "You")
    user_ip = get_client_ip()
    user_email = session.get('user_email', None)
    
    if user_email and is_authenticated():
        token_limit = PATREON_TOKEN_LIMIT if get_user_patreon_status(user_email) == "active" else FREE_TOKEN_LIMIT
        voice_token_limit = PATREON_VOICE_TOKEN_LIMIT if get_user_patreon_status(user_email) == "active" else FREE_VOICE_TOKEN_LIMIT
    else:
        token_limit = FREE_TOKEN_LIMIT
        voice_token_limit = FREE_VOICE_TOKEN_LIMIT

    if not user_message:
        def error_stream():
            yield f"data: {json.dumps({'type': 'error', 'message': 'No message provided'})}\n\n"
            yield "data: [DONE]\n\n"
        return Response(error_stream(), mimetype='text/event-stream')

    # Check token limit for the IP address
    if get_tokens(user_ip) >= token_limit:
        def limit_error_stream():
            yield f"data: {json.dumps({'type': 'error', 'status': 'Token limit exceeded', 'limit_data': {'title': '*SMACK* Token limit exceeded', 'message': 'Support us on Patreon to keep the spankings coming!', 'button_text': 'Join Patreon!'}})}\n\n"
            yield "data: [DONE]\n\n"
        return Response(limit_error_stream(), mimetype='text/event-stream')

    # Add user message to conversation
    conversation.append({"role": "user", "content": f"{user_name}: {user_message}"})

    def generate_stream():
        try:
            # Call Llama API for AI response with streaming enabled
            completion = client.chat.completions.create(
                model="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
                messages=conversation,
                stream=True
            )

            ai_response = ""
            
            # Send initial metadata
            yield f"data: {json.dumps({'type': 'start', 'persona': current_persona})}\n\n"
            
            # Force flush the initial data
            import sys
            if hasattr(sys.stdout, 'flush'):
                sys.stdout.flush()
            
            for chunk in completion:
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    ai_response += content
                    
                    # Send each chunk to the client
                    chunk_data = f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                    yield chunk_data
                    
                    # Force flush each chunk
                    if hasattr(sys.stdout, 'flush'):
                        sys.stdout.flush()
            
            # Post-process the complete response
            ai_response = ai_response.replace(". ", ".\n").replace("! ", "!\n")

            # Define possible prefixes to strip
            persona_prefix = f"{current_persona}: "
            character_names = get_character_names()
            character_prefix = f"{character_names.get(current_persona, '')}: " if current_persona in character_names else None

            # Remove either persona or character prefix if present
            if ai_response.startswith(persona_prefix):
                ai_response = ai_response[len(persona_prefix):].lstrip()
            elif character_prefix and ai_response.startswith(character_prefix):
                ai_response = ai_response[len(character_prefix):].lstrip()
            
            # Add the persona prefix once
            final_response = f"{character_prefix}{ai_response}"
            conversation.append({"role": "assistant", "content": final_response})

            # Estimate token usage (since streaming doesn't provide usage info)
            estimated_tokens = len(ai_response.split()) * 1.3  # Rough estimate
            update_tokens(user_ip, int(estimated_tokens))
            
            # Handle audio if voice chat is enabled
            audio_url = None
            voice_tokens = get_voice_tokens(user_ip)
            if voice_chat_enabled and voice_tokens <= voice_token_limit:
                try:
                    stream_response = openai_tts_test.convert_text_to_audio(ai_response, current_persona)
                    if stream_response:
                        stream_id = str(uuid.uuid4())
                        session[f'stream_{stream_id}'] = {
                            'text': ai_response,
                            'persona': current_persona,
                            'created_at': datetime.now().timestamp()
                        }
                        audio_url = url_for('stream_audio', stream_id=stream_id)
                        
                        # Update voice token usage
                        num_chars = len(ai_response)
                        update_voice_tokens(user_ip, num_chars)
                except Exception as e:
                    app.logger.error(f"Error converting text to audio for streaming: {e}")
            
            # Check for Patreon promotion
            patreon_promo = check_token_thresholds(user_ip)
            
            # Send completion metadata
            completion_data = f"data: {json.dumps({'type': 'complete', 'audio_url': audio_url, 'patreon_promo': patreon_promo, 'current_persona': current_persona})}\n\n"
            yield completion_data
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            app.logger.error(f"Error in streaming response: {e}")
            error_data = f"data: {json.dumps({'type': 'error', 'message': 'An error occurred while generating the response'})}\n\n"
            yield error_data
            yield "data: [DONE]\n\n"

    return Response(
        generate_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route("/clear", methods=["POST"])
def clear_chat():
    global conversation, scenario, current_persona
    # Reset conversation and scenario for the current persona
    conversation = [{"role": "system", "content": PERSONAS[current_persona].format("")}]
    scenario = ""
    print("Conversation cleared with persona:", current_persona)
    return jsonify({
        "status": "Chat cleared!", 
        "conversation": conversation[1:],
        "current_persona": current_persona
    })

@app.route("/get_current_persona", methods=["GET"])
def get_current_persona():
    global current_persona
    return jsonify({
        "current_persona": current_persona
    })

@app.route("/convert_to_audio", methods=["POST"])
def convert_to_audio():
    # Find the last AI message in the conversation
    last_ai_message = None
    for message in reversed(conversation):
        if message["role"] == "assistant":
            last_ai_message = message["content"]
            break

    if not last_ai_message:
        app.logger.error("No AI message found to convert")
        return jsonify({"status": "No AI message found to convert"}), 400

    app.logger.info(f"Converting AI message to audio: {last_ai_message}")
    user_ip = get_client_ip()

    # Call the TTS function, encrypt, and serve decrypted audio
    try:
        audio_file_path = openai_tts_test.convert_text_to_audio(last_ai_message, current_persona)
        key = derive_key(user_ip)
        encrypted_file_path = encrypt_file(audio_file_path, key)
        decrypted_data = decrypt_file_data(bucket.blob(f"audio/{encrypted_file_path}").download_as_bytes(), key)
        if decrypted_data is None:
            return jsonify({"status": "Error decrypting audio"}), 500
        return Response(
            decrypted_data,
            mimetype="audio/mpeg",
            headers={"Content-Disposition": f"inline; filename={os.path.basename(audio_file_path)}"}
        )
    except Exception as e:
        app.logger.error(f"Error converting text to audio or encrypting: {e}")
        return jsonify({"status": "Error converting text to audio"}), 500

@app.route("/serve_audio/<filename>")
def serve_audio(filename):
    user_ip = get_client_ip()
    key = derive_key(user_ip)
    
    # Download from Firebase
    blob = bucket.blob(f"audio/{filename}")
    try:
        encrypted_data = blob.download_as_bytes()
    except Exception as e:
        app.logger.error(f"Error downloading file from Firebase: {e}")
        return jsonify({"status": "Audio file not found"}), 404

    decrypted_data = decrypt_file_data(encrypted_data, key)
    if decrypted_data is None:
        return jsonify({"status": "Unauthorized access or invalid key"}), 403

    return Response(
        decrypted_data,
        mimetype="audio/mpeg",
        headers={"Content-Disposition": f"inline; filename={filename.replace('.enc', '')}"}
    )

@app.route("/get_first_message", methods=["POST"])
def get_first_message():
    global conversation, current_persona, voice_chat_enabled
    user_name = request.json.get("user_name", "You")
    user_ip = get_client_ip()
    user_email = session.get('user_email', None)
    
    # Check token limits based on user status
    if user_email and is_authenticated():
        token_limit = PATREON_TOKEN_LIMIT if get_user_patreon_status(user_email) == "active" else FREE_TOKEN_LIMIT
        voice_token_limit = PATREON_VOICE_TOKEN_LIMIT if get_user_patreon_status(user_email) == "active" else FREE_VOICE_TOKEN_LIMIT
    else:
        token_limit = FREE_TOKEN_LIMIT
        voice_token_limit = FREE_VOICE_TOKEN_LIMIT

    # Check token limit for the IP address
    if get_tokens(user_ip) >= token_limit:
        return jsonify({
            "status": "Token limit exceeded",
            "limit_data": {
                "title": "*SMACK* Token limit exceeded",
                "message": "Support us on Patreon to keep the spankings coming!",
                "button_text": "Join Patreon!"
            }
        }), 403
    # Create a temporary messages list with a minimal greeting including the user's name
    # This ensures the AI knows who it's talking to and can respond appropriately
    temp_messages = conversation.copy()
    temp_messages.append({"role": "user", "content": "Start the conversation based on the scenario. You are speaking to " + user_name + "."})
    
    # Call Llama API for AI response with the temporary messages list that includes user name
    completion = client.chat.completions.create(
        model="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        messages=temp_messages,
        stream=False
    )
    
    # Add AI response to conversation
    ai_response = completion.choices[0].message.content
    # Post-process the response to ensure line breaks and italics
    ai_response = ai_response.replace(". ", ".\n").replace("! ", "!\n")

    # Define possible prefixes to strip
    persona_prefix = f"{current_persona}: "
    character_names = get_character_names()  # Get character names from external file
    character_prefix = f"{character_names.get(current_persona, '')}: " if current_persona in character_names else None

    # Remove either persona or character prefix if present
    if ai_response.startswith(persona_prefix):
        ai_response = ai_response[len(persona_prefix):].lstrip()
    elif character_prefix and ai_response.startswith(character_prefix):
        ai_response = ai_response[len(character_prefix):].lstrip()
    
    # Add the persona prefix once
    final_response = f"{character_prefix}{ai_response}"
    conversation.append({"role": "assistant", "content": final_response})

    # Update token count for the IP address
    update_tokens(user_ip, completion.usage.total_tokens)

    # Print the number of tokens processed so far for the user's IP address
    total_tokens = get_tokens(user_ip)
    print(f"IP {user_ip} has processed {total_tokens} tokens so far.")

    # Convert AI response to audio if voice chat is enabled and token limit is not exceeded
    audio_url = None
    voice_tokens = get_voice_tokens(user_ip)
    if voice_chat_enabled and voice_tokens <= voice_token_limit:
        try:
            # Get streaming response directly from TTS function
            stream_response = openai_tts_test.convert_text_to_audio(ai_response, current_persona=current_persona)
            if stream_response:
                # Generate a unique streaming endpoint URL for this response
                stream_id = str(uuid.uuid4())
                session[f'stream_{stream_id}'] = {
                    'text': ai_response,
                    'persona': current_persona,
                    'created_at': datetime.now().timestamp()
                }

                audio_url = url_for('stream_audio', stream_id=stream_id)
                
                # Update voice token usage
                num_chars = len(ai_response)
                update_voice_tokens(user_ip, num_chars)
                voice_tokens = get_voice_tokens(user_ip)
                print(f"IP {user_ip} has used {voice_tokens} voice tokens so far.")
        except Exception as e:
            app.logger.error(f"Error converting text to audio for streaming: {e}")
        
    # Return the updated conversation (excluding system prompt), current persona, audio URL, and any patreon promo
    return jsonify({
        "status": "First message generated!", 
        "conversation": conversation[1:],
        "current_persona": current_persona,
        "audio_url": audio_url,
        "patreon_promo": None  # This will be None if no threshold is reached
    })

# Add a new endpoint for streaming audio
@app.route("/stream_audio/<stream_id>")
def stream_audio(stream_id):
    stream_data = session.get(f'stream_{stream_id}')
    if not stream_data:
        return jsonify({"error": "Stream not found or expired"}), 404
    
    # Get the text and persona from the session
    text = stream_data['text']
    persona = stream_data['persona']
    
    # Create a generator to stream the audio directly
    def generate():
        try:
            # Get fresh streaming response at request time
            with openai_tts_test.convert_text_to_audio(text, persona) as response:
                # Stream chunks as they arrive for real-time playback
                for chunk in response.iter_bytes():
                    yield chunk
                    # Small sleep to ensure smooth streaming
                    time.sleep(0.01)
        except Exception as e:
            app.logger.error(f"Error streaming audio: {e}")
    
    # Clean up the session after response is created
    session.pop(f'stream_{stream_id}', None)
    
    # Return a streaming response to the client with proper headers for real-time streaming
    return Response(
        generate(),
        mimetype="audio/aac",  # Use "audio/mpeg" for MP3
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",  # For nginx; disables buffering
            "Connection": "keep-alive",  # Keeps TCP connection alive
            "Accept-Ranges": "bytes",    # Allows Safari to seek/stream
            "Transfer-Encoding": "chunked"  # Needed to stream properly
        }
    )

@app.route("/transcribe_audio", methods=["POST"])
def transcribe_audio():
    """Transcribe audio using Fireworks AI speech-to-text"""
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    
    audio_file = request.files['audio']
    user_ip = get_client_ip()
    user_email = session.get('user_email', None)
    
    # Check token limits based on user status
    if user_email and is_authenticated():
        token_limit = PATREON_TOKEN_LIMIT if get_user_patreon_status(user_email) == "active" else FREE_TOKEN_LIMIT
    else:
        token_limit = FREE_TOKEN_LIMIT
    
    # Check token limit for the IP address
    if get_tokens(user_ip) >= token_limit:
        return jsonify({
            "status": "Token limit exceeded",
            "limit_data": {
                "title": "*SMACK* Token limit exceeded",
                "message": "Support us on Patreon to keep the spankings coming!",
                "button_text": "Join Patreon!"
            }
        }), 403
    try:
        # Save the temporary audio file
        temp_audio_path = f"temp_audio_{uuid.uuid4()}.webm"
        audio_file.save(temp_audio_path)
        
        # Print debug info
        app.logger.info(f"Attempting to transcribe audio using Fireworks API. File size: {os.path.getsize(temp_audio_path)} bytes")
        app.logger.info(f"Using fireworks model: fireworks/whisper-v3-turbo")
        
        # Use Fireworks AI Whisper model to transcribe the audio
        with open(temp_audio_path, "rb") as audio:
            transcription = fireworks_client.audio.transcriptions.create(
                model="whisper-v3",
                file=audio,
                response_format="text"
            )
        
        app.logger.info(f"Transcription successful: {transcription[:30]}...")
        
        # Update token usage - rough estimate based on audio length
        file_size = os.path.getsize(temp_audio_path) if os.path.exists(temp_audio_path) else 0
        estimated_tokens = max(100, file_size // 1000)  # Rough estimate: 1 token per KB with minimum of 100
        update_tokens(user_ip, estimated_tokens)
        
        # Remove temporary file
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
        
        return jsonify({
            "text": transcription,
            "status": "success"
        })
        
    except Exception as e:
        app.logger.error(f"Error transcribing audio with Fireworks: {str(e)}")
        
        # Add more detailed error logging
        app.logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Clean up temporary file if it exists
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
        
        return jsonify({"error": f"Transcription failed: {str(e)}"}), 500


def delete_old_audio_files_task():
    """Deletes encrypted audio files older than 30 minutes from Firebase Storage."""
    app.logger.info("Running delete_old_audio_files_task...")
    try:
        with app.app_context(): # Ensure app context for logging and potentially bucket access
            now = datetime.now(timezone.utc) # Use timezone-aware datetime
            cutoff = now - timedelta(minutes=30)
            blobs = bucket.list_blobs(prefix="audio/")
            deleted_count = 0
            for blob in blobs:
                # Ensure blob.updated is timezone-aware (it should be from Firebase)
                if blob.updated and blob.name.startswith("audio/openai_output_") and blob.name.endswith(".enc"):
                    if blob.updated < cutoff:
                        blob.delete()
                        app.logger.info(f"Deleted old encrypted audio file: {blob.name}")
                        deleted_count += 1
            app.logger.info(f"Finished delete_old_audio_files_task. Deleted {deleted_count} files.")
    except Exception as e:
        app.logger.error(f"Error in delete_old_audio_files_task: {str(e)}", exc_info=True)

# --- Add Flask CLI Command ---
@app.cli.command("delete-old-audio")
def delete_old_audio_command():
    """Deletes old audio files from Firebase Storage."""
    print("Starting delete-old-audio command...")
    delete_old_audio_files_task()
    print("delete-old-audio command finished.")

def send_usage_report_task(): # Renamed slightly to avoid confusion
    """
    Collect metrics, generate a report, and email it to the admin.
    Designed to be run once by a scheduler (like a Cron Job).
    """
    app.logger.info("send_usage_report_task started.")
    try:
        app.logger.info("Generating and sending daily usage report...")

        # Collect metrics from the previous day
        # Ensure usage_reports functions are compatible with running outside request context
        # Might need app.app_context() if they access app config or db directly without it
        with app.app_context():
             metrics = usage_reports.collect_daily_metrics(db)
             app.logger.info(f"Collected metrics for date: {metrics.get('date', 'N/A')}")
             # Generate HTML report
             report_html = usage_reports.generate_report_html(metrics)
             app.logger.info("Generated HTML report.")

        # Send email with the report
        msg = Message(
            subject=f"Discipline Chat Daily Report - {metrics['date']}", # Updated subject
            sender=app.config['MAIL_USERNAME'],
            recipients=["fleetingforest4@gmail.com"] # Your email address
        )
        msg.html = report_html

        app.logger.info("Attempting to send email...")
        # Need app context to send mail outside of a request
        with app.app_context():
            mail.send(msg)

        app.logger.info(f"Daily report for {metrics['date']} sent successfully")

    except Exception as e:
        app.logger.error(f"Error sending daily report: {str(e)}", exc_info=True)
    finally:
        app.logger.info("send_usage_report_task finished.")

# --- Add Flask CLI Command ---
@app.cli.command("send-report")
def send_report_command():
    """Sends the daily usage report."""
    print("Starting send-report command...")
    send_usage_report_task()
    print("send-report command finished.")


def reset_tokens_task():
    """Reset token usage for all users if it's the 1st of the month."""
    app.logger.info("Running reset_tokens_task...")
    try:
        with app.app_context(): # Ensure app context for db access and logging
            today = date.today()
            if today.day == 1:  # Check if it's the 1st of the month
                last_reset_ref = db.collection('metadata').document('last_reset')
                last_reset_doc = last_reset_ref.get()
                last_reset_date = last_reset_doc.to_dict().get('date') if last_reset_doc.exists else None

                if last_reset_date != today.isoformat():  # Check if the reset has already been done today
                    users_ref = db.collection('token_usage')
                    users = users_ref.stream()
                    reset_count = 0
                    batch = db.batch()
                    for user in users:
                        user_ref = db.collection('token_usage').document(user.id)
                        batch.update(user_ref, {
                            'tokens': 0,
                            'voice_tokens': 0
                        })
                        reset_count += 1
                        # Commit batch every 500 updates to avoid exceeding limits
                        if reset_count % 500 == 0:
                            batch.commit()
                            batch = db.batch() # Start a new batch
                    
                    if reset_count % 500 != 0: # Commit any remaining updates
                         batch.commit()

                    last_reset_ref.set({'date': today.isoformat()})  # Update the last reset date
                    app.logger.info(f"Tokens and voice tokens reset to 0 for {reset_count} users.")
                else:
                    app.logger.info("Token reset already performed today.")
            else:
                app.logger.info(f"Not the 1st of the month (Day: {today.day}). Skipping token reset.")
    except Exception as e:
        app.logger.error(f"Error in reset_tokens_task: {str(e)}", exc_info=True)

# --- Add Flask CLI Command ---
@app.cli.command("reset-tokens")
def reset_tokens_command():
    """Resets user tokens if it's the 1st of the month."""
    print("Starting reset-tokens command...")
    reset_tokens_task()
    print("reset-tokens command finished.")

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user_ref = db.collection('users').document(email)
        if not user_ref.get().exists:
            flash('Email address not found.', 'error')
            return redirect(url_for('forgot_password'))
        token = serializer.dumps(email, salt=app.config['SECURITY_PASSWORD_SALT'])
        reset_link = url_for('reset_password', token=token, _external=True)
        msg = Message('Password Reset Request', sender=app.config['MAIL_USERNAME'], recipients=[email])
        msg.body = f'To reset your Discipline Chat password, click the following link: {reset_link}\nThis link is valid for 1 hour.'
        mail.send(msg)
        flash('A password reset link has been sent to your email.', 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = serializer.loads(token, salt=app.config['SECURITY_PASSWORD_SALT'], max_age=3600)
    except SignatureExpired:
        return '<h1>The password reset link has expired.</h1>'
    except BadSignature:
        return '<h1>Invalid password reset token.</h1>'
    if request.method == 'POST':
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')
        if not password or password != confirm:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('reset_password', token=token))
        hashed = pbkdf2_sha256.hash(password)
        db.collection('users').document(email).update({'password': hashed})
        flash('Your password has been reset successfully.', 'success')
        return redirect(url_for('login'))
    # No need to flash a message about checking email - they're already here
    return render_template('reset_password.html', token=token)

@app.route('/sitemap.xml')
def sitemap():
    return send_from_directory(app.root_path, 'sitemap.xml', mimetype='application/xml')

@app.route('/google0d0cd6004b26c93e.html')
def serve_google_verification():
    return send_from_directory(app.root_path, 'google0d0cd6004b26c93e.html')

if __name__ == "__main__":
    app.run(debug=True)