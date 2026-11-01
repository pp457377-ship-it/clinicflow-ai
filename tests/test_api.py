PATIENT = {"patient_name": "Jane Citizen", "age": 34, "gender": "female", "phone": "0412 345 678",
           "symptoms": "sore throat and runny nose", "duration": "2 days"}


def admin_headers(client, username="admin", password="secret"):
    r = client.post("/api/admin/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.json()
    return {"X-Admin-Key": r.json()["token"]}


def test_health_and_pages(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/").status_code == 200
    assert client.get("/admin").status_code == 200
    assert client.get("/api/config").json()["ai_provider"] == "offline"


def test_full_patient_flow(client):
    r = client.post("/api/intake", json=PATIENT)
    assert r.status_code == 200
    intake_id = r.json()["intake_id"]
    slots = client.get(f"/api/slots?intake_id={intake_id}").json()["slots"]
    assert slots
    booking = client.post("/api/appointments", json={"intake_id": intake_id, "slot": slots[0]})
    assert booking.status_code == 200
    assert "Jane" in booking.json()["confirmation_message"]
    # slot is no longer offered and cannot be double-booked
    assert slots[0] not in client.get(f"/api/slots?intake_id={intake_id}").json()["slots"]
    other = client.post("/api/intake", json=PATIENT).json()["intake_id"]
    assert client.post("/api/appointments", json={"intake_id": other, "slot": slots[0]}).status_code == 409
    # same intake cannot book twice
    assert client.post("/api/appointments", json={"intake_id": intake_id, "slot": slots[1]}).status_code == 409


def test_emergency_cannot_book(client):
    r = client.post("/api/intake", json={**PATIENT, "symptoms": "I have severe chest pain and can't breathe"})
    body = r.json()
    assert body["triage"]["urgency"] == "emergency"
    assert client.get(f"/api/slots?intake_id={body['intake_id']}").json()["slots"] == []
    assert client.post("/api/appointments", json={"intake_id": body["intake_id"], "slot": "2030-01-01T09:00+10:00"}).status_code == 400


def test_validation_errors(client):
    assert client.post("/api/intake", json={**PATIENT, "age": 200}).status_code == 422
    assert client.post("/api/intake", json={**PATIENT, "phone": "abc"}).status_code == 422
    assert client.post("/api/intake", json={**PATIENT, "symptoms": ""}).status_code == 422


def test_admin_requires_login(client):
    assert client.get("/api/admin/intakes").status_code == 401
    assert client.get("/api/admin/intakes", headers={"X-Admin-Key": "wrong"}).status_code == 401
    assert client.post("/api/admin/login", json={"username": "admin", "password": "nope"}).status_code == 401


def test_admin_queue_sorted_by_urgency(client):
    admin = admin_headers(client)
    client.post("/api/intake", json=PATIENT)
    client.post("/api/intake", json={**PATIENT, "symptoms": "chest pain"})
    client.post("/api/intake", json={**PATIENT, "symptoms": "high fever and getting worse"})
    queue = client.get("/api/admin/intakes", headers=admin).json()["intakes"]
    assert [i["urgency"] for i in queue] == ["emergency", "urgent", "routine"]
    stats = client.get("/api/admin/stats", headers=admin).json()
    assert stats["total_intakes"] == 3 and stats["emergency"] == 1
    r = client.patch(f"/api/admin/intakes/{queue[0]['id']}", json={"status": "reviewed"}, headers=admin)
    assert r.status_code == 200
    assert client.patch("/api/admin/intakes/999", json={"status": "closed"}, headers=admin).status_code == 404


def test_admin_add_edit_delete_intake(client):
    admin = admin_headers(client)
    created = client.post("/api/admin/intakes", json=PATIENT, headers=admin)
    assert created.status_code == 200
    intake = created.json()
    assert intake["patient_name"] == "Jane Citizen" and intake["status"] == "new"
    edited = client.put(f"/api/admin/intakes/{intake['id']}", json={"phone": "0499 000 111", "status": "reviewed"}, headers=admin)
    assert edited.status_code == 200
    assert edited.json()["phone"] == "0499 000 111" and edited.json()["status"] == "reviewed"
    assert client.put("/api/admin/intakes/999", json={"status": "closed"}, headers=admin).status_code == 404
    assert client.delete(f"/api/admin/intakes/{intake['id']}", headers=admin).status_code == 200
    assert all(i["id"] != intake["id"] for i in client.get("/api/admin/intakes", headers=admin).json()["intakes"])
    assert client.delete(f"/api/admin/intakes/{intake['id']}", headers=admin).status_code == 404


def test_delete_intake_frees_appointment_slot(client):
    admin = admin_headers(client)
    intake_id = client.post("/api/intake", json=PATIENT).json()["intake_id"]
    slot = client.get(f"/api/slots?intake_id={intake_id}").json()["slots"][0]
    client.post("/api/appointments", json={"intake_id": intake_id, "slot": slot})
    client.delete(f"/api/admin/intakes/{intake_id}", headers=admin)
    other = client.post("/api/intake", json=PATIENT).json()["intake_id"]
    assert slot in client.get(f"/api/slots?intake_id={other}").json()["slots"]


def test_admin_accounts(client):
    admin = admin_headers(client)
    admins = client.get("/api/admin/admins", headers=admin).json()["admins"]
    assert [a["username"] for a in admins] == ["admin"]
    # create a second account and log in as it
    r = client.post("/api/admin/admins", json={"username": "nurse1", "password": "password123"}, headers=admin)
    assert r.status_code == 200
    assert client.post("/api/admin/admins", json={"username": "nurse1", "password": "password123"}, headers=admin).status_code == 409
    nurse = admin_headers(client, "nurse1", "password123")
    assert client.get("/api/admin/intakes", headers=nurse).status_code == 200
    # cannot delete your own account
    nurse_id = next(a["id"] for a in client.get("/api/admin/admins", headers=admin).json()["admins"] if a["username"] == "nurse1")
    assert client.delete(f"/api/admin/admins/{nurse_id}", headers=nurse).status_code == 400
    assert client.delete(f"/api/admin/admins/{nurse_id}", headers=admin).status_code == 200
    # cannot delete the last remaining account
    last_id = next(a["id"] for a in client.get("/api/admin/admins", headers=admin).json()["admins"] if a["username"] == "admin")
    assert client.delete(f"/api/admin/admins/{last_id}", headers=admin).status_code == 400


def test_confirm_appointment_sends_email(client, monkeypatch):
    admin = admin_headers(client)
    intake_id = client.post("/api/intake", json=PATIENT).json()["intake_id"]
    # no appointment yet -> cannot confirm
    assert client.post(f"/api/admin/intakes/{intake_id}/confirm", headers=admin).status_code == 400
    assert client.post("/api/admin/intakes/999/confirm", headers=admin).status_code == 404
    slot = client.get(f"/api/slots?intake_id={intake_id}").json()["slots"][0]
    client.post("/api/appointments", json={"intake_id": intake_id, "slot": slot})
    sent = []
    monkeypatch.setattr("app.mailer.send_email", lambda to, subject, body: sent.append((to, subject, body)) or True)
    r = client.post(f"/api/admin/intakes/{intake_id}/confirm", headers=admin)
    assert r.status_code == 200
    assert r.json() == {"intake_id": intake_id, "status": "confirmed", "email_sent": False}  # PATIENT has no email
    assert sent == []
    # with an email address, the confirmation email is sent
    other = client.post("/api/intake", json={**PATIENT, "email": "jane@example.com"}).json()["intake_id"]
    slot2 = client.get(f"/api/slots?intake_id={other}").json()["slots"][0]
    client.post("/api/appointments", json={"intake_id": other, "slot": slot2})
    r2 = client.post(f"/api/admin/intakes/{other}/confirm", headers=admin)
    assert r2.json()["email_sent"] is True
    assert sent[0][0] == "jane@example.com" and "confirmed" in sent[0][1].lower()
    intake = client.get("/api/admin/intakes", headers=admin).json()["intakes"]
    assert next(i for i in intake if i["id"] == other)["status"] == "confirmed"


def test_follow_up_questions_and_retriage(client):
    admin = admin_headers(client)
    r = client.post("/api/intake", json=PATIENT).json()
    questions = r["triage"]["follow_up_questions"]
    assert questions  # triage always offers at least one follow-up question
    r2 = client.post(
        f"/api/intakes/{r['intake_id']}/follow-up",
        json={"answers": [{"question": questions[0], "answer": "getting worse each day"}]},
    )
    assert r2.status_code == 200
    stored = next(
        i for i in client.get("/api/admin/intakes", headers=admin).json()["intakes"]
        if i["id"] == r["intake_id"]
    )
    assert stored["triage"]["patient_answers"][0]["answer"] == "getting worse each day"


def test_follow_up_red_flag_escalates(client):
    r = client.post("/api/intake", json=PATIENT).json()
    r2 = client.post(
        f"/api/intakes/{r['intake_id']}/follow-up",
        json={"answers": [{"question": "Any worse?", "answer": "yes, now I have severe chest pain"}]},
    )
    assert r2.json()["triage"]["urgency"] == "emergency"


def test_follow_up_guards(client):
    assert client.post("/api/intakes/999/follow-up", json={"answers": [{"question": "q", "answer": "a"}]}).status_code == 404
    intake_id = client.post("/api/intake", json=PATIENT).json()["intake_id"]
    slot = client.get(f"/api/slots?intake_id={intake_id}").json()["slots"][0]
    client.post("/api/appointments", json={"intake_id": intake_id, "slot": slot})
    # cannot re-triage once an appointment exists
    assert client.post(
        f"/api/intakes/{intake_id}/follow-up", json={"answers": [{"question": "q", "answer": "a"}]}
    ).status_code == 409


def test_change_password(client):
    admin = admin_headers(client)
    bad = client.post("/api/admin/password", json={"current_password": "wrong", "new_password": "newpassword1"}, headers=admin)
    assert bad.status_code == 400
    ok = client.post("/api/admin/password", json={"current_password": "secret", "new_password": "newpassword1"}, headers=admin)
    assert ok.status_code == 200
    # old session is invalidated; new password works
    assert client.get("/api/admin/intakes", headers=admin).status_code == 401
    assert client.post("/api/admin/login", json={"username": "admin", "password": "newpassword1"}).status_code == 200
