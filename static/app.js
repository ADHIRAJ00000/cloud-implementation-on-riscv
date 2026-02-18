// Cloud RISC-V - Main JavaScript

// Utility function for API calls
async function api(endpoint, method = "GET", data = null) {
  const options = {
    method,
    headers: {
      "Content-Type": "application/json",
    },
  };

  if (data) {
    options.body = JSON.stringify(data);
  }

  const response = await fetch(endpoint, options);
  return response.json();
}

// Format date
function formatDate(dateStr) {
  return new Date(dateStr).toLocaleString();
}

// Show notification
function showNotification(message, type = "info") {
  const notification = document.createElement("div");
  notification.className = `notification ${type}`;
  notification.textContent = message;
  document.body.appendChild(notification);

  setTimeout(() => {
    notification.remove();
  }, 3000);
}

console.log("Cloud RISC-V loaded");
