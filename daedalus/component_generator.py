class ComponentGenerator:
    def __init__(self, config: dict, drafter_fn, coder_fn, fast_fn, evaluator_fn):
        self.config = config
        self.drafter_fn = drafter_fn
        self.coder_fn = coder_fn
        self.fast_fn = fast_fn
        self.evaluator_fn = evaluator_fn
        
    async def generate_module(self, module_spec: dict) -> dict:
        import tempfile, os
        max_iterations = self.config.get("runtime", {}).get("max_module_iterations", 3)
        threshold = self.config.get("thresholds", {}).get("default", 0.82)
        task = module_spec.get("task", module_spec.get("name", ""))

        # Use coder (not drafter) for test generation: Go-specific, stdlib-only, file-delimited
        tests = await self.coder_fn(
            "Write Go unit tests ONLY. Use only Go standard library packages "
            "(testing, net/http/httptest, encoding/json, strings, bytes, etc.). "
            "No external imports. Output a single test file using the --- FILE: --- delimiter.",
            f"Write comprehensive Go unit tests for: {task}",
        )
        score = 0.0
        feedback = ""
        implementation = ""

        for iteration in range(max_iterations):
            prompt = f"Implement Go code to pass these tests:\n{tests}"
            if feedback:
                prompt += f"\n\nPrevious attempt feedback:\n{feedback}"
            # Constrain implementation to stdlib as well so go test runs without go mod tidy
            implementation = await self.coder_fn(
                "Use only Go standard library packages. No external imports.",
                prompt,
            )

            test_results = await self.fast_fn(tests, implementation)

            failed = len(test_results.get("test_results", []))
            feedback = test_results.get("feedback", "")

            # Pass task so evaluator can assess correctness against the module spec
            eval_result = await self.evaluator_fn(task, implementation)
            score = eval_result.get("score", 0.0) if isinstance(eval_result, dict) else 0.0
            if score >= threshold:
                return {"status": "complete", "score": score, "quality_score": score, "result": tests + "\n\n" + implementation}

        return {"status": "partial", "score": score, "quality_score": score, "action": "fix", "result": tests + "\n\n" + implementation}
