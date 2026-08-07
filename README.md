# ApexQuery: AI Document Q&A (RAG Application)

ApexQuery is a modern, responsive, document-based Q&A application that extracts text from multiple file types (PDF, Word `.docx`, and Text `.txt`) and processes interactive queries using the Gemini API. It features both a modern web-based single-page application dashboard and a lightweight command-line interface (CLI).

---

## ✨ Features

* **Multi-Format Parsing**:
  * **PDF Documents**: Extract text page-by-page.
  * **Word Files (`.docx`)**: Extract text from paragraphs and tabular columns.
  * **Text Files (`.txt`)**: Read plain UTF-8 raw text directly.
* **Premium Web Dashboard**: A glassmorphic dark theme built using modern Vanilla CSS3 and HTML5.
* **Real-Time Streaming**: Stream AI answers token-by-token directly into the browser using Server-Sent Events (SSE) and native JavaScript `ReadableStream`.
* **Interactive File Management**: Drag-and-drop documents, manage files dynamically in a sidebar, and clear context easily.
* **Interactive CLI Mode**: Ask questions directly in the terminal using colored prompts.

---

## 🛠️ Tech Stack

* **Backend Framework**: [FastAPI](https://fastapi.tiangolo.com/) (running on [Uvicorn](https://www.uvicorn.org/))
* **AI Model & SDK**: [Google GenAI SDK](https://github.com/googleapis/google-genai-python) using `gemini-3.5-flash`
* **Parsing Tools**: `pypdf`, `python-docx`
* **Frontend**:
  * Semantic HTML5
  * FontAwesome 6 Icons
  * Vanilla CSS3 (custom glassmorphic dark theme, linear gradients, hover effects)
  * Vanilla JavaScript (Fetch stream reader, autoscrolling, markdown renderer)
* **Utilities**: `python-dotenv`, `colorama`

---

## 📂 Project Structure

```text
├── uploads/              # Directory for temporary file uploads (gitignored except .gitkeep)
├── static/               # Frontend single-page application assets
│   ├── index.html        # Main dashboard UI
│   ├── style.css         # Custom styling sheet (dark space glassmorphism theme)
│   └── app.js            # Frontend JavaScript controller (upload & stream handlers)
├── main.py               # Command-line interface (CLI) entrypoint
├── web_app.py            # FastAPI backend server application
├── requirements.txt      # Project Python dependencies
├── .env.template         # Template for environment configuration
└── .env                  # Local secrets and API keys (gitignored)
```

---

## 🚀 Installation & Setup

### Prerequisites
* Python 3.12+ installed
* A Gemini API key (obtain one from [Google AI Studio](https://aistudio.google.com/))

### 1. Clone & Navigate
```bash
git clone https://github.com/ThiriloseJonesNithish-R/RAG-App.git
cd RAG-App
```

### 2. Set Up Virtual Environment
Create a virtual environment and activate it:

* **Windows**:
  ```powershell
  python -m venv venv
  .\venv\Scripts\activate
  ```
* **macOS/Linux**:
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Secrets
Copy `.env.template` to a new `.env` file:
```bash
cp .env.template .env
```
Open the `.env` file and insert your Gemini API key:
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```

---

## 🏃 Running the Application

### Option A: Start the Web App (Recommended)
Launch the FastAPI development server:
```bash
python -m uvicorn web_app:app --port 8000 --reload
```
Once initialized, navigate to:
👉 **`http://localhost:8000`** in your browser.

*Drag and drop documents (`test_doc.txt`, etc.) in the left sidebar, and start typing your queries in the chat bar.*

### Option B: Start the CLI App
Launch the interactive console chat loop by specifying document paths:
```bash
python main.py test_doc.txt test_doc.docx
```
*Ask questions directly in your terminal, and type `exit` or `quit` to end the session.*

---

## 📝 License

This project is licensed under the **MIT License**. See the `LICENSE` file for more details.
