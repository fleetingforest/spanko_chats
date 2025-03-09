function sendMessage() {
    let input = document.getElementById("message-input");
    let message = input.value.trim();

    if (message === "") return;

    let chatBox = document.getElementById("chat-box");
    let userDiv = document.createElement("div");
    userDiv.className = "user-message";
    userDiv.textContent = "You: " + message;
    chatBox.appendChild(userDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    let typingDiv = document.createElement("div");
    typingDiv.className = "ai-message";
    typingDiv.textContent = getCurrentPersona() + ": " + getCurrentPersona() + " is typing...";
    chatBox.appendChild(typingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    fetch("/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message }),
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log(data.status);
        chatBox.removeChild(typingDiv);
        updateChat(data.conversation);
    })
    .catch(error => {
        console.error("Error:", error);
        chatBox.removeChild(typingDiv);
        let errorDiv = document.createElement("div");
        errorDiv.className = "ai-message";
        errorDiv.textContent = getCurrentPersona() + ": Oops, something went wrong!";
        chatBox.appendChild(errorDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    });

    input.value = "";
}

function setScenario() {
    let scenarioInput = document.getElementById("scenario-input");
    let scenario = scenarioInput.value.trim();

    if (scenario === "") return;

    fetch("/set_scenario", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario: scenario }),
    })
    .then(response => response.json())
    .then(data => {
        console.log(data.status);
        scenarioInput.value = "";
    })
    .catch(error => console.error("Error:", error));
}

function setPersona() {
    let select = document.getElementById("persona-select");
    let persona = select.value;
    fetch("/set_persona", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ persona: persona }),
    })
    .then(response => response.json())
    .then(data => {
        console.log(data.status);
        updateChat(data.conversation); // Update chat with cleared conversation
    })
    .catch(error => console.error("Error setting persona:", error));
}

function clearChat() {
    console.log("Clear Chat button clicked");
    fetch("/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log("Server response:", data.status);
        updateChat(data.conversation);
        document.getElementById("scenario-input").value = "";
        console.log("Chat cleared and input reset");
    })
    .catch(error => {
        console.error("Error clearing chat:", error);
        let chatBox = document.getElementById("chat-box");
        chatBox.innerHTML = "";
        document.getElementById("scenario-input").value = "";
        console.log("Forced chat clear due to error");
    });
}

function updateChat(conversation) {
    let chatBox = document.getElementById("chat-box");
    chatBox.innerHTML = "";
    console.log("Updating chat with:", conversation);

    conversation.forEach(msg => {
        let messageDiv = document.createElement("div");
        messageDiv.className = msg.role === "user" ? "user-message" : "ai-message";
        let formattedContent = msg.content
            .replace(/_(.+?)_/g, (match, p1) => {
                let capitalized = p1.charAt(0).toUpperCase() + p1.slice(1).toLowerCase();
                return `<i>${capitalized}</i>`;
            })
            .replace(/\n/g, "<br>");
        messageDiv.innerHTML = (msg.role === "user" ? "You" : getCurrentPersona()) + ": " + formattedContent;
        chatBox.appendChild(messageDiv);
    });

    chatBox.scrollTop = chatBox.scrollHeight;
}

function getCurrentPersona() {
    let select = document.getElementById("persona-select");
    return select.value || "Daddy"; // Default to Daddy if not set
}

// Add event listeners
document.getElementById("message-input").addEventListener("keypress", function(event) {
    if (event.key === "Enter") {
        sendMessage();
    }
});

document.getElementById("scenario-input").addEventListener("keypress", function(event) {
    if (event.key === "Enter") {
        setScenario();
    }
});