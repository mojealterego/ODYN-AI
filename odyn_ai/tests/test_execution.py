import asyncio
import tempfile
import unittest

from odyn_ai.core.execution import ExecutionEngine, ExecutionPolicy, ExecutionRequest


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    def test_policy_rejects_traversal(self):
        policy = ExecutionPolicy()
        with self.assertRaises(ValueError):
            policy.validate(ExecutionRequest("web", "build", {"../escape": "x"}))

    def test_commands_are_platform_specific(self):
        self.assertEqual(ExecutionEngine._command("web", "build"), ["npm", "run", "build"])
        self.assertEqual(ExecutionEngine._command("android", "build"), ["./gradlew", "assembleDebug"])

    async def test_missing_toolchain_is_reported(self):
        engine = ExecutionEngine(tempfile.mkdtemp())
        request = ExecutionRequest("web", "build", {"package.json": "{}"}, timeout=1)
        result = await engine.execute(request)
        self.assertFalse(result.ok)
        self.assertIsNone(result.artifact)
        self.assertTrue(result.diagnostics)


if __name__ == "__main__":
    unittest.main()
