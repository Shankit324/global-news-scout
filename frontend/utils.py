import io, sys, datetime, os, threading
from google import genai
import requests
from dotenv import load_dotenv
import time, json, re
from gnews import GNews
import pathway as pw

# Load variables from .env into the system environment
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MODEL = "gemini-2.5-flash-lite"

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import news_connector, user_connector

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