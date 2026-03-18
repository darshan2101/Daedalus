import os

def get_run_dir(run_id: str) -> str:
    """Returns absolute path to outputs/workspace/{run_id}/"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "outputs", "workspace", run_id)

def get_agent_dir(run_id: str, agent_id: str) -> str:
    return os.path.join(get_run_dir(run_id), agent_id)

def write_agent_output(run_id: str, agent_id: str, content: str):
    folder = get_agent_dir(run_id, agent_id)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "output.txt"), "w", encoding="utf-8") as f:
        f.write(content)

def read_agent_output(run_id: str, agent_id: str) -> str:
    folder = get_agent_dir(run_id, agent_id)
    path = os.path.join(folder, "output.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""
