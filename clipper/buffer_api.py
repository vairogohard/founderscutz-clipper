"""Buffer: plant de goedgekeurde clips in op YouTube Shorts en Instagram Reels.

Buffer plaatst via zijn eigen goedgekeurde koppelingen, daarom komen de posts
gewoon openbaar online (eigen API-apps mogen dat bij YouTube en TikTok niet).
Documentatie: https://developers.buffer.com
"""
import json

import requests

from .common import env

URL = "https://api.buffer.com"


def gql(query):
    r = requests.post(URL, json={"query": query}, timeout=90, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {env('BUFFER_API_KEY')}",
    })
    try:
        body = r.json()
    except ValueError:
        raise RuntimeError(f"Buffer gaf geen geldig antwoord ({r.status_code}): {r.text[:300]}")
    if body.get("errors"):
        raise RuntimeError("Buffer-fout: " + "; ".join(e.get("message", "?") for e in body["errors"]))
    return body.get("data") or {}


def s(text):
    """Tekst veilig als GraphQL-string."""
    return json.dumps(text, ensure_ascii=False)


def list_channels():
    orgs = gql("query { account { organizations { id name } } }")["account"]["organizations"]
    channels = []
    for org in orgs:
        data = gql(f"query {{ channels(input: {{ organizationId: {s(org['id'])} }}) {{ id name service }} }}")
        channels.extend(data.get("channels") or [])
    return channels


def _metadata(service, title, category):
    if service == "youtube":
        return (f"metadata: {{ youtube: {{ title: {s(title[:95])}, categoryId: {s(str(category))}, "
                f"madeForKids: false, notifySubscribers: false }} }}")
    if service == "instagram":
        return "metadata: { instagram: { type: reel, shouldShareToFeed: true } }"
    return ""


def schedule_video(channel, text, title, video_url, due_iso, category="22"):
    """Plant één video in op één kanaal. Geeft het Buffer-post-id terug."""
    meta = _metadata(channel["service"], title, category)
    query = f"""
    mutation {{
      createPost(input: {{
        text: {s(text)}
        channelId: {s(channel['id'])}
        schedulingType: automatic
        mode: customScheduled
        dueAt: {s(due_iso)}
        assets: [{{ video: {{ url: {s(video_url)} }} }}]
        {meta}
      }}) {{
        ... on PostActionSuccess {{ post {{ id dueAt }} }}
        ... on MutationError {{ message }}
      }}
    }}"""
    result = gql(query).get("createPost") or {}
    if result.get("message"):
        raise RuntimeError(f"Buffer weigerde de post voor {channel['service']}: {result['message']}")
    post = result.get("post")
    if not post:
        raise RuntimeError(f"Onverwacht antwoord van Buffer: {result}")
    return post["id"]
