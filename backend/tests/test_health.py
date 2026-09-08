"""infra-001 验证：后端可启动 + /health 返回 200。"""


def test_health_returns_200(client):
    r = client.get("/health")
    assert r.status_code == 200


def test_health_payload(client):
    r = client.get("/health")
    body = r.json()
    assert body["status"] == "ok"
    assert "app" in body
    assert "version" in body


def test_api_health_returns_200(client):
    """带 /api 前缀的健康检查（前端经 vite proxy 访问）。"""
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
