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
fireworks_client = OpenAI(
    api_key=os.getenv("FIREWORKS_API_KEY"),
    base_url="https://api.fireworks.ai/inference/v1"
)

# Initialize Firebase
cred = credentials.Certificate("spanking-chat-firebase-adminsdk-fbsvc-e7307d7abb.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ----- Helper functions -----
def register_user(email, password):
    user_ref = db.collection('discipline_users').document(email)
    if user_ref.get().exists:
        return False, "Email already registered"
    hashed = pbkdf2_sha256.hash(password)
    user_ref.set({
        'email': email,
        'password': hashed,
        'created_at': firestore.SERVER_TIMESTAMP
    })
    return True, "Registration successful"

def login_user(email, password):
    user_ref = db.collection('discipline_users').document(email)
    doc = user_ref.get()
    if not doc.exists:
        return False, "User not found"
    data = doc.to_dict()
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
            # Save disciplinarian info
            db.collection('discipline_profiles').document(email).set({
                'user_name': session.get('user_name'),
                'user_gender': session.get('user_gender'),
                'disciplinarian': session.get('disciplinarian'),
                'rules': [],
                'punishments': [],
                'history': []
            })
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

# Chat endpoint using Fireworks DeepSeek model
@app.route('/chat', methods=['POST'])
def chat():
    if 'user_email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    message = request.json.get('message')
    email = session['user_email']
    profile_ref = db.collection('discipline_profiles').document(email)
    profile = profile_ref.get().to_dict()
    conversation = profile.get('history', [])

    system_prompt = generate_system_prompt(profile['disciplinarian'])
    if not conversation:
        conversation.append({'role': 'system', 'content': system_prompt})
    conversation.append({'role': 'user', 'content': message})

    response = fireworks_client.chat.completions.create(
        model="deepseek-v3-0324",
        messages=conversation
    )
    reply = response.choices[0].message.content
    conversation.append({'role': 'assistant', 'content': reply})

    profile_ref.update({'history': conversation})
    return jsonify({'reply': reply})

# Utility to build system prompt from disciplinarian config
def generate_system_prompt(config):
    punishments = ', '.join(config.get('punishments', []))
    prompt = (
        f"You are {config['name']}, a {config['age']}-year-old {config['gender']} disciplinarian. "
        f"Your personality is {config['personality']} and your strictness level is {config['strictness']}. "
        f"You believe in punishments such as: {punishments}. "
        "Your goal is to discipline and support the user with firm but caring guidance."
    )
    return prompt

if __name__ == '__main__':
    app.run(debug=True)
