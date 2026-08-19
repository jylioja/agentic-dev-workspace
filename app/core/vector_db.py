# app/core/vector_db.py
import chromadb
from chromadb.utils import embedding_functions
from pathlib import Path
import os

# Määritetään polku, johon ChromaDB tallentaa vektorit (sama periaate kuin workspacessa)
CURRENT_FILE_DIR = Path(__file__).resolve().parent
BASE_DIR = CURRENT_FILE_DIR.parent.parent 
CHROMA_PATH = BASE_DIR / "chroma_data"
CHROMA_PATH.mkdir(exist_ok=True, parents=True)

# 1. Yhdistetään lokaaliin ChromaDB-tietokantaan
client = chromadb.PersistentClient(path=str(CHROMA_PATH))

# 2. Määritetään Ollaman upotusmalli (Embedding Function)
ollama_ef = embedding_functions.OllamaEmbeddingFunction(
    url="http://localhost:11434/api/embeddings",
    model_name="nomic-embed-text",
)

# 3. UUSI: Luodaan dynaaminen apufunktio, joka hakee kokoelman aina tuoreena
def get_current_collection():
    return client.get_or_create_collection(
        name="chat_history",
        embedding_function=ollama_ef
    )

def add_to_memory(message_id: int, session_id: int, role: str, content: str):
    """
    Muuttaa tekstin vektoriksi ja tallentaa sen ChromaDB:hen.
    """
    if not content or not content.strip():
        return
        
    metadata = {
        "session_id": str(session_id),
        "role": role
    }
    
    try:
        # Haetaan aina tuore collection ennen tallennusta
        collection = get_current_collection()
        collection.add(
            documents=[content],
            metadatas=[metadata],
            ids=[str(message_id)] # ID:n pitää olla string ChromaDB:ssä
        )
    except Exception as e:
        print(f"Virhe vektoritietokantaan tallennuksessa: {e}")

def search_memory(query: str, n_results: int = 3) -> str:
    """
    Searches the agent's vector database memory for past events, user data, and project context.
    Automatically filters out exact duplicate entries.
    
    CRITICAL ANTI-HALLUCINATION TRIGGER: 
    You MUST use this tool EVERY TIME the user asks about specific project names, code names, IDs, 
    or historical context. NEVER guess, invent, or assume project code names. Always search first.
    """
    try:
        # Haetaan aina tuore collection ennen hakua
        collection = get_current_collection()
        
        # Fetch the results from the vector database
        results = collection.query(
            query_texts=[query],
            n_results=n_results
        )
        
        if not results or not results.get('documents') or not results['documents'][0]:
            return "[MEMORY SEARCH] No relevant memories found."
            
        seen_texts = set()
        formatted_results = "[MEMORY SEARCH RESULTS]\n"
        
        for i, doc in enumerate(results['documents'][0]):
            # Data cleanup: Skip if this exact text is already in the list
            if doc not in seen_texts:
                seen_texts.add(doc)
                meta = results['metadatas'][0][i]
                role = meta.get('role', 'unknown')
                formatted_results += f"- (Role: {role}): {doc}\n\n"
                
        return formatted_results
    except Exception as e:
        return f"[ERROR] Failed to search memory: {str(e)}"