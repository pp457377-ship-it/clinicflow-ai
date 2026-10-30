const $ = (id) => document.getElementById(id);
const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const list = (items) => (items && items.length ? `<ul class="tight">${items.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>` : "-");
const FMT = { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" };
// Appointment slots are shown in clinic time (drop the UTC offset); created_at is shown in the viewer's time.
const fmtSlot = (iso) => (iso ? new Date(iso.slice(0, 16)).toLocaleString("en-AU", FMT) : "-");
const fmt = (iso) => (iso ? new Date(iso).toLocaleString("en-AU", FMT) : "-");
const STATUSES = ["new", "booked", "reviewed", "closed"];
let key = sessionStorage.getItem("adminKey");
let intakes = [];

async function api(path, options = {}) {
  const res = await fetch(path, { ...options, headers: { "Content-Type": "application/json", "X-Admin-Key": key || "" } });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) { logout(); throw new Error("Wrong password"); }
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

function logout() {
  key = null;
  sessionStorage.removeItem("adminKey");
  $("dashboard").classList.add("hidden");
  $("logout").classList.add("hidden");
  $("login-section").classList.remove("hidden");
}

async function load() {
  const [stats, data] = await Promise.all([api("/api/admin/stats"), api("/api/admin/intakes")]);
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
    </tr>`).join("");
  $("login-section").classList.add("hidden");
  $("dashboard").classList.remove("hidden");
  $("logout").classList.remove("hidden");
}

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  key = $("password").value;
  $("login-error").classList.add("hidden");
  try {
    await load();
    sessionStorage.setItem("adminKey", key);
  } catch (err) {
    $("login-error").textContent = err.message;
    $("login-error").classList.remove("hidden");
  }
});

$("queue").addEventListener("change", async (e) => {
  const id = e.target.dataset.status;
  if (!id) return;
  await api(`/api/admin/intakes/${id}`, { method: "PATCH", body: JSON.stringify({ status: e.target.value }) });
});

$("queue").addEventListener("click", (e) => {
  if (e.target.tagName === "SELECT" || e.target.tagName === "OPTION") return;
  const row = e.target.closest("tr[data-id]");
  if (!row) return;
  const i = intakes.find((x) => String(x.id) === row.dataset.id);
  const t = i.triage;
  $("m-title").innerHTML = `${escapeHtml(i.patient_name)} <span class="urgency ${i.urgency}">${i.urgency}</span>`;
  $("m-body").innerHTML = `
    <b>Age / sex</b><span>${i.age} / ${escapeHtml(i.gender.replaceAll("_", " "))}</span>
    <b>Contact</b><span>${escapeHtml(i.phone)} ${i.email ? "&middot; " + escapeHtml(i.email) : ""}</span>
    <b>Patient's words</b><span>${escapeHtml(i.symptoms)}</span>
    <b>Duration</b><span>${escapeHtml(i.duration || "-")}</span>
    <b>AI summary</b><span>${escapeHtml(t.summary)}</span>
    <b>Key symptoms</b><span>${list(t.key_symptoms)}</span>
    <b>Red flags</b><span>${list(t.red_flags)}</span>
    <b>Suggested visit</b><span>${escapeHtml(t.suggested_appointment)}</span>
    <b>Questions to ask</b><span>${list(t.questions_for_doctor)}</span>
    <b>Appointment</b><span>${fmtSlot(i.appointment_slot)} (clinic time)</span>
    <b>Analysed by</b><span>${escapeHtml(t.ai_provider)}</span>
    <b>Submitted</b><span>${fmt(i.created_at)}</span>`;
  $("modal-bg").classList.remove("hidden");
});

$("m-close").addEventListener("click", () => $("modal-bg").classList.add("hidden"));
$("modal-bg").addEventListener("click", (e) => { if (e.target.id === "modal-bg") $("modal-bg").classList.add("hidden"); });
$("refresh").addEventListener("click", load);
$("logout").addEventListener("click", (e) => { e.preventDefault(); logout(); });
if (key) load().catch(logout);
