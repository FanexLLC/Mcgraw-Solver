// ---- Configuration ----
const API_URL = "https://mcgraw-solver-production.up.railway.app";

// ---- Mobile Nav Toggle ----
(function () {
  var toggle = document.getElementById("nav-toggle");
  var links = document.getElementById("nav-links");
  if (!toggle || !links) return;

  toggle.addEventListener("click", function () {
    toggle.classList.toggle("active");
    links.classList.toggle("open");
  });

  // Close menu when a link is tapped
  links.querySelectorAll("a").forEach(function (a) {
    a.addEventListener("click", function () {
      toggle.classList.remove("active");
      links.classList.remove("open");
    });
  });
})();

// ---- Checkout Modal ----

function openCheckout(plan, label) {
  document.getElementById("checkout-plan").value = plan;
  document.getElementById("checkout-plan-label").textContent = "Plan: " + label;
  document.getElementById("checkout-message").textContent = "";
  document.getElementById("checkout-form").reset();
  document.getElementById("checkout-plan").value = plan;
  document.getElementById("checkout-modal").classList.add("active");
}

function closeCheckout() {
  document.getElementById("checkout-modal").classList.remove("active");
}

// Close modal on backdrop click
document.getElementById("checkout-modal")?.addEventListener("click", function (e) {
  if (e.target === this) closeCheckout();
});

async function submitOrder(e) {
  e.preventDefault();
  var btn = document.getElementById("checkout-submit");
  var msg = document.getElementById("checkout-message");
  btn.disabled = true;
  btn.textContent = "Submitting...";
  msg.textContent = "";
  msg.className = "form-message";

  var payload = {
    name: document.getElementById("checkout-name").value.trim(),
    email: document.getElementById("checkout-email").value.trim(),
    venmo_username: document.getElementById("checkout-venmo").value.trim(),
    transaction_id: document.getElementById("checkout-txn").value.trim(),
    plan: document.getElementById("checkout-plan").value,
    referral: document.getElementById("checkout-referral").value.trim(),
  };

  try {
    var resp = await fetch(API_URL + "/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    var data = await resp.json();
    if (resp.ok && data.success) {
      msg.textContent = data.message;
      msg.className = "form-message success";
      btn.textContent = "Order Submitted!";
    } else {
      msg.textContent = data.error || "Something went wrong. Please try again.";
      msg.className = "form-message error";
      btn.disabled = false;
      btn.textContent = "Submit Order";
    }
  } catch (err) {
    msg.textContent = "Network error. Please check your connection and try again.";
    msg.className = "form-message error";
    btn.disabled = false;
    btn.textContent = "Submit Order";
  }
  return false;
}

// ---- Admin Dashboard ----

var adminPassword = "";

async function adminLogin(e) {
  e.preventDefault();
  adminPassword = document.getElementById("admin-password").value;
  var msg = document.getElementById("admin-login-message");

  try {
    var resp = await fetch(API_URL + "/api/admin/orders", {
      headers: { "X-Admin-Password": adminPassword },
    });
    if (resp.ok) {
      document.getElementById("admin-login-section").style.display = "none";
      document.getElementById("admin-dashboard").classList.add("active");
      loadOrders();
    } else {
      msg.textContent = "Invalid password";
      msg.className = "form-message error";
      adminPassword = "";
    }
  } catch (err) {
    msg.textContent = "Connection error";
    msg.className = "form-message error";
  }
  return false;
}

async function loadOrders() {
  var pendingBody = document.getElementById("pending-orders-body");
  var historyBody = document.getElementById("history-orders-body");
  if (!pendingBody) return;

  pendingBody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-dim)">Loading...</td></tr>';

  try {
    var resp = await fetch(API_URL + "/api/admin/orders", {
      headers: { "X-Admin-Password": adminPassword },
    });
    var data = await resp.json();
    var orders = data.orders || [];

    var pending = orders.filter(function (o) { return o.status === "pending"; });
    var history = orders.filter(function (o) { return o.status !== "pending"; });

    // Render pending
    if (pending.length === 0) {
      pendingBody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-dim)">No pending orders</td></tr>';
    } else {
      pendingBody.innerHTML = pending.map(function (o) {
        return '<tr>' +
          '<td>' + escHtml(o.name) + '</td>' +
          '<td>' + escHtml(o.email) + '</td>' +
          '<td>' + escHtml(o.venmo_username) + '</td>' +
          '<td>' + escHtml(o.transaction_id) + '</td>' +
          '<td>' + escHtml(o.plan) + '</td>' +
          '<td>' + (o.referral ? escHtml(o.referral) : '-') + '</td>' +
          '<td>' + formatDate(o.created) + '</td>' +
          '<td>' +
            '<button class="btn-sm btn-approve" onclick="approveOrder(\'' + o.id + '\', this)">Approve</button>' +
            '<button class="btn-sm btn-reject" onclick="rejectOrder(\'' + o.id + '\', this)">Reject</button>' +
          '</td>' +
        '</tr>';
      }).join("");
    }

    // Render history
    if (history.length === 0) {
      historyBody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-dim)">No history yet</td></tr>';
    } else {
      historyBody.innerHTML = history.sort(function (a, b) {
        return (b.approved_at || b.created || "").localeCompare(a.approved_at || a.created || "");
      }).map(function (o) {
        var statusClass = "status-" + o.status;
        return '<tr>' +
          '<td>' + escHtml(o.name) + '</td>' +
          '<td>' + escHtml(o.email) + '</td>' +
          '<td>' + escHtml(o.plan) + '</td>' +
          '<td><span class="status-badge ' + statusClass + '">' + o.status + '</span></td>' +
          '<td>' + (o.key ? '<span class="key-display">' + escHtml(o.key) + '</span>' : '-') + '</td>' +
          '<td>' + (o.referral ? escHtml(o.referral) : '-') + '</td>' +
          '<td>' + formatDate(o.approved_at || o.created) + '</td>' +
          '<td>' + escHtml(o.transaction_id) + '</td>' +
        '</tr>';
      }).join("");
    }
  } catch (err) {
    pendingBody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--accent-red)">Error loading orders</td></tr>';
  }
}

async function approveOrder(orderId, btn) {
  btn.disabled = true;
  btn.textContent = "...";

  try {
    var resp = await fetch(API_URL + "/api/admin/approve", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Admin-Password": adminPassword,
      },
      body: JSON.stringify({ order_id: orderId }),
    });
    var data = await resp.json();
    if (resp.ok && data.success) {
      var emailNote = data.email_sent ? "Email sent!" : "Email failed - share key manually: " + data.key;
      alert("Approved! Key: " + data.key + "\nExpires: " + data.expires + "\n" + emailNote);
      loadOrders();
    } else {
      alert("Error: " + (data.error || "Unknown error"));
      btn.disabled = false;
      btn.textContent = "Approve";
    }
  } catch (err) {
    alert("Network error");
    btn.disabled = false;
    btn.textContent = "Approve";
  }
}

async function rejectOrder(orderId, btn) {
  if (!confirm("Reject this order?")) return;
  btn.disabled = true;

  try {
    var resp = await fetch(API_URL + "/api/admin/reject", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Admin-Password": adminPassword,
      },
      body: JSON.stringify({ order_id: orderId }),
    });
    if (resp.ok) {
      loadOrders();
    } else {
      alert("Error rejecting order");
      btn.disabled = false;
    }
  } catch (err) {
    alert("Network error");
    btn.disabled = false;
  }
}

// ---- Utilities ----

function escHtml(str) {
  if (!str) return "";
  var div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function formatDate(iso) {
  if (!iso) return "-";
  try {
    var d = new Date(iso);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch (e) {
    return iso;
  }
}
