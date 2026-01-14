import os, time, json, re, threading, sys, subprocess
import pathway as pw
from gnews import GNews
from pathway.xpacks.llm.embedders import SentenceTransformerEmbedder
from pathway.xpacks.llm.vector_store import VectorStoreServer
import sys
from dotenv import load_dotenv

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