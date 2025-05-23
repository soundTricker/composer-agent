# Composer Agent

The Composer Agent is a project that leverages Lyria for music generation, integrated within the Google Agent Development Kit (ADK) framework. It provides an intelligent agent capable of composing music based on user prompts and parameters, with a user-friendly chat interface for interaction.

## Features

* **AI-Powered Music Composition**: Utilizes Lyria, Google's foundation model for high-quality audio generation, to create unique musical pieces.
* **Interactive Chat Interface**: Built with Chainlit to provide a seamless user experience for requesting and receiving music compositions.
* **Agent-Based Architecture**: Implemented with Google's Agent Development Kit (ADK) for robust and scalable agent interactions.
* **Multi-Agent System**: Consists of a director agent that understands user intent and a composer agent that generates music.
* **Customizable Music Generation**: Supports detailed prompts including genre, mood, instrumentation, tempo, and more.
* **Audio Playback**: Directly plays generated music in the chat interface.

## Prerequisites

Before you begin, ensure you have met the following requirements:

* Python 3.12 or higher
* Access to Google Cloud Project with Lyria API enabled
* Google Cloud credentials configured
* `pip` or `uv` for installing Python packages
* `git` for cloning the repository

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/soundtricker/composer-agent.git
   cd composer-agent
   ```

2. **Set up virtual environments for each component:**

   For the agents component:
   ```bash
   cd apps/agents
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e .
   ```

   For the chatui component:
   ```bash
   cd ../chatui
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e .
   ```

3. **Configure environment variables:**

   For the agents component, create a `.env` file in `apps/agents/composer/` with:
   ```
   GOOGLE_GENAI_USE_VERTEXAI=1
   GOOGLE_CLOUD_PROJECT=your-project-id
   GOOGLE_CLOUD_LOCATION=your-location
   ```

   For the chatui component, create a `.env` file in `apps/chatui/` with:
   ```
   GOOGLE_CLOUD_PROJECT=your-project-id
   GOOGLE_CLOUD_LOCATION=your-location
   BACKEND_TYPE=your-backend-type
   BACKEND_URL=your-backend-url
   GOOGLE_CLOUD_AGENT_ENGINE_ID=your-agent-engine-id
   CHAINLIT_AUTH_SECRET=your-auth-secret
   ```

## Usage

### Running the Chat UI

1. Navigate to the chatui directory:
   ```bash
   cd apps/chatui
   ```

2. Activate the virtual environment:
   ```bash
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Start the Chainlit application:
   ```bash
   chainlit run main.py
   ```

4. Open your browser and navigate to the URL displayed in the terminal (typically http://localhost:8000).

### Interacting with the Composer Agent

1. Start a conversation by describing the type of music you want to create.
2. The agent will ask clarifying questions about genre, mood, instrumentation, etc.
3. Once the agent has enough information, it will generate music based on your specifications.
4. The generated music will be played directly in the chat interface.
5. You can request modifications or create new compositions as needed.

## Project Structure

```
composer-agent/
├── LICENSE
├── README.md
└── apps/
    ├── agents/                 # Agent implementation
    │   ├── composer/           # Main composer agent
    │   │   ├── agent.py        # Root agent implementation
    │   │   ├── prompts.py      # Prompts for the root agent
    │   │   └── sub_agents/     # Sub-agents
    │   │       └── composer/   # Composer sub-agent
    │   │           ├── agent.py    # Composer agent implementation
    │   │           ├── prompts.py  # Prompts for the composer agent
    │   │           └── tools.py    # Tools for music generation
    │   ├── main.py             # Entry point for agents
    │   └── pyproject.toml      # Project configuration
    └── chatui/                 # Chat user interface
        ├── chatui/             # UI implementation
        ├── main.py             # Entry point for the chat UI
        └── pyproject.toml      # Project configuration
```

## License

This project is licensed under the terms included in the [LICENSE](LICENSE) file.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
