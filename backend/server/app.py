from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import logging
import json
from backend.chat.chat import ChatAgentWithMemory

logger = logging.getLogger(__name__)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def read_root():
    return {"message": "Welcome to GPT Researcher"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    chat_agent = None
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                if isinstance(message, dict):
                    # Initialize chat agent based on research mode
                    if chat_agent is None:
                        research_mode = message.get("research_mode", "default")
                        chat_agent = ChatAgentWithMemory(
                            report="Sample report", 
                            config_path="path/to/config", 
                            headers={},
                            research_mode=research_mode
                        )
                    await chat_agent.chat(message.get("message", data), websocket)
                else:
                    if chat_agent is None:
                        chat_agent = ChatAgentWithMemory(report="Sample report", config_path="path/to/config", headers={})
                    await chat_agent.chat(data, websocket)
            except json.JSONDecodeError:
                if chat_agent is None:
                    chat_agent = ChatAgentWithMemory(report="Sample report", config_path="path/to/config", headers={})
                await chat_agent.chat(data, websocket)
    except WebSocketDisconnect:
        await websocket.close()
