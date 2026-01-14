import gradio as gr
import pathway as pw
# Ensure utils.py exists in the same directory or is in your PYTHONPATH
from utils import handle_query, handle_injection 

# --- CUSTOM THEME & CSS ---
CUSTOM_CSS = """
/* Deep Cyber-Noir Base */
body {
    background-color: #050505;
    background-image: 
        radial-gradient(circle at 20% 30%, rgba(220, 38, 38, 0.05) 0%, transparent 50%),
        radial-gradient(circle at 80% 70%, rgba(37, 99, 235, 0.05) 0%, transparent 50%);
    color: #e2e8f0;
    font-family: 'JetBrains Mono', 'Inter', -apple-system, sans-serif;
    margin: 0 !important;
    padding: 0 !important;
    overflow-x: hidden; /* Prevent horizontal scrollbars */
}

/* --- CRITICAL: FULL WIDTH OVERRIDES --- */
.gradio-container {
    max-width: 100% !important; /* Force full width */
    width: 100% !important;
    margin: 0 !important;
    padding: 20px !important; /* Minimal padding */
    min-height: 100vh !important;
    display: flex;
    flex-direction: column;
}

/* Remove internal restrictions often found in Gradio themes */
.gradio-container > .main, 
.gradio-container > .main > .wrap {
    width: 100% !important;
    max-width: 100% !important;
}

/* Glassmorphism Logic */
.gradio-container {
    background: rgba(15, 15, 15, 0.8) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: none !important;
}

/* Component Styling */
.block {
    border-radius: 8px !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    background: rgba(20, 20, 20, 0.4) !important;
}

textarea, input, .gradio-dropdown {
    background-color: rgba(0, 0, 0, 0.6) !important;
    border: 1px solid #333 !important;
    color: #f8fafc !important;
}

h1 {
    font-weight: 800 !important;
    text-transform: uppercase;
    letter-spacing: 2px;
    background: linear-gradient(90deg, #ffffff 0%, #dc2626 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0 !important;
}

/* --- OUTPUT BOX STYLING --- */
#answer_box textarea {
    background: #000000 !important;
    color: #00ff41 !important; /* Matrix/Terminal Green for contrast */
    border-left: 2px solid #dc2626 !important;
    font-family: 'Fira Code', 'Consolas', monospace !important;
    font-size: 14px !important;
    line-height: 1.6 !important;
    box-shadow: inset 0 0 20px rgba(0,0,0,0.9);
}

button.primary {
    background: #dc2626 !important;
    border: 1px solid #991b1b !important;
    color: white !important;
    text-transform: uppercase;
    font-weight: bold !important;
    transition: all 0.3s ease;
}

button.primary:hover {
    background: #ef4444 !important;
    box-shadow: 0 0 15px rgba(220, 38, 38, 0.6);
}

footer { display: none !important; }
"""

# --- UI LAYOUT ---
# fill_width=True ensures the blocks expand to the edges of the browser
with gr.Blocks(
    theme=gr.themes.Default(),
    css=CUSTOM_CSS,
    title="Global News Scout Console",
    fill_width=True, 
    fill_height=True
) as demo:

    # Header Section
    with gr.Row():
        gr.Markdown("""
        # 🛰️ Global News Scout: Intelligence Console
        **Real-time Pathway RAG Pipeline | 2026 Predictive Analysis**
        """)

    # Main Content Row
    # We use equal_height=True to ensure both columns stretch to match the tallest element
    with gr.Row(equal_height=True):
        
        # --- LEFT COLUMN (25%) ---
        # Scale 1 represents 1 part of the total (1+3 = 4 parts) -> 25%
        with gr.Column(scale=1, min_width=300):
            with gr.Group():
                gr.Markdown("### 📡 Uplink Control")
                question_box = gr.Textbox(
                    label="Intelligence Query",
                    placeholder="Enter keywords or specific questions...",
                    lines=4
                )
                
                query_type = gr.Dropdown(
                    label="Routing Protocol",
                    choices=["Fact / Memory Query", "Live Intelligence Analysis"],
                    value="Fact / Memory Query",
                    interactive=True
                )
                
                ask_btn = gr.Button("INITIALIZE SEARCH", variant="primary")

            gr.Markdown("---")
            
            # Injection Section
            with gr.Group():
                gr.Markdown("### 💉 Neural Injection")
                inject_title = gr.Textbox(label="Identifier (Title)")
                inject_content = gr.Textbox(label="Payload (Content)", lines=3)
                inject_category = gr.Textbox(label="Category")
                inject_btn = gr.Button("EXECUTE INJECTION")
            
            inject_status = gr.Textbox(label="Stream Status", interactive=False)
            
            # Footer info moved to left sidebar to save vertical space
            gr.Markdown("""
            <div style="font-size: 0.8em; opacity: 0.6; margin-top: 20px;">
            **System Status:**<br>
            Pathway Stream: ACTIVE<br>
            Vector Store: SYNCED
            </div>
            """)

        # --- RIGHT COLUMN (75%) ---
        # Scale 3 represents 3 parts of the total (1+3 = 4 parts) -> 75%
        with gr.Column(scale=3, min_width=600):
            answer_box = gr.Textbox(
                label="Intelligence Report Output",
                lines=35, # Increased lines to fill vertical space
                interactive=False,
                elem_id="answer_box",
                autoscroll=True
            )

    # Event Wiring
    ask_btn.click(
        fn=handle_query,
        inputs=[question_box, query_type],
        outputs=answer_box
    )

    inject_btn.click(
        fn=handle_injection,
        inputs=[inject_title, inject_content, inject_category],
        outputs=inject_status
    )

# Launch with full width allowed
demo.launch(
    server_name="0.0.0.0", 
    server_port=7860, 
    share=True,
    inbrowser=True
)