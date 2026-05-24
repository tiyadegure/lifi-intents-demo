"""Tests for Web API endpoints: /api/status, /api/presets, /api/preset/{name}, /api/analyze-intent, /api/doctor."""

import os
os.environ["LIFI_AGENT_MOCK_MODE"] = "1"

import pytest
from fastapi.testclient import TestClient
from lifi_agent.server import app, PRESETS

client = TestClient(app)


class TestApiStatus:
    def test_status_returns_mode(self):
        r = client.get("/api/status")
        assert r.status_code == 200
        data = r.json()
        assert "mode" in data
        assert data["mode"] in ("local_mcp", "mock_forced", "mock_fallback", "strict")

    def test_status_returns_endpoint(self):
        r = client.get("/api/status")
        assert "endpoint" in r.json()

    def test_status_returns_connected(self):
        r = client.get("/api/status")
        assert "connected" in r.json()

    def test_status_returns_strict_mode(self):
        r = client.get("/api/status")
        assert "strict_mode" in r.json()


class TestApiPresets:
    def test_presets_returns_list(self):
        r = client.get("/api/presets")
        assert r.status_code == 200
        data = r.json()
        assert "presets" in data
        assert len(data["presets"]) == len(PRESETS)

    def test_preset_has_expected_fields(self):
        r = client.get("/api/presets")
        preset = r.json()["presets"][0]
        assert "name" in preset
        assert "description" in preset
        assert "intent" in preset
        assert "policy" in preset
        assert "category" in preset
        assert "expected_verdict" in preset

    def test_preset_expected_verdict_values(self):
        r = client.get("/api/presets")
        for preset in r.json()["presets"]:
            assert preset["expected_verdict"] in ("EXECUTABLE", "REFUSED")

    def test_preset_intent_has_required_fields(self):
        r = client.get("/api/presets")
        for preset in r.json()["presets"]:
            intent = preset["intent"]
            assert "from_chain" in intent
            assert "to_chain" in intent
            assert "token" in intent
            assert "amount" in intent


class TestApiPreset:
    def test_get_preset_by_name(self):
        r = client.get("/api/preset/safe-transfer")
        assert r.status_code == 200
        data = r.json()
        assert "intent" in data
        assert "policy" in data
        assert data["expected_verdict"] == "EXECUTABLE"

    def test_get_preset_not_found(self):
        r = client.get("/api/preset/nonexistent")
        assert r.status_code == 404
        data = r.json()
        assert data["error"] is True
        assert data["code"] == "PRESET_NOT_FOUND"
        assert "next_action" in data

    def test_get_preset_fee_too_high(self):
        r = client.get("/api/preset/fee-too-high")
        assert r.status_code == 200
        assert r.json()["expected_verdict"] == "REFUSED"

    def test_get_preset_avoid_chain(self):
        r = client.get("/api/preset/avoid-chain")
        assert r.status_code == 200
        assert r.json()["expected_verdict"] == "REFUSED"


class TestApiAnalyzeIntent:
    def test_analyze_basic(self):
        r = client.post("/api/analyze-intent", json={"text": "send 10 USDC from Base to Arbitrum"})
        assert r.status_code == 200
        data = r.json()
        assert "verdict" in data
        assert data["verdict"] in ("EXECUTABLE", "REFUSED")
        assert "steps" in data
        assert "reason" in data

    def test_analyze_returns_intent(self):
        r = client.post("/api/analyze-intent", json={"text": "send 10 USDC from Base to Arbitrum"})
        data = r.json()
        assert data["intent"]["amount"] == "10"
        assert data["intent"]["token"] == "USDC"

    def test_analyze_returns_policy(self):
        r = client.post("/api/analyze-intent", json={"text": "send 10 USDC from Base to Arbitrum if fee < 0.5%"})
        data = r.json()
        assert data["policy"]["max_fee_pct"] == 0.5

    def test_analyze_returns_steps(self):
        r = client.post("/api/analyze-intent", json={"text": "send 10 USDC from Base to Arbitrum"})
        data = r.json()
        step_names = [s["name"] for s in data["steps"]]
        assert "Parse Intent" in step_names
        assert "Get Quote" in step_names

    def test_analyze_missing_text(self):
        r = client.post("/api/analyze-intent", json={})
        assert r.status_code == 400
        data = r.json()
        assert data["error"] is True
        assert data["code"] == "MISSING_INPUT"

    def test_analyze_empty_text(self):
        r = client.post("/api/analyze-intent", json={"text": ""})
        assert r.status_code == 400
        assert r.json()["error"] is True

    def test_analyze_fee_too_high(self):
        r = client.post("/api/analyze-intent", json={"text": "send 10 USDC from Base to Arbitrum if fee < 0.01%"})
        data = r.json()
        assert data["verdict"] == "REFUSED"

    def test_analyze_avoid_chain(self):
        r = client.post("/api/analyze-intent", json={"text": "send 10 USDC from Base to Arbitrum avoid Arbitrum"})
        data = r.json()
        assert data["verdict"] == "REFUSED"

    def test_analyze_total_duration(self):
        r = client.post("/api/analyze-intent", json={"text": "send 10 USDC from Base to Arbitrum"})
        assert "total_duration_ms" in r.json()


class TestApiDoctor:
    def test_doctor_returns_groups(self):
        r = client.get("/api/doctor")
        assert r.status_code == 200
        data = r.json()
        assert "groups" in data
        assert len(data["groups"]) >= 4

    def test_doctor_returns_mode(self):
        r = client.get("/api/doctor")
        assert "mode" in r.json()

    def test_doctor_returns_next_action(self):
        r = client.get("/api/doctor")
        assert "next_action" in r.json()

    def test_doctor_has_warnings(self):
        r = client.get("/api/doctor")
        assert "warnings" in r.json()


class TestUnifiedErrors:
    def test_preset_not_found_shape(self):
        r = client.get("/api/preset/does-not-exist")
        data = r.json()
        assert data["error"] is True
        assert "code" in data
        assert "message" in data
        assert "next_action" in data

    def test_analyze_missing_input_shape(self):
        r = client.post("/api/analyze-intent", json={})
        data = r.json()
        assert data["error"] is True
        assert "code" in data
        assert "message" in data
        assert "next_action" in data
