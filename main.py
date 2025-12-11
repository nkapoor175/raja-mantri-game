# main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uuid

app = FastAPI(title="Raja-Mantri (step 1)")

# In-memory storage (simple notebook for the server)
rooms = {}   # roomId -> { players: [playerId,...], status: "waiting" }
players = {} # playerId -> { name: str, roomId: str, totalScore: int }

# Helper to create unique ids
def new_id() -> str:
    return str(uuid.uuid4())

# Request bodies (Pydantic models help FastAPI parse JSON)
class CreateRoomReq(BaseModel):
    name: str

class JoinRoomReq(BaseModel):
    roomId: str
    name: str

@app.get("/")
def home():
    return {"message": "Game backend running (step 1)!"}

@app.post("/room/create")
def create_room(req: CreateRoomReq):
    # Create room + first player
    room_id = new_id()
    player_id = new_id()

    rooms[room_id] = {
        "players": [player_id],
        "status": "waiting",  # waiting until 4 players
    }

    players[player_id] = {"name": req.name, "roomId": room_id, "totalScore": 0}

    return {
        "roomId": room_id,
        "playerId": player_id,
        "message": "Room created. Waiting for players (1/4)."
    }

@app.post("/room/join")
def join_room(req: JoinRoomReq):
    if req.roomId not in rooms:
        raise HTTPException(status_code=404, detail="Room not found")

    room = rooms[req.roomId]
    if room["status"] != "waiting":
        raise HTTPException(status_code=400, detail="Room not accepting joins right now")

    if len(room["players"]) >= 4:
        raise HTTPException(status_code=400, detail="Room is full (4 players max)")

    player_id = new_id()
    room["players"].append(player_id)
    players[player_id] = {"name": req.name, "roomId": req.roomId, "totalScore": 0}

    return {
        "roomId": req.roomId,
        "playerId": player_id,
        "message": f"Joined room ({len(room['players'])}/4)."
    }
import random

@app.get("/room/players/{roomId}")
def get_players(roomId: str):
    if roomId not in rooms:
        raise HTTPException(status_code=404, detail="Room not found")

    room = rooms[roomId]
    
    # Return player names, not IDs
    players_list = [
        {"playerId": pid, "name": players[pid]["name"]}
        for pid in room["players"]
    ]

    return {
        "roomId": roomId,
        "players": players_list
    }


@app.post("/room/assign/{roomId}")
def assign_roles(roomId: str):
    if roomId not in rooms:
        raise HTTPException(status_code=404, detail="Room not found")

    room = rooms[roomId]

    if len(room["players"]) != 4:
        raise HTTPException(status_code=400, detail="Need exactly 4 players to assign roles")

    # Roles to assign
    roles = ["Raja", "Mantri", "Chor", "Sipahi"]
    random.shuffle(roles)

    # Assign roles to players in order
    room_roles = {}
    for i, pid in enumerate(room["players"]):
        room_roles[pid] = roles[i]

    rooms[roomId]["roles"] = room_roles

    # Find the Mantri
    mantri_id = next(pid for pid, role in room_roles.items() if role == "Mantri")
    rooms[roomId]["mantriId"] = mantri_id

    return {
        "roomId": roomId,
        "rolesAssigned": True,
        "message": "Roles assigned. Each player can now view their role privately."
    }
# --- ROLE CHECK ENDPOINT ---
@app.get("/role/me/{roomId}/{playerId}")
def get_my_role(roomId: str, playerId: str):
    if roomId not in rooms:
        return {"error": "Room not found"}

    if playerId not in rooms[roomId]["roles"]:
        return {"error": "Player not found"}

    return {
        "playerId": playerId,
        "role": rooms[roomId]["roles"][playerId]
    }
# --- GUESS + RESULT ENDPOINTS ---
BASE_POINTS = {"Raja": 1000, "Mantri": 800, "Sipahi": 500, "Chor": 0}

from pydantic import BaseModel

class GuessReq(BaseModel):
    roomId: str
    mantriId: str
    targetId: str

@app.post("/guess/{roomId}")
def mantri_guess(roomId: str, payload: GuessReq):
    # validations
    if roomId not in rooms:
        raise HTTPException(status_code=404, detail="Room not found")
    room = rooms[roomId]
    if "roles" not in room or not room["roles"]:
        raise HTTPException(status_code=400, detail="Roles not assigned yet")
    if payload.mantriId not in room["players"] or payload.targetId not in room["players"]:
        raise HTTPException(status_code=404, detail="Invalid player id(s)")
    if "mantriId" not in room or room["mantriId"] != payload.mantriId:
        raise HTTPException(status_code=403, detail="Only the Mantri can submit a guess")
    if room.get("status") == "finished":
        raise HTTPException(status_code=400, detail="Round already finished")

    # find real chor
    real_chor = next(pid for pid, role in room["roles"].items() if role == "Chor")

    # start with base points per role
    round_scores = { pid: BASE_POINTS[role] for pid, role in room["roles"].items() }

    if payload.targetId == real_chor:
        msg = "Mantri guessed correctly. No points transfer."
    else:
        # Chor steals Mantri's base points
        stolen = BASE_POINTS["Mantri"]
        round_scores[real_chor] += stolen
        round_scores[payload.mantriId] = 0
        msg = "Mantri guessed incorrectly. Chor stole Mantri's points."

    # save round state
    room["guess"] = {"by": payload.mantriId, "target": payload.targetId}
    room["scores"] = round_scores
    room["status"] = "finished"

    # update cumulative totals for players
    for pid, pts in round_scores.items():
        players[pid]["totalScore"] = players.get(pid, {}).get("totalScore", 0) + pts
        # ensure room leaderboard exists
        room.setdefault("leaderboard", {})
        room["leaderboard"][pid] = room["leaderboard"].get(pid, 0) + pts

    return {"roomId": roomId, "message": msg, "roundScores": round_scores}

@app.get("/result/{roomId}")
def get_result(roomId: str):
    if roomId not in rooms:
        raise HTTPException(status_code=404, detail="Room not found")
    room = rooms[roomId]
    if room.get("status") != "finished":
        raise HTTPException(status_code=400, detail="Round not finished yet")
    return {
        "roomId": roomId,
        "roles": room.get("roles", {}),
        "guess": room.get("guess"),
        "roundScores": room.get("scores"),
        "leaderboard": room.get("leaderboard", {})
    }
