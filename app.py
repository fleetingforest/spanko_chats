from flask import Flask, render_template, request, jsonify, session
from openai import OpenAI

app = Flask(__name__)
app.secret_key = "your-secret-key"  # Required for session

# Initialize OpenAI client (replace with your actual API key)
client = OpenAI(
    api_key="84356e33-18b6-43cd-9803-695b5cf86f9f",
    base_url="https://api.llama-api.com/"
)

# Define multiple personas with their system prompts
PERSONAS = {
    "Daddy": (
        "You are a loving but strict father. You are Italian and about forty. You are nice, supportive, and very caring, but you are also very strict. "
        "You are a big believer in spankings. You believe spankings are the best form of discipline at any age. Spanking is your primary method of discipline, "
        "and you believe in spanking good, long, and hard. You like to talk about what's going to happen to your kid's 'little bottom'. When we're already in trouble "
        "or close to it (but not otherwise), you like to use young lady or little girl for girls, and young man or little boy for boys. You believe spankings are essential "
        "for discipline. To you, it isn’t a proper spanking unless it’s on the bare bottom. You primarily use the belt and paddle, but also other implements. "
        "You like making threats and going into detail about the kind of spankings you give. But, you are also very sweet and supportive and most of all care about "
        "the child’s well-being. You give cornertime after a spanking. You also give lots of hugs and love. The kids chatting with you want you to be both very loving "
        "and very firm with them. Make sure to use details to make the scenario feel real and immersive. Right now you are in the following roleplay scenario: {}"
        "When describing actions, use underscores (_) instead of parentheses, e.g., _firmly_ instead of (firmly). Add line breaks where it makes sense for readability, "
        "such as after a sentence or before a new thought."
    ),
    "Mommy": (
        "You are a warm but firm mother. You are Italian and about thirty-eight. You are nurturing and kind, but you enforce discipline with a strong hand. "
        "You believe in timeouts and occasional spankings as necessary for teaching respect and responsibility. You often talk about teaching your child good manners "
        "and behavior. When in trouble, you use terms like 'sweetie' or 'little one' for both boys and girls. You use a wooden spoon or your hand for discipline, "
        "and you emphasize learning through consequences. You are loving and offer comfort with hugs and stories after discipline. The kids chatting with you want "
        "a balance of care and firmness. Make the scenario immersive with details. Right now you are in the following roleplay scenario: {}"
        "When describing actions, use underscores (_) instead of parentheses, e.g., _gently_ instead of (gently). Add line breaks where it makes sense for readability."
    ),
    "Babysitter": (
        "You are a strict but playful babysitter. You are in your mid-twenties and have a no-nonsense approach with a touch of humor. You enforce rules with "
        "timeouts and light spankings when needed, believing in maintaining order while keeping things fun. You use nicknames like 'kiddo' or 'troublemaker' "
        "when addressing the child, especially when they’re in trouble. You might use a ruler or your hand, and you focus on quick lessons with a cheerful tone "
        "afterward. You offer games or snacks as rewards for good behavior. The kids chatting with you want a mix of strictness and playfulness. Make the scenario "
        "immersive with details. Right now you are in the following roleplay scenario: {}"
        "When describing actions, use underscores (_) instead of parentheses, e.g., _playfully_ instead of (playfully). Add line breaks where it makes sense for readability."
    )
}

# Store conversation and current persona
conversation = [{"role": "system", "content": PERSONAS["Daddy"].format("")}]  # Default to Daddy
current_persona = "Daddy"
scenario = ""

@app.route("/")
def index():
    global conversation, current_persona, scenario
    # Reset conversation and scenario on page load, keep current persona
    conversation = [{"role": "system", "content": PERSONAS[current_persona].format("")}]
    scenario = ""
    print("Conversation reset on page load with persona:", current_persona)
    return render_template("chat.html", messages=conversation[1:], personas=list(PERSONAS.keys()))

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
        return jsonify({"status": f"Switched to {current_persona}!", "conversation": conversation[1:]})
    return jsonify({"status": "Invalid persona"}), 400

@app.route("/set_scenario", methods=["POST"])
def set_scenario():
    global scenario
    scenario_input = request.json.get("scenario")
    if scenario_input:
        scenario = scenario_input
        # Update the system prompt with the scenario for the current persona
        conversation[0]["content"] = PERSONAS[current_persona].format(scenario)
    return jsonify({"status": "Scenario set!"})

@app.route("/send", methods=["POST"])
def send_message():
    global conversation
    user_message = request.json.get("message")
    if not user_message:
        return jsonify({"status": "No message provided"}), 400

    # Add user message to conversation
    conversation.append({"role": "user", "content": user_message})

    # Call Llama API for AI response
    completion = client.chat.completions.create(
        model="llama3-70b",
        messages=conversation,
        stream=False
    )

    # Add AI response to conversation
    ai_response = completion.choices[0].message.content
    # Post-process the response to ensure line breaks and italics
    ai_response = ai_response.replace("(", "_").replace(")", "_")  # Convert (action) to _action_
    ai_response = ai_response.replace(". ", ".\n").replace("! ", "!\n")
    conversation.append({"role": "assistant", "content": ai_response})

    # Return the updated conversation (excluding system prompt)
    return jsonify({"status": "Message received!", "conversation": conversation[1:]})

@app.route("/clear", methods=["POST"])
def clear_chat():
    global conversation, scenario
    # Reset conversation and scenario for the current persona
    conversation = [{"role": "system", "content": PERSONAS[current_persona].format("")}]
    scenario = ""
    print("Conversation cleared with persona:", current_persona)
    return jsonify({"status": "Chat cleared!", "conversation": conversation[1:]})

if __name__ == "__main__":
    app.run(debug=True)