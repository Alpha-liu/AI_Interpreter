"""配置读写与鉴权头。"""
from ai_interpreter import config


def test_build_auth_headers_includes_bearer_and_workspace():
    headers = config.build_auth_headers("sk-test", "ws-1")
    assert headers[0] == "Authorization: Bearer sk-test"
    assert headers[1] == "X-DashScope-WorkSpace: ws-1"


def test_build_auth_headers_without_workspace():
    assert config.build_auth_headers("sk-test") == ["Authorization: Bearer sk-test"]


def test_subtitle_config_defaults():
    cfg = config.SubtitleConfig("en")
    assert cfg.target_lang == "en"
    assert cfg.show_source is True
    assert cfg.show_target is True
