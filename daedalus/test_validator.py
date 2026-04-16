import asyncio
import re
import os
import tempfile
from typing import Dict, List

class TestValidator:
    """Runs tests and extracts specific feedback."""
    
    async def validate_module(self, module_name: str, test_file: str, impl_file: str) -> dict:
        """Run tests for a module and return validation dict."""
        with tempfile.TemporaryDirectory() as temp_dir:
            impl_path = os.path.join(temp_dir, "impl.go")
            test_path = os.path.join(temp_dir, "impl_test.go")
            
            with open(impl_path, "w", encoding="utf-8") as f:
                f.write(impl_file.replace("```go", "").replace("```", "").strip() if impl_file else "")
            with open(test_path, "w", encoding="utf-8") as f:
                f.write(test_file.replace("```go", "").replace("```", "").strip() if test_file else "")
                
            mod_proc = await asyncio.create_subprocess_shell(
                "go mod init tempmod",
                cwd=temp_dir,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await mod_proc.communicate()  # await process object, not coroutine
            
            # external imports will fail without go mod tidy — expected; short-circuit handles failures
            cmd = f"go test -v -cover {module_name}"
            print(f"  [test_validator] Executing subprocess: {cmd}")
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=temp_dir
            )
            stdout, stderr = await process.communicate()
        
        output = stdout.decode('utf-8', errors='replace')
        
        failures = self.extract_failures(output)
        coverage = self.get_coverage(output)
        
        status = "failing" if failures else "passing"
        
        feedback_parts = []
        if failures:
            for f in failures:
                feedback_parts.append(f"{f['test']} failing: {f['error']}")
        
        return {
            "status": status,
            "test_results": failures,
            "coverage": coverage,
            "feedback": "; ".join(feedback_parts) if feedback_parts else "All tests passed"
        }
    
    def extract_failures(self, test_output: str) -> List[Dict[str, str]]:
        """Parse test output and extract failing test cases."""
        failures = []
        lines = test_output.split('\n')
        
        current_error = []
        
        for line in lines:
            line_stripped = line.strip()
            
            if line.startswith("panic:"):
                failures.append({
                    "test": "panic",
                    "error": line
                })
                break
                
            if line.startswith("=== RUN"):
                current_error = []
            elif line_stripped and not line.startswith("---") and not line.startswith("FAIL") and not line.startswith("PASS") and not line.startswith("coverage"):
                current_error.append(line_stripped)
            elif line.startswith("--- FAIL:"):
                parts = line.split()
                if len(parts) >= 3:
                    test_name = parts[2]
                    failures.append({
                        "test": test_name,
                        "error": " ".join(current_error) if current_error else "Test failed without specific assertion output"
                    })
                
        return failures
    
    def get_coverage(self, coverage_output: str) -> float:
        """Extract coverage percentage."""
        match = re.search(r"coverage:\s*([0-9.]+)\%", coverage_output)
        if match:
            return float(match.group(1))
        return -1.0
