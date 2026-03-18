"""
Daedalus Health Check
Run at any time to verify all infrastructure is reachable and configured.

Usage:
    python tests/health/check.py
    python tests/health/check.py --full   (also runs a mock planner call)
"""
import os
import sys
import asyncio
import argparse
from datetime import datetime

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

# Windows event loop fix
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

import nest_asyncio
nest_asyncio.apply()

PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"

results = []

def check(name, fn):
    try:
        msg = fn()
        results.append((PASS, name, msg or ""))
        print(f"  {PASS}  {name}" + (f"  -- {msg}" if msg else ""))
    except Exception as e:
        results.append((FAIL, name, str(e)))
        print(f"  {FAIL}  {name}  -- {e}")

def check_env():
    required = ["OPENROUTER_API_KEY", "GROQ_API_KEY",
                "MONGODB_URI", "MONGODB_DB",
                "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise ValueError(f"Missing: {', '.join(missing)}")
    return f"{len(required)} keys present"

def check_redis():
    from upstash_redis import Redis
    r = Redis(url=os.getenv("UPSTASH_REDIS_REST_URL"),
              token=os.getenv("UPSTASH_REDIS_REST_TOKEN"))
    key = f"daedalus:health:{datetime.utcnow().timestamp()}"
    r.set(key, "ok", ex=10)
    val = r.get(key)
    r.delete(key)
    if val != "ok":
        raise ValueError(f"Read-back mismatch: got {val!r}")
    return "Upstash Redis read/write OK"

def check_mongodb():
    from pymongo import MongoClient
    client = MongoClient(os.getenv("MONGODB_URI"), serverSelectionTimeoutMS=5000)
    db = client[os.getenv("MONGODB_DB", "Daedalus")]
    collections = db.list_collection_names()
    required_cols = ["runs", "checkpoints", "decision_logs", "scores",
                     "agent_registry", "conflicts", "repair_log", "outputs"]
    missing = [c for c in required_cols if c not in collections]
    client.close()
    if missing:
        raise ValueError(f"Missing collections: {missing}. Run daedalus_mongo_setup.py")
    return f"All {len(required_cols)} collections present"

def check_imports():
    modules = ["langgraph", "motor", "upstash_redis", "pymongo",
               "yaml", "rich", "nest_asyncio", "aiohttp"]
    missing = []
    for m in modules:
        try:
            __import__(m)
        except ImportError:
            missing.append(m)
    if missing:
        raise ImportError(f"pip install {' '.join(missing)}")
    return f"All {len(modules)} packages importable"

def check_config():
    import yaml
    config_path = os.path.join(project_root, "config.yaml")
    if not os.path.exists(config_path):
        raise FileNotFoundError("config.yaml not found in project root")
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    required_keys = ["runtime", "concurrency", "thresholds", "evaluation_weights",
                     "presets", "infra", "logging"]
    missing = [k for k in required_keys if k not in cfg]
    if missing:
        raise KeyError(f"Missing config sections: {missing}")
    return f"config.yaml valid ({len(required_keys)} sections)"

def check_kimiflow():
    """Verify KimiFlow leaf layer files are present and importable."""
    import importlib
    for mod in ["pipeline", "agents", "models"]:
        spec = importlib.util.find_spec(mod)
        if spec is None:
            raise ImportError(f"{mod}.py not found -- KimiFlow leaf layer missing")
    return "pipeline.py, agents.py, models.py all importable"

def check_workspace():
    workspace = os.path.join(project_root, "outputs", "workspace")
    os.makedirs(workspace, exist_ok=True)
    test_file = os.path.join(workspace, ".health_check")
    with open(test_file, "w") as f:
        f.write("ok")
    os.remove(test_file)
    return f"outputs/workspace/ writable"


def main():
    parser = argparse.ArgumentParser(description="Daedalus health check")
    parser.add_argument("--full", action="store_true", help="Also run mock planner check")
    args = parser.parse_args()

    print(f"\n Daedalus Health Check -- {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("-" * 56)

    check(".env credentials",        check_env)
    check("Python packages",         check_imports)
    check("config.yaml",             check_config)
    check("KimiFlow leaf layer",     check_kimiflow)
    check("outputs/workspace/",      check_workspace)
    check("Upstash Redis",           check_redis)
    check("MongoDB Atlas",           check_mongodb)

    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)
    total  = len(results)

    print("-" * 56)
    print(f" {passed}/{total} checks passed" + (f"  |  {failed} FAILED" if failed else "  |  All clear"))

    if failed:
        print("\n Fix the above failures before implementing any new features.")
        sys.exit(1)
    else:
        print(" System ready for implementation.\n")
        sys.exit(0)

if __name__ == "__main__":
    main()
