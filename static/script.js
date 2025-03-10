// Track the active persona separately from the dropdown selection
let activePersona = "Daddy"; // Default to match the server's default
let userName = "You"; // Default user name

function setName() {
    let nameInput = document.getElementById("name-input");
    if (nameInput.value.trim() !== "") {
        userName = nameInput.value.trim();
        document.getElementById("name-section").style.display = "none"; // Hide name input section
    }
}

function sendMessage() {
    let input = document.getElementById("message-input");
    let message = input.value.trim();

    if (message === "") return;

    let chatBox = document.getElementById("chat-box");
    let userDiv = document.createElement("div");
    userDiv.className = "user-message";
    userDiv.textContent = userName + ": " + message;
    chatBox.appendChild(userDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    let typingDiv = document.createElement("div");
    typingDiv.className = "ai-message";
    typingDiv.textContent = activePersona + ": " + activePersona + " is typing...";
    chatBox.appendChild(typingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    // Show clear chat button after the first message is sent
    document.getElementById("clear-chat-button").style.display = "block";

    fetch("/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message, user_name: userName }),
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
        // Check if the server included the current persona in response
        if (data.current_persona) {
            activePersona = data.current_persona;
        }
    })
    .catch(error => {
        console.error("Error:", error);
        chatBox.removeChild(typingDiv);
        let errorDiv = document.createElement("div");
        errorDiv.className = "ai-message";
        errorDiv.textContent = activePersona + ": Oops, something went wrong!";
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
        document.getElementById("scenario-section").style.display = "none"; // Hide scenario section
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
        // Only update the active persona when the server confirms the change
        if (data.current_persona) {
            activePersona = data.current_persona;
        }
        updateChat(data.conversation); // Update chat with cleared conversation
        document.getElementById("persona-section").style.display = "none"; // Hide persona section
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
        // Check if server sent current persona
        if (data.current_persona) {
            activePersona = data.current_persona;
        }
        document.getElementById("scenario-input").value = "";
        document.getElementById("persona-section").style.display = "block"; // Show persona section
        document.getElementById("scenario-section").style.display = "block"; // Show scenario section
        document.getElementById("clear-chat-button").style.display = "none"; // Hide clear chat button
        console.log("Chat cleared and input reset");
    })
    .catch(error => {
        console.error("Error clearing chat:", error);
        let chatBox = document.getElementById("chat-box");
        chatBox.innerHTML = "";
        document.getElementById("scenario-input").value = "";
        document.getElementById("persona-section").style.display = "block"; // Show persona section
        document.getElementById("scenario-section").style.display = "block"; // Show scenario section
        document.getElementById("clear-chat-button").style.display = "none"; // Hide clear chat button
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
        messageDiv.innerHTML = (msg.role === "user" ? userName : activePersona) + ": " + formattedContent;
        chatBox.appendChild(messageDiv);
    });

    chatBox.scrollTop = chatBox.scrollHeight;
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

document.getElementById("name-form").addEventListener("submit", function(event) {
    event.preventDefault(); // Prevent form submission
    setName();
});

// You might want to add this to synchronize on page load
window.addEventListener('DOMContentLoaded', (event) => {
    // Set the dropdown to match the active persona on load
    document.getElementById("persona-select").value = activePersona;
});