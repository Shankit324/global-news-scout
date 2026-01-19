import gradio as gr
import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import handle_query, handle_injection, get_heartbeat

# --- CUSTOM THEME & CSS ---
CUSTOM_CSS = """
body {
    background-color: #050505;
    background-image: 
        radial-gradient(circle at 20% 30%, rgba(220, 38, 38, 0.05) 0%, transparent 50%),
        radial-gradient(circle at 80% 70%, rgba(37, 99, 235, 0.05) 0%, transparent 50%);
    color: #e2e8f0;
    font-family: 'JetBrains Mono', 'Inter', sans-serif;
}
.gradio-container {
    max-width: 100% !important;
    background: rgba(15, 15, 15, 0.8) !important;
    backdrop-filter: blur(12px) !important;
}
#answer_box textarea {
    color: #00ff41 !important;
    font-family: 'Fira Code', monospace !important;
}
button.primary {
    background: #dc2626 !important;
}
footer { display: none !important; }
"""

# --- UI LAYOUT ---
with gr.Blocks(title="Global News Scout Console", fill_width=True) as demo:

    with gr.Row():
        gr.Markdown("# 🛰️ Global News Scout: Intelligence Console")

    with gr.Row(equal_height=True):
        with gr.Column(scale=1, min_width=300):
            with gr.Group():
                gr.Markdown("### Uplink Control")
                question_box = gr.Textbox(label="Intelligence Query", lines=4)
                query_type = gr.Dropdown(
                    label="Routing Protocol",
                    choices=["Fact / Memory Query", "Live Intelligence Analysis"],
                    value="Live Intelligence Analysis"
                )
                ask_btn = gr.Button("INITIALIZE SEARCH", variant="primary")

            gr.Markdown("--- ### Neural Injection")
            inject_title = gr.Textbox(label="Identifier (Title)")
            inject_content = gr.Textbox(label="Payload (Content)", lines=3)
            inject_category = gr.Textbox(label="Category")
            inject_btn = gr.Button("EXECUTE INJECTION")
            inject_status = gr.Textbox(label="Injection Status", interactive=False)

            gr.Markdown("--- ### System Heartbeat")
            heartbeat_box = gr.Textbox(label="Live Pathway Ingestion", lines=8, interactive=False)
            
            # Using Timer component for periodic updates
            timer = gr.Timer(3)
            timer.tick(get_heartbeat, outputs=heartbeat_box)

        with gr.Column(scale=3, min_width=600):
            answer_box = gr.Textbox(
                label="Intelligence Report Output",
                lines=42,
                interactive=False,
                elem_id="answer_box",
                autoscroll=True
            )

    ask_btn.click(fn=handle_query, inputs=[question_box, query_type], outputs=answer_box)
    inject_btn.click(fn=handle_injection, inputs=[inject_title, inject_content, inject_category], outputs=inject_status)

if __name__ == "__main__":
    print("\nStarting Intelligence Console on Network Interface...")
    demo.launch(
        server_name="0.0.0.0", 
        server_port=7860,
        theme=gr.themes.Default(),
        css=CUSTOM_CSS,
        quiet=True
    )
