# Video Script - ClinicFlow AI (about 3.5 minutes)

Record your screen (OBS, Loom or Zoom) with the app open in one tab and the GitHub repo / prompt file ready in
another. Speak naturally - you don't need to read word for word. Keep the browser console clean and the patient
form empty before you start.

---

**0:00 - Intro (15 s)**
"Hi, I'm Vishal. For Task 1 I built **ClinicFlow AI** - an AI-powered patient intake, triage and appointment
automation system for GP clinics. I chose healthcare because Gokul Infocare runs GP clinics like Robina 7 Day
Doctors, so this solves a real, daily problem for that kind of business. It combines a web app, automation and
AI innovation in one project."

**0:15 - The problem (20 s)**
"At a busy clinic, reception staff spend hours on the phone asking patients what's wrong, guessing how urgent
it is and choosing an appointment type. The doctor then starts every consult with zero context - and a truly
urgent patient can end up waiting behind routine colds. ClinicFlow automates that whole front desk flow."

**0:35 - Demo part 1: AI triage + adaptive interview (50 s)** - *patient page, use a realistic case, e.g.
"high fever 39.8, bad cough, getting worse each day"*
"The patient describes symptoms in their own words. Watch the AI: it produces an urgency level - **Urgent** -
a clinical summary for the doctor, key symptoms, the suggested appointment type and questions the doctor may
ask.
Now the interesting part: **the AI interviews the patient back.** It generated follow-up questions it thinks
would sharpen the assessment. I'll answer them... and the AI re-triages with the extra detail. So this is
multi-turn AI, not a one-shot prompt - a red flag revealed in an answer still escalates to emergency.
Because I'm urgent, it only offers today's and tomorrow's slots. I pick a time and book. Note the message:
the clinic will confirm it - appointments need staff approval, and I'll show what happens next."

**1:25 - Demo part 2: emergency safety (20 s)**
"Safety first. If I type 'chest pain spreading to my left arm', it's flagged **Emergency**, the patient is
told to call 000 and online booking is blocked. This never depends only on the AI - a deterministic rule
layer scans every submission AND every follow-up answer for red flags like chest pain, stroke signs and
suicidal thoughts, and overrides the AI."

**1:45 - Demo part 3: staff dashboard (45 s)** - *open /admin*
"Staff log in with their own account - real authentication with hashed passwords and sessions, not a shared
password. The queue is **sorted by AI urgency**. I open my patient: the AI summary, key symptoms and my
follow-up answers are all here for the doctor.
Now I click **Confirm** - the status becomes 'confirmed' and the patient gets a confirmation email. *Show the
email inbox if SMTP is configured, or point out the status change.*
Staff can also add a walk-in patient, edit any record, delete records, and manage staff accounts - full CRUD,
all done through the same API."

**2:30 - AI tools & prompt engineering (45 s)** - *show docs/PROMPT_DOCUMENTATION.md + app/prompts.py + evaluate.py*
"I used **Devin**, an AI software engineer, to plan, build and test the whole project, and **Google Gemini**
inside the app - it can switch to OpenAI or Groq with one env variable, and there's an offline fallback so it
never breaks.
For prompt engineering: version 1 was too vague - free text, and it tried to diagnose. Version 2 forced JSON
and said 'do not diagnose'. Version 3 added explicit urgency definitions, a 'choose the more urgent level when
unsure' tie-breaker, a few-shot example and prompt-injection defence. Version 4 added the adaptive
follow-up questions you just saw. Every version is measured with an evaluation script: 12 realistic cases,
and the critical metric is **unsafe under-triage - it must be zero**."

**3:15 - Challenges (15 s)**
"Challenges: AI output isn't always valid JSON, so I extract it, validate the schema, retry once and fall back
to the offline engine. I also fixed a timezone bug where a 9 am Brisbane booking displayed as 11 pm, and tuned
rules so a repeat prescription goes to telehealth instead of a long consult."

**3:30 - Outcome (15 s)**
"The result: a working, professional web app - 28 automated tests, CI on every push, Dockerised, deployed live
on Render. It saves reception time, gives doctors context before the consult, confirms bookings by email, and
gets emergencies help faster. Thanks for watching."

---

### Recording checklist
- [ ] Render URL works and `GEMINI_API_KEY` is set (badge shows `AI: gemini (prompt v4)`)
- [ ] Logged in to /admin as `admin` beforehand if needed - or show the login screen once
- [ ] Have the patient's email open (or a phone) to show the confirmation email
- [ ] Fresh, realistic symptom text ready to paste - don't use filler
- [ ] Repo link + live link visible at the end
