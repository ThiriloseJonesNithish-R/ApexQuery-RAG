import os
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from google import genai
from google.genai import types
import main

# Load environment variables
load_dotenv()

app = FastAPI(title="RAG App - AI Document Q&A")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global in-memory storage for documents and chat session
uploaded_files_metadata = []  # List of {"name": str, "size": str, "words": int}
combined_text_cache = ""
active_chat = None
client_instance = None

# Ensure uploads directory exists
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_gemini_client():
    global client_instance
    if client_instance is not None:
        return client_instance
        
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500, 
            detail="GEMINI_API_KEY environment variable is missing. Please configure it in your .env file."
        )
    try:
        # Client automatically picks up GEMINI_API_KEY from environment
        client_instance = genai.Client()
        return client_instance
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to initialize Gemini Client: {str(e)}"
        )

def rebuild_combined_context():
    global combined_text_cache, active_chat
    # Clear active chat so next question starts a new session with new context
    active_chat = None
    
    parts = []
    for meta in uploaded_files_metadata:
        file_path = os.path.join(UPLOAD_DIR, meta["name"])
        content = main.process_file(file_path)
        if content:
            parts.append(
                f"--- START OF FILE: {meta['name']} ---\n"
                f"{content}\n"
                f"--- END OF FILE: {meta['name']} ---"
            )
    combined_text_cache = "\n\n".join(parts)

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    global uploaded_files_metadata
    
    # Validate extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.txt', '.pdf', '.docx']:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file type '{ext}'. Only .txt, .pdf, and .docx are supported."
        )
        
    # Save file
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
        
    # Parse file using main parser
    content = main.process_file(file_path)
    if content is None:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail=f"Failed to parse content from file '{file.filename}'.")
        
    # Calculate metadata
    size_bytes = os.path.getsize(file_path)
    if size_bytes < 1024:
        size_str = f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        size_str = f"{size_bytes / 1024:.1f} KB"
    else:
        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
        
    words = len(content.split())
    
    # Check if duplicate and replace, otherwise append
    exists = False
    for idx, f_meta in enumerate(uploaded_files_metadata):
        if f_meta["name"] == file.filename:
            uploaded_files_metadata[idx] = {
                "name": file.filename,
                "size": size_str,
                "words": words
            }
            exists = True
            break
            
    if not exists:
        uploaded_files_metadata.append({
            "name": file.filename,
            "size": size_str,
            "words": words
        })
        
    # Rebuild context
    rebuild_combined_context()
    
    return {
        "success": True,
        "file": {
            "name": file.filename,
            "size": size_str,
            "words": words
        },
        "all_files": uploaded_files_metadata
    }

@app.post("/api/delete-file")
async def delete_file(filename: str = Form(...)):
    global uploaded_files_metadata
    
    # Find and remove
    found = False
    for idx, meta in enumerate(uploaded_files_metadata):
        if meta["name"] == filename:
            uploaded_files_metadata.pop(idx)
            found = True
            break
            
    if not found:
        raise HTTPException(status_code=404, detail=f"File {filename} not found.")
        
    # Delete file from disk
    file_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        
    # Rebuild context
    rebuild_combined_context()
    
    return {
        "success": True,
        "all_files": uploaded_files_metadata
    }

@app.post("/api/clear")
async def clear_session():
    global uploaded_files_metadata, combined_text_cache, active_chat
    
    # Reset in-memory state
    uploaded_files_metadata = []
    combined_text_cache = ""
    active_chat = None
    
    # Clean disk
    if os.path.exists(UPLOAD_DIR):
        for filename in os.listdir(UPLOAD_DIR):
            file_path = os.path.join(UPLOAD_DIR, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}. Reason: {e}")
                
    return {"success": True}

@app.post("/api/chat")
async def chat_stream(question: str = Form(...)):
    global active_chat, combined_text_cache
    
    client = get_gemini_client()
    
    # Rebuild if empty but files exist
    if not combined_text_cache and uploaded_files_metadata:
        rebuild_combined_context()
        
    # Check if context is available
    if not combined_text_cache.strip():
        raise HTTPException(
            status_code=400, 
            detail="No documents have been uploaded yet. Please upload a document first."
        )

    def event_generator():
        global active_chat
        try:
            if active_chat is None:
                system_instruction = (
                    "You are a helpful, precise AI assistant that answers questions based on the uploaded document contents.\n"
                    "Here are the contents of the document(s) uploaded by the user:\n\n"
                    f"{combined_text_cache}\n\n"
                    "Provide accurate answers referencing the context where possible. If the answer cannot be found or inferred from the text, "
                    "state that it is not present in the documents, but try to answer as best as you can if there's related information."
                )
                active_chat = client.chats.create(
                    model='gemini-3.5-flash',
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.2,
                    )
                )
                
            response_stream = active_chat.send_message_stream(question)
            for chunk in response_stream:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"\n[Error during generation: {str(e)}]"

    return StreamingResponse(event_generator(), media_type="text/plain")

# Serve UI static files
@app.get("/")
async def serve_index():
    return FileResponse(os.path.join("static", "index.html"))

app.mount("/", StaticFiles(directory="static"), name="static")
