import time
from concurrent.futures import ThreadPoolExecutor

import gradio as gr
from agent.core import ask

executor = ThreadPoolExecutor(max_workers=4)

THINKING_FRAMES = [
    "🔎 Thinking",
    "🔎 Thinking.",
    "🔎 Thinking..",
    "🔎 Thinking...",
]


def friendly_error_message(error: Exception) -> str:
    """Maps common failure types to a readable message instead of a raw traceback."""
    error_text = str(error).lower()

    if "api" in error_text and ("key" in error_text or "auth" in error_text or "401" in error_text):
        return (
            "⚠️ I'm having trouble authenticating with the assistant service. "
            "This is likely a configuration issue — please let the app owner know."
        )
    if "rate" in error_text and "limit" in error_text:
        return "⚠️ I'm getting a lot of requests right now. Please wait a moment and try again."
    if "timeout" in error_text or "timed out" in error_text:
        return "⚠️ That took too long to respond. Please try again — sometimes live transit data is slow to load."
    if "connection" in error_text or "network" in error_text:
        return "⚠️ I couldn't connect to the transit data service. Please check your connection and try again."

    return (
        "⚠️ Something went wrong while looking that up. "
        "Please try rephrasing your question, or try again in a moment."
    )


def _clean_history(history):
    """Strips Gradio's chat history dicts down to role/content only.

    Gradio's history dicts can carry extra keys (e.g. "metadata", "options")
    beyond role/content; the Anthropic Messages API rejects unknown fields.
    """
    return [{"role": m["role"], "content": m["content"]} for m in history]

def respond(message, history):
    future = executor.submit(ask, message, conversation_history=_clean_history(history))

    frame = 0
    while not future.done():
        yield THINKING_FRAMES[frame % len(THINKING_FRAMES)]
        frame += 1
        time.sleep(0.4)

    try:
        result = future.result()
    except Exception as e:
        yield friendly_error_message(e)
        return

    yield result["answer"]

# WMATA brand palette
WMATA_NAVY = "#003DA5"
WMATA_RED = "#BF0D3E"
WMATA_ORANGE = "#ED8B00"
WMATA_YELLOW = "#FFD100"
WMATA_GREEN = "#00A94F"
WMATA_SILVER = "#919D9D"

theme = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="slate",
    neutral_hue="slate",
).set(
    body_background_fill="#f4f6f8",
    body_background_fill_dark="#0f1720",
    button_primary_background_fill=WMATA_NAVY,
    button_primary_background_fill_hover="#002D7A",
    button_primary_text_color="white",
    block_title_text_color=WMATA_NAVY,
    block_title_text_color_dark="#5B9BFF",
    block_label_text_color=WMATA_NAVY,
    block_label_text_color_dark="#5B9BFF",
)

custom_css = f"""
#header {{
    text-align: center;
    padding: 16px 0 8px 0;
}}
#header h1 {{
    color: {WMATA_NAVY};
    font-weight: 700;
    margin-bottom: 4px;
}}
.dark #header h1 {{
    color: #5B9BFF;
}}
#header p {{
    color: #555;
}}
.dark #header p {{
    color: #aaa;
}}
#line-dots {{
    display: flex;
    justify-content: center;
    gap: 6px;
    margin-bottom: 12px;
}}
.line-dot {{
    width: 14px;
    height: 14px;
    border-radius: 50%;
    display: inline-block;
}}
.chatbot {{
    border: 1px solid {WMATA_NAVY}22 !important;
    border-radius: 12px !important;
}}
#theme-toggle {{
    max-width: 44px;
    min-width: 44px;
    align-self: flex-end;
}}
"""

# Flips the `dark` class on the app root and remembers the choice for this tab
toggle_js = """
() => {
    const url = new URL(window.location);
    const isDark = document.body.classList.contains('dark');
    if (isDark) {
        document.body.classList.remove('dark');
        url.searchParams.set('__theme', 'light');
    } else {
        document.body.classList.add('dark');
        url.searchParams.set('__theme', 'dark');
    }
    window.history.replaceState({}, '', url);
}
"""

with gr.Blocks(title="DC Metro Transit Assistant") as demo:
    with gr.Row():
        gr.HTML(f"""
            <div id="header" style="flex-grow:1;">
                <h1>🚇 DC Metro Transit Assistant</h1>
                <p>Ask about schedules, live arrivals, service alerts, and station info.</p>
            </div>
        """)
        theme_toggle = gr.Button("🌓", elem_id="theme-toggle", size="sm")

    gr.HTML(f"""
        <div id="line-dots">
            <span class="line-dot" style="background:{WMATA_RED}"></span>
            <span class="line-dot" style="background:{WMATA_ORANGE}"></span>
            <span class="line-dot" style="background:{WMATA_YELLOW}"></span>
            <span class="line-dot" style="background:{WMATA_GREEN}"></span>
            <span class="line-dot" style="background:{WMATA_NAVY}"></span>
            <span class="line-dot" style="background:{WMATA_SILVER}"></span>
        </div>
    """)

    gr.ChatInterface(
        fn=respond,
        examples=[
            "When's the next train at Metro Center?",
            "Is the Red Line running normally?",
            "Is Dupont Circle station accessible?",
        ],
        chatbot=gr.Chatbot(elem_classes=["chatbot"], height=500),
    )

    theme_toggle.click(fn=None, inputs=None, outputs=None, js=toggle_js)

if __name__ == "__main__":
    demo.launch(theme=theme, css=custom_css)