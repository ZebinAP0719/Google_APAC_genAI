"""
YouTube Learning MCP Server
============================
A proper MCP server that exposes tools for searching YouTube educational content
and scoring relevance against the user's learning goal.

Tools exposed:
  - search_learning_resources(goal, topic, max_results)
      Search YouTube for videos relevant to a learning goal + topic.
      Returns videos with a relevance_score (0.0–1.0) and reasoning.

  - get_video_details(video_id)
      Fetch full metadata + transcript summary for a single video.

  - score_resource_relevance(goal, video_title, video_description, channel, tags)
      Pure scoring tool — given any resource metadata, returns a relevance score.
      Useful when the agent wants to re-rank results mid-reasoning.
"""

import os
import re
import json
import math
import asyncio
import logging
import httpx
from datetime import datetime, timezone
from typing import Any
from mcp.server.fastmcp import FastMCP
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from dotenv import load_dotenv      

logging.basicConfig(level=logging.INFO, format="%(asctime)s [MCP] %(message)s")
log = logging.getLogger(__name__)

load_dotenv()
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
YT_SEARCH_URL   = "https://www.googleapis.com/youtube/v3/search"
YT_VIDEOS_URL   = "https://www.googleapis.com/youtube/v3/videos"
YT_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"

app = FastMCP("youtube-learning-mcp")

mcp = FastMCP(
    name="verifact-server",
    host="0.0.0.0",
    port=8081,
)

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_learning_resources",
            description=(
                "Search YouTube for free educational videos relevant to a specific "
                "learning goal and topic. Returns videos sorted by relevance score. "
                "Use this whenever the user wants to learn something new."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": (
                            "The overall learning goal of the user. "
                            "E.g. 'become a backend engineer', 'learn data science for a career switch'"
                        ),
                    },
                    "topic": {
                        "type": "string",
                        "description": (
                            "The specific topic to search for right now. "
                            "E.g. 'Python basics', 'SQL joins', 'neural networks backpropagation'"
                        ),
                    },
                    "level": {
                        "type": "string",
                        "enum": ["beginner", "intermediate", "advanced", "any"],
                        "description": "Skill level of the learner for this topic.",
                        "default": "any",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "How many results to return (1–10). Default 5.",
                        "default": 5,
                    },
                },
                "required": ["goal", "topic"],
            },
        ),
        Tool(
            name="get_video_details",
            description=(
                "Fetch full metadata for a specific YouTube video by its ID. "
                "Returns title, channel, duration, view count, like count, tags, "
                "full description, and a parsed duration in minutes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "video_id": {
                        "type": "string",
                        "description": "The YouTube video ID (11-character string), e.g. 'dQw4w9WgXcQ'",
                    }
                },
                "required": ["video_id"],
            },
        ),
        Tool(
            name="score_resource_relevance",
            description=(
                "Given a learning goal and video metadata, compute a relevance score (0.0–1.0) "
                "with a breakdown of scoring dimensions: topic match, depth, recency, quality signals. "
                "Use this to re-rank or validate resources before including them in a roadmap."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "The user's overall learning goal.",
                    },
                    "topic": {
                        "type": "string",
                        "description": "The specific topic this video should cover.",
                    },
                    "video_title": {"type": "string"},
                    "video_description": {"type": "string"},
                    "channel_name": {"type": "string"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "YouTube tags on the video.",
                    },
                    "view_count": {"type": "integer"},
                    "like_count": {"type": "integer"},
                    "duration_minutes": {"type": "number"},
                    "published_year": {"type": "integer"},
                },
                "required": ["goal", "topic", "video_title"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------

@mcp.tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "search_learning_resources":
        result = await search_learning_resources(**arguments)
    elif name == "get_video_details":
        result = await get_video_details(**arguments)
    elif name == "score_resource_relevance":
        result = score_resource_relevance(**arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
@mcp.tool()
async def search_learning_resources(
    goal: str,
    topic: str,
    level: str = "any",
    max_results: int = 5,
) -> list[dict]:
    """Search YouTube and return relevance-scored results."""
    max_results = max(1, min(max_results, 10))

    # Build a smarter query: inject level modifier if not 'any'
    level_suffix = {"beginner": "for beginners tutorial", "intermediate": "intermediate tutorial",
                    "advanced": "advanced deep dive", "any": "tutorial explained"}.get(level, "")
    query = f"{topic} {level_suffix}".strip()

    if not YOUTUBE_API_KEY:
        log.warning("No YOUTUBE_API_KEY set — returning mock data.")
        raw_videos = mock_videos(topic, max_results + 3)
    else:
        raw_videos = await youtube_search_and_enrich(query, max_results + 3)

    # Score every video
    scored = []
    for v in raw_videos:
        score_data = score_resource_relevance(
            goal=goal,
            topic=topic,
            video_title=v.get("title", ""),
            video_description=v.get("description", ""),
            channel_name=v.get("channel", ""),
            tags=v.get("tags", []),
            view_count=v.get("view_count_int", 0),
            like_count=v.get("like_count_int", 0),
            duration_minutes=v.get("duration_minutes", 0),
            published_year=v.get("published_year", 2020),
        )
        scored.append({**v, **score_data})

    # Sort descending by relevance_score, return top max_results
    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored[:max_results]

@mcp.tool()
async def get_video_details(video_id: str) -> dict:
    """Fetch full metadata for a single video."""
    if not YOUTUBE_API_KEY:
        return {"error": "No YOUTUBE_API_KEY set", "video_id": video_id}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            YT_VIDEOS_URL,
            params={
                "part": "snippet,statistics,contentDetails",
                "id": video_id,
                "key": YOUTUBE_API_KEY,
            },
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return {"error": f"Video {video_id} not found"}
        return parse_video_item(items[0])

@mcp.tool()
def score_resource_relevance(
    goal: str,
    topic: str,
    video_title: str,
    video_description: str = "",
    channel_name: str = "",
    tags: list[str] | None = None,
    view_count: int = 0,
    like_count: int = 0,
    duration_minutes: float = 0,
    published_year: int = 2020,
) -> dict:
    """
    Score a resource on 5 dimensions and return a composite score 0.0–1.0.

    Dimensions:
      1. topic_match     — keyword overlap between topic/goal and title+description+tags
      2. depth_signal    — duration heuristic (too short = shallow, too long = lecture series)
      3. recency         — newer content scores higher (knowledge decay)
      4. quality_signal  — view count + like ratio (social proof)
      5. channel_trust   — known high-quality edu channels get a boost
    """
    tags = tags or []

    # --- 1. Topic match (0–1) ---
    search_corpus = " ".join([
        video_title, video_description[:500], channel_name, " ".join(tags)
    ]).lower()

    goal_words   = set(re.findall(r"\b\w{3,}\b", goal.lower()))
    topic_words  = set(re.findall(r"\b\w{3,}\b", topic.lower()))
    all_keywords = goal_words | topic_words
    corpus_words = set(re.findall(r"\b\w{3,}\b", search_corpus))

    if all_keywords:
        topic_hit_ratio = len(all_keywords & corpus_words) / len(all_keywords)
        title_words = set(re.findall(r"\b\w{3,}\b", video_title.lower()))
        title_bonus  = len(topic_words & title_words) / max(len(topic_words), 1)
        topic_match  = min(1.0, topic_hit_ratio * 0.6 + title_bonus * 0.4)
    else:
        topic_match = 0.5

    # --- 2. Depth signal (0–1) ---
    # Sweet spot: 10–90 min. Penalise <5 min (too shallow) and >180 min (too long for one sitting)
    if duration_minutes <= 0:
        depth_signal = 0.5  # unknown
    elif duration_minutes < 5:
        depth_signal = 0.2
    elif duration_minutes < 10:
        depth_signal = 0.5
    elif duration_minutes <= 90:
        # peak at 30 min
        depth_signal = 1.0 - abs(duration_minutes - 30) / 90
        depth_signal = max(0.5, depth_signal)
    elif duration_minutes <= 180:
        depth_signal = 0.6
    else:
        depth_signal = 0.4

    # --- 3. Recency (0–1) ---
    current_year = datetime.now(timezone.utc).year
    age_years = max(0, current_year - published_year)
    # Decay: full score ≤1 yr old, half score at 4 yr, floor 0.2
    recency = max(0.2, 1.0 - age_years * 0.15)

    # --- 4. Quality signal (0–1) ---
    if view_count > 0 and like_count > 0:
        like_ratio = like_count / view_count  # typically 0.01–0.08
        like_score = min(1.0, like_ratio / 0.04)  # normalise: 4% = perfect
        view_score = min(1.0, math.log10(max(view_count, 1)) / 6)  # 1M views = 1.0
        quality_signal = like_score * 0.5 + view_score * 0.5
    elif view_count > 0:
        quality_signal = min(1.0, math.log10(max(view_count, 1)) / 6)
    else:
        quality_signal = 0.4  # unknown

    # --- 5. Channel trust (0–1) ---
    trusted_channels = {
        "freecodecamp.org": 1.0,
        "mit opencourseware": 1.0,
        "stanford": 1.0,
        "3blue1brown": 1.0,
        "andrej karpathy": 1.0,
        "sentdex": 0.9,
        "corey schafer": 0.9,
        "tech with tim": 0.85,
        "programming with mosh": 0.85,
        "traversy media": 0.85,
        "the coding train": 0.85,
        "statquest": 0.9,
        "statquest with josh starmer": 0.9,
        "two minute papers": 0.85,
        "deep learning ai": 0.95,
        "deeplearning.ai": 0.95,
        "google developers": 0.9,
        "fireship": 0.85,
        "neetcode": 0.9,
        "cs dojo": 0.85,
        "socratica": 0.9,
        "khan academy": 1.0,
        "mit": 1.0,
    }
    channel_lower = channel_name.lower()
    channel_trust = 0.6  # neutral default
    for name, score in trusted_channels.items():
        if name in channel_lower:
            channel_trust = score
            break

    # --- Composite (weighted) ---
    composite = (
        topic_match    * 0.40 +
        depth_signal   * 0.15 +
        recency        * 0.15 +
        quality_signal * 0.20 +
        channel_trust  * 0.10
    )
    composite = round(min(1.0, max(0.0, composite)), 3)

    # Human-readable tier
    if composite >= 0.80:
        tier = "⭐ Highly Relevant"
    elif composite >= 0.60:
        tier = "✅ Relevant"
    elif composite >= 0.40:
        tier = "🔶 Partially Relevant"
    else:
        tier = "❌ Low Relevance"

    return {
        "relevance_score": composite,
        "relevance_tier": tier,
        "score_breakdown": {
            "topic_match":    round(topic_match, 3),
            "depth_signal":   round(depth_signal, 3),
            "recency":        round(recency, 3),
            "quality_signal": round(quality_signal, 3),
            "channel_trust":  round(channel_trust, 3),
        },
    }


# ---------------------------------------------------------------------------
# YouTube API helpers
# ---------------------------------------------------------------------------
@mcp.tool()
async def youtube_search_and_enrich(query: str, n: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        search_resp = await client.get(
            YT_SEARCH_URL,
            params={
                "part": "snippet",
                "q": query,
                "type": "video",
                "relevanceLanguage": "en",
                "maxResults": n,
                "key": YOUTUBE_API_KEY,
            },
        )
        search_resp.raise_for_status()
        items = search_resp.json().get("items", [])
        if not items:
            return []

        video_ids = [i["id"]["videoId"] for i in items]

        stats_resp = await client.get(
            YT_VIDEOS_URL,
            params={
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(video_ids),
                "key": YOUTUBE_API_KEY,
            },
        )
        stats_resp.raise_for_status()
        video_items = stats_resp.json().get("items", [])

    return [parse_video_item(v) for v in video_items]

@mcp.tool()
def parse_video_item(item: dict) -> dict:
    snippet  = item.get("snippet", {})
    stats    = item.get("statistics", {})
    details  = item.get("contentDetails", {})

    duration_iso = details.get("duration", "PT0S")
    duration_min = iso8601_to_minutes(duration_iso)
    view_count   = int(stats.get("viewCount", "0") if stats.get("viewCount") else 0)
    like_count   = int(stats.get("likeCount", "0") if stats.get("likeCount") else 0)
    published    = snippet.get("publishedAt", "2020-01-01")[:10]
    pub_year     = int(published[:4]) if published else 2020

    return {
        "video_id":       item.get("id", ""),
        "title":          snippet.get("title", ""),
        "channel":        snippet.get("channelTitle", ""),
        "published_at":   published,
        "published_year": pub_year,
        "description":    snippet.get("description", "")[:400],
        "url":            f"https://www.youtube.com/watch?v={item.get('id', '')}",
        "thumbnail":      snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
        "tags":           snippet.get("tags", []),
        "duration_iso":   duration_iso,
        "duration_minutes": duration_min,
        "duration_str":   minutes_to_str(duration_min),
        "view_count":     f"{view_count:,}",
        "view_count_int": view_count,
        "like_count":     f"{like_count:,}",
        "like_count_int": like_count,
    }

@mcp.tool()
def iso8601_to_minutes(duration: str) -> float:
    match = re.match(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration
    )
    if not match:
        return 0.0
    h, m, s = (int(x) if x else 0 for x in match.groups())
    return round(h * 60 + m + s / 60, 1)

@mcp.tool()
def minutes_to_str(minutes: float) -> str:
    if minutes <= 0:
        return "unknown"
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m" if h else f"{m}m"


# ---------------------------------------------------------------------------
# Mock data (used when YOUTUBE_API_KEY is not set)
# ---------------------------------------------------------------------------
@mcp.tool()
def mock_videos(topic: str, n: int) -> list[dict]:
    pool = [
        {
            "video_id": "rfscVS0vtbw",
            "title": f"Learn {topic} – Full Course for Beginners",
            "channel": "freeCodeCamp.org",
            "published_at": "2023-05-12",
            "published_year": 2023,
            "description": f"Complete {topic} tutorial from scratch. Covers fundamentals, examples, and projects.",
            "url": "https://www.youtube.com/watch?v=rfscVS0vtbw",
            "thumbnail": "https://i.ytimg.com/vi/rfscVS0vtbw/hqdefault.jpg",
            "tags": [topic.lower(), "tutorial", "beginner", "full course"],
            "duration_iso": "PT4H30M",
            "duration_minutes": 270,
            "duration_str": "4h 30m",
            "view_count": "4,200,000",
            "view_count_int": 4200000,
            "like_count": "110,000",
            "like_count_int": 110000,
        },
        {
            "video_id": "HXV3zeQKqGY",
            "title": f"{topic} Tutorial – Crash Course",
            "channel": "Traversy Media",
            "published_at": "2024-01-08",
            "published_year": 2024,
            "description": f"Quick crash course on {topic}. Great if you already know the basics.",
            "url": "https://www.youtube.com/watch?v=HXV3zeQKqGY",
            "thumbnail": "https://i.ytimg.com/vi/HXV3zeQKqGY/hqdefault.jpg",
            "tags": [topic.lower(), "crash course", "tutorial"],
            "duration_iso": "PT1H15M",
            "duration_minutes": 75,
            "duration_str": "1h 15m",
            "view_count": "1,800,000",
            "view_count_int": 1800000,
            "like_count": "52,000",
            "like_count_int": 52000,
        },
        {
            "video_id": "8jLOx1hD3_o",
            "title": f"Advanced {topic} – Deep Dive",
            "channel": "Tech With Tim",
            "published_at": "2023-11-20",
            "published_year": 2023,
            "description": f"Advanced patterns and best practices in {topic}. Not for beginners.",
            "url": "https://www.youtube.com/watch?v=8jLOx1hD3_o",
            "thumbnail": "https://i.ytimg.com/vi/8jLOx1hD3_o/hqdefault.jpg",
            "tags": [topic.lower(), "advanced", "deep dive"],
            "duration_iso": "PT2H10M",
            "duration_minutes": 130,
            "duration_str": "2h 10m",
            "view_count": "890,000",
            "view_count_int": 890000,
            "like_count": "28,000",
            "like_count_int": 28000,
        },
        {
            "video_id": "rfscVS0Xaaa",
            "title": f"{topic} Explained in 10 Minutes",
            "channel": "Fireship",
            "published_at": "2024-03-01",
            "published_year": 2024,
            "description": f"Fast-paced explainer on core {topic} concepts.",
            "url": "https://www.youtube.com/watch?v=rfscVS0Xaaa",
            "thumbnail": "https://i.ytimg.com/vi/rfscVS0Xaaa/hqdefault.jpg",
            "tags": [topic.lower(), "explainer", "fast"],
            "duration_iso": "PT10M",
            "duration_minutes": 10,
            "duration_str": "10m",
            "view_count": "3,400,000",
            "view_count_int": 3400000,
            "like_count": "95,000",
            "like_count_int": 95000,
        },
        {
            "video_id": "dQw4w9WgXcQ",
            "title": f"MIT Lecture: Introduction to {topic}",
            "channel": "MIT OpenCourseWare",
            "published_at": "2022-09-10",
            "published_year": 2022,
            "description": f"Formal MIT lecture series on {topic}. Rigorous and comprehensive.",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
            "tags": [topic.lower(), "lecture", "university", "MIT"],
            "duration_iso": "PT1H20M",
            "duration_minutes": 80,
            "duration_str": "1h 20m",
            "view_count": "650,000",
            "view_count_int": 650000,
            "like_count": "18,000",
            "like_count_int": 18000,
        },
    ]
    return pool[:n]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    log.info("YouTube Learning MCP Server starting…")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    mcp.run(transport="stdio")
