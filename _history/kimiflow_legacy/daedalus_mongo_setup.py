"""
Daedalus — MongoDB Atlas Setup Script
Run once to create all collections, indexes, and validation schemas.
"""

import os
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import CollectionInvalid

load_dotenv(override=True)

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB  = os.getenv("MONGODB_DB", "Daedalus")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI not found in .env")

client = MongoClient(MONGODB_URI)
db     = client[MONGODB_DB]

print(f"\n Daedalus MongoDB Setup — {MONGODB_DB}")
print("-" * 52)

def create_collection(name, validator=None):
    try:
        db.create_collection(name, validator=validator) if validator else db.create_collection(name)
        print(f"  created  {name}")
    except CollectionInvalid:
        print(f"  exists   {name}  (skipped)")

def create_indexes(col_name, indexes):
    col = db[col_name]
    for idx in indexes:
        col.create_index(**idx)
    print(f"  indexed  {col_name}  ({len(indexes)} indexes)")

# 1. runs
create_collection("runs", {"$jsonSchema": {"bsonType": "object",
    "required": ["_id", "goal", "preset", "status", "started_at"],
    "properties": {
        "_id":               {"bsonType": "string"},
        "goal":              {"bsonType": "string"},
        "preset":            {"bsonType": "string", "enum": ["saas","docs","research","default"]},
        "status":            {"bsonType": "string", "enum": ["running","done","failed","paused"]},
        "started_at":        {"bsonType": "string"},
        "completed_at":      {"bsonType": ["string","null"]},
        "final_score":       {"bsonType": ["double","null"]},
        "system_iterations": {"bsonType": "int"},
        "total_agents":      {"bsonType": "int"},
        "config_snapshot":   {"bsonType": "object"},
    }}})
create_indexes("runs", [
    {"keys": [("status", ASCENDING), ("started_at", DESCENDING)], "name": "status_started"},
    {"keys": [("started_at", DESCENDING)], "name": "started_at_desc"},
])

# 2. checkpoints
create_collection("checkpoints", {"$jsonSchema": {"bsonType": "object",
    "required": ["run_id","agent_id","task","depth","status","timestamp"],
    "properties": {
        "run_id":    {"bsonType": "string"},
        "agent_id":  {"bsonType": "string"},
        "task":      {"bsonType": "string"},
        "depth":     {"bsonType": "int"},
        "parent_id": {"bsonType": ["string","null"]},
        "status":    {"bsonType": "string", "enum": ["done","failed","frozen"]},
        "result":    {"bsonType": "string"},
        "score":     {"bsonType": "double"},
        "iterations":{"bsonType": "int"},
        "frozen":    {"bsonType": "bool"},
        "timestamp": {"bsonType": "string"},
    }}})
create_indexes("checkpoints", [
    {"keys": [("run_id", ASCENDING), ("agent_id", ASCENDING)], "unique": True, "name": "run_agent_unique"},
    {"keys": [("run_id", ASCENDING), ("frozen", ASCENDING)], "name": "run_frozen"},
    {"keys": [("run_id", ASCENDING), ("timestamp", DESCENDING)], "name": "run_timestamp"},
])

# 3. decision_logs
create_collection("decision_logs", {"$jsonSchema": {"bsonType": "object",
    "required": ["run_id","agent_id","depth","iteration","decision","timestamp"],
    "properties": {
        "run_id":         {"bsonType": "string"},
        "agent_id":       {"bsonType": "string"},
        "depth":          {"bsonType": "int"},
        "iteration":      {"bsonType": "int"},
        "decision":       {"bsonType": "string", "enum": ["retry","spawn_sub","freeze","terminate"]},
        "reason":         {"bsonType": "string"},
        "old_specialist": {"bsonType": ["string","null"]},
        "new_specialist": {"bsonType": ["string","null"]},
        "model_used":     {"bsonType": "string"},
        "score":          {"bsonType": "double"},
        "feedback":       {"bsonType": "string"},
        "latency_ms":     {"bsonType": "int"},
        "timestamp":      {"bsonType": "string"},
    }}})
create_indexes("decision_logs", [
    {"keys": [("run_id", ASCENDING), ("agent_id", ASCENDING)], "name": "run_agent"},
    {"keys": [("run_id", ASCENDING), ("timestamp", DESCENDING)], "name": "run_timestamp"},
    {"keys": [("run_id", ASCENDING), ("decision", ASCENDING)], "name": "run_decision"},
])

# 4. scores
create_collection("scores", {"$jsonSchema": {"bsonType": "object",
    "required": ["run_id","agent_id","iteration","weighted_total","timestamp"],
    "properties": {
        "run_id":         {"bsonType": "string"},
        "agent_id":       {"bsonType": "string"},
        "iteration":      {"bsonType": "int"},
        "correctness":    {"bsonType": "double"},
        "completeness":   {"bsonType": "double"},
        "consistency":    {"bsonType": "double"},
        "runnability":    {"bsonType": "double"},
        "format":         {"bsonType": "double"},
        "weighted_total": {"bsonType": "double"},
        "feedback":       {"bsonType": "string"},
        "retry_with":     {"bsonType": ["string","null"]},
        "timestamp":      {"bsonType": "string"},
    }}})
create_indexes("scores", [
    {"keys": [("run_id", ASCENDING), ("agent_id", ASCENDING), ("iteration", ASCENDING)], "name": "run_agent_iter"},
    {"keys": [("run_id", ASCENDING), ("weighted_total", DESCENDING)], "name": "run_score"},
])

# 5. agent_registry
create_collection("agent_registry", {"$jsonSchema": {"bsonType": "object",
    "required": ["run_id","agent_id","task","output_type","specialist","threshold","depth","status"],
    "properties": {
        "run_id":       {"bsonType": "string"},
        "agent_id":     {"bsonType": "string"},
        "task":         {"bsonType": "string"},
        "output_type":  {"bsonType": "string", "enum": ["code","docs","design","research"]},
        "specialist":   {"bsonType": "string", "enum": ["coder","reasoner","drafter","creative","fast","researcher"]},
        "threshold":    {"bsonType": "double"},
        "depth":        {"bsonType": "int"},
        "parent_id":    {"bsonType": ["string","null"]},
        "dependencies": {"bsonType": "array"},
        "status":       {"bsonType": "string", "enum": ["pending","running","done","failed","frozen","terminated"]},
        "score":        {"bsonType": ["double","null"]},
        "iterations":   {"bsonType": ["int","null"]},
    }}})
create_indexes("agent_registry", [
    {"keys": [("run_id", ASCENDING), ("agent_id", ASCENDING)], "unique": True, "name": "run_agent_unique"},
    {"keys": [("run_id", ASCENDING), ("status", ASCENDING)], "name": "run_status"},
    {"keys": [("run_id", ASCENDING), ("depth", ASCENDING)], "name": "run_depth"},
])

# 6. conflicts
create_collection("conflicts", {"$jsonSchema": {"bsonType": "object",
    "required": ["run_id","system_iteration","agent_a","agent_b","interface","resolution","timestamp"],
    "properties": {
        "run_id":           {"bsonType": "string"},
        "system_iteration": {"bsonType": "int"},
        "agent_a":          {"bsonType": "string"},
        "agent_b":          {"bsonType": "string"},
        "interface":        {"bsonType": "string"},
        "resolution":       {"bsonType": "string"},
        "timestamp":        {"bsonType": "string"},
    }}})
create_indexes("conflicts", [
    {"keys": [("run_id", ASCENDING), ("system_iteration", ASCENDING)], "name": "run_iter"},
])

# 7. repair_log
create_collection("repair_log", {"$jsonSchema": {"bsonType": "object",
    "required": ["run_id","system_iteration","repair_attempt","broken_interfaces","reassigned_agents","outcome","timestamp"],
    "properties": {
        "run_id":            {"bsonType": "string"},
        "system_iteration":  {"bsonType": "int"},
        "repair_attempt":    {"bsonType": "int"},
        "broken_interfaces": {"bsonType": "array"},
        "reassigned_agents": {"bsonType": "array"},
        "frozen_agents":     {"bsonType": "array"},
        "outcome":           {"bsonType": "string", "enum": ["pass","fail_retry","fail_full_replan"]},
        "timestamp":         {"bsonType": "string"},
    }}})
create_indexes("repair_log", [
    {"keys": [("run_id", ASCENDING), ("repair_attempt", ASCENDING)], "name": "run_attempt"},
])

# 8. outputs
create_collection("outputs", {"$jsonSchema": {"bsonType": "object",
    "required": ["run_id","agent_id","output_type","content","timestamp"],
    "properties": {
        "run_id":      {"bsonType": "string"},
        "agent_id":    {"bsonType": "string"},
        "output_type": {"bsonType": "string"},
        "content":     {"bsonType": "string"},
        "score":       {"bsonType": ["double","null"]},
        "frozen":      {"bsonType": "bool"},
        "timestamp":   {"bsonType": "string"},
    }}})
create_indexes("outputs", [
    {"keys": [("run_id", ASCENDING), ("agent_id", ASCENDING)], "name": "run_agent"},
    {"keys": [("run_id", ASCENDING), ("frozen", ASCENDING)], "name": "run_frozen"},
])

# Seed verification
print("\n Seeding verification document...")
db["runs"].insert_one({
    "_id": "run_setup_verify", "goal": "Daedalus setup verification",
    "preset": "default", "status": "done",
    "started_at": datetime.utcnow().isoformat() + "Z",
    "completed_at": datetime.utcnow().isoformat() + "Z",
    "final_score": 1.0, "system_iterations": 0,
    "total_agents": 0, "config_snapshot": {"setup": True, "version": "1.0"},
})

print("\n" + "─" * 52)
print(f" Setup complete — {MONGODB_DB} ready")
for name in sorted(db.list_collection_names()):
    count = db[name].count_documents({})
    idx   = len(list(db[name].list_indexes()))
    print(f"   {name:<20} {count:>3} doc(s)   {idx} index(es)")
print("\n Delete verification doc when confirmed:")
print("   db.runs.deleteOne({ _id: 'run_setup_verify' })")
print("─" * 52)
client.close()
