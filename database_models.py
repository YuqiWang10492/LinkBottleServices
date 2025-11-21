from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Users(Base):

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique= True)
    username = Column(String, unique= True)
    first_name = Column(String)
    last_name = Column(String)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    role = Column(String)
    phone_number = Column(String, nullable=True)



class Links(Base):

    __tablename__ = "links"

    id = Column(Integer, primary_key=True, index=True)
    short_code = Column(String, nullable=False , unique=True, index=True)
    alias = Column(String, nullable=False, unique=True)
    title = Column(String)
    original_url = Column(String, nullable=False)
    short_url = Column(String, unique=True, nullable=False)
    created_at = Column(TIMESTAMP)
    clicks = Column(Integer, default=0)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="SET"), nullable=True, index=True)
    
    