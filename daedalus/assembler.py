"""
daedalus/assembler.py

Parses the final combined markdown output, extracts code blocks into real files,
deduplicates file paths (keeping the last occurrence), and packages them into a ZIP archive.
"""

import os
import re
import zipfile
from rich.console import Console
from daedalus.state import RunState

console = Console()

def parse_and_zip(run_id: str, state: RunState, output_base: str = "outputs/builds") -> str:
    """
    Parses the combined result from the RunState, extracts files, writes them
    to a build directory, and creates a ZIP archive.
    Returns the path to the ZIP file.
    """
    console.print("\n[bold magenta]📦 Assembling final deliverable...[/]")
    combined = state.get("combined_result", "")
    if not combined:
        console.print("[yellow]No combined result to assemble.[/]")
        return ""
        
    build_dir = os.path.join(output_base, run_id)
    os.makedirs(build_dir, exist_ok=True)
    
    # Simple regex to catch code blocks
    # Looking for:
    # ```python
    # # file: path/to/file.py
    # code...
    # ```
    # or just:
    # # file: path/to/file.py
    # ```python
    # code
    # ```
    
    # We will use a more resilient approach: split by ```
    blocks = combined.split("```")
    
    extracted_files = {} # path -> content (dict ensures deduplication, last writer wins)
    
    for i in range(1, len(blocks), 2):
        block = blocks[i].strip()
        lines = block.split('\n')
        if not lines:
            continue
            
        # First line is usually the language tag e.g., 'python'
        # Second line might be the # file: path
        lang_line = lines[0].strip()
        content_lines = lines[1:]
        
        filename = None
        
        # Check if filename is in the first few lines of the code block
        for idx_line, line in enumerate(content_lines[:5]):
            line_str = line.strip()
            # Match variations of: # file: main.py, // file: main.js, /* file: main.css */
            match = re.search(r'(?:#|//|/\*)\s*file:\s*([^\s\*]+)', line_str, re.IGNORECASE)
            if match:
                filename = match.group(1).strip()
                break
                
        if not filename:
            # Maybe the file directive was immediately BEFORE the triple backticks?
            # Let's check the text block before this code block.
            prev_block = blocks[i-1].strip().split('\n')
            if prev_block:
                last_line = prev_block[-1].strip()
                match = re.search(r'(?:#|//|/\*|`)\s*file:\s*([^\s\*`]+)', last_line, re.IGNORECASE)
                if match:
                    filename = match.group(1).strip()
        
        if filename:
            # Clean up filename paths
            filename = filename.lstrip('/\\')
            # Join back the content
            extracted_files[filename] = "\n".join(content_lines)
            
    if not extracted_files:
        console.print("[yellow]No file definitions found in the markdown output. Packaging raw output.[/]")
        extracted_files["FINAL.md"] = combined
        
    # Write files to disk
    console.print(f"  [cyan]Writing {len(extracted_files)} files to {build_dir}...[/]")
    for relative_path, content in extracted_files.items():
        # Prevent path traversal attacks
        safe_path = os.path.normpath(relative_path)
        if safe_path.startswith("..") or os.path.isabs(safe_path):
            console.print(f"  [yellow]Skipping unsafe path: {relative_path}[/]")
            continue
            
        full_path = os.path.join(build_dir, safe_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
            
    # Zip it up
    zip_path = f"{build_dir}.zip"
    console.print(f"  [cyan]Zipping to {zip_path}...[/]")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(build_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, build_dir)
                zipf.write(file_path, arcname)
                
    console.print(f"[bold green]✅ Assembly complete: {zip_path}[/]")
    return zip_path
