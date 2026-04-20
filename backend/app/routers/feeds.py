import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db import get_session
from app.models import RSSFeed, Topic
from app.schemas import FeedCreate, FeedRead

router = APIRouter(tags=["feeds"])


@router.post(
    "/api/topics/{topic_id}/feeds",
    response_model=FeedRead,
    status_code=status.HTTP_201_CREATED,
)
def create_feed(
    topic_id: uuid.UUID,
    payload: FeedCreate,
    session: Session = Depends(get_session),
):
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="topic not found")

    feed = RSSFeed(topic_id=topic_id, url=payload.url)
    session.add(feed)
    session.commit()
    session.refresh(feed)
    return feed


@router.delete("/api/feeds/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feed(feed_id: uuid.UUID, session: Session = Depends(get_session)):
    feed = session.get(RSSFeed, feed_id)
    if feed is None:
        raise HTTPException(status_code=404, detail="feed not found")
    session.delete(feed)
    session.commit()
    return None
