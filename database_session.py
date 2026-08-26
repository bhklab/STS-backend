import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote_plus

password_cleaned = quote_plus(os.getenv("DATABASE_PASS", ""))
db_port = os.getenv("DB_PORT") or os.getenv("DATABASE_PORT") or "3306"
engine = create_engine(
    f"mysql+pymysql://{os.getenv('DATABASE_USER')}:{password_cleaned}"
    f"@{os.getenv('DATABASE_IP')}:{db_port}/{os.getenv('SELECTED_DB')}",
    echo=True,
)
database_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def get_db_session():
	session = database_session()
	try:
		yield session
	finally:
		session.close()