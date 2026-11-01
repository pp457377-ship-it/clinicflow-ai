const $ = (id) => document.getElementById(id);
const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const list = (items) => (items && items.length ? `<ul class="tight">${items.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>` : "-");
const FMT = { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" };
// Appointment slots are shown in clinic time (drop the UTC offset); created_at is shown in the viewer's time.
const fmtSlot = (iso) => (iso ? new Date(iso.slice(0, 16)).toLocaleString("en-AU", FMT) : "-");
const fmt = (iso) => (iso ? new Date(iso).toLocaleString("en-AU", FMT) : "-");
const STATUSES = ["new", "booked", "confirmed", "reviewed", "closed"];
let token = sessionStorage.getItem("adminToken");
let me = sessionStorage.getItem("adminUser");
let intakes = [];
let modalMode = "view"; // view | edit | add
let modalIntakeId = null;

async function api(path, options = {}) {
  const res = await fetch(path, { ...options, headers: { "Content-Type": "application/json", "X-Admin-Key": token || "" } });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) { logout(); throw new Error("Session expired - please log in again"); }
  if (!res.ok) {
    let msg = data.detail || `Request failed (${res.status})`;
    if (Array.isArray(msg)) msg = msg.map((d) => `${d.loc[d.loc.length - 1]}: ${d.msg}`).join("; ");
    throw new Error(msg);
  }
  return data;
}

function logout() {
  if (token) api("/api/admin/logout", { method: "POST" }).catch(() => {});
  token = null;
  me = null;
  sessionStorage.removeItem("adminToken");
  sessionStorage.removeItem("adminUser");
  $("dashboard").classList.add("hidden");
  $("logout").classList.add("hidden");
  $("who").classList.add("hidden");
  $("login-section").classList.remove("hidden");
  closeModal();
}

async function load() {
  const [stats, data, admins] = await Promise.all([
    api("/api/admin/stats"),
    api("/api/admin/intakes"),
    api("/api/admin/admins"),
  ]);
  $("s-total").textContent = stats.total_intakes;
  $("s-emergency").textContent = stats.emergency;
  $("s-urgent").textContent = stats.urgent;
  $("s-routine").textContent = stats.routine;
  $("s-booked").textContent = stats.appointments_booked;
  intakes = data.intakes;
  $("empty").classList.toggle("hidden", intakes.length > 0);
  $("queue").innerHTML = intakes.map((i) => `
    <tr class="clickable" data-id="${i.id}">
      <td>${i.id}</td>
      <td><span class="urgency ${i.urgency}">${i.urgency}</span></td>
      <td><b>${escapeHtml(i.patient_name)}</b><br><span class="disclaimer">${i.age} yrs &middot; ${escapeHtml(i.phone)}</span></td>
      <td>${escapeHtml(i.triage.summary)}</td>
      <td>${fmtSlot(i.appointment_slot)}</td>
      <td><select data-status="${i.id}">${STATUSES.map((s) => `<option ${s === i.status ? "selected" : ""}>${s}</option>`).join("")}</select></td>
      <td class="actions">
        ${i.appointment_slot && i.status === "booked" ? `<button type="button" class="small" data-confirm="${i.id}">Confirm</button>` : ""}
        <button type="button" class="secondary small" data-edit="${i.id}">Edit</button>
        <button type="button" class="danger small" data-del="${i.id}">Delete</button>
      </td>
    </tr>`).join("");
  renderAdmins(admins.admins);
  $("who").textContent = me ? `Signed in as ${me}` : "";
  $("who").classList.remove("hidden");
  $("login-section").classList.add("hidden");
  $("dashboard").classList.remove("hidden");
  $("logout").classList.remove("hidden");
}

function renderAdmins(admins) {
  $("admin-list").innerHTML = admins.map((a) => `
    <div class="admin-row">
      <span><b>${escapeHtml(a.username)}</b>${a.username === me ? " (you)" : ""} <span class="disclaimer">added ${fmt(a.created_at)}</span></span>
      ${a.username === me ? "" : `<button type="button" class="danger small" data-deladmin="${a.id}" data-name="${escapeHtml(a.username)}">Remove</button>`}
    </div>`).join("");
}

// ----------------------------------------------------------------- modal
function openView(i) {
  modalMode = "view";
  modalIntakeId = i.id;
  const t = i.triage;
  const answers = (t.patient_answers || []).map((a) => `<li><b>${escapeHtml(a.question)}</b> ${escapeHtml(a.answer)}</li>`);
  $("m-title").innerHTML = `${escapeHtml(i.patient_name)} <span class="urgency ${i.urgency}">${i.urgency}</span>`;
  $("m-body").innerHTML = `
    <b>Age / sex</b><span>${i.age} / ${escapeHtml(i.gender.replaceAll("_", " "))}</span>
    <b>Contact</b><span>${escapeHtml(i.phone)} ${i.email ? "&middot; " + escapeHtml(i.email) : ""}</span>
    <b>Patient's words</b><span>${escapeHtml(i.symptoms)}</span>
    <b>Duration</b><span>${escapeHtml(i.duration || "-")}</span>
    <b>Follow-up answers</b><span>${answers.length ? `<ul class="tight">${answers.join("")}</ul>` : "-"}</span>
    <b>AI summary</b><span>${escapeHtml(t.summary)}</span>
    <b>Key symptoms</b><span>${list(t.key_symptoms)}</span>
    <b>Red flags</b><span>${list(t.red_flags)}</span>
    <b>Suggested visit</b><span>${escapeHtml(t.suggested_appointment)}</span>
    <b>Questions to ask</b><span>${list(t.questions_for_doctor)}</span>
    <b>Appointment</b><span>${fmtSlot(i.appointment_slot)} (clinic time)</span>
    <b>Status</b><span>${escapeHtml(i.status)}</span>
    <b>Analysed by</b><span>${escapeHtml(t.ai_provider)}</span>
    <b>Submitted</b><span>${fmt(i.created_at)}</span>`;
  $("m-body").classList.remove("hidden");
  $("m-form").classList.add("hidden");
  $("m-actions").classList.remove("hidden");
  $("m-confirmbtn").classList.toggle("hidden", !(i.appointment_slot && i.status === "booked"));
  $("modal-bg").classList.remove("hidden");
}

async function confirmAppointment(id) {
  const r = await api(`/api/admin/intakes/${id}/confirm`, { method: "POST" }).catch((err) => { alert(err.message); return null; });
  if (r) {
    alert(r.email_sent
      ? "Appointment confirmed - confirmation email sent to the patient."
      : "Appointment confirmed. No email was sent (patient has no email address, or SMTP is not configured).");
    closeModal();
    await load();
  }
}

function openForm(mode, i = null) {
  modalMode = mode;
  modalIntakeId = i ? i.id : null;
  $("m-title").textContent = mode === "add" ? "Add patient" : `Edit ${i.patient_name}`;
  $("e-name").value = i ? i.patient_name : "";
  $("e-phone").value = i ? i.phone : "";
  $("e-age").value = i ? i.age : "";
  $("e-gender").value = i ? i.gender : "prefer_not_to_say";
  $("e-email").value = i && i.email ? i.email : "";
  $("e-symptoms").value = i ? i.symptoms : "";
  $("e-duration").value = i ? i.duration || "" : "";
  $("e-status").value = i ? i.status : "new";
  $("e-status").classList.toggle("hidden", mode === "add");
  $("e-status-label").classList.toggle("hidden", mode === "add");
  $("m-save").textContent = mode === "add" ? "Add patient" : "Save changes";
  $("m-error").classList.add("hidden");
  $("m-body").classList.add("hidden");
  $("m-actions").classList.add("hidden");
  $("m-form").classList.remove("hidden");
  $("modal-bg").classList.remove("hidden");
}

function closeModal() {
  $("modal-bg").classList.add("hidden");
}

// ----------------------------------------------------------------- events
$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("login-error").classList.add("hidden");
  try {
    const data = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: $("username").value.trim(), password: $("password").value }),
    }).then((r) => r.json().then((d) => ({ ok: r.ok, d })));
    if (!data.ok) throw new Error(data.d.detail || "Login failed");
    token = data.d.token;
    me = data.d.username;
    sessionStorage.setItem("adminToken", token);
    sessionStorage.setItem("adminUser", me);
    $("password").value = "";
    await load();
  } catch (err) {
    $("login-error").textContent = err.message;
    $("login-error").classList.remove("hidden");
  }
});

$("queue").addEventListener("change", async (e) => {
  const id = e.target.dataset.status;
  if (!id) return;
  await api(`/api/admin/intakes/${id}`, { method: "PATCH", body: JSON.stringify({ status: e.target.value }) }).catch((err) => alert(err.message));
});

$("queue").addEventListener("click", async (e) => {
  const editId = e.target.dataset.edit;
  const delId = e.target.dataset.del;
  const confId = e.target.dataset.confirm;
  if (e.target.tagName === "SELECT" || e.target.tagName === "OPTION") return;
  if (confId) {
    await confirmAppointment(confId);
    return;
  }
  if (editId) {
    openForm("edit", intakes.find((x) => String(x.id) === editId));
    return;
  }
  if (delId) {
    const i = intakes.find((x) => String(x.id) === delId);
    if (confirm(`Delete record for ${i.patient_name}? This also removes their appointment and cannot be undone.`)) {
      await api(`/api/admin/intakes/${delId}`, { method: "DELETE" }).catch((err) => alert(err.message));
      await load();
    }
    return;
  }
  const row = e.target.closest("tr[data-id]");
  if (!row) return;
  openView(intakes.find((x) => String(x.id) === row.dataset.id));
});

$("m-confirmbtn").addEventListener("click", () => confirmAppointment(modalIntakeId));

$("m-editbtn").addEventListener("click", () => {
  openForm("edit", intakes.find((x) => x.id === modalIntakeId));
});

$("m-deletebtn").addEventListener("click", async () => {
  const i = intakes.find((x) => x.id === modalIntakeId);
  if (!i || !confirm(`Delete record for ${i.patient_name}? This also removes their appointment and cannot be undone.`)) return;
  await api(`/api/admin/intakes/${i.id}`, { method: "DELETE" }).catch((err) => alert(err.message));
  closeModal();
  await load();
});

$("m-cancel").addEventListener("click", () => {
  if (modalMode === "edit" && modalIntakeId) {
    openView(intakes.find((x) => x.id === modalIntakeId));
  } else {
    closeModal();
  }
});

$("m-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("m-error").classList.add("hidden");
  const payload = {
    patient_name: $("e-name").value.trim(),
    age: Number($("e-age").value),
    gender: $("e-gender").value,
    phone: $("e-phone").value.trim(),
    email: $("e-email").value.trim() || null,
    symptoms: $("e-symptoms").value.trim(),
    duration: $("e-duration").value.trim(),
  };
  if (modalMode === "edit") payload.status = $("e-status").value;
  try {
    if (modalMode === "add") {
      await api("/api/admin/intakes", { method: "POST", body: JSON.stringify(payload) });
    } else {
      await api(`/api/admin/intakes/${modalIntakeId}`, { method: "PUT", body: JSON.stringify(payload) });
    }
    closeModal();
    await load();
  } catch (err) {
    $("m-error").textContent = err.message;
    $("m-error").classList.remove("hidden");
  }
});

$("add-patient").addEventListener("click", () => openForm("add"));

$("admin-list").addEventListener("click", async (e) => {
  const id = e.target.dataset.deladmin;
  if (!id) return;
  if (!confirm(`Remove staff account "${e.target.dataset.name}"?`)) return;
  try {
    await api(`/api/admin/admins/${id}`, { method: "DELETE" });
    await load();
  } catch (err) {
    alert(err.message);
  }
});

$("add-admin-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("admin-msg");
  msg.className = "alert hidden";
  try {
    const d = await api("/api/admin/admins", {
      method: "POST",
      body: JSON.stringify({ username: $("a-username").value.trim(), password: $("a-password").value }),
    });
    msg.textContent = `Account "${d.username}" created.`;
    msg.className = "alert info";
    $("a-username").value = "";
    $("a-password").value = "";
    await load();
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "alert error";
  }
});

$("pw-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("pw-msg");
  msg.className = "alert hidden";
  try {
    await api("/api/admin/password", {
      method: "POST",
      body: JSON.stringify({ current_password: $("pw-current").value, new_password: $("pw-new").value }),
    });
    alert("Password updated. Please log in again with your new password.");
    logout();
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "alert error";
  }
});

$("m-close").addEventListener("click", closeModal);
$("modal-bg").addEventListener("click", (e) => { if (e.target.id === "modal-bg") closeModal(); });
$("refresh").addEventListener("click", load);
$("logout").addEventListener("click", (e) => { e.preventDefault(); logout(); });
if (token) load().catch(logout);
