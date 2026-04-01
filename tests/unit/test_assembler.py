"""Unit tests for daedalus/assembler.py"""
import os
import zipfile
import pytest

from daedalus.assembler import parse_and_zip

def test_assembler_extracts_files_and_zips(tmp_path):
    output_base = str(tmp_path)
    run_id = "run_assemble_123"
    
    combined = '''Here is the final code you requested.

```python
# file: main.py
def hello():
    print("hello world")
```

And here is the utils file:
# file: src/utils.py
```python
def add(a, b):
    return a + b
```

Oh wait, actually I need to update main.py!
```python
# file: main.py
def hello():
    print("hello world!")
    print("updated")
```
'''
    state = {"combined_result": combined}
    
    zip_path = parse_and_zip(run_id, state, output_base=output_base)
    
    assert os.path.exists(zip_path), "ZIP file was not created"
    
    build_dir = os.path.join(output_base, run_id)
    assert os.path.exists(os.path.join(build_dir, "main.py"))
    assert os.path.exists(os.path.join(build_dir, "src", "utils.py"))
    
    # Verify deduplication (last writer wins)
    with open(os.path.join(build_dir, "main.py"), "r", encoding="utf-8") as f:
        content = f.read()
        assert "print(\"hello world!\")" in content
        assert "updated" in content
        
    # Verify ZIP contents
    with zipfile.ZipFile(zip_path, 'r') as z:
        names = z.namelist()
        # Windows might use backslash in namelist or it uses forward slash, handle both
        norm_names = [n.replace('\\', '/') for n in names]
        assert "main.py" in norm_names
        assert "src/utils.py" in norm_names

def test_assembler_no_files_raw_output(tmp_path):
    output_base = str(tmp_path)
    run_id = "run_assemble_456"
    
    combined = "Just some text without any file declarations."
    state = {"combined_result": combined}
    
    zip_path = parse_and_zip(run_id, state, output_base=output_base)
    build_dir = os.path.join(output_base, run_id)
    
    assert os.path.exists(os.path.join(build_dir, "FINAL.md"))
    with open(os.path.join(build_dir, "FINAL.md"), "r", encoding="utf-8") as f:
        assert f.read() == combined
