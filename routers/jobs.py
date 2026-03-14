import httpx
from fastapi import APIRouter, Depends, HTTPException
import models
import schemas
from auth import get_current_user

router = APIRouter()

UPWORK_HOMEPAGE = "https://www.upwork.com"
UPWORK_GRAPHQL_URL = "https://api.upwork.com/graphql"

client = httpx.AsyncClient(
    headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.upwork.com",
        "Referer": "https://www.upwork.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    },
    timeout=30.0,
    follow_redirects=True,
)

@router.on_event("startup")
async def warm_up():
    try:
        await client.get(UPWORK_HOMEPAGE)
        print("✅ Cloudflare cookies obtained")
    except Exception as e:
        print(f"⚠️ Could not warm up client: {e}")

JOB_QUERY = """
query {
    marketplaceJobPosting(id: "JOB_ID_PLACEHOLDER") {
        id
        ownership {
            team {
                id
                name
            }
        }
    }
}
"""

@router.post("/lookup")
async def lookup_job(
    job_query: schemas.JobQuery,
    current_user: models.User = Depends(get_current_user),
):
    token = current_user.upwork_access_token
    if not token:
        raise HTTPException(status_code=400, detail="No Upwork token available.")

    job_id = job_query.job_id.strip()
    query = JOB_QUERY.replace("JOB_ID_PLACEHOLDER", job_id)

    request_headers = {"Authorization": f"Bearer {token}"}

    try:
        response = await client.post(
            UPWORK_GRAPHQL_URL,
            headers=request_headers,
            json={"query": query},
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upwork API timed out")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Network error: {str(e)}")

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Upwork token is invalid or expired")
    if response.status_code != 200:
        print(f"❌ Upwork error: {response.status_code} – {response.text[:500]}")
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Upwork API error: {response.text[:200]}"
        )

    data = response.json()
    if "errors" in data:
        error_msg = data["errors"][0].get("message", "GraphQL error")
        raise HTTPException(status_code=400, detail=f"Upwork error: {error_msg}")

    job_data = data.get("data", {}).get("marketplaceJobPosting")
    if not job_data:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found on Upwork")

    return job_data

@router.on_event("shutdown")
async def shutdown():
    await client.aclose()