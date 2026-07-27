import gradio as gr
from agent.agent import ask

def respond(message, history):
    return ask(message)["answer"]

demo = gr.ChatInterface(fn=respond)

if __name__ == "__main__":
    demo.launch()