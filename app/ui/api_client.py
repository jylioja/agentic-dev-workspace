# app/ui/api_client.py
import requests
import json

API_STREAM_URL = "http://localhost:8000/api/v1/chat/stream"

def stream_chat_from_api(messages: list, agent_override: str = None, session_id: str = "default"):
    """
    Kytkeytyy FastAPI:n striimaavaan endpointiin ja yieldaa tilapäivityksiä 
    sitä mukaa kun niitä saapuu.
    """
    payload = {
        "messages": messages,
        "agent_override": agent_override,
        "session_id": session_id
    }
    
    try:
        # stream=True pitää yhteyden auki ja ottaa dataa vastaan palasina
        with requests.post(API_STREAM_URL, json=payload, stream=True, timeout=300) as response:
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    try:
                        data = json.loads(decoded_line)
                        yield data
                    except json.JSONDecodeError:
                        continue
                        
    except requests.exceptions.RequestException as e:
        yield {
            "type": "error",
            "content": f"❌ **Yhteysvirhe Backendiin:** Palvelin ei vastaa. Varmista, että FastAPI on käynnissä.\n\nDetails: {str(e)}"
        }