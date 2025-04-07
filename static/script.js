// Track the active persona separately from the dropdown selection
let activePersona = "Daddy"; // Default to match the server's default
let userName = "You"; // Default user name
let voiceChatEnabled = false;
let selectedPersonaInOnboarding = null;
let currentOnboardingStep = 1;
// Add setup state tracking variables
let personaSet = false;
let nameSet = false;
let scenarioSet = false;

// Check if this is a first-time visitor
function checkFirstTimeVisitor() {
    // Always show the onboarding overlay regardless of whether the user has visited before
    document.getElementById('onboarding-overlay').style.display = 'flex';
    
    // Reset onboarding state
    currentOnboardingStep = 1;
    selectedPersonaInOnboarding = null;
    
    // Show first step, hide others
    document.querySelectorAll('.onboarding-step').forEach(step => {
        step.classList.remove('active');
    });
    document.querySelector('.onboarding-step[data-step="1"]').classList.add('active');
    
    // Clear any previous selections
    document.querySelectorAll('.persona-option').forEach(option => {
        option.classList.remove('selected');
    });
    
    // Reset input fields in onboarding
    if (document.getElementById('onboarding-name')) {
        document.getElementById('onboarding-name').value = '';
    }
    if (document.getElementById('onboarding-scenario')) {
        document.getElementById('onboarding-scenario').value = '';
    }
}

// Handle persona selection in onboarding
function selectPersonaInOnboarding(persona) {
    // Clear previous selections
    document.querySelectorAll('.persona-option').forEach(option => {
        option.classList.remove('selected');
    });
    
    // Select the clicked persona
    event.currentTarget.classList.add('selected');
    selectedPersonaInOnboarding = persona;
}

// Handle keydown events in the onboarding overlay
function handleOnboardingKeydown(event) {
    // If Enter key is pressed on the first step (persona selection) and not on mobile
    if (event.key === "Enter" && currentOnboardingStep === 1 && selectedPersonaInOnboarding && !isMobileDevice()) {
        nextOnboardingStep();
    }
}

// Handle navigation between onboarding steps
function nextOnboardingStep() {
    // Validate current step
    if (currentOnboardingStep === 1 && !selectedPersonaInOnboarding) {
        alert("Please select a persona to continue.");
        return;
    }
    
    if (currentOnboardingStep === 2) {
        const nameInput = document.getElementById('onboarding-name');
        if (!nameInput.value.trim()) {
            alert("Please enter your name to continue.");
            return;
        }
        userName = nameInput.value.trim();
    }
    
    // Hide current step
    document.querySelector(`.onboarding-step[data-step="${currentOnboardingStep}"]`).classList.remove('active');
    
    // Move to next step
    currentOnboardingStep++;
    
    // Show next step
    document.querySelector(`.onboarding-step[data-step="${currentOnboardingStep}"]`).classList.add('active');
    
    // Focus the input field on the next step if it's a text input
    const stepInput = document.querySelector(`.onboarding-step[data-step="${currentOnboardingStep}"] input`);
    if (stepInput) {
        stepInput.focus();
    }
}

// Complete onboarding and start chat
function completeOnboarding() {
    const scenarioInput = document.getElementById('onboarding-scenario');
    const scenario = scenarioInput.value.trim();
    
    if (!scenario) {
        alert("Please describe a scenario to continue.");
        return;
    }
    
    // Set the persona in the dropdown
    document.getElementById('persona-select').value = selectedPersonaInOnboarding;
    
    // Set the name
    document.getElementById('name-input').value = userName;
    
    // Set the scenario
    document.getElementById('scenario-input').value = scenario;
    
    // Hide the onboarding overlay
    document.getElementById('onboarding-overlay').style.display = 'none';
    
    // Hide the name section as we've already collected it
    document.getElementById('name-section').style.display = 'none';
    
    // Set our state tracking variables
    nameSet = true;
    
    // Trigger the setPersona and setScenario functions
    setPersona(true); // Pass true to indicate we're in the onboarding flow
}

function setName() {
    let nameInput = document.getElementById("name-input");
    if (nameInput.value.trim() !== "") {
        userName = nameInput.value.trim();
        document.getElementById("name-section").style.display = "none"; // Hide name input section
        nameSet = true;
        
        // Check if all requirements are met to start the chat
        checkAndTriggerFirstMessage();
    }
}

// New function to check if we have all requirements to start a chat
function checkAndTriggerFirstMessage() {
    console.log("Checking if we can start chat. Name set:", nameSet, "Persona set:", personaSet, "Scenario set:", scenarioSet);
    
    if (nameSet && personaSet && scenarioSet && document.getElementById("chat-box").children.length === 0) {
        console.log("All conditions met, triggering first message");
        getAiFirstMessage();
    } else {
        console.log("Not all conditions met for starting chat");
    }
}

function sendMessage() {
    let input = document.getElementById("message-input");
    let message = input.value.trim();

    if (message === "") return;

    let chatBox = document.getElementById("chat-box");
    let userDiv = document.createElement("div");
    userDiv.className = "user-message";
    userDiv.textContent = userName + ": " + message;  // Use userName here
    chatBox.appendChild(userDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    let typingDiv = document.createElement("div");
    typingDiv.className = "ai-message";
    let characterNames = {
        "Cute little girl": "Gaby",
        "Strict girlfriend": "Lara",
        "Submissive Girlfriend": "Sophie",
        "Strict teacher": "Mr. Levier",
        "Babysitter": "Gina",
        "Daddy": "Daddy",
        "Mommy": "Mommy",
        "Mischevious student": "Stewart",
        "Cute little boy": "Eli",
        "Bratty teen girl": "Kayla"
    };
    let characterName = characterNames[activePersona] || activePersona;
    typingDiv.textContent = characterName + (voiceChatEnabled ? " is preparing to speak..." : " is typing...");
    chatBox.appendChild(typingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    // Show clear chat button after the first message is sent
    document.getElementById("new-chat-button").style.display = "block";

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
        if (voiceChatEnabled && data.audio_url) {
            // Add audio control element
            let audioDiv = document.createElement("div");
            audioDiv.className = "ai-message";
            let audioControl = document.createElement("audio");
            audioControl.controls = true;
            audioControl.src = data.audio_url;
            audioDiv.appendChild(audioControl);
            chatBox.appendChild(audioDiv);
        } else {
            updateChat(data.conversation);
        }
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

// New function to request the AI's first message
function getAiFirstMessage() {
    let chatBox = document.getElementById("chat-box");
    
    // Don't proceed if there are already messages
    if (chatBox.children.length > 0) {
        console.log("Chat already has messages, not sending first message");
        return;
    }
    
    console.log("Getting AI first message with username:", userName);
    
    // Show "typing" indicator
    let typingDiv = document.createElement("div");
    typingDiv.className = "ai-message";
    let characterNames = {
        "Cute little girl": "Gaby",
        "Strict girlfriend": "Lara",
        "Submissive Girlfriend": "Sophie",
        "Strict teacher": "Mr. Levier",
        "Babysitter": "Gina",
        "Daddy": "Daddy",
        "Mommy": "Mommy",
        "Mischevious student": "Stewart",
        "Cute little boy": "Eli",
        "Bratty teen girl": "Kayla"
    };
    let characterName = characterNames[activePersona] || activePersona;
    typingDiv.textContent = characterName + (voiceChatEnabled ? " is preparing to speak..." : " is typing...");
    chatBox.appendChild(typingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
    
    // Show clear chat button after the first message is requested
    document.getElementById("new-chat-button").style.display = "block";
    
    // Request first message from the AI
    fetch("/get_first_message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_name: userName }),
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log("First message received:", data.status);
        chatBox.removeChild(typingDiv);
        if (voiceChatEnabled && data.audio_url) {
            // Add audio control element
            let audioDiv = document.createElement("div");
            audioDiv.className = "ai-message";
            let audioControl = document.createElement("audio");
            audioControl.controls = true;
            audioControl.src = data.audio_url;
            audioDiv.appendChild(audioControl);
            chatBox.appendChild(audioDiv);
        } else {
            updateChat(data.conversation);
        }
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
}

function setScenario(triggerAiMessage = false) {
    let scenarioInput = document.getElementById("scenario-input");
    let scenarioLabel = document.getElementById("scenario-label");
    let scenarioButton = document.getElementById("set-scenario-button");
    let scenario = scenarioInput.value.trim();

    if (scenario === "") return;
    
    console.log("Setting scenario:", scenario);

    fetch("/set_scenario", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario: scenario }),
    })
    .then(response => response.json())
    .then(data => {
        console.log("Scenario set response:", data.status);
        scenarioInput.value = "";
        // Hide the scenario label, input field, and button
        scenarioLabel.style.display = "none";
        scenarioInput.style.display = "none";
        scenarioButton.style.display = "none";
        
        // Update our scenario state
        scenarioSet = true;
        
        // If this was called from the onboarding flow with the trigger flag
        if (triggerAiMessage) {
            getAiFirstMessage();
        } else {
            // Check if we have all the requirements to start chat
            checkAndTriggerFirstMessage();
        }
    })
    .catch(error => console.error("Error setting scenario:", error));
}

function setPersona(fromOnboarding = false) {
    let select = document.getElementById("persona-select");
    let persona = select.value;
    console.log("Setting persona to:", persona);
    
    fetch("/set_persona", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ persona: persona }),
    })
    .then(response => response.json())
    .then(data => {
        console.log("Persona set response:", data.status);
        // Only update the active persona when the server confirms the change
        if (data.current_persona) {
            activePersona = data.current_persona;
        }
        updateChat(data.conversation); // Update chat with cleared conversation
        document.getElementById("persona-section").style.display = "none"; // Hide persona section
        
        // Update our persona state
        personaSet = true;
        
        // If coming from onboarding, set the scenario now
        if (fromOnboarding) {
            setTimeout(() => {
                setScenario(true); // Pass true to trigger AI first message
            }, 500);
        } else {
            // Check if we can start the chat
            checkAndTriggerFirstMessage();
        }
    })
    .catch(error => console.error("Error setting persona:", error));
}

function clearChat() {
    console.log("New Chat button clicked");
    
    // Reset our state tracking variables
    personaSet = false;
    nameSet = false;
    scenarioSet = false;
    
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
        
        // Show the onboarding overlay instead of just resetting the inputs
        checkFirstTimeVisitor();
        
        // Reset the form elements (they'll be hidden behind the onboarding overlay)
        document.getElementById("scenario-input").value = "";
        document.getElementById("scenario-input").style.display = "block";
        document.getElementById("scenario-label").style.display = "block";
        document.getElementById("set-scenario-button").style.display = "inline-block";
        document.getElementById("persona-section").style.display = "block";
        document.getElementById("scenario-section").style.display = "block";
        document.getElementById("name-section").style.display = "block";
        document.getElementById("new-chat-button").style.display = "none";
        console.log("Chat cleared and onboarding displayed");
    })
    .catch(error => {
        console.error("Error clearing chat:", error);
        let chatBox = document.getElementById("chat-box");
        chatBox.innerHTML = "";
        
        // Show the onboarding overlay even on error
        checkFirstTimeVisitor();
        
        // Reset the form elements
        document.getElementById("scenario-input").value = "";
        document.getElementById("scenario-input").style.display = "block";
        document.getElementById("scenario-label").style.display = "block";
        document.getElementById("set-scenario-button").style.display = "inline-block";
        document.getElementById("persona-section").style.display = "block";
        document.getElementById("scenario-section").style.display = "block";
        document.getElementById("name-section").style.display = "block";
        document.getElementById("new-chat-button").style.display = "none";
        console.log("Forced chat clear and onboarding display due to error");
    });
}

function updateChat(conversation) {
    let chatBox = document.getElementById("chat-box");
    chatBox.innerHTML = "";
    console.log("Updating chat with:", conversation);

    conversation.forEach(msg => {
        let messageDiv = document.createElement("div");
        messageDiv.className = msg.role === "user" ? "user-message" : "ai-message";
        
        // Apply proper formatting to actions in text
        // Process the content to handle action formatting properly
        let content = msg.content;
        
        // First remove any name prefixes if they exist
        const namePrefixes = [
            "You: ", "Daddy: ", "Mommy: ", "Gaby: ", "Lara: ", 
            "Sophie: ", "Mr. Levier: ", "Gina: ", "Stewart: ", 
            "Eli: ", "Kayla: "
        ];
        
        for (const prefix of namePrefixes) {
            if (content.startsWith(prefix)) {
                content = content.substring(prefix.length);
                break;
            }
        }
        
        // Then handle action formatting
        let formattedContent = content
            // Only match underscores that wrap complete action phrases
            // This will avoid catching standalone underscores or incomplete formatting
            .replace(/\b_([\w\s,'\-\.;:!?]+?)_\b/g, (match, p1) => {
                // Capitalize first letter of action text
                let capitalized = p1.charAt(0).toUpperCase() + p1.slice(1);
                // Return properly formatted action text
                return `<i>${capitalized}</i>`;
            })
            .replace(/\n/g, "<br>");
        
        // Add the name prefix for display
        if (msg.role === "user") {
            formattedContent = userName + ": " + formattedContent;
        } else {
            const characterNames = {
                "Cute little girl": "Gaby",
                "Strict girlfriend": "Lara",
                "Submissive Girlfriend": "Sophie",
                "Strict teacher": "Mr. Levier",
                "Babysitter": "Gina",
                "Daddy": "Daddy",
                "Mommy": "Mommy",
                "Mischevious student": "Stewart",
                "Cute little boy": "Eli",
                "Bratty teen girl": "Kayla"
            };
            const characterName = characterNames[activePersona] || activePersona;
            formattedContent = characterName + ": " + formattedContent;
        }
        
        messageDiv.innerHTML = formattedContent;
        chatBox.appendChild(messageDiv);

        // Add audio control element if voice chat is enabled and audio URL is present
        if (voiceChatEnabled && msg.audio_url) {
            let audioDiv = document.createElement("div");
            audioDiv.className = "ai-message";
            let audioControl = document.createElement("audio");
            audioControl.controls = true;
            audioControl.src = msg.audio_url;
            audioDiv.appendChild(audioControl);
            chatBox.appendChild(audioDiv);
        }
    });

    chatBox.scrollTop = chatBox.scrollHeight;
}

function convertToAudio() {
    console.log("Requesting conversion of the last AI message to audio");

    fetch("/convert_to_audio", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        return response.blob();
    })
    .then(blob => {
        console.log("Audio conversion successful");
        const url = window.URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.play();
    })
    .catch(error => {
        console.error("Error converting text to audio:", error);
    });
}

function toggleVoiceChat() {
    fetch("/toggle_voice_chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
    })
    .then(response => response.json())
    .then(data => {
        voiceChatEnabled = data.voice_chat_enabled;
        console.log("Voice chat enabled:", voiceChatEnabled);
        // Change button text based on the current state
        let voiceChatButton = document.getElementById("voice-chat-button");
        if (voiceChatEnabled) {
            voiceChatButton.textContent = "Switch to Text Responses";
        } else {
            voiceChatButton.textContent = "Switch to Voice Responses";
        }
        // Retain audio elements in the chat history
        if (!voiceChatEnabled) {
            let chatBox = document.getElementById("chat-box");
            let audioElements = chatBox.querySelectorAll("audio");
            audioElements.forEach(audio => {
                let audioDiv = document.createElement("div");
                audioDiv.className = "ai-message";
                audioDiv.appendChild(audio);
                chatBox.appendChild(audioDiv);
            });
        }
    })
    .catch(error => console.error("Error toggling voice chat:", error));
}

function showDisclaimer() {
    document.getElementById("disclaimer-modal").style.display = "block";
}

function closeDisclaimer() {
    document.getElementById("disclaimer-modal").style.display = "none";
}

// Close the modal when the user clicks anywhere outside of it
window.onclick = function(event) {
    let modal = document.getElementById("disclaimer-modal");
    if (event.target == modal) {
        modal.style.display = "none";
    }
}

// Add event listeners
document.getElementById("message-input").addEventListener("keypress", function(event) {
    // Only handle Enter key press on non-mobile devices
    if (event.key === "Enter" && !isMobileDevice()) {
        sendMessage();
    }
});

document.getElementById("scenario-input").addEventListener("keypress", function(event) {
    // Only handle Enter key press on non-mobile devices
    if (event.key === "Enter" && !isMobileDevice()) {
        setScenario();
    }
});

document.getElementById("name-form").addEventListener("submit", function(event) {
    event.preventDefault(); // Prevent form submission
    setName();
});

// Add event listener for name input
document.getElementById("name-input").addEventListener("keypress", function(event) {
    // Only handle Enter key press on non-mobile devices
    if (event.key === "Enter" && !isMobileDevice()) {
        setName();
    }
});

// Helper function to detect mobile devices
function isMobileDevice() {
    return (window.innerWidth <= 768) || 
           (navigator.maxTouchPoints > 0 && /Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent));
}

// Add event listeners for persona selection in onboarding
document.addEventListener('DOMContentLoaded', function() {
    // Set up persona option click handlers
    document.querySelectorAll('.persona-option').forEach(option => {
        option.addEventListener('click', function() {
            selectedPersonaInOnboarding = this.getAttribute('data-persona');
            selectPersonaInOnboarding(selectedPersonaInOnboarding);
        });
        
        // Add keydown event listener to handle Enter key press (only on desktop)
        option.addEventListener('keydown', function(event) {
            if (event.key === "Enter" && !isMobileDevice()) {
                selectedPersonaInOnboarding = this.getAttribute('data-persona');
                selectPersonaInOnboarding(selectedPersonaInOnboarding);
                nextOnboardingStep();
                event.preventDefault();
            }
        });
        
        // Make personas focusable
        option.setAttribute('tabindex', '0');
    });
    
    // Add event listener for keypresses in the onboarding overlay
    document.getElementById('onboarding-overlay').addEventListener('keydown', handleOnboardingKeydown);
    
    // Check if this is a first-time visitor
    checkFirstTimeVisitor();
    
    // Set the dropdown to match the active persona on load
    document.getElementById("persona-select").value = activePersona;
    
    // Reset state tracking on page load
    personaSet = false;
    nameSet = false;
    scenarioSet = false;
    
    // Add debug logging
    console.log("Page loaded. Chat setup state - Name:", nameSet, "Persona:", personaSet, "Scenario:", scenarioSet);
});