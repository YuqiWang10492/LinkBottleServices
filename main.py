from fastapi.middleware.cors import CORSMiddleware
#------------------------------------
#python throws error if I don't inline models.py
from fastapi import FastAPI
import database_models
from database import engine
from router import auth, links, admin, users

app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins = ["http://localhost:3000", 'https://mm4jtc.csb.app/'],
    allow_methods = ["*"])

database_models.Base.metadata.create_all(bind=engine)

app.include_router(auth.router)
app.include_router(links.router)
app.include_router(admin.router)
app.include_router(users.router)

@app.get("/")
def greet():
    return 'Welcome to Linkbottle API'