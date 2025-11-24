from datetime import datetime,timezone
import string, random
from typing import Optional, Annotated
from fastapi import APIRouter, Depends, Path, Query, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from database import sessionLocal, engine, get_redis, Redis
from starlette import status
import database_models
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from .auth import get_current_user
from bs4 import BeautifulSoup
import httpx
import json

from pydantic import BaseModel, HttpUrl, Field, constr
class Link(BaseModel):
    alias: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_-]{3,30}$",
        description="Optional alias of 3–30 chars containing only letters, numbers, _ or -",)
    title: Optional[str] = None
    original_url: HttpUrl # validates http/https

    class Config:
        json_schema_extra = {
            'example': {
                'alias': 'your-custom-alias',
                'title': 'Title (Optional)',
                'original_url': 'http://example.com/resource'
            }
        } 
#------------------------------------
API_URL = "localhost:8000/"

CACHE_TTL_SECONDS = 1800  # 30 minutes

chars = string.ascii_letters + string.digits

def link_to_dict(link: database_models.Links) -> dict:
    return {
        "id": link.id,
        "alias": link.alias,
        "original_url": link.original_url,
        "user_id": link.user_id,
        "title": link.title,
        "short_code": link.short_code,
        "short_url": link.short_url,
        "clicks": link.clicks,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }

def getString():
     return ''.join(random.choice(chars) for _ in range(6))

router = APIRouter(
    tags = ['links']
)

def get_db():
    db = sessionLocal()
    try:
        yield db
    finally:
        db.close()
    
def links_user(user_id: int) -> str:
    return f"user:{user_id}:links"

def link_key(key: str) -> str:
    return f"link:{key}"

db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dict,Depends(get_current_user)]

@router.get("/links")
async def get_all_links(user: user_dependency, db: db_dependency, redis: Redis = Depends(get_redis)):
    if not user:
        raise HTTPException(401, detail='Authentication Failed.')
    
    user_id = user.get('id')
    assert user_id is not None
    cache_key = links_user(user_id)# 
    cached_links = await redis.get(cache_key)  
    if cached_links:
        return json.loads(cached_links)

    db_links = db.query(database_models.Links).filter(
        database_models.Links.user_id == user_id).all()
    
    data = [link_to_dict(link) for link in db_links]
    await redis.set(cache_key, json.dumps(data), ex=CACHE_TTL_SECONDS)

    return db_links

@router.get("/links/")
async def get_link_by_key(user: user_dependency, db: db_dependency, key:str, redis: Redis = Depends(get_redis)):
    if not user:
        raise HTTPException(401, detail='Authentication Failed.')
    
    key = key.replace("http://","").replace("https://","").replace(API_URL,"")
    user_id = user.get('id')
    cache_key = link_key(key) 
    cached_link = await redis.get(cache_key)
    if cached_link:
        # Security: make sure the link belongs to this user
        if cached_link["user_id"] != user_id:
            # pretend it's not found to avoid leaking existence
            raise HTTPException(404, key + ": Link not found")
        return json.loads(cached_link)

    db_link = db.query(database_models.Links).filter(
        (database_models.Links.short_code == key),
        database_models.Links.user_id == user_id).first()
    if db_link: 
        data = link_to_dict(db_link)
        await redis.set(cache_key, json.dumps(data), ex=CACHE_TTL_SECONDS)
        return db_link
    #return key+": Link not found"
    raise HTTPException(404,key+": Link not found")

@router.get("/{key}")
async def go_to_link( db: db_dependency, key:str, redis: Redis = Depends(get_redis)):
    
    db_link = db.query(database_models.Links).filter(
        database_models.Links.short_code == key).first()
    if db_link: 
        db_link.clicks += 1  #  
        db.commit()

        cache_key = link_key(db_link.short_code)#  
        data = link_to_dict(db_link)
        # Update cache
        await redis.set(cache_key, json.dumps(data), ex=CACHE_TTL_SECONDS)
        #delete cache for user links list
        if db_link.user_id: #  
            await redis.delete(links_user(db_link.user_id))  #  

        return RedirectResponse(db_link.original_url) #  
    raise HTTPException(404,"Link not found")

@router.post("/shorten/",status_code = status.HTTP_201_CREATED)
async def shorten_link(user: user_dependency, db: db_dependency, link: Link, redis: Redis = Depends(get_redis)):
    #authenticate user
    if not user:
        raise HTTPException(401, detail='Authentication Failed.')
    
    user_id = user.get('id')
    assert user_id is not None

    #check for existing link with same URL for user
    link_check = db.query(database_models.Links).filter(
            database_models.Links.original_url == str(link.original_url)).filter(
            database_models.Links.user_id == user_id).first()
    if link_check:
        raise HTTPException(409,detail="Link with same URL already exists: "+ link_check.short_url) 
    link_check = db.query(database_models.Links).filter(
            database_models.Links.alias == link.alias).first()
    if link_check:
        raise HTTPException(409,detail="Link with same alias already exists.")
    
    title = await fetch_title(str(link.original_url))
    
    short_code = getString()
    while db.query(database_models.Links).filter(
        database_models.Links.short_code == short_code).first():
        short_code = getString()

    timestamp = datetime.now(timezone.utc)
    link_model = database_models.Links( alias = link.alias if link.alias else short_code,
        original_url = str(link.original_url), user_id = user_id, 
        title = link.title if link.title else title, 
        short_code = short_code, created_at=timestamp, short_url = API_URL + short_code)

    db.add(link_model)
    db.commit()

    data = link_to_dict(link_model)

    # Invalidate user's list
    await redis.delete(links_user(user_id))
    # Populate single-link cache
    await redis.set(link_key(link_model.short_code), json.dumps(data), ex=CACHE_TTL_SECONDS) #  

    return link_to_dict(link_model)

@router.put("/links/",status_code = status.HTTP_202_ACCEPTED)
async def update_link(user: user_dependency, db: db_dependency, 
                   link:Link, key:str, redis: Redis = Depends(get_redis)):
    if not user:
        raise HTTPException(401, detail='Authentication Failed.')
    
    key = key.replace("http://","").replace("https://","").replace(API_URL,"")
    user_id = user.get('id')
    assert user_id is not None
    db_link = db.query(database_models.Links).filter(
        (database_models.Links.short_code == key),
        database_models.Links.user_id == user_id).first()
    if db_link:
        link_check = db.query(database_models.Links).filter(
            (database_models.Links.alias == link.alias)|(database_models.Links.short_code == link.alias)
            |((database_models.Links.original_url == str(link.original_url)) & (database_models.Links.user_id == user_id)), 
            database_models.Links.id != db_link.id
            ).first()
        if link_check:
            raise HTTPException(409,detail="Another link with same alias or URL already exists.")

        db_link.title = link.title if link.title else db_link.title
        db_link.alias = link.alias if link.alias else db_link.alias
        db_link.original_url = str(link.original_url)
        db.commit()
        db.refresh(db_link)
  
        cache_key = link_key(db_link.short_code) 
        data = link_to_dict(db_link)
        # Invalidate caches
        await redis.delete(links_user(user_id))
        # Populate single-link cache
        await redis.set(cache_key, json.dumps(data), ex=CACHE_TTL_SECONDS)

        return "Link Updated"
    #return "Link not found"
    raise HTTPException(404,"Link not found")

@router.delete("/by_url/",status_code=status.HTTP_200_OK)
async def delete_link_by_url(user: user_dependency, url:str, db:Session = Depends(get_db), redis: Redis = Depends(get_redis)):
    if not user:
        raise HTTPException(401, detail='Authentication Failed.')

    user_id = user.get('id')
    assert user_id is not None
    db_link = db.query(database_models.Links).filter(
        database_models.Links.original_url == url).filter(
            database_models.Links.user_id == user_id).first()
    if db_link:
        db.delete(db_link)
        db.commit()

        # Invalidate caches
        await redis.delete(links_user(user_id)) #  
        await redis.delete(link_key(db_link.short_code)) #  
        return "Link deleted"
    #return "Link not found"
    raise HTTPException(404,"Link not found")

@router.delete("/by_key/",status_code=status.HTTP_200_OK)
async def delete_link_by_key(user: user_dependency, key:str, db:Session = Depends(get_db), redis: Redis = Depends(get_redis)):
    if not user:
        raise HTTPException(401, detail='Authentication Failed.')

    key = key.replace("http://","").replace("https://","").replace(API_URL,"")
    user_id = user.get('id')
    assert user_id is not None
    db_link = db.query(database_models.Links).filter(
        (database_models.Links.short_code == key),
        database_models.Links.user_id == user_id).first()
    if db_link:
        db.delete(db_link)
        db.commit()

        # Invalidate caches
        await redis.delete(links_user(user_id))
        await redis.delete(link_key(db_link.short_code))
        return "Link deleted"
    #return "Link not found"
    raise HTTPException(404,"Link not found")

async def fetch_title(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=400, detail=f"Error fetching URL: {exc}") from exc

    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code,
                            detail=f"Failed to fetch URL (status {resp.status_code})")

    # Parse HTML
    soup = BeautifulSoup(resp.text, "html.parser")
    title_tag = soup.find("title")

    if not title_tag or not title_tag.string:
        return "No Title"

    return title_tag.string.strip()

