import pytest

from agentaudit_orchestration.config import load_bedrock_env, mcp_server_config


def test_load_bedrock_env_requires_use_bedrock_flag(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    with pytest.raises(RuntimeError, match="CLAUDE_CODE_USE_BEDROCK"):
        load_bedrock_env()


def test_load_bedrock_env_rejects_non_1_use_bedrock_flag(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "true")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    with pytest.raises(RuntimeError, match="CLAUDE_CODE_USE_BEDROCK"):
        load_bedrock_env()


def test_load_bedrock_env_requires_aws_region(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.delenv("AWS_REGION", raising=False)
    with pytest.raises(RuntimeError, match="AWS_REGION"):
        load_bedrock_env()


def test_load_bedrock_env_returns_both_vars_when_set(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    assert load_bedrock_env() == {
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "AWS_REGION": "ap-southeast-2",
    }


def test_mcp_server_config_forwards_only_documented_env_vars(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SOME_OTHER_VAR", "should-not-appear")

    config = mcp_server_config()

    server = config["agentaudit-mcp"]
    assert server["command"]
    assert server["args"] == ["-m", "agentaudit_mcp.server"]
    assert server["env"] == {
        "DATABASE_URL": "postgresql://localhost/db",
        "OPENAI_API_KEY": "sk-test",
    }


def test_mcp_server_config_omits_unset_env_vars(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config = mcp_server_config()

    assert config["agentaudit-mcp"]["env"] == {}
