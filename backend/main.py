import os, time, json, re, threading, sys, subprocess
import pathway as pw
from gnews import GNews
from pathway.xpacks.llm.embedders import SentenceTransformerEmbedder
from pathway.xpacks.llm.vector_store import VectorStoreServer
from dotenv import load_dotenv
from google import genai
import datetime, io
import requests

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MODEL = "gemini-2.5-flash-lite"

# --- CONNECTORS ---

class GlobalScoutSubject(pw.io.python.ConnectorSubject):
    def __init__(self):
        super().__init__()
        self.queries = ["Top Headlines 2026"]
        self.google_news = GNews(language='en', max_results=12)
        self.ingestion_count = 0
        self._lock = threading.Lock()

    def update_queries(self, raw_list):
        with self._lock:
            sanitized = []
            for q in raw_list:
                clean = re.sub(r'[^a-zA-Z0-9\s]', '', str(q)).strip()
                if clean and 3 < len(clean) < 60:
                    sanitized.append(clean)
            self.queries = sanitized if sanitized else ["Latest News"]
            print(f"\n[SYSTEM]: Tracking {len(self.queries)} refined streams...")

    def run(self):
        while True:
            with self._lock:
                active_qs = list(self.queries)
            for q in active_qs:
                try:
                    news = self.google_news.get_news(q)
                    for item in news:
                        self.next(
                            data=f"NEWS: {item['title']} | SUMMARY: {item['description']}",
                            url=item['url'],
                            ingested_at=float(time.time())
                        )
                        self.ingestion_count += 1
                except: continue
            time.sleep(60) # Increased to 60s for Cloud Stability

class UserMemorySubject(pw.io.python.ConnectorSubject):
    def __init__(self):
        super().__init__()
        self.pending_payloads = []
        self._lock = threading.Lock()

    def inject(self, json_data):
        with self._lock:
            if 'id' not in json_data:
                json_data['id'] = f"mem_{int(time.time()*1000)}"
            self.pending_payloads.append(json_data)
            print(f"[MEMORY]: Buffered '{json_data.get('title', 'Unknown')}'")

    def run(self):
        while True:
            with self._lock:
                if self.pending_payloads:
                    for item in self.pending_payloads:
                        self.next(
                            data=json.dumps(item),
                            key=str(item['id']),
                            ingested_at=float(time.time())
                        )
                    self.pending_payloads.clear()
            time.sleep(0.5)

# --- PATHWAY PIPELINE SETUP ---

news_connector = GlobalScoutSubject()
user_connector = UserMemorySubject()

class NewsSchema(pw.Schema):
    data: str
    url: str
    ingested_at: float

class UserSchema(pw.Schema):
    data: str
    key: str
    ingested_at: float

# STREAM: News
raw_news = pw.io.python.read(news_connector, schema=NewsSchema, primary_key=["url"])
processed_news = raw_news.filter(pw.this.ingested_at > (time.time() - 86400)).select(
    data=pw.this.data, 
    _metadata=pw.apply(lambda u: {"url": u}, pw.this.url)
)

# STREAM: User Memory
def format_json_for_llm(json_str):
    try:
        obj = json.loads(json_str)
        return "USER MEMORY:\n" + "\n".join([f"{k.capitalize()}: {v}" for k,v in obj.items()])
    except: return json_str

raw_user = pw.io.python.read(user_connector, schema=UserSchema, primary_key=["key"])
processed_user = raw_user.select(
    data=pw.apply(format_json_for_llm, pw.this.data),
    _metadata=pw.apply(lambda k: {"source": "User_JSON", "id": k}, pw.this.key)
)

# --- VECTOR SERVERS ---

PORT_NEWS = 8000
PORT_USER = 8001

# Embedder initialization (Ensure this matches the pre-loaded model in Dockerfile)
embedder = SentenceTransformerEmbedder(model="all-MiniLM-L6-v2")

def start_vector_servers():
    # News Server
    vector_store = VectorStoreServer(processed_news, embedder=embedder)
    threading.Thread(target=lambda: vector_store.run_server(host="0.0.0.0", port=PORT_NEWS), daemon=True).start()
    threading.Thread(target=news_connector.run, daemon=True).start()

    # User Memory Server
    vs_user = VectorStoreServer(processed_user, embedder=embedder)
    threading.Thread(target=lambda: vs_user.run_server(host="0.0.0.0", port=PORT_USER), daemon=True).start()
    threading.Thread(target=user_connector.run, daemon=True).start()
    
    print(f"PATHWAY SERVERS: Internal ports {PORT_NEWS} and {PORT_USER} are online.")

# Start servers on module load
start_vector_servers()

# --- ANALYST LOGIC ---

def run_scout_analyst(user_prompt):
    client = genai.Client(api_key=GEMINI_API_KEY)
    try:
        q_gen = client.models.generate_content(
            model=MODEL,
            contents=f"Generate 5 precise news search keywords for: {user_prompt}. Return ONLY a valid JSON list of strings."
        )
        clean_text = re.sub(r'```json|```', '', q_gen.text).strip()
        keywords = json.loads(clean_text)
        
        initial_count = news_connector.ingestion_count
        news_connector.update_queries(keywords)

        print("⏳ Hydrating Live Stream...")
        time.sleep(15) # Wait for initial scrape

        r = requests.post(f"http://127.0.0.1:{PORT_NEWS}/v1/retrieve", json={"query": user_prompt, "k": 10})
        results = r.json()

        valid = [res for res in results if (1 - res.get('dist', 1.0)) > 0.55]
        if not valid:
            print(f"DATA GAP: No fresh news found for '{user_prompt}'.")
            return

        context = "\n".join([v['text'] for v in valid])
        unique_links = list({v['metadata']['url']: v for v in valid}.keys())[:3]

        # Final Report
        analyst_prompt = f"Using this news context:\n{context}\n\n" \
                         f"Analyze '{user_prompt}' as a 2026 event. Format with Sentiment, Hot Points, and Summary."
        report = client.models.generate_content(model=MODEL, contents=analyst_prompt)

        print(f"\n{report.text.strip()}\n")
        print("VERIFIED SOURCES:")
        for link in unique_links: print(f"  - {link}")

    except Exception as e:
        print(f"Analyst Error: {e}")

def ask_oracle(query):
    client = genai.Client(api_key=GEMINI_API_KEY)
    context = ""
    
    # Internal Memory Check
    try:
        r_u = requests.post(f"http://127.0.0.1:{PORT_USER}/v1/retrieve", json={"query": query, "k": 2})
        user_hits = r_u.json()
        context += "--- MEMORY ---\n" + "\n".join([h['text'] for h in user_hits if h['dist'] < 0.6])
    except: pass

    # News Check
    try:
        r_n = requests.post(f"http://127.0.0.1:{PORT_NEWS}/v1/retrieve", json={"query": query, "k": 3})
        news_hits = r_n.json()
        context += "\n--- NEWS ---\n" + "\n".join([h['text'] for h in news_hits])
    except: pass

    if not context.strip():
        print("No information found.")
        return

    prompt = f"Answer based on context:\n{context}\n\nQUESTION: {query}"
    resp = client.models.generate_content(model=MODEL, contents=prompt)
    print(f"\n{resp.text.strip()}")

def handle_query(question, query_type):
    # This wrapper is for Gradio consumption
    buffer = io.StringIO()
    sys.stdout = buffer
    
    if query_type == "Fact / Memory Query":
        ask_oracle(question)
    else:
        run_scout_analyst(question)
    
    sys.stdout = sys.__stdout__
    return buffer.getvalue()

def handle_injection(title, content, category):
    payload = {"title": title, "content": content, "category": category, "time": time.ctime()}
    user_connector.inject(payload)
    return f"Success: '{title}' injected into live memory."