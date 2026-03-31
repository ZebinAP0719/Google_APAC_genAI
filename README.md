# 🗺️ LearnPath — General-Purpose Learning Agent

An AI agent built with **Google ADK** that helps users learn *anything* by
building personalised, week-by-week roadmaps backed by real YouTube content —
with **relevance scoring** on every resource.

> **Assignment checklist:**
> ADK ✅ · MCP server ✅ · YouTube Data API v3 ✅ · Relevance scoring ✅ · Cloud Run ✅

---

## 🏗️ Architecture

```
User (ADK Web UI)
      │
      ▼
 ADK Agent  (agent/agent.py)
 Gemini 2.0 Flash
      │
      │  MCP stdio transport
      ▼
 YouTube MCP Server  (mcp_server/youtube_mcp_server.py)
      │
      │  HTTPS
      ▼
 YouTube Data API v3
      │
      ▼
 Relevance Scorer  (pure Python, inside MCP server)
 ├── topic_match    (40%)
 ├── quality_signal (20%)
 ├── recency        (15%)
 ├── depth_signal   (15%)
 └── channel_trust  (10%)
```

---

## 📁 Project Structure

```
learning-agent/
├── agent/
│   ├── __init__.py
│   └── agent.py                  # ADK Agent + MCP toolset config
│
├── mcp_server/
│   ├── __init__.py
│   └── youtube_mcp_server.py     # Full MCP server (3 tools + relevance engine)
│
├── .env.example                  # Copy → .env and fill in keys
├── .gitignore
├── deploy.sh                     # One-command Cloud Run deploy
├── Dockerfile                    # Container definition
├── Makefile                      # Dev shortcuts
├── requirements.txt
└── README.md
```

---

## 🔌 MCP Tools

| Tool | Purpose |
|------|---------|
| `search_learning_resources(goal, topic, level, max_results)` | Search YouTube for a topic within the user's goal. Returns results sorted by relevance score. |
| `get_video_details(video_id)` | Fetch full metadata for a single video. |
| `score_resource_relevance(goal, topic, ...)` | Re-score any resource. Returns composite score + dimension breakdown. |

### Relevance Score Dimensions

| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| `topic_match` | 40% | Keyword overlap between goal/topic and title, description, tags |
| `quality_signal` | 20% | View count + like ratio (social proof) |
| `recency` | 15% | Freshness — penalises content older than 2–3 years |
| `depth_signal` | 15% | Duration heuristic — sweet spot 10–90 min |
| `channel_trust` | 10% | Boost for known edu channels (freeCodeCamp, MIT, 3B1B…) |

---

## ⚙️ Local Setup

### 1. Clone & install

```bash
git clone <your-repo-url>
cd learning-agent
make install      # creates venv + installs deps
make setup        # copies .env.example → .env
```

### 2. Edit `.env`

```
GOOGLE_API_KEY=...      # from https://aistudio.google.com
YOUTUBE_API_KEY=...     # from Google Cloud Console (optional — mock fallback exists)
GCP_PROJECT_ID=...      # for deployment
GCP_REGION=us-central1
```

### 3. Run with ADK default UI

```bash
make run
# → Open http://localhost:8000
```

Then type something like:
- *"I want to learn Python for data science in 4 weeks, I'm a beginner"*
- *"Help me learn guitar from scratch, 30 min/day"*
- *"I need to learn system design for a FAANG interview in 2 months"*

### 4. Test MCP server in isolation

```bash
make test-mcp
# Runs search_learning_resources directly and prints scored results as JSON
```

---

## 🔑 Getting API Keys

### Gemini (required)
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. **Create API key** → copy into `.env` as `GOOGLE_API_KEY`

### YouTube Data API v3 (optional — mock works without it)
1. [Google Cloud Console](https://console.cloud.google.com) → new or existing project
2. **APIs & Services → Enable APIs** → search "YouTube Data API v3" → Enable
3. **APIs & Services → Credentials → Create Credentials → API Key** → copy into `.env`

---

## ☁️ Deploy to Cloud Run

```bash
chmod +x deploy.sh
./deploy.sh
```

The script automatically:
1. Sets your gcloud project
2. Enables required Cloud APIs
3. Stores secrets in Secret Manager
4. Builds the container via Cloud Build
5. Deploys to Cloud Run and prints the public URL

> Requires `gcloud` CLI installed and `gcloud auth login` already done.

---

## 💬 Example Session

```
User:  I want to learn machine learning in 1 month.
       I know Python basics. 1 hour per day.

Agent: Great! Here's your 4-week ML roadmap:

       ## Phase 1 — Math & Foundations (Week 1)
       | Course | Channel | Duration | Relevance | Link |
       |--------|---------|----------|-----------|------|
       | ML Math Essentials | 3Blue1Brown | 45m | 0.87 ⭐ | ▶ Watch |

       📌 Tip: Focus on linear algebra and probability — don't memorise, understand.

       ## Phase 2 — Core Algorithms (Week 2)
       ...
```

---

## 🚀 Extending

- Add more MCP tools: arXiv papers, GitHub trending, Coursera API
- Add user memory (Firestore) to track progress across sessions
- Add a quiz tool so the agent can test comprehension after each phase
- Connect to your own ML project notebooks as supplementary resources
