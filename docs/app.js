// ---- Configuration ----
const API_URL = "https://mcgraw-solver-production.up.railway.app";
let currentPlan = "";

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

// Toggle between Stripe and Venmo payment forms
function togglePaymentMethod() {
  const method = document.querySelector('input[name="payment-method"]:checked').value;
  const stripeFields = document.getElementById('stripe-fields');
  const venmoFields = document.getElementById('venmo-fields');
  const paymentOptions = document.querySelectorAll('.payment-option');

  if (method === 'stripe') {
    stripeFields.style.display = 'block';
    venmoFields.style.display = 'none';
    paymentOptions[0].style.borderColor = 'var(--accent-blue)';
    paymentOptions[1].style.borderColor = 'var(--border)';
  } else {
    stripeFields.style.display = 'none';
    venmoFields.style.display = 'block';
    paymentOptions[0].style.borderColor = 'var(--border)';
    paymentOptions[1].style.borderColor = 'var(--accent-blue)';
  }
}

// Open checkout modal
function openCheckout(plan) {
  currentPlan = plan;

  // Set plan name
  const planNames = {
    'weekly': 'Weekly Plan ($10)',
    'monthly': 'Monthly Plan ($25)',
    'semester': 'Semester Plan ($50)'
  };
  document.getElementById('checkout-plan-name').textContent = planNames[plan];

  // Set Venmo amount
  const venmoAmounts = {'weekly': '10', 'monthly': '25', 'semester': '50'};
  document.getElementById('venmo-amount').textContent = venmoAmounts[plan];

  // Set hidden plan value for Venmo form
  document.getElementById('checkout-plan').value = plan;

  // Show modal
  document.getElementById('checkout-modal').classList.add('active');

  // Reset to Stripe by default
  document.querySelector('input[value="stripe"]').checked = true;
  togglePaymentMethod();

  // Clear form messages
  document.getElementById('venmo-message').textContent = '';
  document.getElementById('venmo-message').className = 'form-message';
}

function closeCheckout() {
  document.getElementById('checkout-modal').classList.remove('active');
}

// Close modal on backdrop click
document.getElementById('checkout-modal')?.addEventListener('click', function (e) {
  if (e.target === this) closeCheckout();
});

// Submit Stripe order and redirect to checkout
async function submitStripeOrder(e) {
  e.preventDefault();

  const name = document.getElementById('stripe-name').value.trim();
  const email = document.getElementById('stripe-email').value.trim();
  const referral = document.getElementById('stripe-referral').value.trim();

  if (!name || !email) {
    alert('Please fill in all required fields');
    return;
  }

  try {
    const response = await fetch(`${API_URL}/api/orders/stripe`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        name: name,
        email: email,
        plan: currentPlan,
        referral: referral || null
      })
    });

    const data = await response.json();

    if (response.ok && data.session_url) {
      // Redirect to Stripe Checkout
      window.location.href = data.session_url;
    } else {
      alert(data.error || 'Failed to create checkout session');
    }
  } catch (error) {
    console.error('Checkout error:', error);
    alert('Network error. Please try again.');
  }
}

// Submit Venmo order
async function submitVenmoOrder(e) {
  e.preventDefault();
  var msg = document.getElementById('venmo-message');
  var btn = e.target.querySelector('button[type="submit"]');

  btn.disabled = true;
  btn.textContent = "Submitting...";
  msg.textContent = "";
  msg.className = "form-message";

  const name = document.getElementById('venmo-name').value.trim();
  const email = document.getElementById('venmo-email').value.trim();
  const venmoUsername = document.getElementById('venmo-username').value.trim();
  const transactionId = document.getElementById('venmo-transaction-id').value.trim();
  const referral = document.getElementById('venmo-referral').value.trim();

  if (!name || !email || !venmoUsername || !transactionId) {
    msg.textContent = 'Please fill in all required fields';
    msg.className = 'form-message error';
    btn.disabled = false;
    btn.textContent = "Submit Venmo Order →";
    return;
  }

  var payload = {
    name: name,
    email: email,
    venmo_username: venmoUsername,
    transaction_id: transactionId,
    plan: currentPlan,
    referral: referral || null,
    payment_method: 'venmo'
  };

  try {
    var resp = await fetch(API_URL + "/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    var data = await resp.json();
    if (resp.ok && data.success) {
      msg.textContent = "Order submitted! You will receive an email once approved (usually within 24 hours).";
      msg.className = "form-message success";
      btn.textContent = "Order Submitted!";
    } else {
      msg.textContent = data.error || "Something went wrong. Please try again.";
      msg.className = "form-message error";
      btn.disabled = false;
      btn.textContent = "Submit Venmo Order →";
    }
  } catch (err) {
    msg.textContent = "Network error. Please check your connection and try again.";
    msg.className = "form-message error";
    btn.disabled = false;
    btn.textContent = "Submit Venmo Order →";
  }
}

// Handle Stripe success redirect
function handleStripeSuccess() {
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.has('session_id')) {
    document.getElementById('success-message').style.display = 'block';
    // Scroll to success message
    document.getElementById('success-message').scrollIntoView({ behavior: 'smooth' });
    // Clear URL params
    window.history.replaceState({}, document.title, window.location.pathname);
  }
}

// Run on page load
document.addEventListener('DOMContentLoaded', function() {
  handleStripeSuccess();
});

// ---- Admin Dashboard ----

var adminToken = localStorage.getItem("adminToken") || "";

// Check for existing token on page load
if (adminToken && document.getElementById("admin-dashboard")) {
  verifyTokenAndLoadDashboard();
}

async function verifyTokenAndLoadDashboard() {
  try {
    var resp = await fetch(API_URL + "/api/admin/orders", {
      headers: { "Authorization": "Bearer " + adminToken },
    });
    if (resp.ok) {
      document.getElementById("admin-login-section").style.display = "none";
      document.getElementById("admin-dashboard").classList.add("active");
      loadOrders();
    } else {
      // Token is invalid or expired
      adminToken = "";
      localStorage.removeItem("adminToken");
    }
  } catch (err) {
    // Network error, keep login form visible
  }
}

async function adminLogin(e) {
  e.preventDefault();
  var password = document.getElementById("admin-password").value;
  var msg = document.getElementById("admin-login-message");

  try {
    var resp = await fetch(API_URL + "/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: password }),
    });
    var data = await resp.json();

    if (resp.ok && data.token) {
      adminToken = data.token;
      localStorage.setItem("adminToken", adminToken);
      document.getElementById("admin-login-section").style.display = "none";
      document.getElementById("admin-dashboard").classList.add("active");
      loadOrders();
    } else {
      msg.textContent = data.error || "Invalid password";
      msg.className = "form-message error";
    }
  } catch (err) {
    msg.textContent = "Connection error";
    msg.className = "form-message error";
  }
  return false;
}

function adminLogout() {
  adminToken = "";
  localStorage.removeItem("adminToken");
  document.getElementById("admin-login-section").style.display = "block";
  document.getElementById("admin-dashboard").classList.remove("active");
}

async function loadOrders() {
  var pendingBody = document.getElementById("pending-orders-body");
  var historyBody = document.getElementById("history-orders-body");
  if (!pendingBody) return;

  pendingBody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-dim)">Loading...</td></tr>';

  try {
    var resp = await fetch(API_URL + "/api/admin/orders", {
      headers: { "Authorization": "Bearer " + adminToken },
    });
    var data = await resp.json();
    var orders = data.orders || [];

    var pending = orders.filter(function (o) { return o.status === "pending"; });
    var history = orders.filter(function (o) { return o.status !== "pending"; });

    // Render pending
    if (pending.length === 0) {
      pendingBody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-dim)">No pending orders</td></tr>';
    } else {
      pendingBody.innerHTML = pending.map(function (o) {
        var paymentBadge = o.payment_method === 'stripe'
          ? '<span style="background:#10b981;color:white;padding:4px 8px;border-radius:4px;font-size:0.85rem;">Stripe</span>'
          : '<span style="background:#6366f1;color:white;padding:4px 8px;border-radius:4px;font-size:0.85rem;">Venmo</span>';
        return '<tr>' +
          '<td>' + escHtml(o.name) + '</td>' +
          '<td>' + escHtml(o.email) + '</td>' +
          '<td>' + escHtml(o.plan) + '</td>' +
          '<td>' + paymentBadge + '</td>' +
          '<td>' + (o.venmo_username ? escHtml(o.venmo_username) : '-') + '</td>' +
          '<td>' + (o.transaction_id ? escHtml(o.transaction_id) : '-') + '</td>' +
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
      historyBody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-dim)">No history yet</td></tr>';
    } else {
      historyBody.innerHTML = history.sort(function (a, b) {
        return (b.approved_at || b.created || "").localeCompare(a.approved_at || a.created || "");
      }).map(function (o) {
        var statusClass = "status-" + o.status;
        var paymentBadge = o.payment_method === 'stripe'
          ? '<span style="background:#10b981;color:white;padding:4px 8px;border-radius:4px;font-size:0.85rem;">Stripe</span>'
          : '<span style="background:#6366f1;color:white;padding:4px 8px;border-radius:4px;font-size:0.85rem;">Venmo</span>';
        return '<tr>' +
          '<td>' + escHtml(o.name) + '</td>' +
          '<td>' + escHtml(o.email) + '</td>' +
          '<td>' + escHtml(o.plan) + '</td>' +
          '<td>' + paymentBadge + '</td>' +
          '<td><span class="status-badge ' + statusClass + '">' + o.status + '</span></td>' +
          '<td>' + (o.key ? '<span class="key-display">' + escHtml(o.key) + '</span>' : '-') + '</td>' +
          '<td>' + (o.referral ? escHtml(o.referral) : '-') + '</td>' +
          '<td>' + formatDate(o.approved_at || o.created) + '</td>' +
          '<td>' + (o.transaction_id ? escHtml(o.transaction_id) : '-') + '</td>' +
        '</tr>';
      }).join("");
    }
  } catch (err) {
    pendingBody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--accent-red)">Error loading orders</td></tr>';
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
        "Authorization": "Bearer " + adminToken,
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
        "Authorization": "Bearer " + adminToken,
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

async function syncStripe() {
  var btn = document.getElementById("sync-stripe-btn");
  var originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Syncing...";

  try {
    var resp = await fetch(API_URL + "/api/admin/sync-stripe", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + adminToken,
      },
    });
    var data = await resp.json();

    if (resp.ok) {
      alert(data.message || "Stripe sync completed successfully");
      loadOrders();
    } else {
      alert("Error: " + (data.error || "Failed to sync from Stripe"));
    }
  } catch (err) {
    alert("Network error");
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
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
