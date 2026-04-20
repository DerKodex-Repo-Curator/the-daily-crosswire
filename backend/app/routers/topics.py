import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.db import get_session
from app.models import NewspaperConfig, Topic
from app.schemas import TopicCreate, TopicRead, TopicUpdate

router = APIRouter(tags=["topics"])


@router.post(
    "/api/configs/{config_id}/topics",
    response_model=TopicRead,
    status_code=status.HTTP_201_CREATED,
)
def create_topic(
    config_id: uuid.UUID,
    payload: TopicCreate,
    session: Session = Depends(get_session),
):
    config = session.get(NewspaperConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="config not found")

    topic = Topic(config_id=config_id, **payload.model_dump())
    session.add(topic)
    session.commit()
    session.refresh(topic)
    return _load_with_feeds(session, topic.id)


@router.patch("/api/topics/{topic_id}", response_model=TopicRead)
def update_topic(
    topic_id: uuid.UUID,
    payload: TopicUpdate,
    session: Session = Depends(get_session),
):
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="topic not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(topic, key, value)

    session.commit()
    session.refresh(topic)
    return _load_with_feeds(session, topic.id)


@router.delete("/api/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic(topic_id: uuid.UUID, session: Session = Depends(get_session)):
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="topic not found")
    session.delete(topic)
    session.commit()
    return None


def _load_with_feeds(session: Session, topic_id: uuid.UUID) -> Topic | None:
    return session.exec(
        select(Topic).where(Topic.id == topic_id).options(selectinload(Topic.feeds))
    ).first()
