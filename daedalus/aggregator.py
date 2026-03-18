import os
import re
from daedalus.state import RunState
from infra.workspace import get_run_dir

# Regex to match: --- FILE: some/path.py ---
# ...content...
# --- END FILE ---
FILE_BLOCK_REGEX = re.compile(
    r"--- FILE:\s*(.+?)\s*---\n(.*?)\n--- END FILE ---",
    re.DOTALL
)

def _aggregate_docs(run_id: str, state: RunState) -> tuple[str, str]:
    """Concatenate markdown outputs with agent task headers."""
    run_dir = get_run_dir(run_id)
    out_path = os.path.join(run_dir, "FINAL.md")
    
    combined = [f"# Final Output: {state.get('goal', 'Daedalus Run')}\n"]
    
    # Sort agent specs by depth (major tasks first)
    specs = sorted(state["agent_specs"], key=lambda s: s.get("depth", 0))
    
    for spec in specs:
        aid = spec["agent_id"]
        if aid not in state["agent_results"]:
            continue
            
        result = state["agent_results"][aid]
        content = result.get("result", "").strip()
        if not content:
            continue
            
        task = spec.get("task", f"Agent {aid}")
        combined.append(f"## {task}\n\n{content}\n")
        
    final_text = "\n".join(combined)
    
    os.makedirs(run_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final_text)
        
    return final_text, out_path

def _aggregate_code(run_id: str, state: RunState) -> tuple[str, str]:
    """Parse FILE blocks and write to final_code/. Also produce a README."""
    run_dir = get_run_dir(run_id)
    out_dir = os.path.join(run_dir, "final_code")
    readme_path = os.path.join(out_dir, "README.md")
    
    os.makedirs(out_dir, exist_ok=True)
    
    # Keep track of file contents. If multiple agents output the same file,
    # the later one overwrites. We iterate by depth (major -> sub).
    files_map = {}
    
    specs = sorted(state["agent_specs"], key=lambda s: s.get("depth", 0))
    
    readme_content = [f"# Final Code: {state.get('goal', 'Daedalus Run')}\n"]
    
    for spec in specs:
        aid = spec["agent_id"]
        if aid not in state["agent_results"]:
            continue
            
        content = state["agent_results"][aid].get("result", "")
        # Extract files
        matches = FILE_BLOCK_REGEX.findall(content)
        for filepath, file_content in matches:
            # Normalize path securely within out_dir
            safe_path = os.path.normpath(filepath).lstrip("\\/")
            files_map[safe_path] = file_content.strip()
            
        # Add summary to readme using any text OUTSIDE file blocks (if any)
        text_only = FILE_BLOCK_REGEX.sub("", content).strip()
        if text_only:
             readme_content.append(f"### Notes from {aid}\n{text_only}\n")
             
    # Write files to disk
    for rel_path, content in files_map.items():
        abs_path = os.path.join(out_dir, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content + "\n")
            
    # Write README
    final_readme = "\n".join(readme_content)
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(final_readme)
        
    return final_readme, out_dir


def aggregate(run_id: str, state: RunState, config: dict) -> RunState:
    """
    Main entry point for Phase A final aggregation.
    Combines agent outputs based on the run's preset.
    """
    preset = state.get("preset", "default")
    
    # We use basic heuristics, but typically 'code' or 'saas' means code extract
    if preset in ("code", "saas"):
        combined_text, out_path = _aggregate_code(run_id, state)
    else:
        # Default, research, docs
        combined_text, out_path = _aggregate_docs(run_id, state)
        
    # Update local state
    state["combined_result"] = combined_text
    state["output_path"] = out_path
    
    return state
