import os, time, json, re, threading, sys, subprocess
import pathway as pw
from gnews import GNews
from pathway.xpacks.llm.embedders import SentenceTransformerEmbedder
from pathway.xpacks.llm.vector_store import VectorStoreServer
import sys
from dotenv import load_dotenv
from google import genai
import datetime, io
import requests

# Load variables from .env into the system environment
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MODEL = "gemini-2.5-flash-lite"

# CONNECTORS
class GlobalScoutSubject(pw.io.python.ConnectorSubject):
    def __init__(self):
        super().__init__()
        self.queries = ["Top Headlines 2026"]
        self.google_news = GNews(language='en', max_results=12)
        self.ingestion_count = 0
        self._lock = threading.Lock()

    def update_queries(self, raw_list):
        with self._lock:
            # SANITIZATION: Strict Alphanumeric filter to prevent GNews URL errors
            sanitized = []
            for q in raw_list:
                clean = re.sub(r'[^a-zA-Z0-9\s]', '', str(q)).strip()
                if clean and 3 < len(clean) < 60:
                    sanitized.append(clean)
            self.queries = sanitized if sanitized else ["Latest News"]
            print(f"\n[SYSTEM UPDATE]: Tracking {len(self.queries)} refined streams...")

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
                        sys.stdout.write(f"\rScout Cache: {self.ingestion_count} articles vector-indexed... ")
                        sys.stdout.flush()
                except: continue
            time.sleep(45)

class UserMemorySubject(pw.io.python.ConnectorSubject):
    """
    A custom connector that acts as an open 'Inbox' for JSON data.
    It stays alive and waits for the user to inject data via `add_data()`.
    """
    def __init__(self):
        super().__init__()
        self.pending_payloads = []
        self._lock = threading.Lock()
        self.history_log = [] # Just for user visibility

    def inject(self, json_data):
        """User-facing method to add data"""
        with self._lock:
            # Add metadata if missing
            if 'id' not in json_data:
                json_data['id'] = f"mem_{int(time.time()*1000)}"

            self.pending_payloads.append(json_data)
            self.history_log.append(json_data)
            print(f"[MEMORY]: Buffered '{json_data.get('title', 'Unknown')}'")

    def run(self):
        while True:
            with self._lock:
                if self.pending_payloads:
                    for item in self.pending_payloads:
                        # Push to Pathway
                        self.next(
                            data=json.dumps(item), # Send as raw JSON string
                            key=str(item['id']),
                            ingested_at=float(time.time())
                        )
                    self.pending_payloads.clear()
            time.sleep(0.5) # Fast polling for real-time feel

# THE PATHWAY PIPELINE
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

# NEWS STREAM
raw_news = pw.io.python.read(news_connector, schema=NewsSchema, primary_key=["url"])
fresh_news = raw_news.filter(pw.this.ingested_at > (time.time() - 86400)) # 24h Window
processed_news = fresh_news.select(data=pw.this.data, _metadata=pw.apply(lambda u: {"url": u}, pw.this.url))

# USER MEMORY STREAM
# Helper to make JSON readable for the Embedder
def format_json_for_llm(json_str):
    try:
        obj = json.loads(json_str)
        # Convert {"title": "X", "fact": "Y"} -> "Title: X. Fact: Y"
        return "USER MEMORY:\n" + "\n".join([f"{k.capitalize()}: {v}" for k,v in obj.items()])
    except: return json_str

raw_user = pw.io.python.read(user_connector, schema=UserSchema, primary_key=["key"])
processed_user = raw_user.select(
    data=pw.apply(format_json_for_llm, pw.this.data),
    _metadata=pw.apply(lambda k: {"source": "User_JSON", "id": k}, pw.this.key)
)

# Port Cleanup
PORT_NEWS = 8000
PORT_USER = 8001

# Clean up ports to prevent "Address already in use" errors
print("🧹 Cleaning ports...")
for port in [PORT_NEWS, PORT_USER]:
    try: subprocess.run(["fuser", "-k", f"{port}/tcp"], stderr=subprocess.DEVNULL)
    except: pass

# Server A (News)
embedder = SentenceTransformerEmbedder(model="all-MiniLM-L6-v2")
vector_store = VectorStoreServer(processed_news, embedder=embedder)
threading.Thread(target=lambda: vector_store.run_server(host="0.0.0.0", port=8000), daemon=True).start()

# Server B (User)
vs_user = VectorStoreServer(processed_user, embedder=embedder)
t_user = threading.Thread(target=lambda: vs_user.run_server(host="0.0.0.0", port=PORT_USER), daemon=True)
t_user.start()

print(f"SYSTEMS ONLINE:")
print(f"   GNews Scout   -> http://0.0.0.0:{PORT_NEWS}")
print(f"   User Memory   -> http://0.0.0.0:{PORT_USER} (Ready for JSON)")

# THE REFINED ANALYST
def run_scout_analyst(user_prompt):
    print(f"\nANALYZING: {user_prompt.upper()}")
    client = genai.Client(api_key=GEMINI_API_KEY)

    try:
        # JSON-Enforced Query Generation
        q_gen = client.models.generate_content(
            model=MODEL,
            contents=f"Generate 5 precise news search keywords for: {user_prompt}. "
                     "Return ONLY a valid JSON list of strings. Do not explain."
        )

        # Clean potential markdown from Gemini
        clean_text = re.sub(r'```json|```', '', q_gen.text).strip()
        keywords = json.loads(clean_text)

        initial_count = news_connector.ingestion_count
        news_connector.update_queries(keywords)

        # The "Warm-Up" Wait (Wait for Ingestion Progress)
        print("⏳ Hydrating Stream (Scraping & Indexing)...")
        max_wait = 45
        start_wait = time.time()
        while (news_connector.ingestion_count - initial_count) < 6:
            if (time.time() - start_wait) > max_wait:
                print("\nIngestion timeout. Proceeding with existing data.")
                break
            time.sleep(3)

        # Final buffer for Vector Store to process the incoming strings
        time.sleep(5)

        # Precision Retrieval
        r = requests.post("http://0.0.0.0:8000/v1/retrieve", json={"query": user_prompt, "k": 10})
        results = r.json()

        # Entity-Aware Filtering
        local_threshold = 0.52 if len(user_prompt.split()) < 3 else 0.58
        valid = [res for res in results if (1 - res.get('dist', 1.0)) > local_threshold]

        if not valid:
            print(f"DATA GAP: No matching intel found for '{user_prompt}' in the last 24h.")
            return

        context = "\n".join([v['text'] for v in valid])
        unique_links = list({v['metadata']['url']: v for v in valid}.keys())[:3]

        # Final Report
        analyst_prompt = f"Using this news context:\n{context}\n\n" \
                         f"Analyze '{user_prompt}' as a 2026 event. Format with Sentiment, Hot Points, and Summary."
        report = client.models.generate_content(model=MODEL, contents=analyst_prompt)

        print("\n" + "═"*70 + "\n" + report.text.strip() + "\n" + "═"*70)
        print("VERIFIED SOURCES:")
        for link in unique_links: print(f"  *** {link}")

    except Exception as e:
        print(f"System Error: {e}")

# Run
# run_scout_analyst("what are new vs old tax regime in Indian tax systme ?")

# USER INTERFACE FUNCTIONS
def inject_memory(title, content, category="General"):
    """
    Simple function for you to add data in real-time.
    """
    payload = {
        "title": title,
        "content": content,
        "category": category,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    user_connector.inject(payload)

def ask_oracle(query):
    """
    Intelligent Query Router: Checks User Memory first, then News.
    """
    client = genai.Client(api_key=GEMINI_API_KEY)
    print(f"\nQUERY: '{query}'")

    # Check User Memory (Port 8001)
    try:
        r = requests.post(f"http://0.0.0.0:{PORT_USER}/v1/retrieve", json={"query": query, "k": 2})
        user_hits = r.json()
    except: user_hits = []

    # Check News (Port 8000)
    try:
        r = requests.post(f"http://0.0.0.0:{PORT_NEWS}/v1/retrieve", json={"query": query, "k": 3})
        news_hits = r.json()
    except: news_hits = []

    # Combine Context
    context = ""
    if user_hits:
        context += "--- INTERNAL MEMORY (High Priority) ---\n"
        context += "\n".join([h['text'] for h in user_hits if h['dist'] < 0.6]) # Strict filter

    if news_hits:
        context += "\n--- EXTERNAL NEWS ---\n"
        context += "\n".join([h['text'] for h in news_hits])

    if not context:
        print("   No relevant data found in Memory or News.")
        return

    # 4. Generate Answer
    prompt = f"Answer based ONLY on the context below.\n\nCONTEXT:\n{context}\n\nQUESTION: {query}"
    resp = client.models.generate_content(model=MODEL, contents=prompt)

    print("-" * 50)
    print(f"ANSWER: {resp.text.strip()}")
    print("-" * 50)

# Capture printed output from backend funcs
def capture_output(fn, *args, **kwargs):
    buffer = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buffer
    try:
        fn(*args, **kwargs)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        sys.stdout = old_stdout
    return buffer.getvalue()


# MAIN QUERY HANDLER
def handle_query(question, query_type):
    """
    This function is called when user clicks 'Ask'.
    It routes queries to the correct backend logic.
    """

    if not question.strip():
        return "Please enter a question."

    # Timestamp for demo clarity
    header = f"Query Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    header += f"Query Type: {query_type}\n\n"

    # Fact / Memory Query: For checking whether our model working or not by injecting data in JSON format
    if query_type == "Fact / Memory Query":
      output = capture_output(ask_oracle, question)
    else:
      # Actual NEWS query (Integrated with GNEWS)
      output = capture_output(run_scout_analyst, question)

    return header + output

# DATA INJECTION HANDLER (liveness proof)
def handle_injection(title, content, category):
    """
    Injects new data into the live system.
    This proves real-time update without restart.
    """

    if not title or not content:
        return "Title and content are required."

    inject_memory(title, content, category)

    return f"Injected '{title}' into live memory at {time.strftime('%H:%M:%S')}"
