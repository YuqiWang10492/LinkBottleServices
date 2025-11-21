from datetime import datetime,timezone
import string, random
from typing import Optional, Annotated
from fastapi import APIRouter, Depends, Path, Query, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from database import sessionLocal, engine
from starlette import status
import database_models
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from .auth import get_current_user
from bs4 import BeautifulSoup
import httpx

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
#API_URL_PATH = API_URL.replace(":","%3A").replace("/","%2F")

chars = string.ascii_letters + string.digits

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
    
db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dict,Depends(get_current_user)]

@router.get("/links")
def get_all_links(user: user_dependency, db: db_dependency):
    if not user:
        raise HTTPException(401, detail='Authentication Failed.')
    
    db_links = db.query(database_models.Links).filter(
        database_models.Links.user_id == user.get('id')).all()
    return db_links

@router.get("/links/")
def get_link_by_key(user: user_dependency, db: db_dependency, key:str):
    if not user:
        raise HTTPException(401, detail='Authentication Failed.')

    db_link = db.query(database_models.Links).filter(
        (database_models.Links.short_code == key) |
        (database_models.Links.short_url == key),
        database_models.Links.user_id == user.get("id"),).first()
    if db_link: return db_link
    #return key+": Link not found"
    raise HTTPException(404,key+": Link not found")

@router.get("/{key}")
def go_to_link( db: db_dependency, key:str):
    
    db_link = db.query(database_models.Links).filter(
        database_models.Links.short_code == key).first()
    if db_link: 
        db_link.clicks += 1  # type: ignore
        db.commit()
        return RedirectResponse(db_link.original_url) # type: ignore
    raise HTTPException(404,"Link not found")

@router.post("/shorten/",status_code = status.HTTP_201_CREATED)
async def shorten_link(user: user_dependency, db: db_dependency, link: Link):
    #authenticate user
    if not user:
        raise HTTPException(401, detail='Authentication Failed.')
    
    #check for existing link with same URL for user
    link_check = db.query(database_models.Links).filter(
            database_models.Links.original_url == str(link.original_url)).filter(
            database_models.Links.user_id == user.get('id')).first()
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
        original_url = str(link.original_url), user_id = user.get('id'), 
        title = link.title if link.title else title, 
        short_code = short_code, created_at=timestamp, short_url = API_URL + short_code)

    db.add(link_model)
    db.commit()

    link_model = db.query(database_models.Links).filter(
        database_models.Links.id == link_model.id).first()

    return link_model

@router.put("/links/",status_code = status.HTTP_202_ACCEPTED)
def update_link(user: user_dependency, db: db_dependency, 
                   link:Link, key:str):
    if not user:
        raise HTTPException(401, detail='Authentication Failed.')
    
    db_link = db.query(database_models.Links).filter(
        (database_models.Links.short_code == key) |
        (database_models.Links.short_url == key),
        database_models.Links.user_id == user.get("id"),).first()
    if db_link:
        link_check = db.query(database_models.Links).filter(
            (database_models.Links.alias == link.alias)|(database_models.Links.short_code == link.alias)
            |(database_models.Links.original_url == str(link.original_url)), 
            database_models.Links.id != db_link.id
            ).first()
        if link_check:
            raise HTTPException(409,detail="Another link with same alias or URL already exists.")

        db_link.title = link.title # type: ignore
        db_link.alias = link.alias # type: ignore
        db_link.original_url = str(link.original_url) # type: ignore
        db.commit()
        return "Link Updated"
    #return "Link not found"
    raise HTTPException(404,"Link not found")

@router.delete("/by_url/}",status_code=status.HTTP_200_OK)
def delete_link_by_url(user: user_dependency, url:str, db:Session = Depends(get_db)):
    if not user:
        raise HTTPException(401, detail='Authentication Failed.')

    db_link = db.query(database_models.Links).filter(
        database_models.Links.original_url == url).filter(
            database_models.Links.user_id == user.get('id')).first()
    if db_link:
        db.delete(db_link)
        db.commit()
        return "Link deleted"
    #return "Link not found"
    raise HTTPException(404,"Link not found")

@router.delete("/{key}",status_code=status.HTTP_200_OK)
def delete_link_by_key(user: user_dependency, key:str, db:Session = Depends(get_db)):
    if not user:
        raise HTTPException(401, detail='Authentication Failed.')

    db_link = db.query(database_models.Links).filter(
        (database_models.Links.short_code == key) |
        (database_models.Links.short_url == key),
        database_models.Links.user_id == user.get("id"),).first()
    if db_link:
        db.delete(db_link)
        db.commit()
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

   