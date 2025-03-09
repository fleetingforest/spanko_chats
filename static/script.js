function sendMessage() {
    let input = document.getElementById("message-input");
    let message = input.value.trim();

    if (message === "") return;

    fetch("/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message }),
    })
    .then(response => response.json())
    .then(data => {
        console.log(data.status);
        window.location.reload(); // Refresh to show new message
    });

    input.value = "";  // Clear input box
}
