from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import ChatTokenUsage, get_db

router = APIRouter()


@router.get("/dashboard/token-usage")
async def token_usage(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    group_by: str = Query("day", regex="^(month|day|hour)$"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not to_date:
        to_date = date.today()
    if not from_date:
        from_date = to_date - timedelta(days=30)

    trunc = f"date_trunc('{group_by}', recorded_at)"

    query = text(f"""
        SELECT {trunc} AS bucket, model_id,
               SUM(tokens_in) AS prompt_tokens,
               SUM(tokens_out) AS completion_tokens,
               SUM(tokens_in + tokens_out) AS total_tokens
        FROM chat_token_usage
        WHERE recorded_at BETWEEN :from_date AND :to_date
        GROUP BY bucket, model_id
        ORDER BY bucket, model_id
    """)

    result = await db.execute(query, {"from_date": from_date, "to_date": to_date})
    rows = result.fetchall()

    buckets = []
    for row in rows:
        buckets.append({
            "timestamp": row.bucket.isoformat(),
            "model_id": row.model_id,
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "total_tokens": row.total_tokens,
        })

    return {"buckets": buckets}


@router.get("/dashboard/cost")
async def dashboard_cost(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    group_by: str = Query("day", pattern="^(month|day|hour)$"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not to_date:
        to_date = date.today()
    if not from_date:
        from_date = to_date - timedelta(days=30)

    trunc = f"date_trunc('{group_by}', completed_at)"

    # Aggregate jobs.actual_cost by completed_at + template_id.
    # media_assets table does not exist in current schema, so we
    # use only jobs data.  Frontend handles missing sources gracefully.
    query = text(f"""
        SELECT {trunc} AS bucket,
               COALESCE(CAST(template_id AS text), 'job_generation') AS model_id,
               COALESCE(SUM(actual_cost), 0) AS cost
        FROM jobs
        WHERE completed_at BETWEEN :from_date AND :to_date + INTERVAL '1 day'
          AND actual_cost IS NOT NULL
          AND user_id = :user_id
        GROUP BY bucket, template_id
        ORDER BY bucket, template_id
    """)

    result = await db.execute(query, {
        "from_date": from_date,
        "to_date": to_date,
        "user_id": str(current_user.id),
    })
    rows = result.fetchall()

    buckets = []
    for row in rows:
        buckets.append({
            "timestamp": row.bucket.isoformat(),
            "model_id": row.model_id,
            "cost": float(row.cost) if row.cost else 0.0,
        })

    return {"buckets": buckets}
