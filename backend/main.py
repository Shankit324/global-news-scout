import os, time, json, re, threading, sys, io, requests
import pathway as pw
from gnews import GNews
from pathway.xpacks.llm.embedders import SentenceTransformerEmbedder
from pathway.xpacks.llm.vector_store import VectorStoreServer
from dotenv import load_dotenv
from google import genai
from contextlib import redirect_stdout

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MODEL = "gemini-2.5-flash-lite"

# Global Heartbeat Log
system_heartbeat = "Intelligence Engine Initializing...\n"

# --- CONNECTORS ---

class GlobalScoutSubject(pw.io.python.ConnectorSubject):
    def __init__(self):
        super().__init__()
        self.google_news = GNews(language='en', max_results=20)
        self.queries = ["Top Highlights"]
        self.ingestion_count = 0
        self.seen_urls = set()
        self._lock = threading.Lock()

    def update_queries(self, raw_list):
        global system_heartbeat
        with self._lock:
            sanitized = []
            for q in raw_list:
                clean = re.sub(r'[^a-zA-Z0-9\s]', '', str(q)).strip()
                if clean and 3 < len(clean) < 60:
                    sanitized.append(clean)
            self.queries = sanitized if sanitized else ["Latest News"]
            msg = f"\n[SYSTEM]: Tracking {len(self.queries)} refined streams...\n"
            system_heartbeat += msg

    def run(self):
        global system_heartbeat
        while True:
            with self._lock:
                active_qs = list(self.queries)
            
            all_news = []
            try:
                # Always grab top stories first for global context
                all_news.extend(self.google_news.get_top_news())
            except: pass

            for q in active_qs:
                try:
                    all_news.extend(self.google_news.get_news(q))
                except: continue
            
            for item in all_news:
                url = item.get('url')
                if url in self.seen_urls: continue
                
                try:
                    self.next(
                        data=f"NEWS: {item['title']} | SUMMARY: {item['description']}",
                        url=url,
                        ingested_at=float(time.time())
                    )
                    self.ingestion_count += 1
                    self.seen_urls.add(url)
                    system_heartbeat = (system_heartbeat + f"Ingested: {item['title'][:55]}...\n")[-2000:]
                except: continue

            if len(self.seen_urls) > 1000: self.seen_urls.clear()
            time.sleep(60)

class UserMemorySubject(pw.io.python.ConnectorSubject):
    def __init__(self):
        super().__init__()
        self.pending_payloads = []
        self._lock = threading.Lock()

    def inject(self, json_data):
        with self._lock:
            json_data['id'] = json_data.get('id', f"mem_{int(time.time()*1000)}")
            self.pending_payloads.append(json_data)

    def run(self):
        while True:
            with self._lock:
                if self.pending_payloads:
                    for item in self.pending_payloads:
                        self.next(data=json.dumps(item), key=str(item['id']), ingested_at=float(time.time()))
                    self.pending_payloads.clear()
            time.sleep(0.5)

# --- PATHWAY PIPELINE ---

news_connector = GlobalScoutSubject()
user_connector = UserMemorySubject()

class NewsSchema(pw.Schema):
    data: str; url: str; ingested_at: float

class UserSchema(pw.Schema):
    data: str; key: str; ingested_at: float

# the system will retain all discovered news in the vector index.
raw_news = pw.io.python.read(news_connector, schema=NewsSchema, primary_key=["url"])
processed_news = raw_news.select(
    data=pw.this.data, 
    _metadata=pw.apply(lambda u, t: {"url": u, "ingested_at": t}, pw.this.url, pw.this.ingested_at)
)

raw_user = pw.io.python.read(user_connector, schema=UserSchema, primary_key=["key"])
processed_user = raw_user.select(
    data=pw.apply(lambda d: d, pw.this.data),
    _metadata=pw.apply(lambda k: {"source": "User_JSON", "id": k}, pw.this.key)
)

# --- ENGINE ---

PORT_NEWS, PORT_USER = 8000, 8001
embedder = SentenceTransformerEmbedder(model="all-MiniLM-L6-v2")

def start_backend_engine():
    vs_news = VectorStoreServer(processed_news, embedder=embedder)
    threading.Thread(target=lambda: vs_news.run_server(host="0.0.0.0", port=PORT_NEWS), daemon=True).start()
    vs_user = VectorStoreServer(processed_user, embedder=embedder)
    threading.Thread(target=lambda: vs_user.run_server(host="0.0.0.0", port=PORT_USER), daemon=True).start()
    threading.Thread(target=news_connector.run, daemon=True).start()
    threading.Thread(target=user_connector.run, daemon=True).start()
    print(f"Intelligence Engine Active on Ports {PORT_NEWS}/{PORT_USER}")

if "ENGINE_LIVE" not in os.environ:
    start_backend_engine()
    os.environ["ENGINE_LIVE"] = "true"

# --- ANALYST LOGIC ---

def run_scout_analyst(user_prompt):
    client = genai.Client(api_key=GEMINI_API_KEY)
    try:
        q_gen = client.models.generate_content(
            model=MODEL,
            contents=f"Generate 5 precise news keywords for: {user_prompt}. Return ONLY a valid JSON list of strings."
        )
        keywords = json.loads(re.sub(r'```json|```', '', q_gen.text).strip())
        
        start_count = news_connector.ingestion_count
        news_connector.update_queries(keywords)

        print("Synchronizing intelligence streams...")
        max_wait, elapsed = 60, 0
        while news_connector.ingestion_count <= start_count + 3 and elapsed < max_wait:
            time.sleep(2); elapsed += 2
        
        time.sleep(3) 

        r = requests.post(f"http://127.0.0.1:{PORT_NEWS}/v1/retrieve", json={"query": user_prompt, "k": 30})
        results = r.json()

        now = time.time()
        scored_results = []
        for res in results:
            semantic_sim = 1 - res.get('dist', 1.0)
            
            # --- GATE 1: THE RELEVANCE FLOOR ---
            # Even for old news, it must be at least 30% related to be considered.
            if semantic_sim < 0.30: continue 

            # --- GATE 2: RECENCY DECAY ---
            t_stamp = res.get('metadata', {}).get('ingested_at', now)
            age_hours = (now - t_stamp) / 3600
            
            # Recency bias: Priority drops but never goes to zero.
            # News from a year ago will have a multiplier around 0.1, 
            # while news from today stays near 1.0.
            recency_multiplier = max(0.1, 1 / (1 + (age_hours / 24))) 
            
            final_score = semantic_sim * recency_multiplier
            scored_results.append((final_score, res))

        # Re-sort: Current + Relevant news will naturally rise to the top.
        scored_results.sort(key=lambda x: x[0], reverse=True)
        valid = [item[1] for item in scored_results]

        if not valid:
            print(f"DATA GAP: No relevant news found for '{user_prompt}'.")
            return

        context = "\n".join([v['text'] for v in valid[:15]])
        unique_links = list({v['metadata']['url']: v for v in valid}.keys())[:3]

        report = client.models.generate_content(
            model=MODEL, 
            contents=f"Context:\n{context}\n\nAnalyze '{user_prompt}' with Sentiment, 3 hotpoints and a brief Summary."
        )

        print(f"\n{report.text.strip()}\n")
        print("VERIFIED SOURCES (PRIORITIZED BY RECENCY AND RELEVANCE):")
        for link in unique_links: print(f"  - {link}")

    except Exception as e: print(f"System Error: {e}")

def ask_oracle(query):
    client = genai.Client(api_key=GEMINI_API_KEY)
    context = ""
    try:
        r_u = requests.post(f"http://127.0.0.1:{PORT_USER}/v1/retrieve", json={"query": query, "k": 3})
        context += "--- MEMORY ---\n" + "\n".join([h['text'] for h in r_u.json() if h['dist'] < 0.6])
    except: pass
    try:
        r_n = requests.post(f"http://127.0.0.1:{PORT_NEWS}/v1/retrieve", json={"query": query, "k": 5})
        context += "\n--- NEWS ---\n" + "\n".join([h['text'] for h in r_n.json()])
    except: pass
    if not context.strip():
        print("No matching information found.")
        return
    resp = client.models.generate_content(model=MODEL, contents=f"Answer based on:\n{context}\n\nQ: {query}")
    print(f"\n{resp.text.strip()}")

def handle_query(question, query_type):
    f = io.StringIO()
    with redirect_stdout(f):
        if query_type == "Fact / Memory Query": ask_oracle(question)
        else: run_scout_analyst(question)
    return f.getvalue()

def handle_injection(title, content, category):
    payload = {"title": title, "content": content, "category": category, "time": time.ctime()}
    user_connector.inject(payload)
    return f"Success: '{title}' injected."

def get_heartbeat(): return system_heartbeat
