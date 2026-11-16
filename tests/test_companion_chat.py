"""The companion route stays natural and keeps one owned conversation in order."""
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.product.companion import build_companion_prompt
from app.product.main import create_app


class CompanionDouble:
    def __init__(self):
        self.calls = []

    async def generate_with_system(self, messages, *, system_prompt, prompt_version):
        self.calls.append((list(messages), system_prompt, prompt_version))
        return "我在听。云岚星今晚也起了潮，你想先从哪一个瞬间说起？"


def register(client):
    response = client.post(
        "/api/account/register",
        headers={"Origin": "https://testserver"},
        json={"username": "companion_user", "password": "demo-password-123", "consent": True},
    )
    assert response.status_code == 201, response.text
    return {"Origin": "https://testserver", "x-csrf-token": response.json()["csrf_token"]}


def test_companion_chat_keeps_natural_turns_and_deduplicates(tmp_path):
    model = CompanionDouble()
    app = create_app(
        Settings(_env_file=None, product_data_dir=tmp_path, product_origin="https://testserver", product_cookie_secure=True),
        model_factory=lambda: model,
    )
    with TestClient(app, base_url="https://testserver") as client:
        headers = register(client)
        created = client.post("/api/companion/sessions", headers=headers, json={})
        assert created.status_code == 201, created.text
        session_id = created.json()["session_id"]
        request_id = str(uuid4())
        body = {
            "content": "我今天有点累，但不想把它说成一份报告。",
            "request_id": request_id,
            "model_consent": True,
            "companion_id": "shiguang",
            "use_memories": False,
        }
        first = client.post(f"/api/companion/sessions/{session_id}/messages", headers=headers, json=body)
        assert first.status_code == 200, first.text
        assert first.json()["reply"].startswith("我在听")
        replay = client.post(f"/api/companion/sessions/{session_id}/messages", headers=headers, json=body)
        assert replay.status_code == 200 and replay.json() == first.json()
        assert len(model.calls) == 1
        session = client.get(f"/api/companion/sessions/{session_id}", headers=headers).json()
        assert [message["role"] for message in session["messages"]] == ["user", "assistant"]
        assert session["messages"][0]["content"] == body["content"]


def test_companion_prompt_is_world_facing_and_not_a_report():
    prompt = build_companion_prompt("weilan", [{"card_id": "demo", "fields": {"facts": "用户主动保存的经历"}}])
    assert "天外来客“未蓝”" in prompt
    assert "来自弦月环" in prompt
    assert "不输出 JSON" in prompt
    assert "自然中文聊天" in prompt
