from sqlalchemy import Integer, String, Float, ForeignKey, Boolean, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import mapped_column

Base = declarative_base()

class Users(Base):

    __tablename__ = "users"

    id =  mapped_column(Integer, primary_key=True, index=True)
    email =  mapped_column(String, unique= True)
    username =  mapped_column(String, unique= True)
    first_name =  mapped_column(String)
    last_name =  mapped_column(String)
    hashed_password =  mapped_column(String)
    is_active =  mapped_column(Boolean, default=True)
    role =  mapped_column(String)
    phone_number =  mapped_column(String, nullable=True)



class Links(Base):

    __tablename__ = "links"

    id =  mapped_column(Integer, primary_key=True, index=True)
    short_code =  mapped_column(String, nullable=False , unique=True, index=True)
    alias =  mapped_column(String, nullable=False, unique=True)
    title =  mapped_column(String)
    original_url =  mapped_column(String, nullable=False)
    short_url =  mapped_column(String, unique=True, nullable=False)
    created_at =  mapped_column(TIMESTAMP)
    clicks =  mapped_column(Integer, default=0)
    user_id =  mapped_column(Integer, ForeignKey('users.id', ondelete="SET NULL"), nullable=True, index=True)
    
    