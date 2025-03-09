from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Store messages in memory (for simplicity)
messages = []

@app.route("/")
def index():
    return render_template("chat.html", messages=messages)

@app.route("/send", methods=["POST"])
def send_message():
    user_message = request.json.get("message")
    messages.append(user_message)
    return jsonify({"status": "Message received!"})

if __name__ == "__main__":
    app.run(debug=True)