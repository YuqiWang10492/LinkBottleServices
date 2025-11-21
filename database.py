import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

#db_url = "postgresql://postgres:beatrice1129@localhost:5432/postgres"
db_url = os.getenv('DATABASE_URL',"postgresql+psycopg://postgres:beatrice1129@localhost:5432/postgres")
engine = create_engine(db_url)
sessionLocal = sessionmaker(autocommit=False, autoflush=False,bind=engine)