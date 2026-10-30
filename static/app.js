const $ = (id) => document.getElementById(id);
const APPT = {
  emergency: "Emergency - call 000 (not bookable online)",
  long: "Long consultation (30 min)",
  standard: "Standard consultation (15 min)",
  telehealth: "Telehealth video/phone consultation",
};
const EXAMPLES = {
  routine: ["Sore throat, runny nose and a mild temperature. Still eating and drinking fine.", "2 days"],
  urgent: ["High fever of 39.5 degrees, bad cough and getting worse each day. Feeling very weak.", "3 days"],
  long: ["Feeling anxious most days, low mood and I can't sleep. It's affecting my work.", "2 months"],
  emergency: ["Crushing chest pain spreading to my left arm and I feel sweaty and sick.", "30 minutes"],
};
let intakeId = null;
let selectedSlot = null;

const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const list = (items) => (items && items.length ? `<ul class="tight">${items.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>` : "-");

function setStep(n) {
  [1, 2, 3].forEach((i) => $(`step-${i}`).classList.toggle("active", i <= n));
}

function showError(el, msg) {
  el.textContent = msg;
  el.classList.remove("hidden");
}

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = data.detail || `Request failed (${res.status})`;
    if (Array.isArray(msg)) msg = msg.map((d) => `${d.loc[d.loc.length - 1]}: ${d.msg}`).join("; ");
    throw new Error(msg);
  }
  return data;
}

fetch("/api/config").then((r) => r.json()).then((c) => {
  $("clinic-name").textContent = `${c.clinic_name} - smart patient intake & booking`;
  $("ai-badge").textContent = c.ai_provider === "offline" ? "AI: offline demo mode" : `AI: ${c.ai_provider} (prompt ${c.prompt_version})`;
});

document.querySelectorAll("[data-example]").forEach((btn) =>
  btn.addEventListener("click", () => {
    const [symptoms, duration] = EXAMPLES[btn.dataset.example];
    $("symptoms").value = symptoms;
    $("duration").value = duration;
    if (!$("patient_name").value) $("patient_name").value = "Alex Taylor";
    if (!$("phone").value) $("phone").value = "0412 345 678";
    if (!$("age").value) $("age").value = 42;
  })
);

$("intake-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("form-error").classList.add("hidden");
  if (!e.target.checkValidity()) {
    showError($("form-error"), "Please fill in your name, mobile number, age and symptoms (at least 5 characters).");
    return;
  }
  const btn = $("submit-btn");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>AI is analysing...';
  try {
    const payload = {
      patient_name: $("patient_name").value.trim(),
      age: Number($("age").value),
      gender: $("gender").value,
      phone: $("phone").value.trim(),
      email: $("email").value.trim() || null,
      symptoms: $("symptoms").value.trim(),
      duration: $("duration").value.trim(),
    };
    const data = await api("/api/intake", { method: "POST", body: JSON.stringify(payload) });
    intakeId = data.intake_id;
    renderResult(data.triage);
  } catch (err) {
    showError($("form-error"), err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Analyse my symptoms";
  }
});

function renderResult(t) {
  $("intake-section").classList.add("hidden");
  $("result-section").classList.remove("hidden");
  setStep(2);
  const badge = $("urgency-badge");
  badge.textContent = t.urgency;
  badge.className = `urgency ${t.urgency}`;
  $("patient-message").textContent = t.patient_message;
  $("r-summary").textContent = t.summary;
  $("r-symptoms").innerHTML = list(t.key_symptoms);
  $("r-appointment").textContent = APPT[t.suggested_appointment] || t.suggested_appointment;
  $("r-questions").innerHTML = list(t.questions_for_doctor);
  $("r-provider").textContent = t.ai_provider === "offline" ? "Offline rule engine (no AI key configured)" : `${t.ai_provider} LLM + safety rules`;
  if (t.urgency === "emergency") {
    $("emergency-alert").innerHTML = `CALL 000 NOW. Red flags detected: ${t.red_flags.map(escapeHtml).join(", ") || "possible emergency"}.`;
    $("emergency-alert").classList.remove("hidden");
  } else {
    loadSlots();
  }
}

async function loadSlots() {
  $("booking-section").classList.remove("hidden");
  setStep(3);
  const box = $("slots");
  box.innerHTML = "Loading available times...";
  try {
    const { slots } = await api(`/api/slots?intake_id=${intakeId}`);
    if (!slots.length) {
      box.textContent = "No online slots available - please call the clinic.";
      return;
    }
    box.innerHTML = "";
    let lastDay = "";
    slots.forEach((iso) => {
      const day = iso.slice(0, 10);
      if (day !== lastDay) {
        lastDay = day;
        const label = document.createElement("div");
        label.className = "day-label";
        label.textContent = new Date(day + "T12:00:00").toLocaleDateString("en-AU", { weekday: "long", day: "numeric", month: "long" });
        box.appendChild(label);
      }
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = iso.slice(11, 16);
      b.addEventListener("click", () => {
        box.querySelectorAll("button").forEach((x) => x.classList.remove("selected"));
        b.classList.add("selected");
        selectedSlot = iso;
        $("book-btn").disabled = false;
      });
      box.appendChild(b);
    });
  } catch (err) {
    box.textContent = err.message;
  }
}

$("book-btn").addEventListener("click", async () => {
  if (!selectedSlot) return;
  $("booking-error").classList.add("hidden");
  $("book-btn").disabled = true;
  try {
    const data = await api("/api/appointments", { method: "POST", body: JSON.stringify({ intake_id: intakeId, slot: selectedSlot }) });
    $("booking-section").classList.add("hidden");
    $("confirm-section").classList.remove("hidden");
    $("confirm-message").textContent = data.confirmation_message;
  } catch (err) {
    showError($("booking-error"), err.message);
    $("book-btn").disabled = false;
    if (err.message.includes("available") || err.message.includes("taken")) loadSlots();
  }
});
