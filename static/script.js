// Track the active persona separately from the dropdown selection
let activePersona = "Daddy"; // Default to match the server's default
let userName = "You"; // Default user name
let voiceChatEnabled = false;
let selectedPersonaInOnboarding = null;
let selectedModeInOnboarding = null;
let currentOnboardingStep = 1;
// Add setup state tracking variables
let personaSet = false;
let nameSet = false;
let scenarioSet = false;

// Variables for tracking bold formatting state during streaming
let isBold = false;
let processedText = "";

// Function to process streaming text with bold formatting
function processStreamingText(newContent) {
    let result = "";
    
    for (let i = 0; i < newContent.length; i++) {
        const char = newContent[i];
        
        if (char === '*') {
            // Toggle bold state when we encounter an asterisk
            if (isBold) {
                // We're ending a bold section
                result += '</i>';
                isBold = false;
            } else {
                // We're starting a bold section
                result += '<i>';
                isBold = true;
            }
        } else {
            // Regular character, just add it
            result += char;
        }
    }
    
    return result;
}

// Function to reset bold formatting state
function resetBoldFormatting() {
    isBold = false;
    processedText = "";
}

// Utility function to create audio elements with autoplay
function createAudioElement(audioUrl, container) {
    let audioDiv = document.createElement("div");
    audioDiv.className = "ai-message";
    let audioControl = document.createElement("audio");
    audioControl.controls = true;
    audioControl.autoplay = true;
    audioControl.src = audioUrl;
    
    // Some browsers require interaction before autoplay works
    // This helps ensure autoplay in those cases
    audioControl.muted = true;
    setTimeout(() => {
        audioControl.muted = false;
        audioControl.play().catch(e => console.log("Autoplay prevented by browser:", e));
    }, 100);
    
    audioDiv.appendChild(audioControl);
    container.appendChild(audioDiv);
    return audioDiv;
}

// Check if this is a first-time visitor
function checkFirstTimeVisitor() {
    // Always show the onboarding overlay regardless of whether the user has visited before
    document.getElementById('onboarding-overlay').style.display = 'flex';
    
    // Reset onboarding state
    currentOnboardingStep = 1;
    selectedPersonaInOnboarding = null;
    selectedModeInOnboarding = null;
    
    // Show first step, hide others
    document.querySelectorAll('.onboarding-step').forEach(step => {
        step.classList.remove('active');
    });
    document.querySelector('.onboarding-step[data-step="1"]').classList.add('active');
    
    // Clear any previous selections
    document.querySelectorAll('.persona-option').forEach(option => {
        option.classList.remove('selected');
    });
    
    document.querySelectorAll('.mode-option').forEach(option => {
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

// Handle chat mode selection in onboarding
function selectModeInOnboarding(mode) {
    // Clear previous selections
    document.querySelectorAll('.mode-option').forEach(option => {
        option.classList.remove('selected');
    });
    
    // Select the clicked mode
    event.currentTarget.classList.add('selected');
    selectedModeInOnboarding = mode;
}

// Handle keydown events in the onboarding overlay
function handleOnboardingKeydown(event) {
    // If Enter key is pressed on the first step (persona selection)
    if (event.key === "Enter" && currentOnboardingStep === 1 && selectedPersonaInOnboarding) {
        nextOnboardingStep();
    }
    
    // If Enter key is pressed on the third step (chat mode selection)
    if (event.key === "Enter" && currentOnboardingStep === 3 && selectedModeInOnboarding) {
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
    
    if (currentOnboardingStep === 3 && !selectedModeInOnboarding) {
        alert("Please select a chat mode to continue.");
        return;
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

// Store the voice chat mode in localStorage when redirecting
function completeOnboarding() {
    const scenarioInput = document.getElementById('onboarding-scenario');
    const scenario = scenarioInput.value.trim();
    
    if (!scenario) {
        alert("Please describe a scenario to continue.");
        return;
    }
    
    // Store settings in localStorage
    localStorage.setItem('userName', userName);
    localStorage.setItem('selectedPersona', selectedPersonaInOnboarding);
    localStorage.setItem('scenario', scenario);
    
    // Also store the flag indicating scenario was set to prevent onboarding on redirect
    localStorage.setItem('scenarioSet', 'true');
    
    // Store voice chat preference in localStorage
    localStorage.setItem('voiceChatEnabled', selectedModeInOnboarding === 'voice' ? 'true' : 'false');
    
    // Check if we need to redirect based on selected mode
    const currentPath = window.location.pathname;
    const isVoiceChatPage = currentPath.includes('voice_chat');
    const shouldBeVoiceChatPage = selectedModeInOnboarding === 'voice';
    
    if (shouldBeVoiceChatPage && !isVoiceChatPage) {
        // Set the internal redirect flag before redirecting - both local and in localStorage
        isInternalRedirect = true;
        localStorage.setItem('isInternalRedirect', 'true');
        
        // First, try to set the scenario in the current page before redirecting
        fetch("/set_scenario", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ scenario: scenario }),
        })
        .then(() => {
            // If we need to switch to voice chat, redirect
            window.location.href = "/voice_chat";
        })
        .catch(() => {
            // Even if setting scenario fails, still redirect
            window.location.href = "/voice_chat";
        });
        return;
    } else if (!shouldBeVoiceChatPage && isVoiceChatPage) {
        // Set the internal redirect flag before redirecting - both local and inLocalStorage
        isInternalRedirect = true;
        localStorage.setItem('isInternalRedirect', 'true');
        
        // First, try to set the scenario in the current page before redirecting
        fetch("/set_scenario", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ scenario: scenario }),
        })
        .then(() => {
            // If we need to switch to text chat, redirect
            window.location.href = "/";
        })
        .catch(() => {
            // Even if setting scenario fails, still redirect
            window.location.href = "/";
        });
        return;
    }
    
    // If we're already on the correct page, complete the onboarding
    voiceChatEnabled = shouldBeVoiceChatPage;
    
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
    personaSet = true;
    
    // Trigger the setPersona function which will also handle the scenario
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
    
    // Add user message to chat box immediately for both modes
    let userDiv = document.createElement("div");
    userDiv.className = "user-message";
    userDiv.textContent = userName + ": " + message;
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

    // Use different endpoints based on voice chat mode
    if (voiceChatEnabled) {
        // For voice chat, use the non-streaming endpoint to get complete text for TTS
        fetch("/send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                message: message,
                user_name: userName 
            }),
        })
        .then(response => response.json())
        .then(data => {
            // Remove typing indicator
            if (chatBox.contains(typingDiv)) {
                chatBox.removeChild(typingDiv);
            }

            if (data.status && data.status.includes("exceeded")) {
                displayError(data);
                return;
            }

            // For voice mode: Don't call updateChat, manually handle the display
            // Add audio element
            if (data.audio_url) {
                createAudioElement(data.audio_url, chatBox);
            }

            // Update persona if changed
            if (data.current_persona) {
                activePersona = data.current_persona;
            }

            // Show Patreon promotion if provided
            if (data.patreon_promo) {
                if (typeof showPatreonModal === 'function') {
                    showPatreonModal(data.patreon_promo);
                } else {
                    const promoDiv = document.createElement('div');
                    promoDiv.innerHTML = data.patreon_promo;
                    chatBox.appendChild(promoDiv);
                }
            }

            chatBox.scrollTop = chatBox.scrollHeight;
        })
        .catch(error => {
            console.error("Error sending message:", error);
            if (chatBox.contains(typingDiv)) {
                chatBox.removeChild(typingDiv);
            }
            displayError({ status: "Error", message: "Failed to send message. Please try again." });
        });
    } else {
        // For text chat, use streaming endpoint for better user experience
        const streamUrl = `/send_stream?message=${encodeURIComponent(message)}&user_name=${encodeURIComponent(userName)}`;
        const evtSource = new EventSource(streamUrl);
        let aiContent = "";

        // Reset bold formatting state for new message
        resetBoldFormatting();

        evtSource.onmessage = function(event) {
            if (event.data === "[DONE]") {
                evtSource.close();
                return;
            }

            const data = JSON.parse(event.data);
            if (data.type === "start") {
                typingDiv.textContent = characterName + ": ";
                // Reset bold formatting state when starting new message
                resetBoldFormatting();
            } else if (data.type === "content") {
                // Process the new content chunk with bold formatting
                const processedChunk = processStreamingText(data.content);
                processedText += processedChunk;
                
                // Update the display with the processed text
                typingDiv.innerHTML = characterName + ": " + processedText.replace(/\n/g, "<br>");
                chatBox.scrollTop = chatBox.scrollHeight;
            } else if (data.type === "complete") {
                evtSource.close();
                // Ensure any unclosed italic tags are properly closed
                if (isBold) {
                    processedText += '</i>';
                    typingDiv.innerHTML = characterName + ": " + processedText.replace(/\n/g, "<br>");
                }

                // Update persona if changed
                if (data.current_persona) {
                    activePersona = data.current_persona;
                }

                // Show Patreon promotion if provided
                if (data.patreon_promo) {
                    if (typeof showPatreonModal === 'function') {
                        showPatreonModal(data.patreon_promo);
                    } else {
                        const promoDiv = document.createElement('div');
                        promoDiv.innerHTML = data.patreon_promo;
                        chatBox.appendChild(promoDiv);
                    }
                }

                chatBox.scrollTop = chatBox.scrollHeight;
            } else if (data.type === "error") {
                evtSource.close();
                chatBox.removeChild(typingDiv);
                displayError(data);
            }
        };

        evtSource.onerror = function(err) {
            console.error("Stream error:", err);
            evtSource.close();
            if (chatBox.contains(typingDiv)) {
                chatBox.removeChild(typingDiv);
            }
        };
    }

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
    
    // Use different endpoints based on voice chat mode
    if (voiceChatEnabled) {
        // For voice chat, use the non-streaming endpoint to get complete text for TTS
        fetch("/get_first_message", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_name: userName }),
        })
        .then(response => response.json())
        .then(data => {
            // Remove typing indicator
            if (chatBox.contains(typingDiv)) {
                chatBox.removeChild(typingDiv);
            }

            if (data.status && data.status.includes("exceeded")) {
                displayError(data);
                return;
            }

            // For voice mode: Don't call updateChat, manually handle the display
            // Add audio element
            if (data.audio_url) {
                createAudioElement(data.audio_url, chatBox);
            }

            // Update persona if changed
            if (data.current_persona) {
                activePersona = data.current_persona;
            }

            // Show Patreon promotion if provided
            if (data.patreon_promo) {
                if (typeof showPatreonModal === 'function') {
                    showPatreonModal(data.patreon_promo);
                } else {
                    const promoDiv = document.createElement('div');
                    promoDiv.innerHTML = data.patreon_promo;
                    chatBox.appendChild(promoDiv);
                }
            }

            chatBox.scrollTop = chatBox.scrollHeight;
        })
        .catch(error => {
            console.error("Error getting first message:", error);
            if (chatBox.contains(typingDiv)) {
                chatBox.removeChild(typingDiv);
            }
            displayError({ status: "Error", message: "Failed to get first message. Please try again." });
        });
    } else {
        // For text chat, use streaming endpoint for better user experience
        const streamUrl = `/get_first_message_stream?user_name=${encodeURIComponent(userName)}`;
        const evtSource = new EventSource(streamUrl);
        let aiContent = "";

        // Reset bold formatting state for new message
        resetBoldFormatting();

        evtSource.onmessage = function(event) {
            if (event.data === "[DONE]") {
                evtSource.close();
                return;
            }

            const data = JSON.parse(event.data);
            if (data.type === "start") {
                typingDiv.textContent = characterName + ": ";
            } else if (data.type === "content") {
                // Process the new content chunk with bold formatting
                const processedChunk = processStreamingText(data.content);
                processedText += processedChunk;
                
                // Update the display with the processed text
                typingDiv.innerHTML = characterName + ": " + processedText.replace(/\n/g, "<br>");
                chatBox.scrollTop = chatBox.scrollHeight;
            } else if (data.type === "complete") {
                evtSource.close();
                // Ensure any unclosed italic tags are properly closed
                if (isBold) {
                    processedText += '</i>';
                    typingDiv.innerHTML = characterName + ": " + processedText.replace(/\n/g, "<br>");
                }

                // Update persona if changed
                if (data.current_persona) {
                    activePersona = data.current_persona;
                }

                // Show Patreon promotion if provided
                if (data.patreon_promo) {
                    if (typeof showPatreonModal === 'function') {
                        showPatreonModal(data.patreon_promo);
                    } else {
                        const promoDiv = document.createElement('div');
                        promoDiv.innerHTML = data.patreon_promo;
                        chatBox.appendChild(promoDiv);
                    }
                }

                chatBox.scrollTop = chatBox.scrollHeight;
            } else if (data.type === "error") {
                evtSource.close();
                chatBox.removeChild(typingDiv);
                displayError(data);
            }
        };

        evtSource.onerror = function(err) {
            console.error("Stream error:", err);
            evtSource.close();
            if (chatBox.contains(typingDiv)) {
                chatBox.removeChild(typingDiv);
            }
        };
    }
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
    
    // Don't proceed if persona is empty or undefined
    if (!persona) {
        console.error("Attempted to set empty persona, aborting request");
        return;
    }
    
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

    // Clear saved settings from localStorage
    localStorage.removeItem('userName');
    localStorage.removeItem('selectedPersona');
    localStorage.removeItem('scenario');

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
        // In voice chat mode, handle AI messages differently
        if (voiceChatEnabled && msg.role === "assistant") {
            // For AI messages in voice mode, just add the audio element
            // If there's an audio URL attached to this message, create the audio element
            if (msg.audio_url) {
                createAudioElement(msg.audio_url, chatBox);
            }
            return; // Skip the rest of the processing for AI messages in voice mode
        }

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
            // Format text between asterisks as italics with capitalized first letter
            .replace(/\*([\w\s,'\-\.;:!?]+?)\*/g, (match, p1) => {
                // Capitalize first letter of asterisk-wrapped text
                let capitalized = p1.charAt(0).toUpperCase() + p1.slice(1);
                return `<i>${capitalized}</i>`;
            })
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
            createAudioElement(msg.audio_url, chatBox);
        }
    });

    chatBox.scrollTop = chatBox.scrollHeight;
}

// Add helper to show styled errors in the chat box
function displayError(data) {
    // Check if this is a token limit error that should be shown as a modal
    if (data.status === "Token limit exceeded") {
        // Check if we have limit_data (new format) or message (old format)
        if (data.limit_data && typeof showPatreonModal === 'function') {
            // Use the structured data from the server
            showPatreonModal(data.limit_data);
            return; // Don't show in chat
        }
    }
    
    // Default error display for non-token limit errors
    const chatBox = document.getElementById("chat-box");
    const errorDiv = document.createElement("div");
    errorDiv.className = "error-message";
    // Use innerHTML to include link
    errorDiv.innerHTML = `
        <strong>${data.status || data.error}</strong>
        <p>${data.message || ''}</p>
        ${data.patreon_url ? `<p><a href="${data.patreon_url}" target="_blank">Support on Patreon</a></p>` : ''}
    `;
    chatBox.appendChild(errorDiv);
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

// Function removed as per requirements

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
document.getElementById("message-input").addEventListener("keydown", function(event) {
    if (event.key === "Enter") {
        if (event.shiftKey) {
            // For Shift+Enter: Allow default behavior (line break)
            return true;
        } else {
            // For Enter without Shift: Send message
            event.preventDefault(); // Prevent default to avoid line break
            sendMessage();
        }
    }
});

document.getElementById("scenario-input").addEventListener("keydown", function(event) {
    if (event.key === "Enter") {
        if (event.shiftKey) {
            // For Shift+Enter: Allow default behavior (line break)
            return true;
        } else {
            // For Enter without Shift: Set scenario
            event.preventDefault(); // Prevent default to avoid line break
            setScenario();
        }
    }
});

document.getElementById("name-form").addEventListener("submit", function(event) {
    event.preventDefault(); // Prevent form submission
    setName();
});

// Add event listener for name input
document.getElementById("name-input").addEventListener("keydown", function(event) {
    if (event.key === "Enter") {
        if (event.shiftKey) {
            // For Shift+Enter: Allow default behavior (line break)
            return true;
        } else {
            // For Enter without Shift: Set name
            event.preventDefault(); // Prevent default to avoid line break
            setName();
        }
    }
});

// New function to load saved settings
function loadSavedSettings() {
    const savedUserName = localStorage.getItem('userName');
    const savedPersona = localStorage.getItem('selectedPersona');
    const savedScenario = localStorage.getItem('scenario');
    const wasScenarioSet = localStorage.getItem('scenarioSet');
    
    if (savedUserName && savedPersona && savedScenario) {
        console.log("Found saved settings, loading them...");
        
        // Set the saved values to our variables
        userName = savedUserName;
        selectedPersonaInOnboarding = savedPersona;
        activePersona = savedPersona;
        
        // Set form values if elements exist
        const nameInput = document.getElementById('name-input');
        const personaSelect = document.getElementById('persona-select');
        const scenarioInput = document.getElementById('scenario-input');
        
        if (nameInput) nameInput.value = savedUserName;
        if (personaSelect) personaSelect.value = savedPersona;
        if (scenarioInput) scenarioInput.value = savedScenario;
        
        // Hide onboarding since we have all the info
        const onboardingOverlay = document.getElementById('onboarding-overlay');
        if (onboardingOverlay) onboardingOverlay.style.display = 'none';
        
        // Hide setup sections since we have the info
        const nameSection = document.getElementById('name-section');
        const personaSection = document.getElementById('persona-section');
        const scenarioLabel = document.getElementById('scenario-label');
        const scenarioSection = document.getElementById('scenario-section');
        const scenarioButton = document.getElementById('set-scenario-button');
        
        if (nameSection) nameSection.style.display = 'none';
        if (personaSection) personaSection.style.display = 'none';
        
        // If scenario was previously set, hide the scenario input section
        if (wasScenarioSet === 'true') {
            if (scenarioLabel) scenarioLabel.style.display = 'none';
            if (scenarioInput) scenarioInput.style.display = 'none';
            if (scenarioButton) scenarioButton.style.display = 'none';
            scenarioSet = true;
        }
        
        // Set our state tracking variables
        nameSet = true;
        personaSet = true;
        
        // Note: We don't call setPersona() here anymore, we'll do that later after the DOM is fully ready
        
        return true;
    }
    
    return false;
}

// Add function to trace the empty persona request
function debugRequest(url, method, body) {
    // Clone the original fetch function
    const originalFetch = window.fetch;
    
    // Override the fetch function
    window.fetch = function(input, init) {
        // Check if this is a request to set_persona
        if (input === "/set_persona" && init && init.method === "POST") {
            const bodyContent = JSON.parse(init.body);
            console.log("SET_PERSONA REQUEST DETECTED:", {
                url: input,
                method: init.method,
                persona: bodyContent.persona,
                stackTrace: new Error().stack
            });
        }
        
        // Call the original fetch function
        return originalFetch.apply(this, arguments);
    };
    
    // Let this function run for 10 seconds then restore original fetch
    setTimeout(() => {
        window.fetch = originalFetch;
        console.log("Fetch debugging disabled");
    }, 10000);
}

// Add logging to detect page transitions
document.addEventListener('DOMContentLoaded', function() {
    console.log("DOMContentLoaded event triggered");
    
    // Check if we just redirected from another chat mode
    const isRedirecting = localStorage.getItem('isInternalRedirect') === 'true';
    if (isRedirecting) {
        console.log("Detected internal redirect between chat modes");
        // Clear the redirect flag now that we've detected it
        localStorage.removeItem('isInternalRedirect');
    }
    
    // Check if we should be in voice chat mode based on localStorage
    const savedVoiceChatMode = localStorage.getItem('voiceChatEnabled');
    if (savedVoiceChatMode !== null) {
        // Set the voice chat mode based on the stored value
        voiceChatEnabled = savedVoiceChatMode === 'true';
        console.log("Voice chat enabled from localStorage:", voiceChatEnabled);
    } else {
        // Set voice chat mode based on current URL path
        voiceChatEnabled = window.location.pathname.includes('voice_chat');
        console.log("Voice chat enabled based on URL:", voiceChatEnabled);
    }
    
    // Enable fetch debugging
    debugRequest();
    
    // Set the dropdown to match the active persona on load
    // IMPORTANT: Do this before any other operations to ensure a valid selection
    const personaSelect = document.getElementById("persona-select");
    if (personaSelect) {
        personaSelect.value = personaSelect.value || activePersona;
    }
    
    // First try to load saved settings
    const hasSavedSettings = loadSavedSettings() || isRedirecting;

    if (!hasSavedSettings) {
        console.log("No saved settings found, showing onboarding overlay");
        // Only show first-time setup if we don't have saved settings
        checkFirstTimeVisitor();
    } else {
        console.log("Saved settings loaded successfully, hiding onboarding overlay");
        // Hide the onboarding overlay explicitly if settings are loaded
        const onboardingOverlay = document.getElementById('onboarding-overlay');
        if (onboardingOverlay) {
            onboardingOverlay.style.display = 'none';
        }

        // Apply the loaded settings to the page
        const scenarioInput = document.getElementById('scenario-input');
        const nameInput = document.getElementById('name-input');

        if (scenarioInput) {
            scenarioInput.value = localStorage.getItem('scenario');
        }

        if (nameInput) {
            nameInput.value = localStorage.getItem('userName');
        }

        // We handle setting the persona later
    }

    // Set up persona option click handlers
    document.querySelectorAll('.persona-option').forEach(option => {
        option.addEventListener('click', function() {
            selectedPersonaInOnboarding = this.getAttribute('data-persona');
            selectPersonaInOnboarding(selectedPersonaInOnboarding);
        });

        // Add keydown event listener to handle Enter key press
        option.addEventListener('keydown', function(event) {
            if (event.key === "Enter") {
                selectedPersonaInOnboarding = this.getAttribute('data-persona');
                selectPersonaInOnboarding(selectedPersonaInOnboarding);
                nextOnboardingStep();
                event.preventDefault();
            }
        });

        // Make personas focusable
        option.setAttribute('tabindex', '0');
    });

    // Set up mode option click handlers
    document.querySelectorAll('.mode-option').forEach(option => {
        option.addEventListener('click', function() {
            selectedModeInOnboarding = this.getAttribute('data-mode');
            selectModeInOnboarding(selectedModeInOnboarding);
        });

        // Add keydown event listener to handle Enter key press
        option.addEventListener('keydown', function(event) {
            if (event.key === "Enter") {
                selectedModeInOnboarding = this.getAttribute('data-mode');
                selectModeInOnboarding(selectedModeInOnboarding);
                nextOnboardingStep();
                event.preventDefault();
            }
        });
    });

    // Add event listener for keypresses in the onboarding overlay
    document.getElementById('onboarding-overlay').addEventListener('keydown', handleOnboardingKeydown);

    // IMPORTANT: We only call checkFirstTimeVisitor once, and only if we don't have saved settings
    // Removed second call to checkFirstTimeVisitor() that was causing double initialization

    // Reset state tracking on page load
    personaSet = false;
    nameSet = false;
    scenarioSet = false;

    // Wait for the DOM to be fully set up before triggering persona-related actions
    setTimeout(() => {
        // Now that everything is initialized, trigger persona loading if we have saved settings
        if (hasSavedSettings) {
            const savedPersona = localStorage.getItem('selectedPersona');
            const savedScenario = localStorage.getItem('scenario');
            
            if (savedPersona && personaSelect) {
                personaSelect.value = savedPersona;
                
                // First set the persona
                setPersona(true); 
                
                // Then ensure the scenario is set in the backend if it was previously set
                if (localStorage.getItem('scenarioSet') === 'true' && savedScenario) {
                    // Set the scenario in the backend
                    fetch("/set_scenario", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ scenario: savedScenario }),
                    })
                    .then(response => response.json())
                    .then(data => {
                        console.log("Scenario restored on page transition:", data.status);
                        scenarioSet = true;
                        
                        // Show the new chat button since we're resuming a chat
                        document.getElementById("new-chat-button").style.display = "block";
                        
                        // Request the first AI message
                        setTimeout(() => {
                            getAiFirstMessage();
                        }, 500);
                    })
                    .catch(error => console.error("Error setting scenario during transition:", error));
                }
            }
        }
    }, 100);

    // Add debug logging
    console.log("Page loaded. Chat setup state - Name:", nameSet, "Persona:", personaSet, "Scenario:", scenarioSet);

    // Let the client tell us whether voice chat is enabled
    fetch("/toggle_voice_chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice_chat_enabled: voiceChatEnabled }),
    })
    .then(response => response.json())
    .then(data => {
        console.log("Voice chat mode set on server:", data.voice_chat_enabled);
    })
    .catch(error => console.error("Error setting voice chat mode:", error));
});

// Function to clear all saved information when user leaves the page
function clearSavedInformation() {
    // Clear all saved settings from localStorage
    localStorage.removeItem('userName');
    localStorage.removeItem('selectedPersona');
    localStorage.removeItem('scenario');
    localStorage.removeItem('scenarioSet');
    localStorage.removeItem('voiceChatEnabled');
    console.log("Cleared all saved user information");
}

// Track if we're doing an internal redirect between chat pages
let isInternalRedirect = false;

// Function to handle page unload/refresh events
function handlePageUnload() {
    // Check localStorage for the redirect flag
    const isRedirecting = localStorage.getItem('isInternalRedirect') === 'true';
    
    // Don't clear data if we're doing an internal redirect between chat modes
    if (!isInternalRedirect && !isRedirecting) {
        clearSavedInformation();
        console.log("Page unloading: localStorage cleared");
    } else {
        console.log("Internal redirect detected: preserving localStorage");
        // Reset the flag if the navigation is cancelled
        isInternalRedirect = false;
    }
}

// Add event listeners for page unload/reload
// Using multiple events for better cross-browser support, especially on mobile
window.addEventListener('beforeunload', handlePageUnload);
window.addEventListener('pagehide', handlePageUnload);

// Add event listener when a new page is being loaded (navigation started)
window.addEventListener('unload', function() {
    // Final reset of the local flag when the page is actually unloaded
    // (but don't clear the localStorage flag here - that gets cleared after the new page loads)
    isInternalRedirect = false;
    console.log("Page unloaded: local isInternalRedirect reset");
});