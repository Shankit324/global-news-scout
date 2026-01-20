# Global News Scout: Real-Time Intelligence & RAG System
**Live Demo:** [https://global-news-scout.onrender.com](https://huggingface.co/spaces/Shankit324/global-news-scout)

**Global News** Scout is a high-performance, real-time Retrieval-Augmented Generation (RAG) system built with **Pathway**, **Google Gemini**, and **Gradio**. It monitors live news streams and combines them with a persistent User Memory to provide context-aware intelligence on current events.

Unlike traditional RAG systems that rely on static databases, this project uses live data streams that update the vector index in real-time without requiring system restarts.

---

## System Architecture


The project is split into a modular backend and frontend to ensure scalability and ease of maintenance:

* **Pathway Pipeline**: Orchestrates real-time data ingestion from GNews and manual user inputs, performing live embedding and indexing using the `SentenceTransformerEmbedder`. 
* **Dual Vector Servers**: 
    * **Port 8000**: Dedicated to the **GNews Scout** stream. 
    * **Port 8001**: Dedicated to **User Memory** and internal data injections. 
* **AI Engine**: Utilizes `gemini-2.5-flash-lite` to generate search keywords and synthesize final analytical reports. 
* **Frontend**: A Gradio-based interface for querying the system and injecting "secret" knowledge into the live index. 

---

## File Structure

```plaintext
global-news-scout/
├── .env               # Environment variables (API Keys)
├── .venv/             # Python virtual environment
├── backend/
│   ├── __init__.py
│   └── main.py        # Pathway logic 
├── frontend/
│   ├── __init__.py
│   └── main.py         # Gradio interface
├── Docekerfile
├── .dockerignore
├── .gitignore
├── requirements.txt    # Project dependencies            
└── README.md           # Project documentation
```

---

## Installation

### 1. Prerequisites
* **Python 3.12 or 3.13** 
* **Google Gemini API Key**
* **Homebrew** (for macOS users)

### 2. macOS System Dependencies
Since this project uses `pyarrow` and `pathway`, macOS users on Apple Silicon (M1/M2/M3) must install the following:
```bash
brew install apache-arrow cmake pkg-config rust
```

### 3. Clone and Setup
```bash
# Clone the repository
git clone [https://github.com/yourusername/global-news-scout.git](https://github.com/yourusername/global-news-scout.git)
cd global-news-scout

# Deactivate and remove any existing .venv
deactivate 2>/dev/null
rm -rf .venv

# Create and activate virtual environment
python3.12 -m venv .venv
source .venv/bin/activate
python3.12 -m pip install --upgrade pip

python3.12 -m pip install -U "pathway[xpack-llm, xpack-llm-docs]" litellm nest_asyncio

# SPECIAL STEP FOR PYTHON 3.14+:
# Install nightly wheels to bypass C++ compilation errors in standard pyarrow
python3.12 -m pip install --extra-index-url [https://pypi.anaconda.org/scientific-python-nightly-wheels/simple](https://pypi.anaconda.org/scientific-python-nightly-wheels/simple) pyarrow

# Install remaining dependencies
python3.12 -m pip install -r requirements.txt
```

### 4. Configure Environment
Create a `.env` file in the root directory:

```plaintext
GEMINI_API_KEY=your_actual_api_key_here
PORT=7860
```

---

## Running the Project

1. **Clean Ports:** The system automatically attempts to clear ports `8000` and `8001` to prevent conflicts.
2. **Execution:** To run the program, execute the following command on terminal:
```bash
pyrhon3.12 ./frontend/main.py
```

**Local Endpoints:**
1. Pathway News Stream: `http://localhost:8000`
2. User Memory Stream: `http://localhost:8001`
3. Gradio UI: `http://localhost:7860`

---

## Key Features

### Real-Time Knowledge Injection (Liveness Testing)

1. **Liveness Proof:** Users can inject custom JSON data (Title, Content, Category) into the live pipeline via the `UserMemorySubject`.
2. **Instant Update:** The data is vectorized immediately and becomes available for the **Fact / Memory Query** route without a system reboot.
3. **Verification:** This feature allows users to verify that the RAG knowledge base is updating dynamically in real-time.

### GNews Intelligence Analyst

1. **Dynamic Tracking:** The system prompts Gemini to convert a single user topic into **5 precise search keywords**, ensuring diverse and comprehensive news coverage.
2. **Automated Scraping:** The `GlobalScoutSubject` runs a cycle every **60 seconds**, scraping Google News, deduplicating URLs, and injecting new vector embeddings in real-time.
3. **Recency Ranking:** Articles are ranked using a custom **Recency Decay Formula** that prioritizes breaking news (0–24h) while still retaining high-relevance historical context: <br>
   $$Score_{final} = Similarity \times \frac{1}{1 + \left( \frac{Age_{hours}}{24} \right)}$$

### Intelligent Query Routing

1. **Routing Logic:** The system routes questions based on intent. It checks **Internal Memory (Port 8001)** for specific user-injected facts first, then leverages **External News (Port 8000)** for broader context.

---

## Technologies Used

| Category | Technology |
| :--- | :--- |
| **Stream Processing** | [Pathway](https://www.pathway.com/) |
| **LLM Engine** | Google Gemini 2.5 Flash Lite |
| **API Framework** | FastAPI (via Pathway VectorStore) |
| **Vector Store** | Pathway VectorStoreServer |
| **Embeddings** | Sentence-Transformers (`all-MiniLM-L6-v2`) |
| **UI** | Gradio |

---

## Troubleshooting

1. **ModuleNotFoundError (Gradio):** This usually happens if pyarrow failed to build. Ensure apache-arrow is installed via brew and re-run installation.
2. **Port Conflicts:** If ports are stuck, run the following command in your terminal:
```bash
lsof -ti:8000,8001,7860 | xargs kill -9
```
