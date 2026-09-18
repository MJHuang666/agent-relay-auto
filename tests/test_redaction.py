import unittest

from tests.shared.agent_relay_runtime_loader import load_runtime_module


redaction = load_runtime_module("redaction")


class RedactionTests(unittest.TestCase):
    def test_redacts_bearer_tokens_named_secrets_and_environment_values(self):
        text = "Authorization: Bearer abc123 API_KEY=secret-value model=gpt-test"
        result = redaction.redact_text(
            text,
            {"API_KEY"},
            {"API_KEY": "secret-value", "OTHER_TOKEN": "token-value"},
        )
        self.assertNotIn("abc123", result)
        self.assertNotIn("secret-value", result)
        self.assertIn("gpt-test", result)


if __name__ == "__main__":
    unittest.main()
