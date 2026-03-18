import os
from motor.motor_asyncio import AsyncIOMotorClient

_client: AsyncIOMotorClient | None = None

def get_db():
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(os.getenv("MONGODB_URI"))
    return _client[os.getenv("MONGODB_DB", "Daedalus")]

async def insert_checkpoint(run_id: str, agent_id: str, data: dict):
    await get_db().checkpoints.insert_one({"run_id": run_id, "agent_id": agent_id, **data})

async def get_checkpoints(run_id: str) -> list[dict]:
    return await get_db().checkpoints.find({"run_id": run_id}).to_list(None)

async def log_decision(run_id: str, agent_id: str, data: dict):
    await get_db().decision_logs.insert_one({"run_id": run_id, "agent_id": agent_id, **data})

async def log_score(run_id: str, agent_id: str, iteration: int, scores: dict):
    await get_db().scores.insert_one({
        "run_id": run_id, "agent_id": agent_id, "iteration": iteration, **scores
    })

async def upsert_registry(run_id: str, spec: dict):
    await get_db().agent_registry.update_one(
        {"run_id": run_id, "agent_id": spec["agent_id"]},
        {"$set": spec}, upsert=True
    )

async def update_run_status(run_id: str, status: str, state_update: dict = None):
    import datetime
    now = datetime.datetime.utcnow().isoformat() + "Z"
    
    update_doc = {"status": status}
    if state_update:
        update_doc.update(state_update)
        
    set_on_insert = {
        "run_id": run_id,
        "started_at": now,
        "goal": state_update.get("goal", "") if state_update else "",
        "preset": state_update.get("preset", "default") if state_update else "default",
    }
        
    # Ensure keys in $setOnInsert or _id aren't in $set to avoid Mongo conflicts
    for key in list(set_on_insert.keys()) + ["_id"]:
        if key in update_doc:
            del update_doc[key]
    
    await get_db().runs.update_one(
        {"_id": run_id}, 
        {
            "$set": update_doc,
            "$setOnInsert": set_on_insert
        }, 
        upsert=True
    )
