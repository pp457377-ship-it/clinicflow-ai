PATIENT = {"patient_name": "Jane Citizen", "age": 34, "gender": "female", "phone": "0412 345 678",
           "symptoms": "sore throat and runny nose", "duration": "2 days"}
ADMIN = {"X-Admin-Key": "secret"}


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


def test_admin_requires_password(client):
    assert client.get("/api/admin/intakes").status_code == 401
    assert client.get("/api/admin/intakes", headers={"X-Admin-Key": "wrong"}).status_code == 401


def test_admin_queue_sorted_by_urgency(client):
    client.post("/api/intake", json=PATIENT)
    client.post("/api/intake", json={**PATIENT, "symptoms": "chest pain"})
    client.post("/api/intake", json={**PATIENT, "symptoms": "high fever and getting worse"})
    queue = client.get("/api/admin/intakes", headers=ADMIN).json()["intakes"]
    assert [i["urgency"] for i in queue] == ["emergency", "urgent", "routine"]
    stats = client.get("/api/admin/stats", headers=ADMIN).json()
    assert stats["total_intakes"] == 3 and stats["emergency"] == 1
    r = client.patch(f"/api/admin/intakes/{queue[0]['id']}", json={"status": "reviewed"}, headers=ADMIN)
    assert r.status_code == 200
    assert client.patch("/api/admin/intakes/999", json={"status": "closed"}, headers=ADMIN).status_code == 404
