import os
import shutil
import zipfile
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
gemini_files_store = {}  # filename -> list of Gemini File objects

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

def extract_docx_images(docx_path, output_dir):
    image_paths = []
    try:
        with zipfile.ZipFile(docx_path) as z:
            for name in z.namelist():
                # docx images are stored under word/media/
                if name.startswith('word/media/') and not name.endswith('/'):
                    base_name = os.path.basename(name)
                    # Create a unique prefix to avoid naming collisions
                    file_prefix = os.path.splitext(os.path.basename(docx_path))[0]
                    dest_name = f"{file_prefix}_{base_name}"
                    dest_path = os.path.join(output_dir, dest_name)
                    
                    with open(dest_path, "wb") as f:
                        f.write(z.read(name))
                    image_paths.append(dest_path)
    except Exception as e:
        print(f"Error extracting images from DOCX {docx_path}: {e}")
    return image_paths

def rebuild_combined_context():
    global combined_text_cache, active_chat
    # Clear active chat so next question starts a new session with new context
    active_chat = None
    
    parts = []
    for meta in uploaded_files_metadata:
        file_path = os.path.join(UPLOAD_DIR, meta["name"])
        ext = os.path.splitext(meta["name"])[1].lower()
        if ext in ['.txt', '.pdf', '.docx']:
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
    global uploaded_files_metadata, gemini_files_store
    
    # Validate extension
    ext = os.path.splitext(file.filename)[1].lower()
    supported_extensions = ['.txt', '.pdf', '.docx', '.png', '.jpg', '.jpeg', '.webp']
    if ext not in supported_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file type '{ext}'. Supported types are: PDF, DOCX, TXT, and Images."
        )
        
    # Save file locally
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
        
    # Process text content (if applicable)
    content = ""
    if ext in ['.txt', '.pdf', '.docx']:
        content = main.process_file(file_path)
        if content is None:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(status_code=400, detail=f"Failed to parse content from file '{file.filename}'.")
    
    # Upload to Gemini File API for multimodal files (PDF, Images, DOCX images)
    client = get_gemini_client()
    gemini_files = []
    
    try:
        if ext == '.pdf':
            # Upload the PDF file directly to Gemini so it reads images/layout natively
            print(f"Uploading PDF '{file.filename}' to Gemini File API...")
            gemini_file = client.files.upload(file=file_path)
            gemini_files.append(gemini_file)
        elif ext in ['.png', '.jpg', '.jpeg', '.webp']:
            # Upload the image directly
            print(f"Uploading image '{file.filename}' to Gemini File API...")
            gemini_file = client.files.upload(file=file_path)
            gemini_files.append(gemini_file)
        elif ext == '.docx':
            # Extract images from Word document and upload them to Gemini
            extracted_images = extract_docx_images(file_path, UPLOAD_DIR)
            if extracted_images:
                print(f"Extracted {len(extracted_images)} images from docx. Uploading to Gemini File API...")
                for img_path in extracted_images:
                    gemini_file = client.files.upload(file=img_path)
                    gemini_files.append(gemini_file)
                    # Clean up local extracted image
                    try:
                        os.remove(img_path)
                    except:
                        pass
                        
        # Store in our gemini file registry
        if gemini_files:
            # Delete old Gemini files if replacing a duplicate
            if file.filename in gemini_files_store:
                for old_file in gemini_files_store[file.filename]:
                    try:
                        client.files.delete(name=old_file.name)
                    except:
                        pass
            gemini_files_store[file.filename] = gemini_files
            
    except Exception as e:
        print(f"Failed to upload to Gemini File API: {e}")
        # We don't block the upload, but warn about OCR/multimodal feature
        
    # Calculate metadata
    size_bytes = os.path.getsize(file_path)
    if size_bytes < 1024:
        size_str = f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        size_str = f"{size_bytes / 1024:.1f} KB"
    else:
        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
        
    words = len(content.split()) if content else 0
    
    pages_count = 0
    if ext == '.pdf':
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            pages_count = len(reader.pages)
        except Exception as e:
            print(f"Failed to read PDF page count: {e}")
            
    # Check if duplicate and replace, otherwise append
    exists = False
    for idx, f_meta in enumerate(uploaded_files_metadata):
        if f_meta["name"] == file.filename:
            uploaded_files_metadata[idx] = {
                "name": file.filename,
                "size": size_str,
                "words": words,
                "pages": pages_count
            }
            exists = True
            break
            
    if not exists:
        uploaded_files_metadata.append({
            "name": file.filename,
            "size": size_str,
            "words": words,
            "pages": pages_count
        })
        
    # Rebuild context
    rebuild_combined_context()
    
    return {
        "success": True,
        "file": {
            "name": file.filename,
            "size": size_str,
            "words": words,
            "pages": pages_count
        },
        "all_files": uploaded_files_metadata
    }

@app.post("/api/delete-file")
async def delete_file(filename: str = Form(...)):
    global uploaded_files_metadata, gemini_files_store
    
    # Find and remove
    found = False
    for idx, meta in enumerate(uploaded_files_metadata):
        if meta["name"] == filename:
            uploaded_files_metadata.pop(idx)
            found = True
            break
            
    if not found:
        raise HTTPException(status_code=404, detail=f"File {filename} not found.")
        
    # Delete associated Gemini files
    client = get_gemini_client()
    if filename in gemini_files_store:
        for gemini_file in gemini_files_store[filename]:
            try:
                client.files.delete(name=gemini_file.name)
                print(f"Deleted Gemini File: {gemini_file.name}")
            except Exception as e:
                print(f"Failed to delete Gemini File {gemini_file.name}: {e}")
        del gemini_files_store[filename]
        
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
    global uploaded_files_metadata, combined_text_cache, active_chat, gemini_files_store
    
    # Delete all uploaded Gemini files
    try:
        client = get_gemini_client()
        for file_list in gemini_files_store.values():
            for gemini_file in file_list:
                try:
                    client.files.delete(name=gemini_file.name)
                except:
                    pass
    except Exception as e:
         print(f"Error clearing Gemini files: {e}")
         
    # Reset in-memory state
    uploaded_files_metadata = []
    combined_text_cache = ""
    active_chat = None
    gemini_files_store = {}
    
    # Clean disk
    if os.path.exists(UPLOAD_DIR):
        for filename in os.listdir(UPLOAD_DIR):
            if filename == '.gitkeep':
                continue
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
    global active_chat, combined_text_cache, gemini_files_store
    
    client = get_gemini_client()
    
    # Rebuild if empty but files exist
    if not combined_text_cache and uploaded_files_metadata:
        rebuild_combined_context()
        
    # Check if context is available (either text context or multimodal files)
    if not combined_text_cache.strip() and not gemini_files_store:
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
                    "For plain text context (from text or Word paragraphs), refer to this data:\n\n"
                    f"{combined_text_cache}\n\n"
                    "You will also receive document files (such as PDFs or images) directly. Analyze them to answer the user's questions.\n"
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
                
                # Gather all Gemini Files
                gemini_files = []
                for file_list in gemini_files_store.values():
                    gemini_files.extend(file_list)
                    
                # If there are uploaded files, pass them in the first chat message
                if gemini_files:
                    contents = gemini_files + [f"User question: {question}"]
                    response_stream = active_chat.send_message_stream(contents)
                else:
                    response_stream = active_chat.send_message_stream(question)
            else:
                # Subsequent messages already have the file context in chat history
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
